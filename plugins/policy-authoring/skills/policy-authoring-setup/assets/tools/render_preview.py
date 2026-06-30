#!/usr/bin/env python3
"""정책 spec JSON → 자기완결 HTML 미리보기 (billing 6-섹션 NC스튜디오 포맷, 의존성 없음).

JSON-first 진실원천. HTML은 spec에서 100% 생성한다(수기 편집 금지 → json↔html 이격 차단).
섹션: 0.히스토리 / 1.개요 / 2.용어 / 3.유즈케이스(가.액터·나.유즈케이스·라.상태전이) /
      4.프로세스 / 5.기능 / 6.정책(가.목록·나.상세) / 최종 점검 기준.
배지는 spec 필드로만: field_review→붉은 'BSS/현업 검토 필요', internal_integration→앰버 '내부 통합 필요'.
CSS는 tools/preview_style.css(billing 최종본 추출, base+policy 통합)를 그대로 사용.

섹션 빌더는 MyPart_PolicyWrite/tools/splice_preview.py 를 _replace_between 없이 문자열반환형으로 포팅.

사용: python3 render_preview.py --config=policy_config.json --unit=<hub|faq|store> [--out=preview.html]
"""
from __future__ import annotations
import html as _html
import json
import os
import sys
from collections import defaultdict

DEFAULT_CONFIG = "policy_config.json"
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))


def load_config(path):
    if path and os.path.isfile(path):
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    return {}


def overlay_unit(cfg, unit):
    """config.units[unit] 블록을 top-level 키로 끌어올린다(있으면)."""
    units = cfg.get("units") or {}
    if not unit:
        return cfg
    if unit not in units:
        raise SystemExit(f"--unit={unit} 가 units 에 없습니다. 가능: {sorted(units)}")
    merged = dict(cfg)
    merged.update(units[unit])
    return merged


def load_css():
    p = os.path.join(SCRIPT_DIR, "preview_style.css")
    if os.path.isfile(p):
        return open(p, encoding="utf-8").read()
    return "<style></style>"


def _e(s):
    """HTML escape + <strong>/<br> 보존."""
    raw = _html.escape(str(s) if s is not None else "")
    return (raw.replace("&lt;strong&gt;", "<strong>").replace("&lt;/strong&gt;", "</strong>")
               .replace("&lt;br/&gt;", "<br/>").replace("&lt;br&gt;", "<br>"))


def _multiline(s):
    return "<br>".join(_e(ln) for ln in (s or "").split("\n"))


# ─────────────────── 그룹/인덱스 헬퍼 ───────────────────
def _uc_groups(spec):
    """UC 문서순 → {uc_id: [process,...]}. process는 usecase_ids[0]을 1차 UC로 그룹(중복 회피)."""
    uc_by_id = {u["id"]: u for u in spec.get("usecases", [])}
    prs_by_uc = defaultdict(list)
    for pr in spec.get("processes", []):
        uids = pr.get("usecase_ids") or ([pr["usecase_id"]] if pr.get("usecase_id") else [])
        prs_by_uc[uids[0] if uids else None].append(pr)
    uc_order = [u["id"] for u in spec.get("usecases", [])]
    # spec UC 순서에 없는(=None 등) 그룹도 뒤에 붙임
    for k in prs_by_uc:
        if k not in uc_order:
            uc_order.append(k)
    return uc_order, prs_by_uc, uc_by_id


def _fn_by_pr(spec):
    by = defaultdict(list)
    for fn in spec.get("functions", []):
        by[fn.get("process_id")].append(fn)
    return by


def _pis_by_pg(spec):
    by = defaultdict(list)
    for pi in spec.get("policy_details", []):
        gid = pi.get("group_id") or pi.get("policy_id")
        if gid:
            by[gid].append(pi)
    return by


