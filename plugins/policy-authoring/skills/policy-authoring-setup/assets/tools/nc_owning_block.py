#!/usr/bin/env python3
"""Owning-block faithfulness — 복원된 PI content가 *자기 자신의 HTML 구획* 안에서
나온 텍스트인지 독립 검증한다(제로-날조 게이트).

dev_format 파서가 어떻게 content를 귀속시켰는지와 무관하게, 이 모듈은 HTML을
제목 앵커(pi-detail-title / policy-item-title / pi-title) 위치로 다시 슬라이스해서
각 PI가 "소유"하는 구획(자기 제목 → 다음 PI 제목 직전)을 만든다. 복원된 content의
정규화 텍스트가 그 구획 평문의 부분문자열이면 PASS(충실), 아니면 FAIL(날조/오귀속).

정규화: HTML 엔티티 unescape → 태그 제거 → 단어문자(\\w, 유니코드)만 남김.
  - 불릿('•','-'), 공백, 구두점, `&#x27;` 같은 엔티티 잔재를 제거해 dev_format의
    재포맷(리스트→문장 합치기)과 raw 평문 사이 표기 차이를 흡수한다.
  - 단어 시퀀스는 보존하므로, 다른 PI에서 새어 들어온 텍스트(오귀속)는 자기 구획에
    없어 부분문자열 검사를 통과하지 못한다 → 날조로 걸린다.

말렙드 네스팅(닫히지 않은 div로 형제 PI가 중첩, `( PI-… 0 06)`처럼 공백 끼인 id)도
제목 *위치*로만 슬라이스하므로 div 경계 붕괴에 영향받지 않는다. id의 내부 공백은
제거해 정규화한다.
"""
from __future__ import annotations

import html as _html
import re
from collections import OrderedDict

# 제목 앵커: title 클래스 직후 가장 가까운 (PI-…). a/span 래퍼·내부 공백 허용.
TITLE_ANCHOR = re.compile(
    r'class="(?:pi-detail-title|policy-item-title|pi-title)"[^>]*>'
    r'.*?\(\s*(?:<a[^>]*>\s*|<span[^>]*>\s*)?'
    r'(PI-[A-Z0-9\- ]+?)\s*(?:</a>|</span>)?\s*\)',
    re.S)
_TAG = re.compile(r'<[^>]+>')
_WORD = re.compile(r'\w', re.U)


def norm_pi_id(s: str) -> str:
    """PI id 내부 공백 제거('( PI-…-0 06)' → 'PI-…-006')."""
    return re.sub(r'\s+', '', s or '')


def plain(s: str) -> str:
    """HTML 조각 → 엔티티 unescape + 태그 제거 평문."""
    return _html.unescape(_TAG.sub(' ', s or ''))


def wordonly(s: str) -> str:
    """평문/콘텐츠 → 단어문자만(공백·구두점·불릿·엔티티잔재 제거)."""
    return ''.join(_WORD.findall(_html.unescape(s or '')))


def owning_segments(html: str) -> "OrderedDict[str, str]":
    """HTML → OrderedDict pi_id -> 소유 구획 평문(자기 제목 → 다음 제목 직전).

    같은 id가 여러 제목 앵커로 나오면 첫 정의를 채택한다(이후 교차참조 무시).
    """
    anchors = [(m.start(), norm_pi_id(m.group(1))) for m in TITLE_ANCHOR.finditer(html)]
    segs: "OrderedDict[str, str]" = OrderedDict()
    for i, (pos, pid) in enumerate(anchors):
        end = anchors[i + 1][0] if i + 1 < len(anchors) else len(html)
        if pid not in segs:
            segs[pid] = plain(html[pos:end])
    return segs


def is_faithful(content: str, segment_plain: str | None) -> bool:
    """복원 content의 단어시퀀스가 소유 구획 평문 안에 부분문자열로 존재하는가."""
    if segment_plain is None:
        return False
    cw = wordonly(content)
    if not cw:
        return False
    return cw in wordonly(segment_plain)
