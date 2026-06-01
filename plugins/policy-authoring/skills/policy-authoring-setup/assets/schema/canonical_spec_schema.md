# 표준 spec JSON 스키마 (이식의 인터페이스)

이 스킬 세트의 도구(audit·build·render)는 **하나의 표준 spec JSON 형태**를 입출력으로 쓴다.
팀원은 프로젝트 폴더·소스 문서 형식이 어떻든, **자기 소스를 이 형태의 baseline spec JSON으로
변환**하기만 하면 도구가 그대로 동작한다. → 스키마가 인터페이스다.

## ID 패턴
`<BIZ>` = `policy_config.json`의 `business_code`(예: BIL·DATA·ROAM). `<DOMAIN>` = 대문자 도메인(CHRG·BILL…).

| 노드 | ID 형식 | 예 |
|---|---|---|
| 유스케이스 UC | `UC-<BIZ>-<DOMAIN>-NN` | UC-BIL-CUS-01 |
| 프로세스 PR | `PR-<BIZ>-<DOMAIN>-NNN` | PR-BIL-CHRG-001 |
| 기능 FN | `FN-<BIZ>-<DOMAIN>-NNN` | FN-BIL-CHRG-001 |
| 정책그룹 PG | `PG-<BIZ>-<DOMAIN>-NN` | PG-BIL-CHRG-01 |
| 정책상세 PI | `PI-<BIZ>-<DOMAIN>-NN-NN` | PI-BIL-CHRG-01-02 |

## top-level 키
```
meta · history · overview · actors · terms
usecases · processes · process_details
functions · function_details
policy_groups · policies · policy_details
states · state_transitions · concept_model · trace_matrix
```
- `policies` = `policy_groups`의 alias(같은 id 목록, audit H5가 검사).
- `trace_matrix`·각종 롤업 필드는 **build의 rebuild_rollups가 재생성**하므로 처음엔 비어 있어도 된다.
- `states`·`state_transitions`·`overview`·`history` 등은 도구가 깊이 검사하지 않음(있으면 보존).

## 핵심 노드 필드 (도구가 읽는 것)

### usecases[]
`id` · `name` · `related_processes[]`(PR id, 역참조 — build가 채움) · `process_target`("N"이면 PR 없는 비프로세스 UC로 인정).

### processes[] / process_details[]
- process: `id` · `name` · `description` · `usecase_id`(단수) · `usecase_ids[]`(복수) · `related_functions[]`(FN id) · `related_policies[]`(PG id, 파생) · `related_policy_details[]`(PI id, 파생).
- process_details: `process_id` + 롤업 미러(`related_policy_details`·`related_policies`).

### functions[] / function_details[]
- function: `id` · `name` · `description` · `process_id`(/`process_ids[]`) · `related_policies[]`·`related_policy_details[]`(파생).
- function_details: `function_id` · **`sub_functions[]`**(세부기능 문자열 배열) · **`subfn_pis[]`**(각 세부기능에 매핑된 PI id 리스트 — 위치별, build가 채움) · **`subfn_ui[]`**(각 세부기능 UI여부 **불리언** — 위치별) · 롤업 미러.
  - ⚠️ `sub_functions`·`subfn_pis`·`subfn_ui` **3 배열 길이·순서 일치**(audit F1/F2). 매핑은 위치(인덱스) 기반.

### policy_groups[] (= policies[])
`id` · `name` · `description` · `items[]`(소속 PI id).

### policy_details[]
`id` · `name`("명칭 (ID)" 권장) · `group_id`(/`policy_id`, 소속 PG) ·
`rule_statement`(/`content`) · `criteria_values[]`(/`criteria`) · `customer_notice`(/`notice`) ·
`source_note`(근거·치환 제외) · `detail_tables[]`(표) · `field_review`(있으면 붉은 배지) ·
`applies_to[]`(관할 세부기능 ref `"FN-id#idx"`, idx 1-based) · `applies_to_functions[]`(FN id, build가 파생).

### meta
`title`(렌더 제목) · `business_code` · 기타 자유.

## 최소 예시
```json
{
  "meta": {"title": "예시 정책서", "business_code": "BIZ"},
  "usecases": [{"id": "UC-BIZ-CUS-01", "name": "조회", "related_processes": []}],
  "processes": [{"id": "PR-BIZ-CHRG-001", "name": "정보 조회", "usecase_ids": ["UC-BIZ-CUS-01"], "related_functions": ["FN-BIZ-CHRG-001"]}],
  "process_details": [{"process_id": "PR-BIZ-CHRG-001"}],
  "functions": [{"id": "FN-BIZ-CHRG-001", "name": "기본 조회", "process_id": "PR-BIZ-CHRG-001"}],
  "function_details": [{"function_id": "FN-BIZ-CHRG-001", "sub_functions": ["요약 조회", "상세 조회"], "subfn_pis": [[],[]], "subfn_ui": [false,false]}],
  "policy_groups": [{"id": "PG-BIZ-CHRG-01", "name": "조회 정책", "items": ["PI-BIZ-CHRG-01-01"]}],
  "policies": [{"id": "PG-BIZ-CHRG-01", "name": "조회 정책", "items": ["PI-BIZ-CHRG-01-01"]}],
  "policy_details": [{"id": "PI-BIZ-CHRG-01-01", "name": "조회 기간 (PI-BIZ-CHRG-01-01)", "group_id": "PG-BIZ-CHRG-01"}],
  "trace_matrix": {}
}
```
이 상태로 build → rebuild_rollups 가 `subfn_pis`·롤업·`trace_matrix`를 채운다(PI override의 applies_to 기준).

## 소스 변환 가이드
팀원 소스가 이 형태가 아니면 onboarding(`policy-authoring-setup`)이 매핑을 돕는다. 흔한 경우:
- **이미 구조화된 데이터(스프레드시트/JSON/DB)**: 컬럼→위 필드로 매핑하는 1회용 변환 스크립트 작성.
- **as-is 문서(HTML/MD)만 있음**: 계층을 먼저 추출(UC/PR/FN/PG) → 골격 spec 생성 → 정책 상세는 작성 스킬로 채움.
- **business_code/도메인 코드**만 정하면 ID 패턴은 자동으로 따라온다.