def _table(cls, headers, rows, widths=None):
    """rows: list of list[str](이미 HTML). headers: list[str]. widths: list[int|None] px(선택, 빌링 인라인 폭 정합)."""
    out = [f'<table class="{cls}">\n<thead><tr>']
    for i, h in enumerate(headers):
        w = widths[i] if (widths and i < len(widths)) else None
        st = f' style="width: {w}px;"' if w else ""
        out.append(f"<th{st}>{_e(h)}</th>")
    out.append("</tr></thead>\n<tbody>")
    for r in rows:
        out.append("<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>")
    out.append("</tbody>\n</table>\n")
    return "".join(out)


# ─────────────────── 섹션 렌더러 ───────────────────
def _doc_title(m):
    """h1·title용 '{모듈명} 정책서' (이미 '정책서'로 끝나면 그대로). 빌링 h1 관례 정합."""
    t = (m or {}).get("title", "정책서")
    return t if t.rstrip().endswith("정책서") else f"{t} 정책서"


def render_header(spec):
    m = spec.get("meta", {})
    biz = m.get("business_code", "")
    rows = [
        f'<tr><th>정책서 ID</th><td class="mono">POL-{_e(biz)}</td></tr>',
        f'<tr><th>문서 구분</th><td>{_e(m.get("document_type", "간소화 버전"))}</td></tr>',
    ]
    if m.get("document_status"):
        rows.append(f'<tr><th>문서 상태</th><td>{_e(m.get("document_status"))}</td></tr>')
    rows.append(f'<tr><th>버전</th><td class="mono">{_e(m.get("version", ""))}</td></tr>')
    if m.get("author"):
        rows.append(f'<tr><th>작성자</th><td>{_e(m.get("author"))}</td></tr>')
    rows.append(f'<tr><th>작성일</th><td>{_e(m.get("date", ""))}</td></tr>')
    if m.get("basis"):
        rows.append(f'<tr><th>작성 기준</th><td>{_e(m.get("basis"))}</td></tr>')
    return (f'<div class="eyebrow">통합채널 정책서 간소화 버전</div>\n'
            f'<h1>{_e(_doc_title(m))}</h1>\n'
            f'<table class="meta">\n' + "\n".join(rows) + "\n</table>\n")


def render_history(spec):
    his = spec.get("history", []) or []
    out = ["<h2>0. 문서 히스토리</h2>\n"]
    if his:
        rows = [[f'<span class="mono">{_e(h.get("version", ""))}</span>', _e(h.get("change", "")),
                 _e(h.get("date", "")), _e(h.get("author", ""))] for h in his]
        out.append(_table("history-table", ["버전", "변경 내용", "변경일자", "변경자"], rows, [90, None, 120, 180]))
    return "".join(out)


def render_overview(spec):
    o = spec.get("overview", {}) or {}
    parts = ["<h2>1. 개요</h2>\n<h3>가. 범위</h3>\n"]
    for s in (o.get("scope") or []):
        parts.append(f'<p class="plain-text">• {_e(s)}<br/></p>')
    parts.append("\n<h3>나. 설계 원칙</h3>\n")
    for p in (o.get("principles") or []):
        if isinstance(p, dict):
            parts.append(f'<p class="principle-text">• <b>{_e(p.get("name", ""))}</b>: {_e(p.get("description", ""))}<br/></p>')
        else:
            parts.append(f'<p class="principle-text">• {_e(p)}<br/></p>')
    parts.append("\n")
    return "".join(parts)


def render_terms(spec):
    rows = [[f'<span class="mono">{_e(t.get("id"))}</span>', _e(t.get("name")),
             _multiline(t.get("description"))] for t in spec.get("terms", [])]
    return "<h2>2. 주요 용어</h2>\n" + _table("term-list-table", ["용어 ID", "용어", "설명"], rows, [130, 220, None])


# ─────────────────── 다이어그램(mermaid) 헬퍼 ───────────────────
def _mm_id(s):
    """ID/이름 → mermaid 노드 id (ASCII 영숫자·_ 만)."""
    nid = "".join(ch if (ch.isalnum() and ord(ch) < 128) else "_" for ch in str(s)).strip("_")
    return nid or "n"


