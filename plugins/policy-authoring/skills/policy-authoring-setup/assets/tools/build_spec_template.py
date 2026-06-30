#!/usr/bin/env python3
"""정책 spec 빌드 파이프라인 (config 구동, 이식 가능, 멀티 unit).

파이프라인 순서 (이 순서가 핵심):
  1) baseline spec 로드
  2) 내용 override 적용 (PI 본문 + 세부기능 N:M 매핑)
  3) rebuild_rollups        ← override 직후, 멱등. STRUCTURAL 정합의 핵심.
  4) apply_term_replacements ← 맨 마지막. 레거시→최종 용어(근거 필드 제외).
  5) 저장 + 카운트 출력

unit별 PI override는 tools/overrides/<unit>.py 에 둔다(--unit 으로 로드).
config 는 units{<unit>:{baseline_spec_path,spec_path,...}} 구조 + 공통 top-level 키.

사용:
  python3 build_spec.py --config=policy_config.json --unit=<hub|faq|store>
  # config.units[unit].baseline_spec_path 를 읽어 config.units[unit].spec_path 로 저장.
"""
from __future__ import annotations
import importlib
import json
import os
import sys

DEFAULT_CONFIG = "policy_config.json"

# ══════════════════════════════════════════════════════════════════════
#  모듈 레벨 기본값(--unit 미지정 시). 실제 PI override는 tools/overrides/<unit>.py.
#  키 형식 = "PI-<BIZ>-<DOMAIN>-NN-NN". applies_to = ["FN-<BIZ>-<DOMAIN>-NNN#idx"] (idx 1-based)
# ══════════════════════════════════════════════════════════════════════
PI_CONTENT_OVERRIDES: dict = {}
UI_SUBFNS: set = set()        # 순수 UI/표현 세부기능 ref ("FN-id#idx"). 1:1 정책 강제 금지.
FN_DESC_OVERRIDES: dict = {}  # FN '설명'을 세부기능 단위 줄로 교체(선택).


# ══════════════════════════════════════════════════════════════════════
#  이하 골격 — 보통 수정 불필요 (config로 동작)
# ══════════════════════════════════════════════════════════════════════
def load_config(path):
    if path and os.path.isfile(path):
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    return {}


def overlay_unit(cfg, unit):
    """config.units[unit] 블록을 top-level 키로 끌어올린다(있으면). 공통 키는 보존."""
    units = cfg.get("units") or {}
    if not unit:
        return cfg
    if unit not in units:
        raise SystemExit(f"--unit={unit} 가 units 에 없습니다. 가능: {sorted(units)}")
    merged = dict(cfg)
    merged.update(units[unit])
    return merged


def load_unit_overrides(unit):
    """unit별 override 모듈 로드 → (PI_CONTENT_OVERRIDES, UI_SUBFNS, FN_DESC_OVERRIDES).
    --unit 미지정이면 모듈 레벨 기본값."""
    if not unit:
        return PI_CONTENT_OVERRIDES, UI_SUBFNS, FN_DESC_OVERRIDES
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    mod = importlib.import_module(f"overrides.{unit}")
    return (getattr(mod, "PI_CONTENT_OVERRIDES", {}),
            getattr(mod, "UI_SUBFNS", set()),
            getattr(mod, "FN_DESC_OVERRIDES", {}))


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


def apply_overrides(spec, pi_overrides, ui_subfns):
    """PI 본문 필드 세팅 + applies_to 로 FD.subfn_pis/subfn_ui 재구성 + PI.applies_to_functions.

    세부기능↔PI 매핑의 진실원천 = override의 applies_to. 따라서 subfn_pis를 전부 재구성한다(멱등).
    override에 없는 PI는 FN 미연결(배경 PI)로 남는다 = 의도(STRUCTURAL 아님).
    """
    pi_by = {pi["id"]: pi for pi in spec.get("policy_details", [])}
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
    for pid, ov in pi_overrides.items():
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
        if "internal_integration" in ov:
            pi["internal_integration"] = ov["internal_integration"]
        if "rule_type" in ov:
            pi["rule_type"] = ov["rule_type"]
        if "decision_spec" in ov:
            pi["decision_spec"] = dict(ov["decision_spec"])
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
        raise SystemExit(f"PI override unknown PI id: {unknown}")
    print(f"  [overrides] PI {len(pi_overrides)} 적용, UI 세부기능 {len(ui_subfns)}")
    return spec


