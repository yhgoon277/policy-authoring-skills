#!/usr/bin/env python3
"""NC 정책서 HTML에서 PG→PI(정책 항목 상세) 매핑을 복원하는 공유 파서.

기획자가 작성한 HTML이 그룹↔상세 연결의 진실원천이다. ncstudio json 변환이
이 연결을 잃어버려도(빈 items·빈 policy_id), HTML의 `정책 상세` 섹션 PG별
`정책 항목 상세` 필드에는 각 PG에 속한 PI들이 그대로 남아있다.

네 가지 마크업 변형을 모두 처리한다:
  ① <h4 id="PG-..."> 구획 + policy-item/pi-title 앵커 id="PI-..."   (결제)
  ② '정책 ID' 표행 구획 + policy-item 앵커                          (나의가입정보)
  ③ <h4 id="PG"> + draft-list <li> 텍스트형 (PI-...)               (주문계약)
  ④ <h4 id="pg-PG-..."> 구획 + div.policy-item / .policy-item-title (AI검색 v0.5x)
     ※ PI id는 title 내 정본 (PI-...) 링크에서 추출 — div의 id="pi-..." 속성은
       후속 ID 정정이 미반영돼 드리프트할 수 있어 신뢰하지 않는다.

PG 귀속은 마커('정책 항목 상세') 직전의 *정의 컨텍스트*(<hN id=PG> 또는 '정책 ID' 행)로
결정한다 — 본문 곳곳의 교차참조 href="#PG-..."는 구획 시작이 아니므로 무시한다.
PG 헤딩 id는 bare(PG-...) 또는 접두(pg-PG-...) 둘 다 인식한다.

반환: OrderedDict  PG_id -> [ {id, name, body}, ... ]  (PG 내 PI 순서·중복제거 보존)
PI가 전혀 없는 모듈(AI검색·통합알림: prose 렌더)은 빈 매핑 → 트랙 B 신호.
"""
import re
from collections import OrderedDict

MARKER = "정책 항목 상세"
# PG 헤딩: id="PG-..." 또는 id="pg-PG-..."(접두) 모두 — 캡처는 정본 PG id
H_PG = re.compile(r'<h[1-6][^>]*\sid="(?:pg-)?(PG-[A-Z0-9\-]+)"')
ID_LABEL = re.compile(r'정책\s*ID')
PG_TOKEN = re.compile(r'(PG-[A-Z0-9\-]+)')
PI_ANCHOR = re.compile(r'id="(PI-[A-Z0-9\-]+)"')
PI_TEXT = re.compile(r'\((PI-[A-Z0-9\-]+)\)')
TAG = re.compile(r'<[^>]+>')

# 구조형 한 항목: pi-title(이름 + 앵커 id) … pi-body(ul) 까지
POLICY_ITEM = re.compile(
    r'class="pi-title">\s*[•\-\s]*(?P<name>.*?)\s*\(<a[^>]*id="(?P<id>PI-[A-Z0-9\-]+)"'
    r'(?P<rest>.*?)(?=class="pi-title">|</td>|$)',
    re.S)
# 텍스트형 한 항목: <li>이름 (PI-...)</li>
LI_ITEM = re.compile(r'<li[^>]*>\s*(?P<name>.*?)\s*\((?P<id>PI-[A-Z0-9\-]+)\)\s*</li>', re.S)
# 변형 ④ 한 항목: div.policy-item-title> • 이름 (<a ...>PI-...</a>) … (다음 항목/끝까지)
# PI id는 title 링크 *텍스트*(정본)에서 — div의 id="pi-..." 속성(드리프트)은 무시.
POLICY_ITEM5 = re.compile(
    r'class="policy-item-title">\s*[•\-\s]*(?P<name>.*?)\s*'
    r'\(<a[^>]*>\s*(?P<id>PI-[A-Z0-9\-]+)\s*</a>\)'
    r'(?P<rest>.*?)(?=class="policy-item-title">|</td>|$)',
    re.S)
