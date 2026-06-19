#!/usr/bin/env python3
"""create-sb orchestrator — 입력 spec 무결성 사전검증 게이트 (Step 0, 에이전트 호출 전).

결정론으로 *입력단*을 막는다 — 모듈코드 일관성·조인 키·FK 실재·빈 조인.
빈 조인을 조용히 통과시키지 않는 것이 핵심(빈 슬라이스→creator 수작업 복원→전체 재실행 방지).
정책 사실의 SSOT는 spec이므로 여기서 *고치지* 않고 *막고 리포트*만 한다 — 수정은 사람/상류.

두 심각도 — ERROR는 고객-SB 파이프라인을 *조용히 깨뜨리는* 부류(차단), WARN은 thin spec 특성(리포트만).
이번 세션 PDD에서 실증된 파손 부류만 ERROR로 둔다(FK 댕글링은 PDD에서 멀쩡했으므로 WARN).

ERROR (차단, exit 1):
  MODULE_CODE_MISMATCH  정의 ID(usecases/processes/functions/policy_groups/policy_details/states)의
                        모듈 세그먼트 ≠ meta.business_code (PRD/PDD 혼용류 — 근본 원인을 입력단에서 차단)
  USECASE_ID_EMPTY      process.usecase_id 공란 (slice_uc/extract_skeleton 조인 무효화)
  USECASE_ID_UNRESOLVED process.usecase_id가 usecases에 없음
  JOIN_EMPTY            프로세스가 있는데 고객 UC↔프로세스 조인이 전무 (빈 슬라이스 직결)
  GROUP_DETAIL_UNLINKED 고객 참조 policy_group에 연결된 policy_details 0개 (빈 policy_id·빈 items.id류
                        — extract_skeleton이 정책항목 0개로 산출, PAY/주문 등에서 실증)

WARN (비차단, 리포트):
  FK_FUNCTION/POLICY    고객 프로세스의 related_functions/related_policies 미실재 (thin spec — 부분 나열 허용)

사용: python3 validate_spec_input.py SPEC1.json [SPEC2.json ...]
종료코드: ERROR 0 → 0, ERROR ≥1 → 1 (WARN만 있으면 0).
"""
import argparse, json, re, sys
# NOTE: 디자인팀 create-sb 게이트(validate_spec_input.py) 무수정 이식본.
# 로컬 사전검증 = 디자인팀 업로드 게이트와 동일 판정(5 ERROR + 2 WARN). 로직 변경 금지.

SEG = re.compile(r"^[A-Z]+-([A-Z0-9]+)-")


def seg(i):
    m = SEG.match(i or "")
    return m.group(1) if m else None


