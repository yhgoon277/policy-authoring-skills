#!/usr/bin/env python3
"""정책 spec 빌드 파이프라인 템플릿 (config 구동, 이식 가능).

파이프라인 순서 (이 순서가 핵심):
  1) baseline spec 로드
  2) 내용 override 적용 (PI 본문 + 세부기능 N:M 매핑)
  3) rebuild_rollups        ← override 직후, 멱등. STRUCTURAL 정합의 핵심.
  4) apply_term_replacements ← 맨 마지막. 레거시→최종 용어(근거 필드 제외).
  5) 저장 + 카운트 출력

골격(3·4·main)은 그대로 두고, 아래 PI_CONTENT_OVERRIDES / UI_SUBFNS / FN_DESC_OVERRIDES 또는
config의 pi_content_overrides / ui_subfns / fn_desc_overrides 만 자기 모듈 값으로 채운다.
(작성 규칙 = policy-detail-authoring 스킬 / FN 설명 = policy-hierarchy-decomposition 스킬)

사용:
  python3 build_spec_template.py [--config=policy_config.json]
  # config.baseline_spec_path 를 읽어 config.spec_path 로 저장.
"""
from __future__ import annotations
import json
import os
import sys

DEFAULT_CONFIG = "policy_config.json"

# ══════════════════════════════════════════════════════════════════════
#  여기를 채운다 — PI 내용 override (정책 상세 작성)
#  키 형식 = "PI-<BIZ>-<DOMAIN>-NN-NN". applies_to = ["FN-<BIZ>-<DOMAIN>-NNN#idx"] (idx 1-based)
# ══════════════════════════════════════════════════════════════════════
PI_CONTENT_OVERRIDES: dict = {
    # 예시 1건(삭제·교체용):
    # "PI-BIZ-CHRG-01-02": {
    #     "rule": "청구요금은 이번 달을 포함해 최근 6개월까지 조회할 수 있다.",
    #     "criteria": ["조회 가능 기간: 최근 6개월", "갱신 시점: 매월 1일"],
    #     "notice": "",
    #     "source_note": "as-is 요금 정책서 섹션 1.1(조회 기간)",
    #     "applies_to": ["FN-BIZ-CHRG-001#1", "FN-BIZ-CHRG-002#2"],
    #     "tables": [{
    #         "caption": "회선 종류별 조회 시점",
    #         "headers": ["회선 종류", "조회 가능 시점"],
    #         "rows": [["이동전화", "5일경"], ["유선", "6일경"]],
    #         "note": "정기청구 작업: 매월 1~3일",
    #     }],
    #     "field_review": "축 다: to-be 갱신 주기 미정. 가정=매월 1일. 질문=실제 갱신 시점?",
    # },
}

# 정책 불필요한 순수 UI/표현·내부처리 세부기능 ref ("FN-id#idx"). 1:1 정책 강제 금지.
UI_SUBFNS: set = set()

# FN '설명'을 세부기능 단위 줄로 교체(선택). {FN-id: [줄1, 줄2, ...]} (줄 수 = sub_functions 수)
FN_DESC_OVERRIDES: dict = {}


# ══════════════════════════════════════════════════════════════════════
#  이하 골격 — 보통 수정 불필요 (config로 동작)
# ══════════════════════════════════════════════════════════════════════
def load_config(path):
    if path and os.path.isfile(path):
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    return {}


def parse_ref(ref):
    """'FN-BIZ-CHRG-002#4' -> ('FN-BIZ-CHRG-002', 4)"""
    if "#" not in ref:
        return ref, None
    fn, i = ref.rsplit("#", 1)
    try:
        return fn, int(i)
    except ValueError:
        return fn, None


def _derive_pgs(pi_ids, pi_to_pg):
    pgs = set()
    for pid in pi_ids:
        pg = pi_to_pg.get(pid)
        if pg:
            pgs.add(pg)
    return sorted(pgs)


def _merge_pgs(existing, derived, fallback):
    """existing + derived + fallback 순서 보존 union (cross-cutting 표기 제외)."""
    seen, out = set(), []
    for src in (existing or [], derived or [], fallback or []):
        for p in src:
            if p and "(CROSS" not in p and p not in seen:
                seen.add(p)
                out.append(p)
    return out


def _merged_dict(static_value, cfg, key):
    merged = dict(static_value)
    extra = cfg.get(key) or {}
    if not isinstance(extra, dict):
        raise SystemExit(f"config.{key} must be an object")
    merged.update(extra)
    return merged


