#!/usr/bin/env python3
"""rebuild_policy_from_source — 정책층(policy_details·policy_groups)을 원천 HTML 기준 재구성.

R3 결정: 원천 HTML(진실원천)이 PI 정본. reconcile가 입력 spec(기능별 스킴)과 원천(PG기반
스킴)을 union하던 "과복원"을 멈추고, **원천 HTML의 PI 집합·PG그룹을 정본으로 재구성**한다.
  - 원천에 없는 입력전용 PI(예: PARTNER·ORD)는 제외(원천 엄격, 사용자 결정).
  - 콘텐츠 출처(옵션 B): 원천 구조를 기준으로, 원천에 없는 rich 필드(고객안내·근거·applies_to
    ·criteria·표)만 이름매칭된 입력 spec PI에서 **가산 보강**(원천을 덮어쓰지 않음 → R3 무위배).
원천 파싱은 dev_format_vendor.parse_html(rich PolicyDetailItem: rules·detail_tables 포함).
R5 도메인코드 현행화 시 target_code로 원천 id를 relabel.
"""
import copy
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dev_format_vendor as dfv  # noqa: E402


def _norm(s):
    return re.sub(r"\s+", " ", (s or "")).strip().lower()


_PG_HEADING = re.compile(r'<h[1-6][^>]*>(.*?)</h[1-6]>', re.S)
# 리뷰 마커: [검증필요]·[검토필요]·[기술검토필요]·[추가작성필요]·[현업검토필요] 등 [...필요]
_REVIEW = re.compile(r'\[[^\]]*필요\]')


def _pg_names_from_html(html):
    """원천 §6 헤딩(<h4>N) 명칭 (PG-...)</h4>)에서 PG 명칭 추출 — spec에 없는 원천 PG 보강용."""
    out = {}
    for m in _PG_HEADING.finditer(html or ""):
        inner = m.group(1)
        pgm = re.search(r'(PG-[A-Z0-9-]+)', inner)
        if not pgm:
            continue
        name = re.sub(r'<[^>]+>', '', inner)
        name = re.sub(r'\(\s*PG-[A-Z0-9-]+\s*\)', '', name)
        name = re.sub(r'^\s*\d+\)\s*', '', name).strip()
        if name and pgm.group(1) not in out:
            out[pgm.group(1)] = name
    return out


def _rebuild_usecases(tables, relabel):
    """원천 HTML의 유즈케이스 표(§3)에서 UC를 정본으로 추출 — id·액터·명칭·설명."""
    for t in tables:
        b = dfv.CLASS_TO_BUCKET.get((t.table_class or "").strip())
        hs = " ".join(t.headers or [])
        if b != "usecases" and not ("유즈케이스" in hs and "액터" in hs):
            continue

        def col(*needles):
            for i, h in enumerate(t.headers or []):
                if any(n in (h or "") for n in needles):
                    return i
            return -1

        ac, nc, dc = col("액터"), col("유즈케이스명"), col("설명")
        ucs = []
        for row in t.rows:
            uid = next((i for c in row for i in (c.ids or []) if i.startswith(("US-", "UC-"))), None)
            if not uid:
                continue
            if relabel:
                uid = relabel(uid)
            ucs.append({"id": uid,
                        "actor": row[ac].text.strip() if 0 <= ac < len(row) else "",
                        "name": row[nc].text.strip() if 0 <= nc < len(row) else "",
                        "description": row[dc].text.strip() if 0 <= dc < len(row) else ""})
        if ucs:
            return ucs
    return None


