#!/usr/bin/env python3
"""NC 입력 적합성 — 결정론 수정기 (보수적: HTML 근거 있는 것만).

디자인팀 게이트(validate_nc_input)를 막는 결함 중, *기계로 100% 안전하게* 고칠 수
있는 것만 수정한다. HTML(기획자 의도의 진실원천)에 근거가 없는 그룹↔상세는 절대
추정 연결하지 않는다(→ 트랙 B Codex 키트).

패스(순서 고정):
  1) rebuild_policy_details_from_html  HTML PG→PI로 policy_details 재구성 + items/policy_id 양방향
                                       (원본 id 기준 매칭 → 이후 모듈코드 정규화가 함께 보정)
  2) fix_module_code                   정의 ID·전 참조의 모듈 세그먼트를 meta.business_code로 정규화
  3) fix_usecase_join                  process.usecase_id 공란을 process.name==usecase.name(유일)로 충전
  4) split_concatenated_refs           related_policies/functions의 붙은 ID 문자열 분리

원본 미변경. <name>_fixed.json 산출. 멱등. 변경 요약 로깅. 말미 validate 재실행.

사용:
  python3 tools/fix_nc_input.py SPEC.json [--html HTML] [--out OUT.json]
"""
import argparse
import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import nc_html_link  # noqa: E402
import nc_owning_block  # noqa: E402

PREFIXES = ("UC", "US", "PR", "FN", "PG", "PI", "ST")
DEF_COLLECTIONS = ("usecases", "processes", "functions", "policy_groups", "policy_details", "states")
REF_PI_FIELDS = ("related_policy_details",)
ID_IN_STR = re.compile(r'(PG-[A-Z0-9\-]+|FN-[A-Z0-9\-]+|PI-[A-Z0-9\-]+|PR-[A-Z0-9\-]+)')


def _norm(s):
    return re.sub(r'\s+', '', re.sub(r'\([^)]*\)', '', s or '')).strip()


def _seg(i):
    m = re.match(r'^[A-Z]+-([A-Z0-9]+)-', i or "")
    return m.group(1) if m else None


# ---------------------------------------------------------------- pass 1
def rebuild_policy_details_from_html(spec, html_map, log):
    if not html_map or not any(html_map.values()):
        log.append("rebuild: HTML PG→PI 없음 → 건너뜀")
        return
    groups = spec.get("policy_groups", []) or []
    old_details = spec.get("policy_details", []) or []
    old_name_by_id = {d.get("id"): _norm(d.get("name", "")) for d in old_details}

    covered = {g["id"] for g in groups if html_map.get(g["id"])}
    new_name_to_id = {}
    new_details = []
    for g in groups:
        gid = g["id"]
        pis = html_map.get(gid)
        if pis:
            items = []
            for pi in pis:
                new_details.append({
                    "id": pi["id"], "policy_id": gid, "group_id": gid,
                    "name": pi["name"] or pi["id"],
                    "content": pi["body"] or pi["name"],
                })
                items.append({"id": pi["id"], "name": pi["name"] or pi["id"]})
                new_name_to_id[_norm(pi["name"])] = pi["id"]
            g["items"] = items
        else:
            # HTML 미커버 그룹만 기존 상세 보존(커버된 그룹은 HTML로 전면 대체 = 충실 복원)
            for d in old_details:
                if (d.get("policy_id") or d.get("group_id")) == gid:
                    new_details.append(d)
    spec["policy_details"] = new_details

    # function/process(_details)의 related_policy_details 이름기준 리맵
    dropped = 0
    remapped = 0
    for coll in ("functions", "function_details", "processes", "process_details"):
        for node in spec.get(coll, []) or []:
            for f in REF_PI_FIELDS:
                refs = node.get(f)
                if not isinstance(refs, list):
                    continue
                out = []
                for rid in refs:
                    oldname = old_name_by_id.get(rid)
                    if oldname:  # 기존 상세를 가리키던 참조 → 이름기준 새 id로 리맵
                        new = new_name_to_id.get(oldname)
                        if new:
                            if new not in out:
                                out.append(new)
                            remapped += 1
                        else:
                            dropped += 1  # 새 상세에 대응 이름 없음 → 드롭(게이트 비검사)
                    else:
                        out.append(rid)  # 기존 상세가 아닌 참조는 보존
                node[f] = out
    log.append(f"rebuild: policy_details {len(old_details)}→{len(new_details)} (HTML 커버 그룹 {len(covered)}), "
               f"related_policy_details 리맵 {remapped}·드롭 {dropped}")