def check_spec(path):
    d = json.load(open(path, encoding="utf-8"))
    err, warn = [], []
    mod = (d.get("meta") or {}).get("business_code")
    if not mod:
        return ["META: meta.business_code 없음"], []
    ucs, procs = d.get("usecases", []), d.get("processes", [])
    fns, pgs, pds, sts = (d.get("functions", []), d.get("policy_groups", []),
                          d.get("policy_details", []), d.get("states", []))

    # A. 모듈코드 일관성 — 정의 ID 세그먼트 == business_code (FK 참조는 D/C에서 실재로 검사)
    def consistency(arr, label):
        bad, example = {}, ""
        for x in arr:
            s = seg(x.get("id"))
            if s and s != mod:
                bad[s] = bad.get(s, 0) + 1
                example = example or x.get("id")
        if bad:
            err.append(f"MODULE_CODE_MISMATCH: {label} ID 모듈세그먼트 {bad} ≠ business_code '{mod}' (예: {example})")
    for arr, label in [(ucs, "usecases"), (procs, "processes"), (fns, "functions"),
                       (pgs, "policy_groups"), (pds, "policy_details"), (sts, "states")]:
        consistency(arr, label)

    uc_ids = {u["id"] for u in ucs}
    fn_ids = {f["id"] for f in fns}
    pg_ids = {g["id"] for g in pgs}
    cus_uc = {u["id"] for u in ucs if "고객" in (u.get("actor") or "")}

    # B. usecase_id 무결성
    empty = [p["id"] for p in procs if not (p.get("usecase_id") or "").strip()]
    if empty:
        err.append(f"USECASE_ID_EMPTY: {len(empty)}/{len(procs)} 프로세스 usecase_id 공란 (예: {empty[:3]})")
    unresolved = [p["id"] for p in procs
                  if (p.get("usecase_id") or "").strip() and p["usecase_id"] not in uc_ids]
    if unresolved:
        err.append(f"USECASE_ID_UNRESOLVED: {unresolved[:5]} usecases에 없음")

    # E. 조인 비어있음 (치명 — 빈 슬라이스 직결)
    if procs and cus_uc and not any(p.get("usecase_id") in cus_uc for p in procs):
        err.append("JOIN_EMPTY: 고객 UC↔프로세스 조인 0건 (전 프로세스 usecase_id 공란/타UC — 빈 슬라이스 발생)")

    # 고객 프로세스 집합 (FK·group-detail은 고객 산출 범위에만 적용 — admin/sys 노이즈 제외)
    cus_pr = [p for p in procs if p.get("usecase_id") in cus_uc]

    # D. group↔detail 링크 (ERROR) — 고객 참조 그룹은 detail ≥1개 해소돼야 함 (정방향 items 또는 역방향 policy_id)
    det_by_pg = {}
    for x in pds:
        if x.get("policy_id"):
            det_by_pg[x["policy_id"]] = det_by_pg.get(x["policy_id"], 0) + 1
    pg_by_id = {g["id"]: g for g in pgs}
    referenced = {gid for p in cus_pr for gid in p.get("related_policies", []) or [] if gid in pg_ids}
    unlinked = []
    for gid in sorted(referenced):
        g = pg_by_id.get(gid)
        fwd = len([it for it in (g.get("items") if g else []) or [] if it.get("id")])
        if det_by_pg.get(gid, 0) == 0 and fwd == 0:
            unlinked.append(gid)
    if unlinked:
        err.append(f"GROUP_DETAIL_UNLINKED: 고객참조 그룹 {len(unlinked)}개 연결 policy_details 0개 "
                   f"(빈 policy_id·빈 items.id — extract_skeleton 정책항목 0개 산출): {unlinked[:5]}")

    # C. FK 실재 (WARN) — 고객 프로세스만. thin spec은 함수/그룹 부분 나열 허용
    fk_fn = sorted({fid for p in cus_pr for fid in p.get("related_functions", []) or [] if fid not in fn_ids})
    fk_pg = sorted({gid for p in cus_pr for gid in p.get("related_policies", []) or [] if gid not in pg_ids})
    if fk_fn:
        warn.append(f"FK_FUNCTION: 고객 프로세스가 참조하는 미실재 함수 {len(fk_fn)}개: {fk_fn[:5]}")
    if fk_pg:
        warn.append(f"FK_POLICY_GROUP: 고객 프로세스가 참조하는 미실재 그룹 {len(fk_pg)}개: {fk_pg[:5]}")
    return err, warn


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("specs", nargs="+")
    args = ap.parse_args()
    out, n_err, n_warn = {}, 0, 0
    for p in args.specs:
        try:
            err, warn = check_spec(p)
        except Exception as e:
            err, warn = [f"PARSE_FAIL: {e}"], []
        if err or warn:
            out[p] = {"errors": err, "warnings": warn}
        n_err += len(err)
        n_warn += len(warn)
    print(json.dumps({"specs": out, "checked": len(args.specs),
                      "errors": n_err, "warnings": n_warn}, ensure_ascii=False, indent=2))
    sys.exit(0 if n_err == 0 else 1)


if __name__ == "__main__":
    main()
