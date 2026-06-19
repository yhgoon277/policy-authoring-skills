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

---

## NC스튜디오 풀스키마 필드 (`enrich_spec.py`가 채움)
NC스튜디오에 업로드해 검증하려면 baseline의 핵심 필드 외에 NC 풀스키마 필드가 필요하다. build 말미(`bake` 직후) `enrich()`가 이 필드들을 기계 시드하므로 baseline에는 비워둬도 된다. config `nc_required_fields`가 audit 그룹 **K**(STRUCTURAL)로 존재를 강제한다.

### policy_details[] (NC 필드)
- **`decision_spec`** — 닫힌 판정(실제 값·조건·횟수·시간·상태). NC **G5**(정책 구체성)가 검사. `enrich._route_axes(criteria, rule)`가 criteria/rule 원문을 키워드로 판정축(`criteria_values`·`restriction_rule`·`priority`·`exception_allow`·`exception_deny`·`history_logging`·`allow_rule`)에 라우팅(원문 substring 재사용, 날조 0). 빈 축은 키 omit(NC가 수용 확인).
- **`rule_type`** — 판정 유형 분류(override에서 지정 가능).
- **`mockup_binding`**(/`mockup_*`) — 화면 바인딩.
- **`review_status`** — 검토 상태.
- (이미 위에서 다룬) `source_basis`도 NC 근거 필드.

### processes[] / functions[] (NC 필드)
- process: `usecase_id`(단수, K필수)·`case_branches`(케이스 분기).
- function: `details`(K필수, element 단위 세부 — `enrich`가 64/64 채움).

## requirement_links (NC G2 — 요구사항↔노드 연결)
NC **G2**는 우리 노드가 요구사항에 연결돼 있을 것을 요구한다. 우리 업로드 spec에는 요구 데이터가 없으므로(`convert_autodraft`가 제거), `enrich_spec.py:emit_requirement_links`가 build의 `enrich` 직후 호출돼 `meta.topic_learning.requirement_links[]`·`requirement_implications`·노드 `source_requirement_ids`/`refs`를 생성한다. 설정이 없으면 no-op.

config `units.<unit>.requirement_links` 블록:
- `emit.meta`·`emit.nodes` — meta·노드에 각각 emit 할지.
- `matrix_path` — tracked 커버리지 매트릭스(`coverage_gate.parse_matrix`로 REQ→노드 파싱, 라이브 필터=dangling 0).
- `nc_coverage_path` — NC식 요구 ID(예 `CS-H01-003`) jsonl. 요구명 정규화로 매트릭스와 브리지.
- `requirements_index_path` — 요구 인덱스 jsonl.
- `nc_only_dispositions{}` — 자동 매칭 안 되는 NC식 요구 ID의 수동 처분(`decision`·`nodes[]`·`note`). ⚠️ NC는 **빈-노드 verdict(범위밖/전략, `nodes:[]`)를 미수용** — 가능한 한 노드 ≥1 연결.

audit 그룹 **L**(dangling·유일성·양방향)이 `requirement_links` 활성 시 검증, 비활성이면 no-op.