def _mm_label(s):
    """mermaid 라벨 안전화: mermaid·HTML 특수문자를 평이하게 치환(다이어그램 라벨용, 표는 원문 유지)."""
    s = str(s or "")
    for a, b in [('"', "'"), ("<", "("), (">", ")"), ("&", "+"),
                 ("[", "("), ("]", ")"), ("{", "("), ("}", ")"), ("|", "/"),
                 ("\n", " "), ("\r", " ")]:
        s = s.replace(a, b)
    return s.strip()


def _strip_unit_prefix(name, title):
    """다이어그램 가독성: 유즈케이스명에서 모듈명 접두 제거(표는 원문 유지)."""
    name = str(name or "")
    for pre in ((title + " ") if title else "", "고객센터 통합허브 "):
        if pre and name.startswith(pre):
            return name[len(pre):]
    return name


def _usecase_diagram(spec):
    """다. 유즈케이스 다이어그램 — mermaid graph(액터↔유즈케이스) + HTML 폴백."""
    actors = spec.get("actors", []) or []
    ucs = spec.get("usecases", []) or []
    if not actors or not ucs:
        return ""
    title = (spec.get("meta") or {}).get("title", "")
    name_to_actor = {a.get("name"): a for a in actors}
    lines = ["graph LR",
             "  classDef actorCls fill:#fff7ed,stroke:#fb923c,stroke-width:1.5px,color:#7c2d12;",
             "  classDef ucCls fill:#eff6ff,stroke:#60a5fa,stroke-width:1.3px,color:#1e3a8a;"]
    for a in actors:
        lines.append(f'  {_mm_id(a.get("id"))}["{_mm_label(a.get("name"))}"]:::actorCls')
    lines.append(f'  subgraph SYS["{_mm_label(title) or "업무 시스템"}"]')
    lines.append("    direction TB")
    for u in ucs:
        lines.append(f'    {_mm_id(u.get("id"))}(["{_mm_label(_strip_unit_prefix(u.get("name"), title))}"]):::ucCls')
    lines.append("  end")
    for u in ucs:
        a = name_to_actor.get(u.get("actor"))
        if a:
            lines.append(f'  {_mm_id(a.get("id"))} --- {_mm_id(u.get("id"))}')
    mm = "\n".join(lines)
    by_actor = defaultdict(list)
    for u in ucs:
        by_actor[u.get("actor")].append(u)
    fb = ['<div class="diagram-fallback-html"><strong>액터 ↔ 유즈케이스</strong><ul>']
    for a in actors:
        items = by_actor.get(a.get("name"), [])
        ul = ", ".join(f'{_e(u.get("name"))} (<span class="mono">{_e(u.get("id"))}</span>)' for u in items) or "—"
        fb.append(f'<li><b>{_e(a.get("name"))}</b> (<span class="mono">{_e(a.get("id"))}</span>): {ul}</li>')
    fb.append("</ul></div>")
    return ('<p class="plain-text">액터, 시스템 경계, 유즈케이스, 연결 관계를 개념적으로 표현한다. '
            '다이어그램이 보이지 않으면 아래 목록으로 확인한다.<br/></p>\n'
            f'<div class="diagram-wrap mermaid-diagram uml-usecase-diagram"><pre class="mermaid-src">{mm}</pre></div>\n'
            + "".join(fb) + "\n")