def rebuild(spec, source_html, target_code=None):
    """원본 spec은 변형하지 않음(deepcopy). 정책층만 원천 기준으로 교체."""
    import nc_html_link
    tables, items, _ = dfv.parse_html(Path(source_html))
    html_text = Path(source_html).read_text(encoding="utf-8")
    pg_names = _pg_names_from_html(html_text)
    # dev_format_vendor의 pg_id가 일부 원천(§6 변형)에서 누락되므로, 견고 파서(nc_html_link)의
    # PG→PI 매핑으로 PI→PG 폴백 테이블을 만든다(원본 코드 기준). 누락 PI에 group_id 채움.
    pi_to_pg = {}
    for pg_id, lst in nc_html_link.parse_pg_pi(html_text).items():
        for x in lst:
            if x.get("id"):
                pi_to_pg[x["id"]] = pg_id
    relabel = None
    if target_code:
        import domain_code_normalize as dcn
        relabel = lambda s: dcn.relabel_to(s, target_code)
        pg_names = {relabel(k): v for k, v in pg_names.items()}

    in_pi_by_name = {_norm(p.get("name", "")): p for p in (spec.get("policy_details") or []) if p.get("name")}
    spec_pg = {g.get("id"): g for g in (spec.get("policy_groups") or [])}

    pds, pg_order = [], []
    pg_seen = {}
    for it in items:
        pid = (getattr(it, "pi_id", "") or "").strip()
        pg = (getattr(it, "pg_id", "") or "").strip()
        if not pid:
            continue
        if not pg:                       # dfv pg_id 누락 → 견고 파서 폴백(원본 코드로 조회)
            pg = pi_to_pg.get(pid, "")
        src = in_pi_by_name.get(_norm(getattr(it, "name", "")), {})
        if relabel:
            pid, pg = relabel(pid), relabel(pg)
        content = (getattr(it, "content", "") or "").strip()
        crit_all = list(getattr(it, "rules", []) or [])
        # 중복 방지: content가 criteria 이어붙임과 같으면(리스트형 본문) 문단을 비우고 criteria만.
        # 리드문단(criteria 밖 잔여)이 있으면 그 잔여만 rule_statement로.
        lead = content
        for c in crit_all:
            lead = lead.replace(c, "")
        lead = lead.strip()
        rule_statement = lead if crit_all else content
        # [검증필요]류 리뷰 마커가 붙은 항목은 criteria에서 빼 field_review(검토 뱃지)로 승격(골든 스타일).
        review = [c for c in crit_all if _REVIEW.search(c)]
        crit = [c for c in crit_all if not _REVIEW.search(c)]
        field_review = " / ".join(review) if review else src.get("field_review", "")
        pd = {
            "id": pid, "group_id": pg, "policy_id": pg,
            "name": getattr(it, "name", "") or src.get("name", ""),
            "rule_statement": rule_statement or src.get("rule_statement", ""),
            "criteria": crit or list(src.get("criteria", []) or []),
            "field_review": field_review,
            "detail_tables": list(getattr(it, "detail_tables", []) or []) or list(src.get("detail_tables", []) or []),
            "content": "",
        }
        # 옵션 B: 원천에 없는 rich 필드만 입력 spec에서 가산 보강(덮어쓰지 않음)
        for f in ("customer_notice", "notice", "source_note", "field_review",
                  "internal_integration", "applies_to", "criteria_values"):
            if src.get(f) and not pd.get(f):
                pd[f] = src[f]
        pd.setdefault("source_note", "원천 HTML 정책서에서 복원")
        pds.append(pd)
        if pg not in pg_seen:
            pg_seen[pg] = []
            pg_order.append(pg)
        pg_seen[pg].append(pid)

    name_by_id = {p["id"]: p["name"] for p in pds}
    pgs = []
    for pg in pg_order:
        g = spec_pg.get(pg if not relabel else pg, {})  # 이름/설명은 기존 spec PG에서(있으면)
        pgs.append({"id": pg, "name": g.get("name") or pg_names.get(pg, ""), "description": g.get("description", ""),
                    "items": [{"id": pi, "name": name_by_id.get(pi, "")} for pi in pg_seen[pg]]})

    out = copy.deepcopy(spec)
    out["policy_details"] = pds
    out["policy_groups"] = pgs
    # usecase층도 원천 정본으로 복원(원천에 있으면). 원천에 없는 UC 참조는 원천 표에서 채워짐.
    ucs = _rebuild_usecases(tables, relabel)
    if ucs:
        out["usecases"] = ucs
    return out


if __name__ == "__main__":
    import argparse
    import json
    ap = argparse.ArgumentParser()
    ap.add_argument("spec_json")
    ap.add_argument("source_html")
    ap.add_argument("--target-code", default=None)
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    spec = json.load(open(a.spec_json, encoding="utf-8"))
    out = rebuild(spec, a.source_html, a.target_code)
    print(f"  [rebuild] policy_details {len(spec.get('policy_details', []))}→{len(out['policy_details'])} · "
          f"policy_groups {len(spec.get('policy_groups', []))}→{len(out['policy_groups'])}")
    if a.out:
        json.dump(out, open(a.out, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        print(f"  saved: {a.out}")
