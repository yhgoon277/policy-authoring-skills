#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""NC스튜디오 변환 HTML에 로컬 리치 렌더 섹션을 이식(splice) — 빌링 splice_preview.py 패턴 이식.

배경: NC스튜디오 변환기는 정책 상세를 평면 텍스트로만 렌더한다(표·현업검토 배지·💬 고객 안내
불가). 빌링의 최종 HTML(v1.1.119)은 NC 변환본에 자체 렌더 섹션을 이식한 가공본이며, 본 도구가
같은 흐름을 hub에 제공한다. 렌더 단일원천 = render_preview.py 산출 preview(섹션 donor) —
렌더 로직을 중복 구현하지 않는다.

동작:
  1) preview <style>에서 리치 클래스(policy-*·pdt-* 등) CSS 규칙을 발췌해 base 마지막
     </style> 앞에 마커 블록으로 주입(멱등 — 재실행 시 교체).
  2) --sections(기본 5,6)의 <h2>N. …</h2> ~ 다음 <h2> 범위를 preview 동일 섹션으로 교체.
     (4장 프로세스 정의는 NC 자체 렌더가 케이스 분기·다이어그램 포함으로 더 풍부 → 기본 보존.)
  3) samples/deliverable/<base 파일명>_spliced.html 로 저장 + 리치 클래스 카운트 보고.

사용:
  python3 tools/splice_nc_html.py --unit=hub --base="~/Downloads/NC_..._v0.14.html"
  python3 tools/splice_nc_html.py --unit=hub --base=... --sections=4,5,6 --out=...
"""
from __future__ import annotations

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from build_spec import load_config, overlay_unit  # noqa: E402

CSS_MARK_BEGIN = "/* == splice_nc_html: 리치 렌더 CSS (자동 주입) == */"
CSS_MARK_END = "/* == /splice_nc_html == */"

# preview CSS에서 발췌할 셀렉터 토큰 — 정책 상세 콜아웃·표 서식(빌링 정합 클래스)
CSS_TOKENS = (
    "policy-stmt", "policy-criteria", "policy-detail-table", "pdt-caption", "pdt-note",
    "policy-notice", "policy-meta", "pm-label", "policy-review-flag", "policy-review-note",
    "policy-group", "policy-item", "policy-list-table",
    "function-list-table", "extended-function-list-table", "field-review", "internal-integration",
)


def extract_rich_css(preview_html: str) -> str:
    m = re.search(r"<style[^>]*>(.*?)</style>", preview_html, re.S)
    if not m:
        raise SystemExit("preview에 <style> 블록이 없음")
    css = m.group(1)
    rules = []
    for rule in css.split("}"):
        if "{" not in rule:
            continue
        selector = rule.split("{", 1)[0]
        if any(tok in selector for tok in CSS_TOKENS):
            rules.append(rule.strip() + " }")
    if not rules:
        raise SystemExit("preview CSS에서 리치 클래스 규칙을 찾지 못함")
    return "\n".join(rules)


def inject_css(base_html: str, css_block: str) -> tuple[str, str]:
    """</body> 직전 독립 <style> 블록으로 주입 — NC가 body 안에도 style을 두므로
    문서 최후순위에 둬야 cascade에서 확실히 이기고, 0~4장 등 비교체 영역이 byte 보존된다."""
    block = f"<style>\n{CSS_MARK_BEGIN}\n{css_block}\n{CSS_MARK_END}\n</style>\n"
    if CSS_MARK_BEGIN in base_html:  # 멱등: 기존 블록 교체
        pat = re.compile(r"<style>\s*" + re.escape(CSS_MARK_BEGIN) + r".*?" +
                         re.escape(CSS_MARK_END) + r"\s*</style>\n?", re.S)
        return pat.sub(block, base_html), "교체"
    idx = base_html.rfind("</body>")
    if idx < 0:
        raise SystemExit("base에 </body> 없음")
    return base_html[:idx] + block + base_html[idx:], "신규"


def section_span(html: str, num: int) -> tuple[int, int]:
    """<h2 ...>N. ...</h2> 시작 ~ 다음 <h2 ...> 직전. h2의 속성(id= 등)을 허용한다
    (NC 변환본은 <h2 id="6.-정책-정의">처럼 헤딩에 id 속성을 붙이기도 한다)."""
    m = re.search(rf"<h2[^>]*>\s*{num}\.", html)
    if not m:
        raise SystemExit(f"섹션 {num} <h2> 마커 없음")
    start = m.start()
    nxt = re.search(r"<h2[^>]*>", html[m.end():])
    end = m.end() + nxt.start() if nxt else len(html)
    return start, end


def splice_sections(base_html: str, preview_html: str, sections: list[int]) -> str:
    # 뒤 섹션부터 교체(앞 인덱스 보존)
    for num in sorted(sections, reverse=True):
        bs, be = section_span(base_html, num)
        ps, pe = section_span(preview_html, num)
        base_html = base_html[:bs] + preview_html[ps:pe] + base_html[be:]
    return base_html


def main(argv) -> int:
    config_path, unit = "policy_config.json", None
    base_path, out_path, sections = None, None, [5, 6]
    for a in argv[1:]:
        if a.startswith("--config="):
            config_path = a.split("=", 1)[1]
        elif a.startswith("--unit="):
            unit = a.split("=", 1)[1]
        elif a.startswith("--base="):
            base_path = os.path.expanduser(a.split("=", 1)[1])
        elif a.startswith("--out="):
            out_path = os.path.expanduser(a.split("=", 1)[1])
        elif a.startswith("--sections="):
            sections = [int(x) for x in a.split("=", 1)[1].split(",") if x.strip()]
    cfg = overlay_unit(load_config(config_path), unit)
    preview_path = cfg.get("preview_out")
    if not base_path or not os.path.isfile(base_path):
        print("ERROR: --base=<NC 변환 HTML 경로> 필요", file=sys.stderr)
        return 2
    if not preview_path or not os.path.isfile(preview_path):
        print("ERROR: preview 없음 — 먼저 render_preview.py 실행", file=sys.stderr)
        return 2

    base = open(base_path, encoding="utf-8").read()
    preview = open(preview_path, encoding="utf-8").read()

    base, css_mode = inject_css(base, extract_rich_css(preview))
    base = splice_sections(base, preview, sections)

    if not out_path:
        stem = os.path.splitext(os.path.basename(base_path))[0]
        out_path = os.path.join("samples", "deliverable", f"{stem}_spliced.html")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    open(out_path, "w", encoding="utf-8").write(base)

    counts = {c: len(re.findall(rf'class="[^"]*\b{c}\b', base))
              for c in ("policy-stmt", "policy-detail-table", "policy-review-flag", "policy-notice")}
    print(f"  [splice] 섹션 {sections} 교체 · CSS {css_mode} 주입")
    print(f"  [splice] 리치 클래스: {counts} · 💬 {base.count('💬')}")
    print(f"  [write] {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