def _state_diagram(spec):
    """3) 상태 전이 다이어그램 — mermaid flowchart(graph LR)로 상태 전이 표현 + HTML 폴백.
    stateDiagram-v2는 mermaid 10.9 빌드에서 렌더 실패 → 검증된 flowchart 엔진으로 동등 표현."""
    sts = spec.get("states", []) or []
    trans = spec.get("state_transitions", []) or []
    if not trans:
        return ""
    seen = [s.get("name") for s in sts]
    for t in trans:
        for k in ("current_state", "next_state"):
            v = t.get(k)
            if v and v not in seen:
                seen.append(v)
    sid = {name: f"S{i + 1}" for i, name in enumerate(seen)}
    lines = ["graph LR",
             "  classDef stCls fill:#eff6ff,stroke:#60a5fa,stroke-width:1.3px,color:#1d4ed8;",
             "  classDef endCls fill:#f1f5f9,stroke:#94a3b8,stroke-width:1.3px,color:#334155;",
             '  START(("시작")):::endCls',
             '  DONE(("종료")):::endCls']
    for name in seen:
        lines.append(f'  {sid[name]}["{_mm_label(name)}"]:::stCls')
    if seen:
        lines.append(f'  START --> {sid[seen[0]]}')
    outset, edges = set(), set()
    for t in trans:
        cs, ns, ev = t.get("current_state"), t.get("next_state"), t.get("event")
        if not cs or not ns or (cs, ns, ev) in edges:
            continue
        edges.add((cs, ns, ev))
        outset.add(cs)
        ev_lbl = _mm_label(ev)
        lines.append(f'  {sid[cs]} -->|{ev_lbl}| {sid[ns]}' if ev_lbl else f'  {sid[cs]} --> {sid[ns]}')
    for name in seen:
        if name not in outset:
            lines.append(f'  {sid[name]} --> DONE')
    mm = "\n".join(lines)
    fb, seen2 = ['<div class="diagram-fallback-html"><strong>상태 전이</strong><ul>'], set()
    for t in trans:
        cs, ns, ev = t.get("current_state"), t.get("next_state"), t.get("event")
        if not cs or not ns or (cs, ns, ev) in seen2:
            continue
        seen2.add((cs, ns, ev))
        fb.append(f'<li>{_e(cs)} → {_e(ns)} <span class="mono">({_e(ev)})</span></li>')
    fb.append("</ul></div>")
    return ('<h4>3) 상태 전이 다이어그램</h4>\n'
            '<p class="plain-text">대표 상태와 전이 이벤트를 개념적으로 보여준다. 상세 판정 기준은 위 전이표를 따른다.<br/></p>\n'
            f'<div class="diagram-wrap state-transition-mermaid mermaid-diagram"><pre class="mermaid-src">{mm}</pre></div>\n'
            + "".join(fb) + "\n")


def _mermaid_assets():
    """mermaid CDN + 명시적 render() 주입 JS.
    mermaid.run()은 이 빌드에서 빈 SVG(16×16)를 내므로, .mermaid-src 소스를 읽어
    mermaid.render()로 SVG를 생성·주입한다(성공 시 .mermaid-rendered → 폴백 숨김,
    실패/CDN 차단 시 HTML 폴백 노출)."""
    return (
        '<script src="https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.min.js"></script>\n'
        '<script>\n(function () {\n'
        '  function isErr(svg) { return /aria-roledescription="error"|Syntax error/i.test(svg || ""); }\n'
        '  function init() {\n'
        '    if (!window.mermaid) return;\n'
        '    try { window.mermaid.initialize({ startOnLoad: false, securityLevel: "loose", theme: "default", flowchart: { htmlLabels: true, curve: "basis" } }); } catch (e) { return; }\n'
        '    document.querySelectorAll(".diagram-wrap.mermaid-diagram .mermaid-src").forEach(function (src, i) {\n'
        '      var wrap = src.closest(".diagram-wrap.mermaid-diagram");\n'
        '      var code = (src.textContent || "").trim();\n'
        '      if (!wrap || !code) return;\n'
        '      try {\n'
        '        Promise.resolve(window.mermaid.render("mmd_render_" + i, code)).then(function (res) {\n'
        '          if (res && res.svg && !isErr(res.svg)) { wrap.innerHTML = res.svg; wrap.classList.add("mermaid-rendered"); }\n'
        '        }).catch(function () {});\n'
        '      } catch (e) {}\n'
        '    });\n  }\n'
        '  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);\n'
        '  else init();\n})();\n</script>\n'
    )


