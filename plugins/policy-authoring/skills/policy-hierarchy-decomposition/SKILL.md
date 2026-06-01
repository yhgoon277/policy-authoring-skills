---
name: policy-hierarchy-decomposition
description: Design and decompose a policy specification's UC→Process(PR)→Function(FN)→sub-function hierarchy. Use this whenever the user is building or revising a policy/requirements spec and needs to split a process into functions, decide sub-function granularity, assign new function IDs, write function descriptions, or handle multi-party (1:N) flows such as delegation, split-payment, backup payment methods, shared limits, or family billing. Trigger on phrases like "기능 분화", "PR을 FN으로 나눠", "프로세스를 기능으로", "세부기능 정리", "process decomposition", "function breakdown", or when reviewing whether an existing decomposition is correct. Even when the user does not say "분화" explicitly, prefer this skill whenever the task is about the shape of the function layer rather than naming or policy-detail content.
---

# 정책 계층·기능 분화 (Policy Hierarchy & PR-FN Decomposition)

> **Claude/Codex에서**: 작업 대상(스펙 일부·프로세스 설명 등)을 대화에 붙여넣거나 업로드하고 적용을 요청하면 가이드대로 동작한다. 효과를 온전히 보려면 `policy-*` 5개 스킬을 함께 설치한다.

정책 명세의 기능 레이어를 **기획자·개발자가 바로 화면을 그릴 수 있는** 단위로 쪼개고 묶는 방법.

## 계층 모델

```
UC (유스케이스)  →  PR (프로세스)  →  FN (기능)  →  sub_functions (세부기능)
                                          ↑ 이 스킬이 다루는 레이어
PG (정책그룹)    →  PI (정책상세)        FN ↔ PI 는 N:M 으로 매핑(③에서)
```

- **이 스킬의 범위** = FN·세부기능의 *모양*(무엇을 FN으로 두고, 세부기능을 어떻게 끊을지, FN '설명'을 어떻게 구성할지).
- **범위 밖**: 이름·문장 다듬기 → `policy-naming-readability`(②) / PI 내용·매핑 → `policy-detail-authoring`(③) / 연결·ID 검증 → `policy-integrity-audit`(④).

> **참조 구현**: 통신 "청구및수납관리" 모듈(business_code `BIL`). 아래 예시 중 `BIL`·BSS·SWING이 나오면 그 프로젝트 사례다 — 다른 모듈에선 자기 도메인 용어로 치환해 읽는다.

---

## 분화 6규칙

각 FN을 만들 때 아래 6규칙을 적용한다. 핵심은 **"FN/세부기능은 회원이 보는 화면·조작 단위"** 라는 것.

### 규칙 1 — 백엔드 처리는 별도 FN으로 분리하지 말 것
백엔드 처리(시스템 동기화·외부 시스템 등록·결제 게이트웨이 호출·외부 API)는 **프론트 FN으로 분화하지 않는다.** 회원 동의·실행 CTA가 있는 프론트 FN의 흐름 안에서 "백엔드 X 요청 전송"으로 **명시만** 한다.

- **왜**: 진입·검토·처리·결과 패턴에서 "처리"는 회원이 조작하는 프론트 액션(폼 제출·CTA 클릭)이어야 한다. 백엔드 등록 자체는 화면이 없어 FN으로 분리하면 화면을 그릴 수 없다.
- **적용**:
  - 4 FN 패턴이 안 맞으면 억지로 4개 만들지 말고 **3 FN**(입력 → 검토·실행 → 결과)으로.
  - 백엔드 동기화는 직전 FN의 description·output에 "백엔드 처리 요청 전송 / 결과는 다음 FN으로 전달".
  - 결과 안내 FN에서 "백엔드 등록 성공 후" 금지 → "처리가 완료된 후 / 처리 결과 수신 후"로 추상화.
- *예(BIL)*: 자동납부 해지에서 "BSS·SWING 해지 등록" FN을 따로 둔 초안 → 제외하고 직전 '검토·실행' FN에 흡수.

### 규칙 2 — 진입·표시 컴포넌트는 화면 단위로 구체화
진입 FN의 description을 "다음 FN으로 정보 전달" 식 데이터 흐름으로 뭉뚱그리지 말고, **실제 화면에 어떤 카드·컨트롤·라벨이 노출되는지** 구현 가능한 수준으로 쓴다.