# ---------------------------------------------------------------- pass 2
def _walk_strings(obj, fn):
    if isinstance(obj, str):
        return fn(obj)
    if isinstance(obj, list):
        return [_walk_strings(x, fn) for x in obj]
    if isinstance(obj, dict):
        return {k: (v if k in ("source_note", "source_basis", "source_refs") else _walk_strings(v, fn))
                for k, v in obj.items()}
    return obj


def fix_module_code(spec, log):
    biz = (spec.get("meta") or {}).get("business_code")
    if not biz:
        log.append("module_code: business_code 없음 → 건너뜀")
        return
    wrong = set()
    for coll in DEF_COLLECTIONS:
        for x in spec.get(coll, []) or []:
            s = _seg(x.get("id"))
            if s and s != biz:
                wrong.add(s)
    if not wrong:
        log.append(f"module_code: 불일치 세그먼트 없음(biz={biz})")
        return
    pat = re.compile(r'\b([A-Z]{2,4})-(' + "|".join(sorted(map(re.escape, wrong), key=len, reverse=True)) + r')-')
    n = [0]

    def sub(s):
        new, c = pat.subn(lambda m: f"{m.group(1)}-{biz}-", s)
        n[0] += c
        return new

    for k in list(spec.keys()):
        spec[k] = _walk_strings(spec[k], sub)
    log.append(f"module_code: 세그먼트 {sorted(wrong)}→{biz} 치환 {n[0]}건")


# ---------------------------------------------------------------- pass 3
def fix_usecase_join(spec, log):
    ucs = spec.get("usecases", []) or []
    name_count = {}
    name_to_id = {}
    for u in ucs:
        nm = _norm(u.get("name", ""))
        name_count[nm] = name_count.get(nm, 0) + 1
        name_to_id[nm] = u["id"]
    filled = 0
    skipped = 0
    for p in spec.get("processes", []) or []:
        if (p.get("usecase_id") or "").strip():
            continue
        nm = _norm(p.get("name", ""))
        if nm and name_count.get(nm) == 1:
            p["usecase_id"] = name_to_id[nm]
            uids = p.setdefault("usecase_ids", [])
            if name_to_id[nm] not in uids:
                uids.append(name_to_id[nm])
            filled += 1
        elif nm:
            skipped += 1
    log.append(f"usecase_join: usecase_id 충전 {filled} (모호·미매칭 {skipped})")


# ---------------------------------------------------------------- pass 4
def split_concatenated_refs(spec, log):
    n = 0
    for coll in ("processes", "process_details", "functions", "function_details"):
        for node in spec.get(coll, []) or []:
            for f in ("related_policies", "related_functions"):
                refs = node.get(f)
                if not isinstance(refs, list):
                    continue
                out, changed = [], False
                for r in refs:
                    ids = ID_IN_STR.findall(r) if isinstance(r, str) else []
                    if len(ids) > 1:
                        changed = True
                        for x in ids:
                            if x not in out:
                                out.append(x)
                    else:
                        if r not in out:
                            out.append(r)
                if changed:
                    node[f] = out
                    n += 1
    log.append(f"split_refs: 붙은 ID 문자열 분리 {n} 필드")