def render_usecases_section(spec):
    out = ["<h2>3. 유즈케이스 정의</h2>\n<h3>가. 액터</h3>\n"]
    arows = [[f'<span class="mono">{_e(a.get("id"))}</span>', _e(a.get("name")), _e(a.get("description"))]
             for a in spec.get("actors", [])]
    out.append(_table("actor-list-table", ["액터 ID", "액터명", "설명"], arows))
    out.append("<h3>나. 유즈케이스</h3>\n")
    urows = [[f'<span class="mono">{_e(u.get("id"))}</span>', _e(u.get("actor")), _e(u.get("name")),
              _e(u.get("description")), f'<span class="center">{_e(u.get("process_target"))}</span>']
             for u in spec.get("usecases", [])]
    out.append(_table("usecase-list-table", ["유즈케이스 ID", "액터", "유즈케이스명", "설명", "프로세스화"], urows))
    ucd = _usecase_diagram(spec)
    if ucd:
        out.append("<h3>다. 유즈케이스 다이어그램</h3>\n")
        out.append(ucd)
    sts = spec.get("states", []) or []
    strans = spec.get("state_transitions", []) or []
    if sts or strans:
        out.append("<h3>라. 상태 전이표</h3>\n")
        if sts:
            out.append("<h4>1) 상태 코드</h4>\n")
            srows = [[f'<span class="mono">{_e(s.get("id"))}</span>', _e(s.get("name")),
                      _e(s.get("description")), _e(s.get("next_action"))] for s in sts]
            out.append(_table("state-code-table", ["상태 코드", "상태명", "정의", "대표 후속 처리"], srows))
        if strans:
            out.append("<h4>2) 상태 전이 기준</h4>\n")
            trows = [["<br>".join(_e(x) for x in (t.get("usecase_ids") or [])), _e(t.get("current_state")),
                      _e(t.get("event")), _e(t.get("next_state")), _e(t.get("criteria"))] for t in strans]
            out.append(_table("state-transition-table",
                              ["유즈케이스", "현재 상태", "전이 이벤트", "다음 상태", "처리 기준"], trows))
        out.append(_state_diagram(spec))
    return "".join(out)


def render_processes(spec):
    uc_order, prs_by_uc, uc_by_id = _uc_groups(spec)
    fn_by_pr = _fn_by_pr(spec)
    pg_by_id = {pg["id"]: pg for pg in spec.get("policy_groups", [])}
    out = ["<h2>4. 프로세스 정의</h2>\n<h3>가. 프로세스 목록</h3>\n",
           '<p class="plain-text">프로세스는 고객 또는 운영자가 경험하는 순서대로 작성한다.<br/></p>\n']
    idx = 0
    for uid in uc_order:
        prs = prs_by_uc.get(uid) or []
        if not prs:
            continue
        idx += 1
        uc = uc_by_id.get(uid, {})
        out.append(f'<h4>{idx}) {_e(uc.get("name", uid))} (<span class="mono">{_e(uid)}</span>)</h4>\n')
        rows = []
        for pr in prs:
            fns = fn_by_pr.get(pr["id"], [])
            fns_html = "<br>".join(f'{_e(f["name"])} (<span class="mono">{_e(f["id"])}</span>)' for f in fns) or "—"
            pgs = [p for p in (pr.get("related_policies") or []) if "(CROSS" not in (p or "")]
            pgs_html = "<br>".join(
                f'{_e((pg_by_id.get(p) or {}).get("name", ""))} (<span class="mono">{_e(p)}</span>)' for p in pgs) or "—"
            rows.append([f'<span class="mono">{_e(pr["id"])}</span>', _e(pr.get("name")),
                         _e(pr.get("description")), fns_html, pgs_html])
        out.append(_table("process-list-table", ["프로세스 ID", "프로세스명", "설명", "관련 기능", "관련 정책"], rows,
                          [150, 170, None, 230, 260]))
    return "".join(out)