- **왜**: 데이터 흐름만 적으면 구현할 정보가 없다("무슨 기능인지 모르겠다"는 피드백의 원인).
- **적용**:
  - "조회되어 전달된다" → 화면 컴포넌트로: *예(BIL)* "결제수단 카드 표시(신한카드 1234·국민은행 \*\*\*\*0987 마스킹), 통합청구 라벨, 묶인 청구계정 수".
  - 다건 보유 처리: "카드별 라디오·체크박스로 대상 선택".
  - 컨트롤·CTA·라벨·마스킹 형식 등 UI 디테일까지.
  - sub_functions에서 "다음 FN으로 전달" 같은 시스템 흐름 항목은 삭제 — 화면 컴포넌트·사용자 액션만 남긴다.

### 규칙 3 — sub_functions 4개 고정 금지, 자연 통합(2~5)
세부기능을 무조건 4개로 맞추지 않는다. 같은 컴포넌트의 **부수 속성**(마스킹·비활성·헤더 라벨·상시 노출 위치 등)은 메인 항목에 괄호로 흡수한다.

- **왜**: 4개 강제는 "굳이 나눌 필요 없는 세부기능까지 나누게" 만든다.
- **적용**:
  - 후보를 다 적은 뒤 점검: "이건 별도 사용자 액션·화면 컴포넌트인가, 메인 항목의 속성·조건인가?"
  - 속성·조건(라벨·마스킹·비활성·상시 노출·강조 분기)은 **괄호로 흡수**. 별도 인터랙션(클릭·드릴다운·재시도·CTA·필터)만 별도 항목.
  - 통합 후 **2~5개**가 자연스러움.
  - **align 필수**: sub_functions를 통합하면 같은 FN의 description / processing_logic / output_information도 같은 수준으로 맞춘다(한쪽만 고치면 불일치).
- *예(BIL)*: "통합계좌 카드 그룹" + "통합계좌 라벨" + "비노출 처리" → "통합계좌 인출 카드 그룹 (보유 회원만 노출, 헤더 + 통합 인출일·금액·계좌)".

### 규칙 4 — sub_functions는 자연어 키워드 (내부 ID·코드 금지)
세부기능 항목은 **한눈에 무엇인지 아는 자연어 키워드 요약**. PI/UC/PR/FN ID 등 내부 식별자 직접 노출 금지. 괄호 설명이 한 줄 넘으면 통합·분리 검토.

- **왜**: "PI-09 customer_notice 헤더 안내" 같은 표기는 기획자가 못 알아본다.
- **적용**:
  - ID는 자연어로: "PI-09 customer_notice" → "만료 임박 안내 문구".
  - 괄호 안은 5~15자 부가 정보만. 동사·명사 키워드 중심("X 표시"·"Y 버튼"·"Z 안내").
  - 한 항목에 "X + Y + Z" 복수 동작이면 키워드 단위로 분리 또는 자연 통합.
  - 단, **description·processing_logic·output_information은 ID 인용 OK**(자세한 설명 컨텍스트).

### 규칙 5 — 신규 FN ID = 카테고리 max + 1 (다른 PR 충돌 회피)
새 FN ID는 같은 카테고리에서 **이미 다른 PR이 쓰는 ID를 절대 재사용하지 않는다.** 카테고리 전체 FN ID의 max + 1부터.

- **왜**: 빌드의 신설 로직이 "fn_id 존재 시 신설 대신 덮어쓰기"로 분기하면, 다른 PR의 FN name·description이 조용히 망가진다(회귀).
- **적용**:
  - 신설 전 같은 카테고리 모든 FN ID 조회 → max 확인 → +1부터:
    ```bash
    python3 -c "import json,sys; spec=json.load(open(sys.argv[1])); cat=sys.argv[2]; \
    print(sorted(f['id'] for f in spec['functions'] if cat in f['id']))" <spec.json> <BIZ-CATEGORY>
    ```
  - 신설 후 **회귀 점검**(직전 spec과 description diff)으로 다른 PR의 FN이 변경됐는지 검증 → `policy-integrity-audit`(④).

### 규칙 6 — description은 sub_functions를 빠짐없이 전개
FN description은 sub_functions 각 항목을 **(1)…(2)…(3)… 로 하나씩** 풀어, *동작·조건/분기·예외 fallback·고객 문구·관련 PI 인용*까지 담는다. 범위만 1~2문장 요약하면 미달.

