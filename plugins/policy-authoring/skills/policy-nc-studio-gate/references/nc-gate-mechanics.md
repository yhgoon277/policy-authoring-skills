# NC 게이트 메커니즘 — config·플래그·필드 (진실 원천 인용)

도구: `tools/enrich_spec.py`·`tools/audit_id_integrity.py`·`policy_config.json`·`tools/build_spec.py`. 모든 키·동작은 위 파일에서 직접 확인한 것이다.

---

## 빌드 훅 (자동 호출 지점)
`build_spec.py`(말미, bake/normalize 이후):
```python
from enrich_spec import enrich, emit_requirement_links
enrich(spec, cfg.get("business_code", "CS"))
emit_requirement_links(spec, cfg)        # cfg = unit-overlaid config
```
→ 게이트 충족은 별도 명령 없이 **빌드에 포함**된다. emit은 config에 `requirement_links`가 없으면 즉시 return(no-op).

---

## G2 — `emit_requirement_links(spec, cfg)`

### config 블록 (`policy_config.json` → `units.<unit>.requirement_links`)
| 키 | 역할 |
|---|---|
| `emit.meta` (bool) | `meta.topic_learning`에 `requirements_count`·`requirement_implications`·`requirement_links[]`·source_profile `requirement_ids` 임베드 |
| `emit.nodes` (bool) | 라이브 노드에 `source_requirement_ids`·`source_requirement_refs` 부착 |
| `matrix_path` | tracked 커버리지 매트릭스(예 `audit/hub_coverage_matrix.md`) — `coverage_gate.parse_matrix`+`NODE_RE`로 REQ→노드 |
| `nc_coverage_path` | NC식 요구 ID·명(예 `data/index/hub_requirement_coverage.jsonl`) |
| `requirements_index_path` | 우리 요구 인덱스(예 `data/index/requirements.jsonl`) — 요구명 정규화 브리지 키 |
| `nc_only_dispositions` | 미매치/오버라이드 요구 처리: `{nc_id: {decision, nodes[], note}}` |

### 동작
1. **라이브 노드 집합** = spec의 UC/PR/FN/PG/PI id (`live`).
2. **매트릭스 파싱** → `matrix[req] = {decision, nodes}`. 노드는 `NODE_RE.findall` 결과 중 **`live`에 있는 것만**(dangling 차단).
3. **요구명 브리지** — `_norm_req_name`(NFKC·소문자·구분자 제거, `1:1→1대1`)로 NC 요구명 ↔ 우리 REQ id. unit 한정(`cfg.domain.lower()`).
4. **링크 생성** — NC coverage jsonl 각 행에 대해:
   - `nc_id in nc_only_dispositions` → 매뉴얼 disposition 우선(decision·라이브 노드).
   - 브리지 매치 → 매트릭스 노드.
   - else → `decision="미매핑"`, nodes=[].
5. **임베드** — `emit.meta`면 `topic_learning`, `emit.nodes`면 노드 필드. **sorted·멱등**.

### nc_only_dispositions — decision 유형 (hub 실례)
- `"통합(의미연결)"`·`"반영(의미연결)"` → nodes ≥1 (의미상 흡수한 노드).
- `"전략(설계반영)"` → nodes=[] (covered-by-design).
- `"범위밖(...)"` → nodes=[] (타 콘솔/모듈 소관, 예 이탈TM·캠페인 콘솔).

⚠️ **NC는 빈-노드 verdict 미수용**: 범위밖/전략으로 nodes=[]만 두면 NC가 "미연결"로 본다. hub G2 통과 시 4건은 수동 노드 연결로 carve-out(11APP·이용방법안내→`PI-CS-OPR-01-05`·여정케어→`UC-CS-CS-05`·single-view→`PI-CS-REQ-01-10`), 진짜 범위밖만 nodes=[] 유지.

### 학습
- NC식↔우리 요구 크로스워크는 **요구명 정규화**에만 의존(원본 NC ID는 spec/jsonl/xlsx에 없음).
- 프로세스-오염 주의: NC G2 피드백이 정책 본문의 'one-click'/'클릭' 업무흐름 단정을 지적할 수 있음 → baseline 직접편집으로 평문화(`한 번에`/`즉시`). 정책 본문 클릭 0 목표.

---

## G5 — `enrich_policy_details` + `_route_axes`