def render_functions(spec):
    uc_order, prs_by_uc, _ = _uc_groups(spec)
    fn_by_pr = _fn_by_pr(spec)
    fd_by_id = {fd["function_id"]: fd for fd in spec.get("function_details", [])}
    pi_by_id = {pi["id"]: pi for pi in spec.get("policy_details", [])}
    out = ["<h2>5. 기능 정의</h2>\n<h3>가. 기능 목록</h3>\n",
           '<p class="plain-text">기능은 프로세스를 수행하기 위한 처리 단위로 작성한다.<br/></p>\n']
    idx = 0
    for uid in uc_order:
        for pr in prs_by_uc.get(uid) or []:
            fns = fn_by_pr.get(pr["id"], [])
            if not fns:
                continue
            idx += 1
            out.append(f'<h4>{idx}) {_e(pr["name"])} (<span class="mono">{_e(pr["id"])}</span>)</h4>\n')
            rows = []
            for fn in fns:
                fd = fd_by_id.get(fn["id"], {})
                subs = fd.get("sub_functions") or []
                subfn_pis = fd.get("subfn_pis") or []
                subfn_ui = fd.get("subfn_ui") or []
                sub_lines = []
                for i, s in enumerate(subs):
                    pis_i = subfn_pis[i] if i < len(subfn_pis) else []
                    ui_i = subfn_ui[i] if i < len(subfn_ui) else False
                    if pis_i:
                        tag = '<span class="mono">(' + ", ".join(_e(p) for p in pis_i) + ')</span>'
                        sub_lines.append(f"{_e(s)} {tag}")
                    elif ui_i:
                        sub_lines.append(f'{_e(s)} <span class="mono">(UI·정책 없음)</span>')
                    else:
                        sub_lines.append(_e(s))
                pis = fd.get("related_policy_details") or fn.get("related_policy_details") or []
                pis_html = "<br>".join(
                    f'{_e((pi_by_id.get(p) or {}).get("name", "").split(" (")[0])} (<span class="mono">{_e(p)}</span>)'
                    for p in pis if p in pi_by_id) or "—"
                rows.append([f'<span class="mono">{_e(fn["id"])}</span>', _e(fn.get("name")),
                             _multiline(fn.get("description")), "<br>".join(sub_lines) or "—", pis_html])
            out.append(_table("function-list-table",
                              ["기능 ID", "기능명", "설명", "세부 기능 구성 (적용 정책 상세)", "관련 정책 상세"], rows,
                              [130, 150, None, 300, 200]))
    return "".join(out)


def render_policy_list(spec):
    uc_order, prs_by_uc, _ = _uc_groups(spec)
    pg_by_id = {pg["id"]: pg for pg in spec.get("policy_groups", [])}
    pis_by_pg = _pis_by_pg(spec)
    out = ["<h2>6. 정책 정의</h2>\n<h3>가. 정책 목록</h3>\n",
           '<p class="plain-text">정책은 기능 동작 기준이다. 인증·횟수·유효시간·권한·제한·고지·저장·예외·운영 판단 항목을 정책으로 분리한다.<br/></p>\n']
    idx = 0
    for uid in uc_order:
        for pr in prs_by_uc.get(uid) or []:
            pgs = [pg_by_id[p] for p in (pr.get("related_policies") or [])
                   if "(CROSS" not in (p or "") and p in pg_by_id]
            if not pgs:
                continue
            idx += 1
            out.append(f'<h4>{idx}) {_e(pr["name"])} (<span class="mono">{_e(pr["id"])}</span>)</h4>\n')
            rows = []
            for pg in pgs:
                items = "<br>".join(_e(pi.get("name", "")) for pi in pis_by_pg.get(pg["id"], [])) or "—"
                rows.append([f'<span class="mono">{_e(pg["id"])}</span>', _e(pg.get("name")),
                             _e(pg.get("description")), items])
            out.append(_table("policy-list-table", ["정책 ID", "정책명", "설명", "정책 상세"], rows, [150, 190, None, 260]))
    return "".join(out)


