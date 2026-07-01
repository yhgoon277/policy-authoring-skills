#!/usr/bin/env python3
"""domain_code_map — 정책서 도메인명→도메인코드 권위 매핑 (R5 도메인코드 현행화).

**SSOT는 옆의 `domain_codes.md`** (AI/사람이 직접 읽고 편집하는 권위표). 이 모듈은 그 표를
런타임에 파싱해 매핑을 구성한다. md 부재·파싱실패 시에만 아래 baked 폴백을 쓴다(무크래시).
코드의 '/'는 ID/SEG 정규식·CSS 선택자를 깨뜨리므로(검증: `PI-EVT/MSN-…` → SEG=None) ID·
business_code에는 '/' 제거형을 쓴다(EVT/MSN→EVTMSN).

조회:
  code_for_name(도메인명)      → 권위 코드('/' 제거형) 또는 ''
  code_for_current(현행코드)   → 권위 코드('/' 제거형) 또는 ''  (현행 business_code 식별)
  is_authoritative(코드)       → 이미 권위코드인가(bool)
  resolve_target(코드)         → 현행/권위 어느 쪽이든 권위코드로 해소, 미결이면 ''
  suggest_code(도메인명)       → 미등록 도메인의 코드 후보(휴리스틱; 사람 확정용)
  add_domain(name, code, ...)  → domain_codes.md에 한 행 추가(대화형 등록) 후 매핑 갱신
"""
import os
import re

# md 부재/파싱실패 시 폴백(=SSOT domain_codes.md와 동일 내용). 정상 경로는 md 로드.
_BAKED_AUTHORITATIVE = {
    "가이드라인/ 공통/ 품질/ 적응형": "UXP", "전시/관리 기능": "DSP", "상품 목록": "PRDL",
    "외부 BP 서비스 관리 체계": "BPS", "AI Agent": "AIA", "추천": "RCM", "데이터 트래킹 체계": "ANA",
    "이벤트/미션 프로그램": "EVTMSN", "외부 쿠폰": "CPN", "멤버십 혜택/T 플러스포인트": "BENTPNT",
    "상품상세/담기": "PRD", "카트/장바구니": "CART", "할인/시뮬레이션": "SIM", "주문/계약/가입": "JOIN",
    "선물주문": "GFT", "상품변경": "CHG", "결제": "PAY", "주문 상태/사후 관리": "ORH", "배송/재고": "DLV",
    "나의 가입 정보": "INFO", "회선 변경/관리": "MOD", "멤버십 카드 관리": "MBS", "청구 및 수납 관리": "BIL",
    "나의 데이터·통화": "DTC", "상품·서비스 혜택 이용/공유": "MYBEN", "통합 쿠폰/이용권함": "MYCPN",
    "회원 가입/탈퇴/인증": "MBR", "회원정보 조회/변경": "MBI", "통합 알림": "ALM", "통합 약관": "AGR",
    "설정": "SET", "고객센터_통합허브": "CSHUB", "고객센터_FAQ/공지/이용안내": "GUIDE",
    "고객센터_매장안내": "STORE",
}
_BAKED_CURRENT = {
    "AIS": "AI Agent", "PAY": "결제", "MYI": "나의 가입 정보", "DTC": "나의 데이터·통화",
    "PDD": "상품상세/담기", "PRD": "상품상세/담기", "EVT": "이벤트/미션 프로그램", "DSP": "전시/관리 기능",
    "ORD": "주문/계약/가입", "BIL": "청구 및 수납 관리", "ARZ": "통합 알림",
}

_SEP_RE = re.compile(r"^[-: ]*$")


def table_path():
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "domain_codes.md")


