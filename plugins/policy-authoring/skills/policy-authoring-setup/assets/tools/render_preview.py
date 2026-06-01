#!/usr/bin/env python3
"""정책 상세(PI) 미리보기 렌더러 — spec JSON → 자기완결 HTML (이식 가능, 의존성 없음).

정책 그룹(PG) → 정책 상세(PI)를, 가독형 포맷으로 렌더한다:
  제목 '명칭 (ID)' (+ 붉은 '현업 검토 필요' 배지) → 정책문 → 표 → 기준값 불릿
  → 고객 안내 콜아웃 → 근거·관련기능 muted 푸터 → field_review 사유.

외부 문서/도구에 의존하지 않는 단일 HTML 파일을 만든다. (기존 산출물 HTML에 끼워넣는
splice 방식이 필요하면 이 렌더 결과의 섹션을 잘라 붙이면 된다.)

사용:
  python3 render_preview.py [--config=policy_config.json] [--out=preview.html] [spec.json]
"""
from __future__ import annotations
import html
import json
import os
import re
import sys

DEFAULT_CONFIG = "policy_config.json"

CSS = """
<style id="policy-detail-format">
body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,"Noto Sans KR",sans-serif;
  color:#1f2937;max-width:920px;margin:24px auto;padding:0 16px;line-height:1.6;}
h1{font-size:20px;border-bottom:2px solid #e5e7eb;padding-bottom:8px;}
h2.pg{font-size:17px;margin:28px 0 6px;color:#111827;}
.pg-desc{color:#6b7280;font-size:13px;margin:0 0 12px;}
.pi{border:1px solid #e5e7eb;border-radius:8px;padding:12px 14px;margin:10px 0;}
.pi-title{font-weight:600;font-size:15px;margin-bottom:6px;}
.pi-id{color:#9ca3af;font-weight:400;font-size:13px;}
.pi-rule{margin:4px 0 8px;}
.policy-detail-table{width:100%;border-collapse:collapse;table-layout:auto;margin:6px 0 10px;font-size:13px;}
.policy-detail-table caption{text-align:left;color:#374151;font-weight:600;margin-bottom:4px;}
.policy-detail-table th,.policy-detail-table td{border:1px solid #d1d5db;padding:4px 8px;text-align:left;vertical-align:top;}
.policy-detail-table th{background:#f3f4f6;}
.table-note{color:#6b7280;font-size:12px;margin:2px 0 8px;}
ul.criteria{margin:4px 0 8px;padding-left:18px;}
.policy-notice{background:#eff6ff;border-left:3px solid #93c5fd;padding:6px 10px;margin:6px 0;border-radius:4px;font-size:13px;}
.policy-meta{color:#6b7280;font-size:12px;margin-top:8px;border-top:1px dashed #e5e7eb;padding-top:6px;}
.policy-review-flag{display:inline-block;background:#fee2e2;color:#b91c1c;font-size:11px;font-weight:600;
  padding:1px 6px;border-radius:4px;margin-left:6px;vertical-align:middle;}
.policy-review-note{color:#b91c1c;font-size:12px;margin-top:4px;}
</style>
"""


def load_config(path):
    if path and os.path.isfile(path):
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    return {}


def e(s):
    """escape + **bold** → <strong>."""
    s = html.escape(str(s or ""))
    return re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", s)


def parse_ref(ref):
    if "#" not in ref:
        return ref, None
    fn, i = ref.rsplit("#", 1)
    try:
        return fn, int(i)
    except ValueError:
        return fn, None


def title_with_id(name, pid):
    name = name or pid
    if pid and pid not in name:
        return f'{e(name)} <span class="pi-id">({e(pid)})</span>'
    return e(name)


def render_table(t):
    out = ['<table class="policy-detail-table">']
    if t.get("caption"):
        out.append(f"<caption>{e(t['caption'])}</caption>")
    if t.get("headers"):
        out.append("<tr>" + "".join(f"<th>{e(h)}</th>" for h in t["headers"]) + "</tr>")
    for row in (t.get("rows") or []):
        out.append("<tr>" + "".join(f"<td>{e(c)}</td>" for c in row) + "</tr>")
    out.append("</table>")
    if t.get("note"):
        out.append(f'<div class="table-note">{e(t["note"])}</div>')
    return "".join(out)


