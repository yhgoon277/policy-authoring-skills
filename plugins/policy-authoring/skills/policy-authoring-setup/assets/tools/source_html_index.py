#!/usr/bin/env python3
"""source_html_index — 원본 NC 정책서 HTML에서 진실원천(SSOT) 매핑을 추출.

기획자가 작성한 원본 HTML이 UC/PR/FN/PG/PI 매핑의 진실원천(R3)이다. 짝 JSON은
없거나 stale일 수 있으므로, HTML에서 직접 매핑을 떠서 두 곳에 쓴다:
  (1) R3 원천보존 잠금 — 플러그인 산출 매핑이 원본과 동일한지(승인 없는 발산 차단).
  (2) R1 콘텐츠 충실성 — 원본 콘텐츠/관계가 산출 HTML에 무손실로 보존됐는지.

build_index(path) -> {
  "process_to_functions":     {PR: [FN,...]},   # §4 프로세스 표 '관련 기능' (N:M)
  "process_to_policy_groups": {PR: [PG,...]},   # §4 '관련 정책'
  "function_to_subfns":       {FN: [텍스트,...]}, # §5 기능 표 '세부 기능 구성'
  "function_to_pis":          {FN: [PI,...]},   # §5 '관련 정책 상세'/세부기능 내 PI
  "pg_to_pis":                {PG: [PI,...]},   # §6 정책 상세 (nc_html_link 견고 파서)
}
재사용: dev_format_vendor.parse_html(테이블 모델) · nc_html_link.parse_pg_pi(PG→PI).
"""
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dev_format_vendor  # noqa: E402
import nc_html_link  # noqa: E402


def _bucket(table):
    """테이블 의미 분류 — CSS class 우선, 헤더 텍스트 폴백(레거시 무class 표)."""
    b = dev_format_vendor.CLASS_TO_BUCKET.get((table.table_class or "").strip())
    if b:
        return b
    hs = " ".join(table.headers or [])
    if "프로세스" in hs and "관련 기능" in hs:
        return "processes"
    if "세부 기능" in hs:
        return "functions"
    if "정책" in hs and "정책 상세" in hs and "프로세스" not in hs:
        return "policy_list"
    return ""


def _col(headers, *needles):
    for i, h in enumerate(headers or []):
        if any(n in (h or "") for n in needles):
            return i
    return -1


def _cell_ids(row, col, prefix):
    if col < 0 or col >= len(row):
        return []
    return [i for i in (row[col].ids or []) if i.startswith(prefix)]


def _first_id(row, prefix):
    for c in row:
        for i in (c.ids or []):
            if i.startswith(prefix):
                return i
    return None


def _add(d, key, vals):
    bucket = d.setdefault(key, [])
    for v in vals:
        if v and v not in bucket:
            bucket.append(v)


# 기능 목록 표(function-list-table)의 '세부 기능 구성' 셀은 <br>로 구분된 텍스트 목록이다.
# dev_format_vendor의 Cell.text는 <br>를 보존하지 못해(연결됨) 경계가 사라지므로,
# 세부기능·관련정책상세는 raw HTML에서 직접 파싱한다. (다중 class·4/5열 변형 모두 처리)
_FN_TABLE = re.compile(
    r'<table[^>]*class="[^"]*(?:function-list-table|nc-preview-function-table)[^"]*"[^>]*>(.*?)</table>',
    re.S)
_TR = re.compile(r'<tr[^>]*>(.*?)</tr>', re.S)
_TD = re.compile(r'<t([dh])\b[^>]*>(.*?)</t\1>', re.S)
_BR = re.compile(r'<br\s*/?>', re.I)
_TAG = re.compile(r'<[^>]+>')
_PI = re.compile(r'\b(PI-[A-Z0-9\-]+)\b')
_FN = re.compile(r'\b(FN-[A-Z0-9\-]+)\b')
_PI_SUFFIX = re.compile(r'\s*\(\s*PI-[A-Z0-9\-]+\s*\)\s*$')