def apply_overrides(spec, cfg=None):
    """PI 본문 필드 세팅 + applies_to 로 FD.subfn_pis/subfn_ui 재구성 + PI.applies_to_functions.

    세부기능↔PI 매핑의 진실원천 = 이 override의 applies_to. 따라서 subfn_pis를 전부 재구성한다(멱등).
    """
    cfg = cfg or {}
    pi_content_overrides = _merged_dict(PI_CONTENT_OVERRIDES, cfg, "pi_content_overrides")
    ui_subfns = set(UI_SUBFNS) | set(cfg.get("ui_subfns") or [])
    fn_desc_overrides = _merged_dict(FN_DESC_OVERRIDES, cfg, "fn_desc_overrides")

    pi_by = {pi["id"]: pi for pi in spec.get("policy_details", [])}
    fn_by = {fn["id"]: fn for fn in spec.get("functions", [])}
    fd_by = {fd.get("function_id"): fd for fd in spec.get("function_details", [])}

    # 1) 모든 FD의 subfn_pis/subfn_ui 를 sub_functions 길이에 맞춰 초기화
    for fd in spec.get("function_details", []):
        n = len(fd.get("sub_functions") or [])
        fd["subfn_pis"] = [[] for _ in range(n)]
        fd["subfn_ui"] = [False] * n

    # 2) UI 세부기능 표기
    for ref in ui_subfns:
        fid, i = parse_ref(ref)
        fd = fd_by.get(fid)
        if fd and i and 1 <= i <= len(fd["subfn_ui"]):
            fd["subfn_ui"][i - 1] = True

    # 3) PI override 적용
    unknown = []
    for pid, ov in pi_content_overrides.items():
        pi = pi_by.get(pid)
        if not pi:
            unknown.append(pid)
            continue
        if "rule" in ov:
            pi["rule_statement"] = ov["rule"]
            pi["content"] = ov["rule"]
        if "criteria" in ov:
            pi["criteria_values"] = list(ov["criteria"])
        if "notice" in ov:
            pi["customer_notice"] = ov["notice"]
        if "source_note" in ov:
            pi["source_note"] = ov["source_note"]
        if "tables" in ov:
            pi["detail_tables"] = ov["tables"]
        if "field_review" in ov:
            pi["field_review"] = ov["field_review"]
        refs = list(ov.get("applies_to") or [])
        pi["applies_to"] = refs
        fns = []
        for ref in refs:
            fid, i = parse_ref(ref)
            if fid not in fns:
                fns.append(fid)
            fd = fd_by.get(fid)
            if fd and i and 1 <= i <= len(fd["subfn_pis"]):
                if pid not in fd["subfn_pis"][i - 1]:
                    fd["subfn_pis"][i - 1].append(pid)
        pi["applies_to_functions"] = sorted(fns)
    if unknown:
        raise SystemExit(f"PI_CONTENT_OVERRIDES unknown PI id: {unknown}")

    # 4) FN description override 적용(선택)
    unknown_fn = []
    for fid, lines in fn_desc_overrides.items():
        fn = fn_by.get(fid)
        if not fn:
            unknown_fn.append(fid)
            continue
        if not isinstance(lines, list):
            raise SystemExit(f"FN_DESC_OVERRIDES[{fid}] must be a list")
        fd = fd_by.get(fid, {})
        sub_count = len(fd.get("sub_functions") or [])
        if sub_count and len(lines) != sub_count:
            raise SystemExit(f"FN_DESC_OVERRIDES[{fid}] length {len(lines)} != sub_functions {sub_count}")
        fn["description"] = " ".join(f"({i + 1}) {line}" for i, line in enumerate(lines))
    if unknown_fn:
        raise SystemExit(f"FN_DESC_OVERRIDES unknown FN id: {unknown_fn}")

    print(f"  [overrides] PI {len(pi_content_overrides)} 적용, UI 세부기능 {len(ui_subfns)}, FN 설명 {len(fn_desc_overrides)}")
    return spec


