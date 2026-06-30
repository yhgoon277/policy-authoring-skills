#!/usr/bin/env python3
"""HTML↔JSON 정합 진단 — 기획자 의도(HTML) 대비 ncstudio JSON 변환의 이격 분류.

HTML이 기획자의 최종 의도(진실원천)이고 JSON은 자동변환 산출물이다. 게이트(errors=0)를
통과하더라도 JSON이 HTML 의도를 온전히 담지 못할 수 있다. 이 도구는 *수정하지 않고*
각 PG/PI 이격을 다음으로 분류해 리포트한다(기획자 전달용):

  ① div앵커-제목 드리프트  : HTML 내부에서 <div id="pi-X">와 제목 정본 (Y)가 불일치
                             (후속 ID 정정이 div 속성에 미반영). 기획자 측 HTML 위생.
  ② phantom 참조           : JSON 고객 프로세스가 참조하나 JSON 정의에도 HTML에도 없는 FN/PG.
  ③ 실내용 손실            : HTML 정본 PI에 본문이 있는데 JSON policy_details에 부재. (진짜 손실)
  ④ placeholder 이름만     : HTML에도 본문 없이 이름만(기획자 미작성) + JSON 부재. 손실 아님.
  ⑤ JSON-only              : JSON policy_details에 있으나 HTML 정본에 없음.

정본(canonical) PI id는 HTML 제목의 (PI-...) 링크 텍스트 기준(nc_html_link 파서) — div의
id="pi-..." 속성은 드리프트할 수 있어 신뢰하지 않는다.

사용:
  python3 tools/diff_nc_html_json.py SPEC.json [--html HTML] [--format md|json]
"""
import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import nc_html_link  # noqa: E402

# 한 policy-item 블록: div 앵커 id="pi-X" … 제 제목 링크 (Y) 를 *블록 내부에서* 짝지음.
ITEM_BLOCK = re.compile(
    r'<div[^>]*class="policy-item"[^>]*\sid="pi-(?P<div>PI-[A-Z0-9\-]+)"'
    r'.*?class="policy-item-title">.*?\(<a[^>]*>\s*(?P<title>PI-[A-Z0-9\-]+)\s*</a>\)',
    re.S)


def _norm(s):
    return re.sub(r'\s+', ' ', (s or '')).strip()


def html_drift(html):
    """각 policy-item 블록 내부에서 div 앵커 id와 제목 정본 id를 짝지어 불일치 추출."""
    pairs = []
    for m in ITEM_BLOCK.finditer(html):
        dv, tt = m.group("div"), m.group("title")
        if dv != tt:
            pairs.append((dv, tt))
    return pairs


def customer_phantom_refs(d, html):
    """게이트 FK 경고와 동형: 고객 프로세스가 참조하나 정의에도 HTML에도 없는 FN/PG."""
    ucs = d.get("usecases", []) or []
    cus_uc = {u["id"] for u in ucs if "고객" in (u.get("actor") or "")}
    fn_ids = {f["id"] for f in d.get("functions", []) or []}
    pg_ids = {g["id"] for g in d.get("policy_groups", []) or []}
    out = []
    for p in d.get("processes", []) or []:
        if p.get("usecase_id") not in cus_uc:
            continue
        for fid in (p.get("related_functions") or []):
            if fid not in fn_ids and fid not in html:
                out.append({"process": p["id"], "kind": "function", "ref": fid})
        for gid in (p.get("related_policies") or []):
            if gid not in pg_ids and gid not in html:
                out.append({"process": p["id"], "kind": "policy_group", "ref": gid})
    return out


def diagnose(spec_path, html_path=None, fmt="md"):
    d = json.load(open(spec_path, encoding="utf-8"))
    if html_path is None:
        cand = spec_path.replace("_spec.json", ".html")
        html_path = cand if os.path.exists(cand) else None
    html = open(html_path, encoding="utf-8").read() if html_path else ""

    # HTML 정본 PI(제목 링크 기준) — {pid: {name, has_body, pg}}
    pg_pi = nc_html_link.parse_pg_pi(html) if html else {}
    html_pi = {}
    for pg, items in pg_pi.items():
        for it in items:
            html_pi[it["id"]] = {"name": it["name"], "has_body": bool(_norm(it["body"])), "pg": pg}

    # JSON policy_details — {pid: {name, has_content}}
    json_pi = {}
    for x in d.get("policy_details", []) or []:
        content = x.get("content") or x.get("rule_statement") or ""
        json_pi[x["id"]] = {"name": x.get("name", ""), "has_content": bool(_norm(content))}

    html_ids = set(html_pi)
    json_ids = set(json_pi)

    drift_pairs = html_drift(html)
    phantom = customer_phantom_refs(d, html)

    # ③ 실내용 손실: HTML 본문 有 · (JSON 부재 OR JSON content 공란).
    #    B: 공란 row(JSON에 PI는 있으나 비어있음)도 손실로 포함 — recover가 채우는 대상과
    #    일치시켜 거짓음성 해소(이전엔 '부재'만 잡고 '공란'은 무손실로 오판).
    content_loss = sorted(
        pid for pid in html_ids
        if html_pi[pid]["has_body"]
        and (pid not in json_ids or not json_pi[pid]["has_content"]))
    content_loss_emptyrow = sorted(
        pid for pid in (html_ids & json_ids)
        if html_pi[pid]["has_body"] and not json_pi[pid]["has_content"])
    # ④ placeholder: HTML 본문 無 · JSON 부재
    placeholder = sorted(
        pid for pid in (html_ids - json_ids) if not html_pi[pid]["has_body"])
    # ⑤ JSON-only
    json_only = sorted(json_ids - html_ids)
    # B: 측정불가 — 파서가 HTML PI를 0개 인식했는데 JSON엔 PI가 있고 HTML 본문이 존재.
    #    이 경우 content_loss=0은 '무손실'이 아니라 '측정불가'(미지원 포맷 가능성).
    unmeasurable = bool(len(html_ids) == 0 and len(json_ids) > 0 and html.strip())

    # PG 수준 요약
    html_pg = set(pg_pi)
    json_pg = {g["id"] for g in d.get("policy_groups", []) or []}

    report = {
        "module": (d.get("meta") or {}).get("topic") or os.path.basename(spec_path),
        "business_code": (d.get("meta") or {}).get("business_code"),
        "counts": {
            "html_canonical_pi": len(html_ids),
            "json_policy_details": len(json_ids),
            "html_pg_sections": len(html_pg),
            "json_policy_groups": len(json_pg),
            "content_loss_emptyrow": len(content_loss_emptyrow),
        },
        "unmeasurable": unmeasurable,
        "drift": {
            "count": len(drift_pairs),
            "examples": [{"div_anchor": a, "title_canonical": b} for a, b in drift_pairs[:20]],
        },
        "phantom": phantom,
        "content_loss": [{"id": p, "name": html_pi[p]["name"], "pg": html_pi[p]["pg"]} for p in content_loss],
        "placeholder_only": [{"id": p, "name": html_pi[p]["name"], "pg": html_pi[p]["pg"]} for p in placeholder],
        "json_only": [{"id": p, "name": json_pi[p]["name"]} for p in json_only],
        "pg_in_json_not_html": sorted(json_pg - html_pg),
        "pg_in_html_not_json": sorted(html_pg - json_pg),
    }
    if fmt == "json":
        return json.dumps(report, ensure_ascii=False, indent=2)
    return render_md(report)