# 변형 ⑥ 한 항목: <p|div class="pi-detail-title">• 이름 (PI-...) …  — id는 평문 (PI-...) 또는
#   <span class="mono">(PI-...)</span> 둘 다. 본문 = 다음 pi-detail-title 직전까지 전체
#   (pi-core-question·pi-detail-list·policy-detail-subtable). 서브표 내부 </td>는 경계로 쓰지 않는다.
POLICY_ITEM6 = re.compile(
    r'class="pi-detail-title">\s*[•\-\s]*(?P<name>.*?)\s*'
    r'(?:<span[^>]*>)?\s*\(\s*(?P<id>PI-[A-Z0-9\-]+)\s*\)'
    r'(?P<rest>.*?)(?=class="pi-detail-title">|$)',
    re.S)


def _text(s):
    return TAG.sub(" ", s or "").replace("&nbsp;", " ").strip()


def _pg_for(html, p):
    """마커 위치 p 직전의 가장 가까운 정의 컨텍스트에서 PG id 추출."""
    best_pos, best_pg = -1, None
    for m in H_PG.finditer(html, 0, p):
        if m.start() > best_pos:
            best_pos, best_pg = m.start(), m.group(1)
    for m in ID_LABEL.finditer(html, 0, p):
        seg = html[m.start():m.start() + 300]
        mm = PG_TOKEN.search(seg)
        if mm and m.start() > best_pos:
            best_pos, best_pg = m.start(), mm.group(1)
    return best_pg


def _region_end(html, p):
    """이 PG의 '정책 항목 상세' td 영역 끝(다음 마커/다음 PG 정의 중 가장 가까운 곳)."""
    cands = [len(html)]
    nm = html.find(MARKER, p + len(MARKER))
    if nm >= 0:
        cands.append(nm)
    m = H_PG.search(html, p + 1)
    if m:
        cands.append(m.start())
    m = ID_LABEL.search(html, p + len(MARKER))
    if m:
        cands.append(m.start())
    return min(cands)


def parse_pg_pi(html):
    """HTML 문자열 → OrderedDict PG -> [{id,name,body}]."""
    mapping = OrderedDict()
    for m in re.finditer(MARKER, html):
        p = m.start()
        pg = _pg_for(html, p)
        if not pg:
            continue
        region = html[p:_region_end(html, p)]
        bucket = mapping.setdefault(pg, [])
        have = {x["id"] for x in bucket}
        # 구조형 우선
        for im in POLICY_ITEM.finditer(region):
            pid = im.group("id")
            if pid in have:
                continue
            body = " ".join(_text(li) for li in re.findall(r'<li[^>]*>(.*?)</li>', im.group("rest"), re.S))
            bucket.append({"id": pid, "name": _text(im.group("name")), "body": body})
            have.add(pid)
        # 변형 ④ div.policy-item (정본 id = title 링크 텍스트)
        for im in POLICY_ITEM5.finditer(region):
            pid = im.group("id")
            if pid in have:
                continue
            body = " ".join(_text(li) for li in re.findall(r'<li[^>]*>(.*?)</li>', im.group("rest"), re.S))
            bucket.append({"id": pid, "name": _text(im.group("name")), "body": body})
            have.add(pid)
        # 변형 ⑥ pi-detail-block (정본 id = mono span, 본문 = 블록 전체 텍스트)
        for im in POLICY_ITEM6.finditer(region):
            pid = im.group("id")
            if pid in have:
                continue
            bucket.append({"id": pid, "name": _text(im.group("name")), "body": _text(im.group("rest"))})
            have.add(pid)
        # 텍스트형(draft-list)
        for im in LI_ITEM.finditer(region):
            pid = im.group("id")
            if pid in have:
                continue
            bucket.append({"id": pid, "name": _text(im.group("name")), "body": ""})
            have.add(pid)
        # 최후수단: 앵커/텍스트 id만이라도(이름 없이)
        if not bucket:
            ids = []
            for x in PI_ANCHOR.findall(region) + PI_TEXT.findall(region):
                if x not in have and x not in ids:
                    ids.append(x)
            for pid in ids:
                bucket.append({"id": pid, "name": "", "body": ""})
    return mapping


def parse_file(path):
    with open(path, encoding="utf-8") as f:
        return parse_pg_pi(f.read())


if __name__ == "__main__":
    import sys
    import json
    for path in sys.argv[1:]:
        m = parse_file(path)
        npi = sum(len(v) for v in m.values())
        print(f"{path}: PG {len(m)} / PI {npi}")
        print(json.dumps({k: [x["id"] for x in v] for k, v in list(m.items())[:3]},
                         ensure_ascii=False, indent=2))