def _load_table(path=None):
    """domain_codes.md → (AUTHORITATIVE, CURRENT_CODE_TO_NAME). 실패 시 baked 폴백."""
    path = path or table_path()
    auth, cur = {}, {}
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                if not line.lstrip().startswith("|"):
                    continue
                cells = [c.strip() for c in line.strip().strip("|").split("|")]
                if len(cells) < 2:
                    continue
                name, code = cells[0], cells[1]
                if not name or name == "도메인명" or _SEP_RE.match(name):
                    continue
                if not code or _SEP_RE.match(code):
                    continue
                auth[name] = code
                alias = cells[2] if len(cells) > 2 else ""
                for a in (x.strip() for x in alias.split(",")):
                    if a:
                        cur[a] = name
    except OSError:
        pass
    if not auth:  # md 부재/파싱실패 → baked 폴백(무크래시)
        return dict(_BAKED_AUTHORITATIVE), dict(_BAKED_CURRENT)
    return auth, cur


AUTHORITATIVE, CURRENT_CODE_TO_NAME = _load_table()


def strip_slash(code):
    """ID·business_code용 정규화: '/' 제거(EVT/MSN→EVTMSN)."""
    return (code or "").replace("/", "")


def code_for_name(name):
    """도메인명 → 권위 코드('/' 제거형). 미수록이면 ''. """
    return strip_slash(AUTHORITATIVE.get((name or "").strip(), ""))


def code_for_current(current_code):
    """현행 business_code → 권위 코드('/' 제거형). 미식별이면 ''. """
    name = CURRENT_CODE_TO_NAME.get((current_code or "").strip())
    return code_for_name(name) if name else ""


def is_authoritative(code):
    """code가 이미 권위코드('/' 제거형 기준)인가."""
    c = strip_slash((code or "").strip())
    return bool(c) and c in {strip_slash(v) for v in AUTHORITATIVE.values()}


def resolve_target(code):
    """현행/권위 어느 쪽이든 권위 코드로 해소. 미결이면 ''.
    (a) 현행코드 매핑 우선 → (b) 이미 권위코드면 그대로. 새 도메인·이미 현행화된 코드 모두 처리."""
    t = code_for_current(code)
    if t:
        return t
    if is_authoritative(code):
        return strip_slash((code or "").strip())
    return ""


def suggest_code(name):
    """미등록 도메인의 권위코드 후보(휴리스틱; 최종은 사람 확정). name의 ASCII 대문자 이니셜을
    최대 4자로. 한글 전용 등 ASCII가 없으면 '' (사람이 직접 제안)."""
    letters = re.sub(r"[^A-Za-z]", "", name or "").upper()
    return letters[:4]


def add_domain(name, code, alias="", note="", path=None):
    """domain_codes.md 표에 한 행을 추가(대화형 등록)하고 매핑을 갱신. 권위코드('/' 제거형) 반환.
    이미 있는 도메인명이면 추가하지 않고 기존 코드를 반환(중복 방지)."""
    global AUTHORITATIVE, CURRENT_CODE_TO_NAME
    path = path or table_path()
    name = (name or "").strip()
    code = strip_slash((code or "").strip())
    if not name or not code:
        raise ValueError("add_domain: name·code 필수")
    auth, _ = _load_table(path)
    if name in auth:  # 이미 등록 → 무변경
        AUTHORITATIVE, CURRENT_CODE_TO_NAME = _load_table(path)
        return strip_slash(auth[name])
    row = f"| {name} | {code} | {alias.strip()} | {note.strip()} |\n"
    with open(path, encoding="utf-8") as f:
        lines = f.readlines()
    last_tbl = max((i for i, ln in enumerate(lines) if ln.lstrip().startswith("|")), default=len(lines) - 1)
    lines.insert(last_tbl + 1, row)
    with open(path, "w", encoding="utf-8") as f:
        f.writelines(lines)
    AUTHORITATIVE, CURRENT_CODE_TO_NAME = _load_table(path)
    return code


if __name__ == "__main__":
    import sys
    for c in sys.argv[1:]:
        print(f"{c} -> {resolve_target(c) or code_for_name(c) or '(미식별)'}")