# ---------------------------------------------------------------- pass 4.5
def fix_ref_format(spec, log):
    """하이픈이 빠진 참조 id를 실재 id로 복원 (예: FN-…-0010101 → FN-…-001-01-01).

    변환 과정에서 related_functions/policies의 id 하이픈이 탈락하는 드리프트를 교정한다.
    실재 정의 id의 '하이픈 제거형'이 유일하게 일치할 때만 복원(모호하면 보존).
    """
    def strip(s):
        return s.replace("-", "") if isinstance(s, str) else s
    fn_by_strip = {}
    pg_by_strip = {}
    for x in spec.get("functions", []) or []:
        fn_by_strip.setdefault(strip(x["id"]), []).append(x["id"])
    for x in spec.get("policy_groups", []) or []:
        pg_by_strip.setdefault(strip(x["id"]), []).append(x["id"])
    fn_ids = {x["id"] for x in spec.get("functions", []) or []}
    pg_ids = {x["id"] for x in spec.get("policy_groups", []) or []}
    n = 0
    for coll in ("processes", "process_details", "functions", "function_details"):
        for node in spec.get(coll, []) or []:
            for field, defined, by_strip in (
                    ("related_functions", fn_ids, fn_by_strip),
                    ("related_policies", pg_ids, pg_by_strip)):
                refs = node.get(field)
                if not isinstance(refs, list):
                    continue
                out = []
                for r in refs:
                    if isinstance(r, str) and r not in defined:
                        cand = by_strip.get(strip(r))
                        if cand and len(cand) == 1:
                            r = cand[0]
                            n += 1
                    if r not in out:
                        out.append(r)
                node[field] = out
    log.append(f"ref_format: 하이픈 탈락 참조 복원 {n}건")


# ---------------------------------------------------------------- pass 5
def drop_phantom_refs(spec, html_text, log):
    """전 프로세스의 related_functions/policies 중 *정의에도 HTML에도 없는* dangling 참조 제거.

    보수적: 정의 부재 + HTML(기획자 의도) 부재를 동시 만족하는 변환 잔재만 삭제한다.
    HTML에 존재하면(기획자 의도) 건드리지 않는다 → 실재 노드 누락은 별도 정합 대상.
    고객/비고객(시스템·운영자·대리·상담사) 프로세스 모두 대상 — 게이트는 고객만 보지만
    비고객 프로세스의 dangling도 그래프 무결성 흠이므로 함께 정리한다.
    """
    fn_ids = {f["id"] for f in spec.get("functions", []) or []}
    pg_ids = {g["id"] for g in spec.get("policy_groups", []) or []}
    removed = []
    for p in spec.get("processes", []) or []:
        for field, defined in (("related_functions", fn_ids), ("related_policies", pg_ids)):
            refs = p.get(field)
            if not isinstance(refs, list):
                continue
            out = []
            for r in refs:
                if isinstance(r, str) and r not in defined and r not in html_text:
                    removed.append((p["id"], field, r))
                else:
                    out.append(r)
            if len(out) != len(refs):
                p[field] = out
    log.append(f"phantom_refs: dangling(정의·HTML 모두 부재) 제거 {len(removed)}건"
               + (" — " + ", ".join(sorted({r for _, _, r in removed})) if removed else ""))


# ---------------------------------------------------------------- pass: recover
# ③content_loss 복원 — dev_format(vendored) 파서로 HTML의 PI content/rules를 읽어,
# 비어있거나 누락된 policy_details에만 채운다. mono(`(PI-…)`)·id="pi-"·말렙드 네스팅을
# 모두 읽는다(nc_html_link이 못 읽는 형식 포함). 제로-날조: 복원 content가 자기 소유
# HTML 구획(nc_owning_block)의 부분문자열일 때만 기록하고, 실패는 deferred 매니페스트로
# 보낸다. 기존 non-empty content는 절대 덮어쓰지 않는다(비파괴).
RECOVER_NOTE = "recovered_from_html:owning_block_pass"


def _is_empty(s):
    return not (s or "").strip()


