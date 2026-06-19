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

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import nc_html_link  # noqa: E402

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


# 패스 이름(선택 실행용). 기본은 전체. AI검색처럼 게이트 PASS·정합만 필요한 모듈은
# --passes phantom 으로 phantom 정리만 적용(정책 상세 재구성 등 비파괴).
ALL_PASSES = ("rebuild", "module_code", "usecase_join", "split_refs", "ref_format", "phantom")


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