def render_policy_details(spec):
    """6.나 정책 상세 — billing .policy-item 포맷. field_review 붉음 / internal_integration 앰버."""
    pis_by_pg = _pis_by_pg(spec)
    fn_by_id = {f["id"]: f for f in spec.get("functions", [])}
    fd_by_id = {fd["function_id"]: fd for fd in spec.get("function_details", [])}
    parts = ["<h3>나. 정책 상세</h3>\n"]
    idx = 0
    for pg in spec.get("policy_groups", []):
        pis = pis_by_pg.get(pg["id"], [])
        if not pis:
            continue
        idx += 1
        parts.append(f'<h4>{idx}) {_e(pg["name"])} 정책 (<span class="mono">{_e(pg["id"])}</span>)</h4>\n')
        parts.append('<div class="policy-group">\n')
        for pi in pis:
            parts.append('<div class="policy-item">\n')
            disp = pi.get("name", "").split(" (PI-")[0].rstrip()
            fr = pi.get("field_review")
            iin = pi.get("internal_integration")
            flag = ' <span class="policy-review-flag">BSS/현업 검토 필요</span>' if fr else ""
            iflag = ' <span class="policy-integration-flag">내부 통합 필요</span>' if iin else ""
            parts.append(f'<div class="policy-item-title">• {_e(disp)} '
                         f'<span class="mono">({_e(pi["id"])})</span>{flag}{iflag}</div>\n')
            parts.append('<div class="policy-item-content">')
            rs = pi.get("rule_statement") or ""
            content = pi.get("content") or ""
            if rs:
                parts.append(f'<div class="policy-stmt">{_e(rs)}</div>')
            if content and content != rs:
                parts.append(f'<div class="policy-stmt">{_e(content)}</div>')
            for tbl in (pi.get("detail_tables") or []):
                if not (isinstance(tbl, dict) and tbl.get("headers") and tbl.get("rows")):
                    continue
                cap = tbl.get("caption")
                if cap and str(cap).strip():
                    parts.append(f'<div class="pdt-caption">{_e(cap)}</div>')
                parts.append('<table class="policy-detail-table"><thead><tr>')
                parts += [f"<th>{_e(h)}</th>" for h in tbl["headers"]]
                parts.append("</tr></thead><tbody>")
                for row in tbl["rows"]:
                    parts.append("<tr>" + "".join(f"<td>{_e(c)}</td>" for c in row) + "</tr>")
                parts.append("</tbody></table>")
                note = tbl.get("note")
                if note and str(note).strip():
                    parts.append(f'<div class="pdt-note">{_e(note)}</div>')
            cv = pi.get("criteria_values") or pi.get("criteria")
            if cv and isinstance(cv, list) and not pi.get("detail_tables"):
                items = [c for c in cv if str(c).strip()]
                if items:
                    parts.append('<ul class="policy-criteria">' + "".join(f"<li>{_e(c)}</li>" for c in items) + "</ul>")
            cn = pi.get("customer_notice") or pi.get("notice") or ""
            if cn and isinstance(cn, str) and cn.strip():
                parts.append(f'<div class="policy-notice"><b>💬 고객 안내</b>{_e(cn)}</div>')
            meta = []
            sn = pi.get("source_note") or ""
            # C: 내부 복원 마커(recovered_from_html:owning_block_pass[:crosswalk])는
            #    verify_recovery용 기계 표식이므로 화면 '근거'엔 사람 친화 문구로 표시.
            if sn.strip().startswith("recovered_from_html"):
                sn = "HTML 정책서 본문에서 복원"
            if sn.strip():
                meta.append(f'<span class="policy-meta-row"><span class="pm-label">근거</span> · {_e(sn)}</span>')
            ref_items = []
            for ref in (pi.get("applies_to") or []):
                fid, _, k = ref.partition("#")
                fn = fn_by_id.get(fid)
                if not fn:
                    continue
                subs = (fd_by_id.get(fid) or {}).get("sub_functions") or []
                try:
                    stext = subs[int(k) - 1]
                except (ValueError, IndexError):
                    stext = ""
                ref_items.append(f'{fn.get("name", "")} › {stext}' if stext else fn.get("name", ""))
            if ref_items:
                meta.append(f'<span class="policy-meta-row"><span class="pm-label">관련 기능</span> · '
                            + " / ".join(_e(it) for it in ref_items) + "</span>")
            if fr:
                meta.append(f'<span class="policy-meta-row policy-review-note">[BSS/현업 검토 필요] {_e(fr)}</span>')
            if iin:
                meta.append(f'<span class="policy-meta-row policy-integration-note">[내부 통합 필요] {_e(iin)}</span>')
            if meta:
                parts.append('<div class="policy-meta">' + "".join(meta) + "</div>")
            parts.append("</div>\n</div>\n")
        parts.append("</div>\n")
    return "".join(parts)