def recover_content_loss(spec, html_path, log, deferred_out=None):
    if not html_path or not os.path.exists(html_path):
        log.append("recover: HTML 없음 → 건너뜀")
        return {"recovered": 0, "deferred": 0, "deferred_path": None}

    from dev_format_vendor import parse_html  # vendored, stdlib-only
    html_text = open(html_path, encoding="utf-8").read()
    _tables, items, _title = parse_html(Path(html_path))
    segs = nc_owning_block.owning_segments(html_text)

    details = spec.setdefault("policy_details", [])
    by_id = {d.get("id"): d for d in details}
    # A. id-스킴 크로스워크 인덱스: HTML과 JSON의 PI id 스킴이 다를 때
    #    (예: PI-…-APPROVAL-001-001 ↔ PI-…-APR-001) 같은 논리 정책을 신규 PI로
    #    중복 추가(과복원)하지 않기 위해 *정규화 이름*으로 기존 PI를 찾는다.
    by_name = {}
    for d in details:
        nm = _norm(d.get("name") or "")
        if nm:
            by_name.setdefault(nm, d)
    groups = {g.get("id"): g for g in (spec.get("policy_groups", []) or [])}

    recovered, deferred = 0, []
    created, filled = 0, 0
    crosswalked = 0  # 스킴만 다른 동일 정책 — 신규 추가 회피(빈 본문이면 충전)
    for it in items:
        pid = it.pi_id
        content = (it.content or "").strip()
        if _is_empty(content):
            continue  # HTML도 본문 없음 → 손실 아님(placeholder)
        existing = by_id.get(pid)
        if existing is not None and not _is_empty(existing.get("content") or existing.get("rule_statement")):
            continue  # 기존 non-empty → 절대 덮어쓰지 않음
        # content_loss 대상(누락 or 빈 entry). 소유-구획 충실성 게이트.
        seg = segs.get(pid)
        if not nc_owning_block.is_faithful(content, seg):
            deferred.append({
                "pi_id": pid, "pg_id": it.pg_id, "name": it.name,
                "reason": ("no_owning_segment" if seg is None else "owning_block_fail"),
                "content_preview": content[:160],
            })
            continue
        # 충실 → 기록. rules는 구획 충실한 항목만 추가(엄격).
        faithful_rules = [r for r in (it.rules or []) if nc_owning_block.is_faithful(r, seg)]
        if existing is None:
            # A. 크로스워크: id는 JSON에 없지만 같은 정규화 이름의 PI가 이미 있으면
            #    (스킴만 다른 동일 정책) 신규 PI로 중복 추가하지 않는다(과복원 차단).
            xref = by_name.get(_norm(it.name or "")) if it.name else None
            if xref is not None and xref.get("id") != pid:
                crosswalked += 1
                if _is_empty(xref.get("content") or xref.get("rule_statement")):
                    xref["content"] = content
                    if faithful_rules and not xref.get("rules"):
                        xref["rules"] = faithful_rules
                    xref["source_note"] = RECOVER_NOTE + ":crosswalk"
                    filled += 1
                    recovered += 1
                continue  # 기존 non-empty면 동일 정책 → JSON판 유지(무변경)
            entry = {
                "id": pid, "policy_id": it.pg_id or "", "group_id": it.pg_id or "",
                "name": it.name or pid, "content": content,
                "source_note": RECOVER_NOTE,
            }
            if faithful_rules:
                entry["rules"] = faithful_rules
            details.append(entry)
            by_id[pid] = entry
            if it.name:
                by_name.setdefault(_norm(it.name), entry)  # 신규 이름 등록(후속 중복 회피)
            created += 1
            # 그룹 items 양방향 보강(비파괴: 누락시에만 추가)
            g = groups.get(it.pg_id)
            if g is not None:
                gitems = g.setdefault("items", [])
                if not any(isinstance(x, dict) and x.get("id") == pid for x in gitems):
                    gitems.append({"id": pid, "name": it.name or pid})
        else:
            existing["content"] = content
            if faithful_rules and not existing.get("rules"):
                existing["rules"] = faithful_rules
            existing["source_note"] = RECOVER_NOTE
            filled += 1
        recovered += 1

    deferred_path = None
    if deferred and deferred_out:
        manifest = {
            "module": (spec.get("meta") or {}).get("topic")
            or os.path.basename(html_path),
            "html": os.path.basename(html_path),
            "what": "③content_loss PI whose recovered content FAILED owning-block "
                    "faithfulness (would be fabrication) — left as content_loss",
            "count": len(deferred),
            "options": ["author_now (manual reconcile)", "defer (record reason)",
                        "out_of_scope (record reason)"],
            "items": deferred,
        }
        os.makedirs(os.path.dirname(deferred_out) or ".", exist_ok=True)
        json.dump(manifest, open(deferred_out, "w", encoding="utf-8"),
                  ensure_ascii=False, indent=2)
        deferred_path = deferred_out

    log.append(f"recover: content_loss 복원 {recovered}건(신규 {created}·충전 {filled}), "
               f"crosswalk(스킴상이 동일정책 중복회피) {crosswalked}건, "
               f"deferred(owning-block FAIL/구획부재) {len(deferred)}건"
               + (f" → {os.path.basename(deferred_path)}" if deferred_path else ""))
    return {"recovered": recovered, "created": created, "filled": filled,
            "crosswalked": crosswalked, "deferred": len(deferred), "deferred_path": deferred_path}