def _txt(s):
    return re.sub(r'\s+', ' ', _TAG.sub('', (s or '').replace('&nbsp;', ' '))).strip()


def _extract_function_tables(html, idx):
    """raw HTML의 모든 function-list-table에서 FN→세부기능(<br>분리)·FN→PI 추출."""
    for tbl in _FN_TABLE.findall(html):
        header, body = None, []
        for r in _TR.findall(tbl):
            cells = _TD.findall(r)  # [(tag, content), ...]
            if any(tag == "h" for tag, _ in cells):
                header = [_txt(c) for _, c in cells]
            elif cells:
                body.append([c for _, c in cells])
        if not header:
            continue
        sub_col = next((i for i, h in enumerate(header) if "세부 기능" in h), -1)
        pol_col = next((i for i, h in enumerate(header) if "관련 정책" in h), -1)
        name_col = next((i for i, h in enumerate(header) if "기능명" in h or "기능 명" in h), -1)
        desc_col = next((i for i, h in enumerate(header) if h.strip() in ("설명", "기능 설명")), -1)
        for cells in body:
            fn = next((m.group(1) for c in cells for m in [_FN.search(c)] if m), None)
            if not fn:
                continue
            idx["function_to_subfns"].setdefault(fn, [])
            idx["function_to_pis"].setdefault(fn, [])
            if 0 <= name_col < len(cells) and fn not in idx["function_names"]:
                nm = re.sub(r'\s*\(\s*FN-[A-Z0-9\-]+\s*\)\s*$', '', _txt(cells[name_col])).strip()
                if nm:
                    idx["function_names"][fn] = nm
            if 0 <= desc_col < len(cells) and fn not in idx["function_descriptions"]:
                dv = _txt(cells[desc_col])
                if dv:
                    idx["function_descriptions"][fn] = dv
            if 0 <= sub_col < len(cells):
                raw = cells[sub_col]
                _add(idx["function_to_pis"], fn, _PI.findall(raw))
                for piece in _BR.split(raw):
                    t = _PI_SUFFIX.sub("", _txt(piece)).strip()
                    if t and t not in idx["function_to_subfns"][fn]:
                        idx["function_to_subfns"][fn].append(t)
            if 0 <= pol_col < len(cells):
                _add(idx["function_to_pis"], fn, _PI.findall(cells[pol_col]))


def build_index(path):
    with open(path, encoding="utf-8") as f:
        html = f.read()
    tables, _items, _title = dev_format_vendor.parse_html(Path(path))
    idx = {
        "process_to_functions": {},
        "process_to_policy_groups": {},
        "function_to_subfns": {},
        "function_to_pis": {},
        "pg_to_pis": {},
        "function_names": {},          # FN→기능명(원천 §5) — 원천정본 기능 복원용
        "function_descriptions": {},   # FN→설명(원천 §5)
    }
    for t in tables:
        if _bucket(t) == "processes":
            fn_col = _col(t.headers, "관련 기능")
            pg_col = _col(t.headers, "관련 정책")
            for row in t.rows:
                pr = _first_id(row, "PR-")
                if not pr:
                    continue
                _add(idx["process_to_functions"], pr, _cell_ids(row, fn_col, "FN-"))
                _add(idx["process_to_policy_groups"], pr, _cell_ids(row, pg_col, "PG-"))

    # FN→세부기능·FN→PI: raw HTML(<br> 보존) 직접 파싱
    _extract_function_tables(html, idx)

    # PG→PI: 견고 파서(6변형 + dev_format 폴백)
    pg_pi = nc_html_link.parse_pg_pi(html)
    idx["pg_to_pis"] = {pg: [x["id"] for x in lst] for pg, lst in pg_pi.items()}
    return idx


if __name__ == "__main__":
    import json
    for p in sys.argv[1:]:
        ix = build_index(p)
        print(p)
        print(json.dumps({k: (len(v) if isinstance(v, dict) else v) for k, v in ix.items()},
                         ensure_ascii=False, indent=2))