def link_unlinked_pis_to_existing_pg(spec):
    """group_id/policy_id 가 비어 렌더 6.나에서 누락되는 PI를, 자기 ID로부터 '정준 PG'를 유도해
    그 PG가 policy_groups 에 실제로 존재할 때만 group_id 로 연결한다(보수적·결정적).

    유도 규칙(데이터셋 공통 ID 문법): PI-<BIZ>-<DOM>-<NNN>-<II> → PG-<BIZ>-<DOM>-<NNN>
    (마지막 항목 일련번호만 제거; 'PG-'+segments[1:-1]). 결과 PG가 목록에 없으면 건드리지 않는다.

    절대 금지(자의적 ID 정규화 금지와 동일 원칙):
      - PI/PG ID 자체를 바꾸지 않는다(유도값을 PI에 다시 쓰지 않음).
      - 이미 group_id/policy_id 가 있는 PI(=명시 링크, 누락 PG 가리키는 dangling 포함)는 손대지 않는다 → 그건 담당자 결정(매니페스트).
      - 존재하지 않는 PG를 만들지 않는다.
    효과: 소스가 단지 링크 필드를 비워둔 PI만 복구. clean 모듈은 unlinked PI=0 → no-op.
    """
    pg_ids = {g["id"] for g in spec.get("policy_groups", [])}
    linked = 0
    for pi in spec.get("policy_details", []):
        if pi.get("group_id") or pi.get("policy_id"):
            continue
        parts = str(pi.get("id", "")).split("-")
        if len(parts) < 4 or parts[0] != "PI":
            continue
        cand = "PG-" + "-".join(parts[1:-1])
        if cand in pg_ids:
            pi["group_id"] = cand
            linked += 1
    if linked:
        print(f"  [link_pi_pg] 비링크 PI {linked}건을 자기 ID 유도 정준 PG(존재 확인)로 연결")
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


def bake_pi_ids_into_names(spec):
    """정책 상세 name 끝에 ' (<id>)' 부착 — NC스튜디오가 name을 그대로 렌더하므로 ID가 함께 노출된다.
    빌링 spec 관례와 동일하게 policy_details + policy_groups[].items + policies[].items 의 name을 모두 갱신.
    멱등: 이미 '(<id>)'로 끝나면 skip. (render_preview.py는 name의 내장 ID를 떼고 재부착 → 이중 표기 없음.)
    """
    def bake(obj_list):
        n = 0
        for o in obj_list or []:
            pid = o.get("id")
            name = o.get("name", "")
            if not pid or not isinstance(name, str):
                continue
            if name.rstrip().endswith(f"({pid})"):
                continue
            o["name"] = f"{name} ({pid})"
            n += 1
        return n

    n = bake(spec.get("policy_details", []))
    for pg in spec.get("policy_groups", []):
        n += bake(pg.get("items"))
    for pol in (spec.get("policies") or []):
        n += bake(pol.get("items"))
    print(f"  [bake_ids] 정책 상세 name {n}건에 ID 부착")
    return spec


def normalize_pg_names(spec):
    """정책 그룹 name 끝의 '정책' 접미를 제거 — 렌더러·NC스튜디오가 'X 정책'으로 재부착하므로
    '정책 정책' 중복을 막는다. 빌링 관례(PG name에 '정책' 미포함)와 정합. policy_groups + policies 동시. 멱등."""
    n = 0

    def strip_one(o):
        nonlocal n
        nm = (o.get("name") or "").rstrip()
        if nm.endswith("정책"):
            new = nm[:-2].rstrip()
            if new and new != o.get("name"):
                o["name"] = new
                n += 1

    for pg in spec.get("policy_groups", []):
        strip_one(pg)
    for pol in (spec.get("policies") or []):
        strip_one(pol)
    print(f"  [normalize_pg] 정책 그룹 name '정책' 접미 {n}건 제거")
    return spec


def main(argv):
    config_path = DEFAULT_CONFIG
    unit = None
    for a in argv[1:]:
        if a.startswith("--config="):
            config_path = a.split("=", 1)[1].strip()
        elif a.startswith("--unit="):
            unit = a.split("=", 1)[1].strip()
    cfg = overlay_unit(load_config(config_path), unit)
    baseline = cfg.get("baseline_spec_path")
    out = cfg.get("spec_path")
    if not baseline or not out:
        print("ERROR: baseline_spec_path/spec_path 없음 (units 사용 시 --unit=<key> 지정).", file=sys.stderr)
        return 2

    pi_ov, ui_ov, _fn_desc = load_unit_overrides(unit)
    spec = json.load(open(baseline, encoding="utf-8"))
    apply_overrides(spec, pi_ov, ui_ov)
    link_unlinked_pis_to_existing_pg(spec)
    rebuild_rollups(spec, cfg)
    apply_term_replacements(spec, cfg)
    normalize_pg_names(spec)
    bake_pi_ids_into_names(spec)
    # NC 풀스키마 보강 — bake 이후 필수(enrich_policies_items가 baked name을 읽음)
    from enrich_spec import enrich, emit_requirement_links
    enrich(spec, cfg.get("business_code", "CS"))
    # 요구사항↔노드 연결 임베드(NC G2) — enrich 직후·write 직전, cfg 전달(설정 없으면 no-op)
    emit_requirement_links(spec, cfg)

    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
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