def render_md(r):
    c = r["counts"]
    L = [f"# HTML↔JSON 정합 진단 — {r['module']} ({r['business_code']})",
         "",
         "HTML(기획자 최종 의도) 대비 ncstudio JSON 변환의 이격 분류. 정본 PI id는 HTML 제목의 "
         "`(PI-…)` 링크 기준(div `id=` 속성은 드리프트하므로 비신뢰).",
         "",
         "## 요약",
         f"- HTML 정본 PI: **{c['html_canonical_pi']}** · JSON policy_details: **{c['json_policy_details']}**",
         f"- HTML PG 상세: {c['html_pg_sections']} · JSON policy_groups: {c['json_policy_groups']}",
         f"- ① div앵커-제목 드리프트: **{r['drift']['count']}**(HTML 위생, 기획자)",
         f"- ② phantom 참조: **{len(r['phantom'])}**",
         f"- ③ 실내용 손실(HTML 본문 有·JSON 無): **{len(r['content_loss'])}**",
         f"- ④ placeholder 이름만(HTML도 미작성): **{len(r['placeholder_only'])}**",
         f"- ⑤ JSON-only(HTML 정본 부재): **{len(r['json_only'])}**",
         ""]

    L.append("## ② phantom 참조 (변환 잔재 — 정의·HTML 모두 부재)")
    if r["phantom"]:
        for p in r["phantom"]:
            L.append(f"- `{p['ref']}` ({p['kind']}) ← {p['process']}")
    else:
        L.append("- 없음")
    L.append("")

    L.append("## ③ 실내용 손실 — HTML에 본문이 있으나 JSON에 부재 (기획자 확인·보강 대상)")
    if r["content_loss"]:
        for x in r["content_loss"]:
            L.append(f"- `{x['id']}` {x['name']}  · 소속 {x['pg']}")
    else:
        L.append("- 없음")
    L.append("")

    L.append("## ① div앵커-제목 드리프트 (HTML 내부 위생 — div `id=` 미정정)")
    if r["drift"]["examples"]:
        for x in r["drift"]["examples"]:
            L.append(f"- div `{x['div_anchor']}` ↔ 제목 `{x['title_canonical']}`")
        if r["drift"]["count"] > len(r["drift"]["examples"]):
            L.append(f"- … 외 {r['drift']['count'] - len(r['drift']['examples'])}건")
    else:
        L.append("- 없음")
    L.append("")

    L.append("## ④ placeholder 이름만 (HTML도 본문 미작성 — 손실 아님)")
    L.append(f"- {len(r['placeholder_only'])}건"
             + (": " + ", ".join(f"`{x['id']}`" for x in r["placeholder_only"][:15]) if r["placeholder_only"] else ""))
    L.append("")

    L.append("## ⑤ JSON-only (HTML 정본에 없음 — 변환 부가/번호 어긋남 후보)")
    if r["json_only"]:
        for x in r["json_only"]:
            L.append(f"- `{x['id']}` {x['name']}")
    else:
        L.append("- 없음")
    L.append("")

    if r["pg_in_json_not_html"] or r["pg_in_html_not_json"]:
        L.append("## PG 이격")
        if r["pg_in_json_not_html"]:
            L.append(f"- JSON에만: {', '.join(r['pg_in_json_not_html'])}")
        if r["pg_in_html_not_json"]:
            L.append(f"- HTML에만: {', '.join(r['pg_in_html_not_json'])}")
        L.append("")
    return "\n".join(L)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("spec")
    ap.add_argument("--html", default=None)
    ap.add_argument("--format", choices=["md", "json"], default="md")
    args = ap.parse_args()
    print(diagnose(args.spec, args.html, args.format))


if __name__ == "__main__":
    main()