### decision_spec 스켈레톤 (PI마다)
override 작성본이 없으면 기존 필드에서 기계 시드:
- `criteria_values` = `" / ".join(criteria_values)` 또는 `rule[:160]`.
- `allow_rule` = `rule_statement`(또는 `content`).
- `customer_notice` = `"…"`(있으면).
- `_route_axes(criteria_values, rule)` 결과 병합.
- 전부 비면 폴백 `{"criteria_values": "(기준 정의 예정)"}`.

### `_route_axes` — 판정축 라우팅 (`_AXIS_KEYWORDS`)
criteria/rule 원문을 키워드로 축에 매핑. **매칭 없는 축은 반환 안 함(키 omit)**.
| 축 | 키워드(발췌) |
|---|---|
| `restriction_rule` | 제한·불가·초과·한도·만료·금지·차단·최대·최소·이내·범위·…한해·처리 전·전 본인확인 |
| `exception_deny` | 예외·실패 시·미충족·거부·반려·오류 시·없거나·않으면·지나면·초과하면 |
| `priority` | 우선·먼저·순위·긴급·선제 |
| `history_logging` | 이력·저장·기록 |

- 매칭된 원문 substring을 `" / ".join` — **날조 0**(새 문장 생성 안 함).
- 빈 축은 omit → 리터럴 `"(없음)"` 폐기. **NC가 omit 수용**(hub G5 PASS 확인) → "해당 없음" 승격 불필요.

### 키워드 오탐 함정
참조 구현에서 `"로그"`(이력) 키워드가 `"로그인"`을 오라우팅 → 4건(ACC·REQ·ERR·SCH) 오축. **정밀화 필요**: 키워드를 `로그인`과 충돌 안 하게 좁히고, `최소`·`범위` 같은 방어가능 키워드는 유지. 게이트 후 **적대 검수로 오라우팅 반증** 권장.

### 모호 표현 (진짜 본문 수정 1건)
G5 '빈 표현' 탐지가 잡는 것: `criteria`에 주체·시점 불명("필요 시" 등). 이건 비렌더 메타가 아니라 **렌더되는 criteria 본문**이므로 override로 구체화한다. hub 사례: `PI-CS-NEXT-01-10` "필요 시"→"처리 종료 시 또는 고객이 다른 업무 진입을 선택할 때"(`tools/overrides/hub.py`).

---

## enrich 풀스키마 (게이트 전제 — `enrich()` 체인)
`enrich_nc_aliases`(usecase_id 단수·process_details 미러) → `enrich_process_details`(case_branches·role) → `enrich_function_details`(component_policy_role) → `enrich_processes` → `enrich_functions`(mockup_component_level·function_type·granularity·sub_functions 폴백) → `enrich_functions_details_alias`(`functions[].details`) → `enrich_policy_details`(위 G5) → `enrich_policies_items`(`PG.items=[{id,name}]`).

---

## 감사 그룹 K·L (`audit_id_integrity.py`)

### K — NC 필수필드 존재 (STRUCTURAL, `nc_required_fields` 구동)
`policy_config.json` top-level:
```json
"nc_required_fields": {
  "processes": ["usecase_id"],
  "functions": ["details"],
  "process_details": ["related_functions","usecase_ids","case_branches"],
  "policy_details": ["decision_spec","rule_type","mockup_binding","review_status"]
}
```
- K1 processes·K2 functions·K4 policy_details = **빈값 금지**(존재+truthy).
- K3 process_details = **키 존재만**(빈 리스트 허용).
- 비면 그룹 K **전체 생략**. `enrich`가 결정론으로 채우므로 0이 정상.

### L — 요구↔노드 정합 (STRUCTURAL)
- L1: `requirement_links[].nodes` 전부 라이브 노드 실존(**dangling 0**).
- L2: NC requirement_id 유일 · `requirements_count == len(links)`.
- L4: **양방향 일치** — `link.nodes` ⇄ 노드 `source_requirement_ids`.
- `links`도 노드 필드도 없으면 **no-op**(baseline STRUCTURAL 0 유지).

---

## 통과 ≠ 품질 (다시)
`render_preview.py`는 `decision_spec`·`topic_learning`·`source_requirement`·`requirement_links`를 **0회 참조** → preview·splice 배포본에 미렌더. hub: G2+G5 ~600 변경 중 기획자-가시 본문 변화 = `PI-CS-NEXT-01-10` 1줄. 나머지는 NC 적재/거버넌스용 부가 구조(0날조 미러 + 추적 메타). 게이트 충족은 자동화하되 **"내용 품질 개선"으로 보고 금지**. 전수 증거: `audit/nc_healthcheck_value_audit_2026-06-18.md`.