def rebuild_rollups(spec, cfg, strip_pr_only=False):
    """진실원천(subfn_pis·group_id·applies_to)에서 롤업·파생·양방향·trace_matrix 재계산 (멱등).

    config: pr_pi_remove(오류 매핑 제외), manual_pg_fallback(PI 0건 PR의 PG 보강).
    """
    pr_pi_remove = {tuple(x) for x in (cfg.get("pr_pi_remove") or [])}
    manual_pg_fallback = cfg.get("manual_pg_fallback") or {}

    pis = spec.get("policy_details", [])
    prs = spec.get("processes", [])
    prds = spec.get("process_details", [])
    fns = spec.get("functions", [])
    fds = spec.get("function_details", [])
    ucs = spec.get("usecases", [])

    pi_ids = {p["id"] for p in pis}
    pi_to_pg = {p["id"]: (p.get("group_id") or p.get("policy_id")) for p in pis}
    fd_by = {fd.get("function_id"): fd for fd in fds}
    prd_by = {d.get("process_id"): d for d in prds}

    # (a) FN.related_policy_details = union(FD.subfn_pis) + (c) FN.related_policies = derive_PG
    fn_pi = {}
    for f in fns:
        fd = fd_by.get(f["id"], {})
        union = []
        for lst in (fd.get("subfn_pis") or []):
            for p in (lst or []):
                if p in pi_ids and p not in union:
                    union.append(p)
        f["related_policy_details"] = list(union)
        fn_pi[f["id"]] = set(union)
        if fd:
            fd["related_policy_details"] = list(union)
        f["related_policies"] = _derive_pgs(union, pi_to_pg)
        if fd:
            fd["related_policies"] = list(f["related_policies"])

    # (b)(d) PR 롤업
    for pr in prs:
        pid = pr["id"]
        union = []
        for fid in (pr.get("related_functions") or []):
            for p in sorted(fn_pi.get(fid, set())):
                if p not in union:
                    union.append(p)
        existing = pr.get("related_policy_details") or []
        if strip_pr_only:
            new_rpd = list(union)
        else:
            new_rpd = list(union)
            for p in existing:
                if p in pi_ids and p not in new_rpd and (pid, p) not in pr_pi_remove:
                    new_rpd.append(p)
        pr["related_policy_details"] = new_rpd
        derived = _derive_pgs(new_rpd, pi_to_pg)
        pr["related_policies"] = _merge_pgs(pr.get("related_policies"), derived,
                                            manual_pg_fallback.get(pid, []))
        prd = prd_by.get(pid)
        if prd:
            prd["related_policy_details"] = list(new_rpd)
            prd["related_policies"] = list(pr["related_policies"])

    # (f) PI.applies_to_functions ↔ FN.related_policy_details 양방향 정합
    pi_to_fns = {}
    for f in fns:
        for p in fn_pi.get(f["id"], set()):
            pi_to_fns.setdefault(p, set()).add(f["id"])
    for pi in pis:
        cur = set(pi.get("applies_to_functions") or [])
        pi["applies_to_functions"] = sorted(cur | pi_to_fns.get(pi["id"], set()))

    # UC.related_processes 역참조
    uc_to_prs = {}
    for pr in prs:
        for uc in (pr.get("usecase_ids") or []):
            uc_to_prs.setdefault(uc, []).append(pr["id"])
    for u in ucs:
        u["related_processes"] = sorted(uc_to_prs.get(u["id"], []))

    # (g) trace_matrix 재생성
    f2p = {f["id"]: list(f.get("related_policy_details") or []) for f in fns if f.get("related_policy_details")}
    p2fn = {pi["id"]: sorted(pi.get("applies_to_functions") or []) for pi in pis if pi.get("applies_to_functions")}
    background = sorted(pi["id"] for pi in pis if not pi.get("applies_to_functions"))
    spec["trace_matrix"] = {
        "uc_to_process": {u["id"]: sorted(uc_to_prs.get(u["id"], [])) for u in ucs if uc_to_prs.get(u["id"])},
        "process_to_function": {pr["id"]: list(pr.get("related_functions") or []) for pr in prs if pr.get("related_functions")},
        "function_to_policy_detail": f2p,
        "policy_detail_to_function": p2fn,
        "background_pds": background,
        "coverage": {
            "uc_count": len(ucs), "process_count": len(prs), "function_count": len(fns),
            "policy_detail_count": len(pis), "policy_group_count": len(spec.get("policy_groups", [])),
            "covered_pd_count": len(p2fn), "background_pd_count": len(background),
        },
    }
    print(f"  [rebuild_rollups] PR {len(prs)}·FN {len(fns)}·PI {len(pis)} 재계산, 배경 PI {len(background)}")
    return spec


def apply_term_replacements(spec, cfg):
    """본문 전역 용어 치환(근거 필드 제외). config.term_replacements / term_skip_keys."""
    terms = cfg.get("term_replacements") or {}
    skip = set(cfg.get("term_skip_keys") or
               ["source_note", "source_refs", "source_basis", "global_standard_ref", "v1.0_match", "field_review"])
    if not terms:
        return spec
    cnt = [0]

    def repl(s):
        out = s
        for old, new in terms.items():
            out = out.replace(old, new)
        return out

    def walk(o):
        if isinstance(o, str):
            r = repl(o)
            if r != o:
                cnt[0] += 1
            return r
        if isinstance(o, list):
            return [walk(x) for x in o]
        if isinstance(o, dict):
            return {k: (x if k in skip else walk(x)) for k, x in o.items()}
        return o

    for key in list(spec.keys()):
        spec[key] = walk(spec[key])
    print(f"  [term] {cnt[0]} 문자열 치환 ({terms}; 근거 필드 제외)")
    return spec


def main(argv):
    config_path = DEFAULT_CONFIG
    for a in argv[1:]:
        if a.startswith("--config="):
            config_path = a.split("=", 1)[1].strip()
    cfg = load_config(config_path)
    baseline = cfg.get("baseline_spec_path")
    out = cfg.get("spec_path")
    if not baseline or not out:
        print("ERROR: policy_config.json 에 baseline_spec_path 와 spec_path 를 설정하세요.", file=sys.stderr)
        return 2

    spec = json.load(open(baseline, encoding="utf-8"))
    apply_overrides(spec, cfg)
    rebuild_rollups(spec, cfg)
    apply_term_replacements(spec, cfg)

    with open(out, "w", encoding="utf-8") as fh:
        json.dump(spec, fh, ensure_ascii=False, indent=2)

    counts = {k: len(spec.get(k, [])) for k in
              ("usecases", "processes", "functions", "policy_groups", "policy_details")}
    print(f"  [write] {out}")
    print(f"  [counts] {counts}")
    print("  다음: audit_id_integrity.py 로 STRUCTURAL 0 확인 → render_preview.py 로 미리보기.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
