---
name: policy-naming-readability
description: Make policy-spec names and descriptions instantly understandable to non-technical planners. Use this whenever the user wants to clean up names or descriptions in a policy/requirements document — expanding cryptic item names, simplifying sub-function names, rendering "명칭 (ID)", or rewriting process/group/function descriptions in plain language by removing internal codes, jargon, acronyms, translationese, and stiff template phrasing. Trigger on "명칭 정리", "이름 이해하기 쉽게", "설명 풀어쓰기", "가독성 개선", "plain language", "rename sub-functions", "용어 풀이", or when a planner says the spec is hard to read. Prefer this skill when the task is about how things are worded or labeled, as opposed to the structure of the function layer or the substance of policy details.
---

# 명칭·설명 가독성 (Policy Naming & Plain-Language Readability)

> **Claude/Codex에서**: 다듬을 이름/세부기능 목록·설명을 대화에 붙여넣거나 업로드하고 적용을 요청하면 가이드대로 동작한다. 효과를 온전히 보려면 `policy-*` 5개 스킬을 함께 설치한다.

정책 명세의 **이름과 설명**을, 비전문가 기획자가 사전 지식 없이 바로 이해하도록 다듬는 방법.

- **이 스킬의 범위** = 명칭·설명의 *표현*(단어·문장). 구조를 바꾸지 않는다.
- **범위 밖**: FN/세부기능 구조 → `policy-hierarchy-decomposition`(①) / PI 내용 → `policy-detail-authoring`(③) / 검증 → `policy-integrity-audit`(④).

> **핵심 원칙**: 내부 용어·라벨을 그대로 옮기지 말고 **뜻을 일상어로 의역**한다. 단, 핵심 수치(18개월·만 19세 등)와 최종 시스템 용어(확정된 시스템·상품명)는 보존한다.

> **참조 구현**: 통신 "청구및수납관리" 모듈(`BIL`). 세부기능명 507개·PI명 26건을 이 규칙으로 정비함.

---

## 1. 렌더 칼럼은 "명칭 (ID)"
목록/표에서 식별자는 **이름 뒤 괄호**로 보인다 — "ID 명칭"이 아니라 **"명칭 (ID)"**.
- 데이터(JSON)에는 ID를 그대로 보관하고, **렌더 단계에서만** "명칭 (ID)" 형식으로 출력.
- 모든 목록 칼럼('정책 상세'·'관련 정책' 등)을 같은 형식으로 통일.

## 2. 항목 명칭 풀어쓰기 (PI명 등)
암호식 이름을 일상어로.
- **제거/풀이 대상**: 기호(×·→·매트릭스), 영문 약칭(CTA·link·dual·SSO·cross-distinction), 보안·기술 약어(PCI DSS·시간코드 T0~T9), "N건"·"N코드" 같은 내부 카운트 표기.
- **보존**: 확정된 시스템·원장·채널명, 상품명, 핵심 수치.
- *예(BIL)*: 내부 약칭 PG(선불폰)·MIRI(미리 선납) 등은 의미가 드러나는 이름으로("선불폰 충전"·"미리 선납"). 시스템 용어(BSS·NOVA·Next Channel)는 유지.

## 3. 세부기능명 간결화
세부기능 배열의 **문자열만** 다듬는다 — **개수·순서·위치는 절대 불변**(아래 가드 참조).

치환 가이드(예시):

| 원형 | 다듬은 표현 |
|---|---|
| CTA | 버튼 |
| link | 화면 이동 |
| fallback | 대체 표시 |
| 라벨 | 표시 |
| 폼 | 양식 |
| 롤백 | 되돌리기 |
| PG(결제대행) | 결제기관 |
| PI·FN·UC·1:N·0P·5열 등 내부코드 | 자연어로 풀거나 제거 |

- 분류 의미가 있는 코드는 **의미를 보존하며** 자연어화: *예(BIL)* "BSS 코드분류" → "발행 유형"(분류 의미 유지).
- ⚠️ 치환표의 약어는 **도메인마다 뜻이 다를 수 있다** — 기계적 일괄 치환 전에 그 맥락의 실제 의미부터 확정한다. *예*: "PG"가 결제대행이면 "결제기관", 요금제그룹이면 그 의미로 풀거나 코드 제거.
- 확정 시스템 actor(예 BSS)·포인트 상품명 등은 유지.

> ⚠️ **applies_to 인덱스 보존 가드(필수)**: 세부기능 ↔ PI 매핑은 **배열 위치(1-based index)** 로 참조된다. 이름을 바꾸느라 항목을 추가/삭제/재정렬하면 매핑이 전부 어긋난다. **문자열 교체만, 개수·순서 고정.** 검증은 4번 워크플로와 ④ 감사로.

## 4. 설명(PR/PG/FN description) 풀어쓰기
목록 표의 '설명' 칸을 쓸 때:
1. **비전문가가 바로 이해**하도록 — 정책 상세·기능 라벨을 그대로 옮기지 말고 뜻을 일상어로.
2. **내부 코드·약어는 빼거나 풀이**: *예* "PCI DSS" → "카드 결제 정보를 안전하게 다루는 국제 보안 기준(PCI DSS)"; 시간코드·시스템코드는 의미로 서술; "dual 노출" → "선불·일반 회선을 함께 보여주는 방식".
3. **정형 골격 금지**: "~을 정의한다 / 규정한다 / 담는다"로 줄세우지 않기. **종결어만 바꾸는 것도 규격화** — 문장 구조 자체를 변주.
4. **번역투 금지**: "단일 진실원(single source of truth)" → "다른 정책들이 기준으로 삼는 정책".
5. 핵심 수치(개월·연령 등)는 의역 중에도 **유지**.

## 5. 명명 규칙 검증
정비 후 자동 점검은 `policy-integrity-audit`(④)의 **그룹 I(SEMANTIC)**:
- I1: 세부기능명에 괄호 금지(통합 후 잔여 괄호 검출).
- I2: PI명에 기호 금지(×·→ 등 잔여 검출).

---

## 대량 정비 워크플로 (재사용)
세부기능명 수백 개처럼 양이 많을 때 안전한 절차 — **인덱스 보존이 생명**:

1. **드래프트**(서브에이전트 병렬, 카테고리별): 각 항목의 `{old, new}` 를 **위치 정렬된 JSON**으로 반환받는다.
2. **검증 스크립트**: spec의 기존 배열을 **위치별로 정렬 출력** + 개수 일치 + 금지 토큰 0 확인 = **applies_to 인덱스 보존 가드**.
3. **applier**: 해당 override 영역으로 스코프해 **FN별 sub_functions 전체 배열을 통째로 교체**(개수·순서 불변). ⚠️ 같은 FN-id가 다른 override(설명 등)에도 있으면 시작 오프셋을 정확히 잡을 것.
4. **빌드** → 개수 불변 확인(세부기능 총수·PI 총수).
5. **감사** → STRUCTURAL 0, 그룹 I 0(괄호·기호 0).
6. **렌더 → 커밋**(도구 + 정규 spec + 렌더 산출물만 선별 add).

> *예(BIL)*: 13개 카테고리 507개 세부기능을 이 절차로 전수 간결화, 개수·순서 100% 보존, audit 그룹 I PASS.

## 다른 스킬과의 연계
- 이름이 가리키는 **구조(무엇을 FN/세부기능으로 둘지)** → `policy-hierarchy-decomposition`(①).
- 명명 규칙 위반 **검출** → `policy-integrity-audit`(④) 그룹 I.
