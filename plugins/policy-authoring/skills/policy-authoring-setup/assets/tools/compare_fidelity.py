#!/usr/bin/env python3
"""compare_fidelity (T-R1) — 원본 NC HTML(진실원천) ↔ 생성 HTML 콘텐츠/관계 충실성 진단.

두 HTML을 `source_html_index`로 동일하게 파싱해 매핑을 떠서 **손실만** 잡는다:
원본에 있는 콘텐츠/관계가 생성에서 비거나 빠지면 결함(HIGH). 포맷 업그레이드(생성에만
추가된 칼럼/항목)는 결함 아님. R5 도메인코드 현행화가 있으면 비교 전 원본 ID를 목표코드로
relabel해(R5-aware) 라벨 변경을 손실로 오탐하지 않는다.

**구간 분리(R3 헤드 완전보존 + R1 §5+ 본문 골든)**: 배포물은 §0~§4(문서히스토리·개요·주요용어·
유즈케이스/상태전이 다이어그램·프로세스 정의 케이스표)를 원천 HTML 그대로 완전보존하고(NC가
골든보다 풍부한 구간), §5 기능·§6 정책만 골든 스타일로 렌더한다(NC 평면텍스트→골든 리치). 따라서
헤드(§0~§4)는 원천과 바이트 동일해야 하며(HEAD_PRESERVED), 골든 스타일 검사는 §5+ 본문에만 적용한다.

불변식(원본=기준). principle 필드로 R1(스타일)/R3(보존)을 태깅:
  [R3·손실=원본−생성]
  FN_DROPPED     §5 기능 정의에서 원본 기능이 생성에 없음(N:M→1:1 붕괴 등)        HIGH
  FN_SUBFN_LOST  기능의 세부기능 텍스트가 원본엔 있는데 생성은 비었음(— 등)        HIGH
  PG_DROPPED     원본 정책그룹이 생성에 없음                                       HIGH
  PI_LOST        정책그룹 내 정책항목(PI)이 원본엔 있는데 생성에 없음              HIGH
  PR_FN_LOST     §4 프로세스→기능 관계가 원본엔 있는데 생성에 없음                 HIGH
  HEAD_PRESERVED §5 이전 헤드(§0~§4)가 원천과 다름(다이어그램·케이스표 변형)       HIGH
  [R3·발산=생성−원본, approved 로그 면제]
  FN_ADDED       원천에 없는 기능이 생성에 추가됨(무단 발산)                       HIGH
  PG_ADDED       원천에 없는 정책그룹이 생성에 추가됨                              HIGH
  PI_ADDED       원천에 없는 정책항목이 생성에 추가됨                              HIGH
  [R1·골든 스타일, §5+ 본문]
  STYLE_POLICYLIST_PIID  §6 정책목록 '정책 상세'에 PI-id 병기 없음                 HIGH
  FN_NO_POLICY   관련 정책상세 없는 기능(완료게이트, "기능은 무조건 정책상세 포함") MED

verdict: HIGH 1개라도 있으면 FAIL. 발산은 approved(사람 승인 id 목록)로 면제.
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import source_html_index as shi  # noqa: E402
import domain_code_normalize as dcn  # noqa: E402

_EMPTY_SUBFN = ({"—"}, {"-"}, {"–"}, {""}, set())

# 불변식 → 원칙 매핑(run_acceptance가 R1/R3로 버킷팅). 손실·발산·헤드보존=R3(원천보존),
# 골든 스타일·완료게이트=R1.
_PRINCIPLE = {
    "FN_DROPPED": "R3", "FN_SUBFN_LOST": "R3", "PG_DROPPED": "R3", "PI_LOST": "R3",
    "PR_FN_LOST": "R3", "HEAD_PRESERVED": "R3", "FN_SOURCE_ORPHAN": "R3",
    "FN_ADDED": "R3", "PG_ADDED": "R3", "PI_ADDED": "R3",
    "STYLE_POLICYLIST_PIID": "R1", "FN_NO_POLICY": "R1",
}


def _relabel_index(idx, target):
    """R5-aware: 인덱스의 모든 ID 키/값 도메인세그먼트를 target으로 relabel."""
    if not target:
        return idx
    r = lambda s: dcn.relabel_to(s, target)
    out = {}
    for k in ("process_to_functions", "process_to_policy_groups", "function_to_pis", "pg_to_pis"):
        out[k] = {r(key): [r(v) for v in vals] for key, vals in (idx.get(k) or {}).items()}
    # function_to_subfns: 키(FN)만 relabel, 값(세부기능 텍스트)은 그대로
    out["function_to_subfns"] = {r(key): list(vals) for key, vals in (idx.get("function_to_subfns") or {}).items()}
    return out


def _is_empty_subfn(vals):
    return set(v.strip() for v in (vals or [])) in _EMPTY_SUBFN


def compare(orig_html, gen_html, target_code=None, approved=None):
    o = shi.build_index(orig_html)
    g = shi.build_index(gen_html)
    if target_code:
        o = _relabel_index(o, target_code)
    approved = set(approved or [])   # 사람 승인된 발산 id(무단 발산 면제)
    findings = []

    def add(inv, sev, key, detail, ov=None, gv=None):
        findings.append({"invariant": inv, "severity": sev, "key": key,
                         "principle": _PRINCIPLE.get(inv, "R3"),
                         "detail": detail, "orig": ov, "gen": gv})

    o_f2s, g_f2s = o["function_to_subfns"], g["function_to_subfns"]
    # 원천이 아는 기능 = §5 정의 ∪ §4 프로세스가 참조. (원천 §4↔§5 불일치 대응)
    src_proc_fns = {fn for fns in o["process_to_functions"].values() for fn in fns}
    source_known_fns = set(o_f2s) | src_proc_fns
    # FN_DROPPED — 원본 §5 기능이 생성 §5에 없음. 단 §4 어떤 프로세스에도 미연결(원천 고아)이면
    # 프로세스-그룹 렌더가 배치할 수 없음 → 원천 §4↔§5 불일치 = 사람 확인(FN_SOURCE_ORPHAN, MED).
    for fn in o_f2s:
        if fn not in g_f2s:
            if fn in src_proc_fns:
                add("FN_DROPPED", "HIGH", fn, "원본 §5 기능이 생성에 없음(N:M 붕괴 가능)")
            else:
                add("FN_SOURCE_ORPHAN", "MED", fn,
                    "원천 §5 정의 기능이 §4 어떤 프로세스에도 미연결(원천 §4↔§5 불일치) — 사람 확인")
    # FN_SUBFN_LOST — 세부기능 텍스트가 원본엔 있는데 생성은 빔
    for fn, subs in o_f2s.items():
        if fn in g_f2s and not _is_empty_subfn(subs) and _is_empty_subfn(g_f2s[fn]):
            add("FN_SUBFN_LOST", "HIGH", fn, "세부기능 텍스트 손실(생성 빈칸)",
                subs[:4], g_f2s[fn])

    # PG_DROPPED / PI_LOST
    o_pg, g_pg = o["pg_to_pis"], g["pg_to_pis"]
    for pg, pis in o_pg.items():
        if pg not in g_pg:
            add("PG_DROPPED", "HIGH", pg, "원본 정책그룹이 생성에 없음", pis[:5])
        else:
            miss = [p for p in pis if p not in g_pg[pg]]
            if miss:
                add("PI_LOST", "HIGH", pg, f"정책항목 {len(miss)}개 손실", miss[:5])

    # PR_FN_LOST — §4 프로세스→기능 관계 손실
    o_p2f, g_p2f = o["process_to_functions"], g["process_to_functions"]
    for pr, fns in o_p2f.items():
        gset = set(g_p2f.get(pr, []))
        miss = [f for f in fns if f not in gset]
        if miss:
            add("PR_FN_LOST", "HIGH", pr, f"프로세스→기능 {len(miss)}개 손실", miss[:5])

    # ── R3 발산(divergence): 배포물에 있으나 원천에 없는 엔티티 = 무단 추가(원천보존 strict) ──
    # 승인 로그(approved)에 등재된 id는 면제. 파생 FN→PI는 기존 PI를 링크할 뿐 신규 엔티티가
    # 아니므로 여기서 오탐되지 않음(엔티티 단위 검사).
    for fn in g_f2s:
        if fn not in source_known_fns and fn not in approved:
            add("FN_ADDED", "HIGH", fn, "원천(§5·§4)에 없는 기능이 생성에 추가됨(무단 발산)")
    for pg in g_pg:
        if pg not in o_pg and pg not in approved:
            add("PG_ADDED", "HIGH", pg, "원천에 없는 정책그룹이 생성에 추가됨(무단 발산)")
    o_pi_all = {p for pis in o_pg.values() for p in pis}
    g_pi_all = {p for pis in g_pg.values() for p in pis}
    added_pi = [p for p in g_pi_all if p not in o_pi_all and p not in approved]
    if added_pi:
        add("PI_ADDED", "HIGH", "policy_items",
            f"원천에 없는 정책항목 {len(added_pi)}개 추가(무단 발산)", added_pi[:5])

    # R1 골든 스타일 + R3 헤드 완전보존 자동검수.
    # 배포물 구조: §0~§4(문서히스토리~프로세스 정의, 다이어그램·용어·유즈케이스·프로세스 케이스표)
    # = 원천 HTML 완전보존(R3, NC가 골든보다 풍부한 구간), §5 기능·§6 정책 = 골든 스타일 렌더
    # (R1, NC 평면텍스트→골든 리치). 따라서 (a) 헤드(§0~§4)는 원천과 바이트 동일해야 하고,
    # (b) 골든 스타일 검사는 §5+ 본문에만 적용(원천이 policy-list-table 등 클래스를 헤드의 액터/
    # 유즈케이스/프로세스 표에 재사용해도 오탐 금지).
    try:
        with open(gen_html, encoding="utf-8") as _f:
            gen_txt = _f.read()
    except (OSError, TypeError):
        gen_txt = ""
    try:
        with open(orig_html, encoding="utf-8") as _f:
            orig_txt = _f.read()
    except (OSError, TypeError):
        orig_txt = ""

    def _split_body(txt):
        """(§5 이전 헤드=§0~§4, §5 이후 본문). §5 마커 없으면 (None, 전체)."""
        mm = re.search(r'<h2[^>]*>\s*5\.', txt)
        return (txt[:mm.start()], txt[mm.start():]) if mm else (None, txt)

    # (a) HEAD_PRESERVED — §5 이전 헤드(§0~§4)가 원천과 동일(R5 현행화 시 원천 헤드도 목표코드 relabel).
    o_head, _ = _split_body(orig_txt)
    g_head, _ = _split_body(gen_txt)
    if target_code and o_head is not None:
        o_head = dcn.relabel_to(o_head, target_code)
    if o_head is not None and g_head is not None and o_head != g_head:
        add("HEAD_PRESERVED", "HIGH", "head",
            "§0~§4 헤드가 원천과 다름(완전보존 위배 — 다이어그램·개요·프로세스 케이스표 변형/재생성)")

    # (b) 골든 스타일 검사 — §5+ 본문에만.
    _, body_txt = _split_body(gen_txt)
    pl_tables = re.findall(r'<table class="policy-list-table">(.*?)</table>', body_txt, re.S)
    if pl_tables and any(("(PI-" not in t and "(POL-" not in t) for t in pl_tables):
        add("STYLE_POLICYLIST_PIID", "HIGH", "policy_list", "정책목록 '정책 상세'에 PI-id 병기 없음(골든은 명+ID)")
    # 완료게이트: 관련 정책상세 없는 기능("기능은 무조건 정책상세 포함")
    no_pi = [fn for fn in g.get("function_to_subfns", {}) if not g.get("function_to_pis", {}).get(fn)]
    if no_pi:
        add("FN_NO_POLICY", "MED", "functions",
            f"관련 정책상세 없는 기능 {len(no_pi)}개(작업자 저작 필요): {no_pi[:5]}")

    highs = sum(1 for f in findings if f["severity"] == "HIGH")
    return {
        "findings": findings,
        "summary": {"high": highs, "total": len(findings),
                    "orig_functions": len(o_f2s), "gen_functions": len(g_f2s),
                    "orig_pgs": len(o_pg), "gen_pgs": len(g_pg)},
        "verdict": "FAIL" if highs else "PASS",
    }


if __name__ == "__main__":
    import argparse
    import json
    ap = argparse.ArgumentParser()
    ap.add_argument("orig_html")
    ap.add_argument("gen_html")
    ap.add_argument("--target-code", default=None)
    ap.add_argument("--approved", default=None, help="승인된 발산 id JSON(list) 경로")
    a = ap.parse_args()
    approved = None
    if a.approved and os.path.exists(a.approved):
        with open(a.approved, encoding="utf-8") as _f:
            approved = json.load(_f)
    r = compare(a.orig_html, a.gen_html, a.target_code, approved=approved)
    print(json.dumps({"verdict": r["verdict"], "summary": r["summary"],
                      "findings_by_invariant": {inv: sum(1 for f in r["findings"] if f["invariant"] == inv)
                                                for inv in {f["invariant"] for f in r["findings"]}},
                      "sample": r["findings"][:6]}, ensure_ascii=False, indent=2))
