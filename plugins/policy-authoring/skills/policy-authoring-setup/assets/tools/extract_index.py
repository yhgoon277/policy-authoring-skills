#!/usr/bin/env python3
"""입력 소스 → 읽기 최적화 JSONL 인덱스 + 커버리지 매트릭스 seed (경량 지식관리).

산출:
  data/index/requirements.jsonl   — 요구사항 151건(합성 ID REQ-<UNIT>-NNN, unit=Depth4)
  data/index/as_is_clauses.jsonl  — as-is 10개 HTML의 heading 단위 절(service 태그)
  audit/<unit>_coverage_matrix.md — unit별 커버리지 매트릭스 seed(요구사항 행). Phase 1에서 채움.

외부 네트워크 없음. 로컬 의존: openpyxl, beautifulsoup4.
사용: python3 extract_index.py
"""
from __future__ import annotations
import glob
import json
import os
import unicodedata

import openpyxl
from bs4 import BeautifulSoup

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Depth4(요구사항) → (unit key, REQ 도메인 prefix)
UNIT_BY_DEPTH4 = {
    "고객센터_통합허브": ("hub", "HUB"),
    "고객센터_FAQ/공지/이용안내": ("faq", "FAQ"),
    "고객센터_매장안내": ("store", "STR"),
}
UNIT_TITLE = {"hub": "통합허브", "faq": "FAQ·공지·이용안내", "store": "매장안내"}


def service_of(fname):
    fname = unicodedata.normalize("NFC", fname)  # macOS 파일명 NFD→NFC (한글 매칭)
    for key, svc in (("월드", "T월드"), ("멤버십", "T멤버십"), ("우주", "T우주"), ("다이렉트샵", "T다이렉트샵")):
        if key in fname:
            return svc
    return "기타"


def extract_requirements():
    f = glob.glob(os.path.join(ROOT, "requirements", "*.xlsx"))
    if not f:
        print("  ⚠️ requirements/*.xlsx 없음 — 요구사항 추출 생략")
        return [], {}
    ws = openpyxl.load_workbook(f[0], read_only=True, data_only=True).worksheets[0]
    reqs, counters = [], {}
    for r in ws.iter_rows(min_row=2, values_only=True):
        if not r or not any(r):
            continue
        depth4 = (r[1] or "").strip()
        unit, prefix = UNIT_BY_DEPTH4.get(depth4, ("misc", "MISC"))
        counters[prefix] = counters.get(prefix, 0) + 1
        reqs.append({
            "requirement_id": f"REQ-{prefix}-{counters[prefix]:03d}",
            "unit": unit, "depth4": depth4,
            "name": (r[2] or "").strip(), "description": (r[3] or "").strip(),
            "fo_bo": (r[4] or "").strip(), "source": (r[5] or "").strip(),
            "edit_status": (r[6] or "").strip(), "reviewer_status": (r[7] or "").strip(),
            "ai_flag": "O" if (r[8] and str(r[8]).strip()) else "",
        })
    return reqs, counters


def extract_as_is_clauses():
    clauses, cid = [], 0
    for path in sorted(glob.glob(os.path.join(ROOT, "samples", "as_is", "*.html"))):
        fname = os.path.basename(path)
        svc = service_of(fname)
        soup = BeautifulSoup(open(path, encoding="utf-8").read(), "html.parser")
        stack = []  # (level, text)
        for h in soup.find_all(["h1", "h2", "h3", "h4"]):
            level = int(h.name[1])
            text = h.get_text(" ", strip=True)
            if not text:
                continue
            while stack and stack[-1][0] >= level:
                stack.pop()
            path_bc = " › ".join(t for _, t in stack)
            stack.append((level, text))
            # 다음 heading 전까지 텍스트 스니펫
            snip = []
            for sib in h.next_elements:
                if getattr(sib, "name", None) in ("h1", "h2", "h3", "h4"):
                    break
                if isinstance(sib, str):
                    s = sib.strip()
                    if s:
                        snip.append(s)
                if sum(len(x) for x in snip) > 240:
                    break
            cid += 1
            clauses.append({
                "clause_id": f"ASIS-{cid:04d}", "service": svc, "as_is_file": fname,
                "level": level, "heading": text, "clause_path": path_bc,
                "snippet": " ".join(snip)[:240],
            })
    return clauses


def write_jsonl(path, rows):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")


def seed_coverage_matrix(unit, reqs):
    """unit 커버리지 매트릭스 seed(요구사항 행). 이미 있으면 덮지 않음(Phase 1 작업 보호)."""
    path = os.path.join(ROOT, "audit", f"{unit}_coverage_matrix.md")
    if os.path.exists(path):
        return path, False
    head = (f"# 고객센터 {UNIT_TITLE.get(unit, unit)} — as-is→to-be 커버리지 매트릭스\n\n"
            "> Phase 1(계층·통폐합)에서 **통폐합 결정·to-be 노드·as-is 출처**를 채운다. "
            "`coverage_gate.py --unit=" + unit + "` 로 검증(요구사항 전건 매핑/범위밖·노드 실존).\n"
            "> 통폐합 결정 ∈ {유지, 통합, 수정, 신설, 삭제(범위밖)}.\n\n"
            "| # | requirement_id | 요구사항명 | FO/BO | 통폐합 결정 | to-be 노드(PR/FN/PG/PI) | as-is 출처(service›clause) | 메모 |\n"
            "|---|---|---|---|---|---|---|---|\n")
    rows = []
    for i, q in enumerate(reqs, 1):
        nm = q["name"].replace("|", "/")
        rows.append(f"| {i} | {q['requirement_id']} | {nm} | {q['fo_bo']} |  |  |  |  |\n")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    open(path, "w", encoding="utf-8").write(head + "".join(rows))
    return path, True


def main():
    reqs, counters = extract_requirements()
    write_jsonl(os.path.join(ROOT, "data", "index", "requirements.jsonl"), reqs)
    print(f"  [requirements] {len(reqs)}건 → data/index/requirements.jsonl  {counters}")

    clauses = extract_as_is_clauses()
    write_jsonl(os.path.join(ROOT, "data", "index", "as_is_clauses.jsonl"), clauses)
    from collections import Counter
    print(f"  [as_is_clauses] {len(clauses)}절 → data/index/as_is_clauses.jsonl  {dict(Counter(c['service'] for c in clauses))}")

    for unit in ("hub", "faq", "store"):
        ur = [q for q in reqs if q["unit"] == unit]
        path, created = seed_coverage_matrix(unit, ur)
        print(f"  [matrix] {unit}: {len(ur)}행 {'생성' if created else '유지(기존 보호)'} → {os.path.relpath(path, ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