def render_pi(pi, fn_by, fd_by):
    out = ['<div class="pi">']
    flag = ' <span class="policy-review-flag">현업 검토 필요</span>' if pi.get("field_review") else ""
    out.append(f'<div class="pi-title">{title_with_id(pi.get("name"), pi.get("id"))}{flag}</div>')
    rule = pi.get("rule_statement") or pi.get("content")
    if rule:
        out.append(f'<div class="pi-rule">{e(rule)}</div>')
    for t in (pi.get("detail_tables") or []):
        out.append(render_table(t))
    crit = pi.get("criteria_values") or pi.get("criteria") or []
    if crit and not pi.get("detail_tables"):
        out.append('<ul class="criteria">' + "".join(f"<li>{e(c)}</li>" for c in crit) + "</ul>")
    notice = pi.get("customer_notice") or pi.get("notice")
    if notice:
        out.append(f'<div class="policy-notice">💬 {e(notice)}</div>')
    # 근거·관련기능 muted 푸터
    meta = []
    if pi.get("source_note"):
        meta.append(f"근거: {e(pi['source_note'])}")
    refs = []
    for ref in (pi.get("applies_to") or []):
        fid, i = parse_ref(ref)
        fn = fn_by.get(fid) or {}
        subs = (fd_by.get(fid) or {}).get("sub_functions") or []
        stext = subs[i - 1] if (i and 1 <= i <= len(subs)) else ""
        label = fn.get("name", fid)
        refs.append(f"{e(label)} › {e(stext)}" if stext else e(label))
    if refs:
        meta.append("관련 기능: " + " / ".join(refs))
    if meta:
        out.append('<div class="policy-meta">' + " · ".join(meta) + "</div>")
    if pi.get("field_review"):
        out.append(f'<div class="policy-review-note">[현업 검토 필요] {e(pi["field_review"])}</div>')
    out.append("</div>")
    return "".join(out)


def main(argv):
    args = [a for a in argv[1:] if not a.startswith("--")]
    config_path, out_path = DEFAULT_CONFIG, None
    for a in argv[1:]:
        if a.startswith("--config="):
            config_path = a.split("=", 1)[1].strip()
        elif a.startswith("--out="):
            out_path = a.split("=", 1)[1].strip()
    cfg = load_config(config_path)
    spec_path = args[0] if args else cfg.get("spec_path")
    if not spec_path:
        print("ERROR: spec 경로를 지정하거나 config.spec_path 를 설정하세요.", file=sys.stderr)
        return 2
    out_path = out_path or cfg.get("preview_out") or "/tmp/policy_preview.html"

    spec = json.load(open(spec_path, encoding="utf-8"))
    fn_by = {f["id"]: f for f in spec.get("functions", [])}
    fd_by = {fd.get("function_id"): fd for fd in spec.get("function_details", [])}
    pi_by = {pi["id"]: pi for pi in spec.get("policy_details", [])}

    title = (spec.get("meta") or {}).get("title") or "정책 상세 미리보기"
    parts = ["<!doctype html><html lang='ko'><head><meta charset='utf-8'>",
             f"<title>{e(title)}</title>", CSS, "</head><body>",
             f"<h1>{e(title)} — 정책 상세</h1>"]
    for pg in spec.get("policy_groups", []):
        parts.append(f'<h2 class="pg">{title_with_id(pg.get("name"), pg.get("id"))}</h2>')
        if pg.get("description"):
            parts.append(f'<p class="pg-desc">{e(pg["description"])}</p>')
        for it in (pg.get("items") or []):
            pid = it["id"] if isinstance(it, dict) else it
            pi = pi_by.get(pid)
            if pi:
                parts.append(render_pi(pi, fn_by, fd_by))
    parts.append("</body></html>")

    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(parts))
    n_flag = sum(1 for pi in spec.get("policy_details", []) if pi.get("field_review"))
    n_tbl = sum(len(pi.get("detail_tables") or []) for pi in spec.get("policy_details", []))
    print(f"  [render] {out_path}  (PG {len(spec.get('policy_groups', []))}·PI {len(pi_by)}·표 {n_tbl}·현업검토 {n_flag})")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
