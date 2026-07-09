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

⑤ 견고 파서 폴백(dev_format_vendor): 위 마커/헤딩-id 기반 변형이 못 잡는 포맷
   — PG id가 헤딩 *텍스트*(<h4>… (PG-…)</h4>)에 있고 PI가 div.policy-item-title +
   <span class="mono">(PI-…)</span> 인 '간소화' 변형(전시·이벤트미션·나의데이터통화·
   청구및수납 등) — 은 dev_format_vendor.parse_html 로 PolicyDetailItem(pi_id·pg_id·
   name·content)을 받아 pg_id로 묶어 보강한다. 레거시가 더 적게 찾을 때만 교체하므로
   기존 포맷은 무영향(회귀 0). PI id가 아예 없는 prose 포맷(통합알림: 판단축 완결표)은
   양 파서 모두 빈 매핑 → 트랙 B 신호.

반환: OrderedDict  PG_id -> [ {id, name, body}, ... ]  (PG 내 PI 순서·중복제거 보존)
"""
import os
import re
import tempfile
from collections import OrderedDict
from pathlib import Path

MARKER = "정책 항목 상세"
# PG 헤딩: id="PG-..." 또는 id="pg-PG-..."(접두) 모두 — 캡처는 정본 PG id
H_PG = re.compile(r'<h[1-6][^>]*\sid="(?:pg-)?(PG-[A-Z0-9\-]+)"')
ID_LABEL = re.compile(r'정책\s*ID')
PG_TOKEN = re.compile(r'(PG-[A-Z0-9\-]+)')
PI_ANCHOR = re.compile(r'id="(PI-[A-Z0-9\-]+)"')
PI_TEXT = re.compile(r'\((PI-[A-Z0-9\-]+)\)')
TAG = re.compile(r'<[^>]+>')

# 변형 ⑦(data-속성): <a data-pi-id="PI-.." data-policy-id="PG-..">이름 (PI-..)</a> 가 PG 귀속을
# 명시하는 full-document 골든 렌더(주문계약 v0.45 등) — MARKER·헤딩-id 없이 이 속성으로 그룹핑.
A_TAG = re.compile(r'<a\b(?P<attrs>[^>]*)>(?P<txt>.*?)</a>', re.S)
DATA_PI = re.compile(r'\bdata-pi-id="(PI-[A-Z0-9\-]+)"')
DATA_PG = re.compile(r'\bdata-(?:parent-)?policy-id="(PG-[A-Z0-9\-]+)"')

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


def _devfmt_mapping(html):
    """dev_format_vendor 견고 파서로 PG->PI 매핑 복원(레거시 변형 미커버 포맷용).

    dev_format_vendor.parse_html 는 파일 경로를 받으므로 임시파일에 써서 호출한다.
    실패(미설치·파싱오류)하면 None(폴백 안 함)."""
    try:
        import dev_format_vendor
    except Exception:
        return None
    fd, tmp = tempfile.mkstemp(suffix=".html")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(html)
        res = dev_format_vendor.parse_html(Path(tmp))
    except Exception:
        return None
    finally:
        try:
            os.unlink(tmp)
        except OSError:
            pass
    items = res[1] if isinstance(res, tuple) else res
    mapping = OrderedDict()
    for it in items:
        pid = (getattr(it, "pi_id", "") or "").strip()
        if not pid:
            continue
        pg = (getattr(it, "pg_id", "") or "PG-UNKNOWN").strip() or "PG-UNKNOWN"
        bucket = mapping.setdefault(pg, [])
        if any(x["id"] == pid for x in bucket):
            continue
        bucket.append({"id": pid,
                       "name": (getattr(it, "name", "") or "").strip(),
                       "body": (getattr(it, "content", "") or "").strip()})
    return mapping


def _dataattr_mapping(html):
    """변형 ⑦: <a data-pi-id data-policy-id>이름 (PI-..)</a> 로 PG→PI 복원.

    각 PI를 그것을 처음 선언한 <a>(둘 다 보유)의 PG에 귀속시킨다. 속성이 없는 포맷은
    빈 매핑 → 상위 선택 로직에서 무영향(회귀 0)."""
    mapping = OrderedDict()
    seen = set()
    for m in A_TAG.finditer(html):
        a = m.group("attrs")
        pi, pg = DATA_PI.search(a), DATA_PG.search(a)
        if not (pi and pg) or pi.group(1) in seen:
            continue
        seen.add(pi.group(1))
        name = PI_TEXT.sub("", _text(m.group("txt"))).strip()  # '이름 (PI-..)'→'이름'
        mapping.setdefault(pg.group(1), []).append({"id": pi.group(1), "name": name, "body": ""})
    return mapping


def _real_pg(mapping):
    """PG-UNKNOWN 아닌 실 PG를 하나라도 잡았는가(그룹핑 성공 여부)."""
    return any(pg != "PG-UNKNOWN" for pg in (mapping or {}))


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
    # ⑤ 견고 파서 폴백: 레거시가 더 적게(또는 0) 찾았으면 dev_format_vendor 결과로 교체.
    #   dev ≥ legacy 가 검증돼 있어(추가분은 실존 PI) 회귀 없이 커버리지만 넓힌다.
    legacy_total = sum(len(v) for v in mapping.values())
    best = mapping
    dev_map = _devfmt_mapping(html)
    if dev_map is not None and sum(len(v) for v in dev_map.values()) > legacy_total:
        best = dev_map
    # ⑦ data-속성 변형: legacy·dev가 실 PG 그룹핑에 실패(전부 PG-UNKNOWN/빈맵)했을 때만,
    #    data-policy-id가 실 PG를 복원하면 채택. 실 PG를 이미 잡은 포맷은 무영향(회귀 0).
    if not _real_pg(best):
        data_map = _dataattr_mapping(html)
        if _real_pg(data_map):
            best = data_map
    return best


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