# 패스 이름(선택 실행용). 기본은 전체. AI검색처럼 게이트 PASS·정합만 필요한 모듈은
# --passes phantom 으로 phantom 정리만 적용(정책 상세 재구성 등 비파괴).
# recover: ③content_loss를 dev_format으로 비파괴 복원(소유-구획 충실 게이트).
ALL_PASSES = ("rebuild", "module_code", "usecase_join", "split_refs", "ref_format", "phantom", "recover")


# ---------------------------------------------------------------- driver
def fix_spec(spec_path, html_path=None, out_path=None, passes=ALL_PASSES):
    spec = json.load(open(spec_path, encoding="utf-8"))
    if html_path is None:
        cand = spec_path.replace("_spec.json", ".html")
        html_path = cand if os.path.exists(cand) else None
    html_text = open(html_path, encoding="utf-8").read() if html_path else ""
    html_map = nc_html_link.parse_pg_pi(html_text) if html_text else {}
    log = []
    if "rebuild" in passes:
        rebuild_policy_details_from_html(spec, html_map, log)
    if "module_code" in passes:
        fix_module_code(spec, log)
    if "usecase_join" in passes:
        fix_usecase_join(spec, log)
    if "split_refs" in passes:
        split_concatenated_refs(spec, log)
    if "ref_format" in passes:
        fix_ref_format(spec, log)
    if "phantom" in passes:
        drop_phantom_refs(spec, html_text, log)

    out_path = out_path or spec_path.replace("_spec.json", "_spec_fixed.json").replace(".json", ".json")
    if out_path == spec_path:
        out_path = spec_path[:-5] + "_fixed.json"
    if "recover" in passes:
        deferred_out = out_path[:-5] + "_recovery_deferred.json"
        recover_content_loss(spec, html_path, log, deferred_out=deferred_out)

    json.dump(spec, open(out_path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)

    from validate_nc_input import check_spec
    err, warn = check_spec(out_path)
    print(f"\n=== {os.path.basename(spec_path)} ===")
    for line in log:
        print("  -", line)
    print(f"  → {os.path.basename(out_path)}  | 게이트 ERROR {len(err)} / WARN {len(warn)}")
    for e in err:
        print("     ERROR:", e)
    return len(err)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("specs", nargs="+")
    ap.add_argument("--html", default=None)
    ap.add_argument("--out", default=None)
    ap.add_argument("--passes", default=None,
                    help="쉼표구분 패스(기본 전체): " + ",".join(ALL_PASSES))
    args = ap.parse_args()
    passes = tuple(p.strip() for p in args.passes.split(",")) if args.passes else ALL_PASSES
    total = 0
    for sp in args.specs:
        total += fix_spec(sp, args.html, args.out, passes)
    sys.exit(0 if total == 0 else 1)


if __name__ == "__main__":
    main()