def render_final_check(spec):
    fc = spec.get("final_check", []) or []
    if not fc:
        return ""
    out = ['<h2>최종 점검 기준</h2>\n<div class="guide">\n',
           f'<div class="guide-title">{_e(_doc_title(spec.get("meta") or {}))} 제출 전 점검</div>\n<ul>']
    for c in fc:
        out.append(f"<li>{_e(c if isinstance(c, str) else c.get('text', c))}</li>")
    out.append("</ul>\n</div>\n")
    return "".join(out)


def main(argv):
    args = [a for a in argv[1:] if not a.startswith("--")]
    config_path, out_path, unit = DEFAULT_CONFIG, None, None
    for a in argv[1:]:
        if a.startswith("--config="):
            config_path = a.split("=", 1)[1].strip()
        elif a.startswith("--out="):
            out_path = a.split("=", 1)[1].strip()
        elif a.startswith("--unit="):
            unit = a.split("=", 1)[1].strip()
    cfg = overlay_unit(load_config(config_path), unit)
    spec_path = args[0] if args else cfg.get("spec_path")
    if not spec_path:
        print("ERROR: spec 경로 지정 또는 config.spec_path/--unit 필요.", file=sys.stderr)
        return 2
    out_path = out_path or cfg.get("preview_out") or "/tmp/policy_preview.html"
    spec = json.load(open(spec_path, encoding="utf-8"))

    m = spec.get("meta") or {}
    doctitle = " ".join(x for x in [_doc_title(m), m.get("document_type", "간소화 버전"), m.get("version", "")] if x).strip()
    body = "".join([
        render_header(spec), render_history(spec), render_overview(spec), render_terms(spec),
        render_usecases_section(spec), render_processes(spec), render_functions(spec),
        render_policy_list(spec), render_policy_details(spec), render_final_check(spec),
    ])
    html = (f'<!DOCTYPE html>\n<html lang="ko">\n<head>\n<meta charset="utf-8"/>\n'
            f'<meta content="width=device-width, initial-scale=1" name="viewport"/>\n'
            f"<title>{_e(doctitle)}</title>\n{load_css()}\n</head>\n<body>\n"
            f'<div class="page">\n{body}\n</div>\n{_mermaid_assets()}</body>\n</html>\n')

    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write(html)
    n_pi = len(spec.get("policy_details", []))
    n_flag = sum(1 for pi in spec.get("policy_details", []) if pi.get("field_review"))
    n_amber = sum(1 for pi in spec.get("policy_details", []) if pi.get("internal_integration"))
    n_tbl = sum(len(pi.get("detail_tables") or []) for pi in spec.get("policy_details", []))
    print(f"  [render] {out_path}  (PG {len(spec.get('policy_groups', []))}·PI {n_pi}·표 {n_tbl}·"
          f"현업검토 {n_flag}·내부통합 {n_amber})")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
