#!/usr/bin/env python3
"""fn_pi_derive — 기능→정책상세(FN→PI)를 PG경유 근사로 파생 (하이브리드, 사용자 D5 결정).

골든은 기능마다 관련 정책상세(복수)를 노출한다. 원천 간소화엔 FN→PI 정밀 매핑이 없으므로
**PG경유 근사**로 채운다: 기능의 related_policies(PG) → 그 PG에 속한 PI들을 related_policy_details
초안으로 배정. authored(이미 값 있음)는 보존(덮어쓰지 않음, R3). 파생분은 `related_policy_details_approx`
마커로 표시(authored와 구분 → 렌더가 '근사·검토 필요' 표기). 완료게이트: 정책상세 0인 기능 리포트
("기능은 무조건 정책상세 포함").

정밀 세부기능별 매핑(subfn_pis)은 근사로 채우면 노이즈가 커(기능 PI 전부를 각 세부기능에) 거짓 정밀이
되므로 authoring(policy-detail-authoring)에 맡긴다 — 세부기능 텍스트는 그대로 노출, PI 병기는 저작 시.
"""
import copy
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def derive_fn_pi(spec, mark=True):
    """빈 related_policy_details를 PG경유 근사로 채움. (out, report) 반환. 원본 미변형."""
    out = copy.deepcopy(spec)
    pis_by_pg = {}
    for p in out.get("policy_details", []) or []:
        pg = (p.get("group_id") or p.get("policy_id") or "").strip()
        if pg and p.get("id"):
            pis_by_pg.setdefault(pg, []).append(p["id"])

    # 프로세스 경유 fallback: 기능에 related_policies가 없으면 소속 프로세스(related_functions로 참조)의
    # related_policies(PG)를 사용 — "기능은 무조건 정책상세 포함" 충족(coarse 근사).
    fn_pgs_via_pr = {}
    for pr in out.get("processes", []) or []:
        pr_pgs = pr.get("related_policies") or []
        for fid in (pr.get("related_functions") or []):
            bucket = fn_pgs_via_pr.setdefault(fid, [])
            for pg in pr_pgs:
                if pg not in bucket:
                    bucket.append(pg)

    derived = []
    for fn in out.get("functions", []) or []:
        if fn.get("related_policy_details"):       # authored/기존 → 보존
            continue
        pgs = fn.get("related_policies") or fn_pgs_via_pr.get(fn["id"]) or []
        pis = []
        for pg in pgs:
            for pi in pis_by_pg.get(pg, []):
                if pi not in pis:
                    pis.append(pi)
        if pis:
            fn["related_policy_details"] = pis
            if mark:
                fn["related_policy_details_approx"] = True
            derived.append(fn["id"])

    missing = [fn["id"] for fn in (out.get("functions", []) or [])
               if not fn.get("related_policy_details")]
    return out, {"derived": derived, "missing_policy_functions": missing,
                 "n_functions": len(out.get("functions", []) or [])}


if __name__ == "__main__":
    import argparse
    import json
    ap = argparse.ArgumentParser()
    ap.add_argument("spec_json")
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    spec = json.load(open(a.spec_json, encoding="utf-8"))
    out, rep = derive_fn_pi(spec)
    print(f"  [fn_pi_derive] 파생 {len(rep['derived'])}개 기능 · 정책상세 없는 기능 {len(rep['missing_policy_functions'])}/"
          f"{rep['n_functions']}")
    if rep["missing_policy_functions"]:
        print("    미보유:", rep["missing_policy_functions"][:8])
    if a.out:
        json.dump(out, open(a.out, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        print(f"  saved: {a.out}")
