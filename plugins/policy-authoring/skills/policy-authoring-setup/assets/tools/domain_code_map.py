#!/usr/bin/env python3
"""domain_code_map — 정책서 도메인명→도메인코드 권위 매핑 (R5 도메인코드 현행화).

출처: `policy domain code.xlsx` (2026-07 기준, 35행). 코드의 '/'는 ID/SEG 정규식·CSS
선택자를 깨뜨리므로(검증: `PI-EVT/MSN-…` → SEG=None, ID 분해) ID·business_code에는
'/' 제거형을 쓴다(EVT/MSN→EVTMSN, BEN/TPNT→BENTPNT).
'AI검색'은 xlsx 미수록 → 사용자 결정으로 'AI Agent(AIA)'에 매핑.

조회:
  code_for_name(도메인명)        → 권위 코드('/' 제거형) 또는 ''
  code_for_current(현행코드)     → 권위 코드('/' 제거형) 또는 ''  (테스트셋 현행 식별)
"""

# 도메인명 → 코드 (xlsx 원시 표기; '/' 포함 가능)
AUTHORITATIVE = {
    "가이드라인/ 공통/ 품질/ 적응형": "UXP",
    "전시/관리 기능": "DSP",
    "상품 목록": "PRDL",
    "외부 BP 서비스 관리 체계": "BPS",
    "AI Agent": "AIA",
    "추천": "RCM",
    "데이터 트래킹 체계": "ANA",
    "이벤트/미션 프로그램": "EVT/MSN",
    "외부 쿠폰": "CPN",
    "멤버십 혜택/T 플러스포인트": "BEN/TPNT",
    "상품상세/담기": "PRD",
    "카트/장바구니": "CART",
    "할인/시뮬레이션": "SIM",
    "주문/계약/가입": "JOIN",
    "선물주문": "GFT",
    "상품변경": "CHG",
    "결제": "PAY",
    "주문 상태/사후 관리": "ORH",
    "배송/재고": "DLV",
    "나의 가입 정보": "INFO",
    "회선 변경/관리": "MOD",
    "멤버십 카드 관리": "MBS",
    "청구 및 수납 관리": "BIL",
    "나의 데이터·통화": "DTC",
    "상품·서비스 혜택 이용/공유": "MYBEN",
    "통합 쿠폰/이용권함": "MYCPN",
    "회원 가입/탈퇴/인증": "MBR",
    "회원정보 조회/변경": "MBI",
    "통합 알림": "ALM",
    "통합 약관": "AGR",
    "설정": "SET",
    "고객센터_통합허브": "CSHUB",
    "고객센터_FAQ/공지/이용안내": "GUIDE",
    "고객센터_매장안내": "STORE",
}

# 1차 정책서 10모듈 현행 business_code → 권위 도메인명 (현행 코드로 모듈 식별).
# 입력 문서 도메인명이 xlsx와 정확히 일치하지 않는 경우의 식별 보조.
CURRENT_CODE_TO_NAME = {
    "AIS": "AI Agent",          # 'AI검색' — 사용자 결정(AIA)
    "PAY": "결제",
    "MYI": "나의 가입 정보",
    "DTC": "나의 데이터·통화",
    "PDD": "상품상세/담기",
    "PRD": "상품상세/담기",
    "EVT": "이벤트/미션 프로그램",
    "DSP": "전시/관리 기능",
    "ORD": "주문/계약/가입",
    "BIL": "청구 및 수납 관리",
    "ARZ": "통합 알림",
}


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


if __name__ == "__main__":
    import sys
    for c in sys.argv[1:]:
        print(f"{c} -> {code_for_current(c) or code_for_name(c) or '(미식별)'}")