- **왜**: "4종 카드 표시 + CTA 제공" 식 범위 나열은 각 세부기능이 *어떻게* 동작하는지를 빠뜨린다.
- **적용**:
  - sub n개 ↔ description (1)~(n) 1:1 대응 확인.
  - 각 전개 항목에 동작 + 조건/분기 + 예외 + 고객 문구(있으면) + 관련 PI 인용.
  - 자동 점검은 키워드 매칭 오탐이 많음 → description 분량(같은 PR군 평균 대비) + (1)(2) 전개 유무로 1차 스크리닝 후 육안 확인.
- *기준 예(BIL)*: 회선 종별 분기·통합청구·미납 합산을 PI 인용 + 분기별 동작으로 전개(평균 ~380자).

---

## 다자(1:N) 배정 게이트

대납·나눠내기·예비결제수단·가족 위임·통합 한도처럼 **1:N·복수 주체** PR은, 기존 분해(요청 폼 + 등록 등)를 무비판 수용하지 말고 분화 전 두 가지를 먼저 점검한다.

1. **인접 도메인 경계 확인** — 비슷한 개념을 다루는 다른 도메인이 있는지, 이미 구분 정책이 있는지. *예(BIL)*: 대납(DLG) vs 나눠내기(SPLT) vs 예비결제수단(RESERVE)은 별도 정책으로 명시 구분 — "금액 분담"은 나눠내기 영역이지 대납이 아님.
2. **주체별 배정/할당 단계가 컴포넌트로 명시됐는지** — 1:N 매핑인데 "각 주체가 무엇을·얼마를·어느 범위를 담당하는지 사전 결정"하는 FN/PI가 없으면 거의 확실한 누락. 이 배정은 보통 등록·실행이 아니라 **요청/신청 시점**에 정해진다.
   - *예(BIL)*: 대납 1:N(1 청구계정 : N 대납자)의 올바른 의미는 **범위 배정**(각 대납자가 회선·항목·기간을 배정받아 전액 대납, 중복 배정 금지로 이중납부 방지). "범위 배정·미배정 잔여" FN/PI 추가로 해결.

경계가 모호하거나 배정 방식에 선택지가 있으면 **추측하지 말고 사용자에게 방향을 묻는다**(AskUserQuestion).

---

## 분화 체크리스트 (모든 FN 작성 시)

- [ ] 백엔드 처리(시스템 동기화·외부 등록·PG·API)만 다루는 FN이 별도로 있는가? → 제외하고 인접 FN에 흡수 (규칙 1)
- [ ] description에 "전달된다·조회된다·매핑된다"가 화면 디테일 없이 단독으로 있는가? → 화면 컴포넌트로 풀어쓰기 (규칙 2)
- [ ] sub_functions에 "다음 FN으로 X 전달" 항목이 있는가? → 화면 컴포넌트·사용자 액션으로 대체 (규칙 2)
- [ ] sub_functions가 강제로 4개인가? → 속성·조건은 괄호로 흡수해 2~5개로 (규칙 3)
- [ ] sub_functions 통합 시 description/processing_logic/output_information도 align했는가? (규칙 3)
- [ ] sub_functions에 PI/UC/PR/FN ID가 직접 노출됐는가? → 자연어 키워드로 (규칙 4)
- [ ] sub_functions 괄호 설명이 한 줄을 넘는가? → 통합/분리 (규칙 4)
- [ ] 신설 FN ID가 카테고리 max+1인가? 다른 PR의 ID를 덮어쓰지 않는가? (규칙 5)
- [ ] description이 sub_functions 각 항목을 (1)…(2)… 로 전개했는가? (규칙 6)
- [ ] 1:N PR이면 인접 경계 확인 + 주체별 배정 단계가 컴포넌트로 있는가? (다자 게이트)

---

## 다른 스킬과의 연계
- FN '설명'·세부기능명의 **문장·단어 다듬기** → `policy-naming-readability`(②).
- 분화 결과의 **ID 충돌·세부기능 커버리지·롤업** 검증 → `policy-integrity-audit`(④).
- 세부기능에 붙는 **PI(정책 상세) 작성·매핑** → `policy-detail-authoring`(③).
