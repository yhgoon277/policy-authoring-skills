---
name: policy-nc-studio-gate
description: Prepare a policy spec to pass NC스튜디오 health-check gates G2 (요구사항↔노드 연결) and G5 (정책 구체성/decision_spec) on upload. Use when an NC스튜디오 upload fails or warns on requirement-linkage or policy-specificity, or the user mentions "NC 업로드", "health check", "헬스체크", "G2", "G5", "요구사항 미연결", "decision_spec", "판정축", "요구사항 추적", "NC 게이트", or asks why a gate failed / how to pass it. Prefer this skill when the concern is NC-schema conformance for upload, not policy content substance.
version: 0.2.0
---

# NC스튜디오 게이트 통과 (NC Studio Health-Check Gates: G2·G5)

> **Claude/Codex에서**: 게이트 대상 unit과 `policy_config.json`을 대화에 붙이고 실패 메시지를 공유하면 가이드대로 config 블록·재빌드 절차를 안내한다. `policy-*` 스킬을 함께 설치 권장.

NC스튜디오 업로드 시 두 health-check 게이트를 통과시키는 작업. **G2 = 요구사항↔노드 연결**(우리 노드가 NC 요구 레지스트리에 묶여 있나), **G5 = 정책 구체성**(정책 상세에 닫힌 판정값이 있나). 둘 다 **빌드 파이프라인이 결정론으로 충족** — 본문은 거의 손대지 않는다.

> **참조 구현**: 고객센터 `hub` unit. G2 통과 `0a402d5`·G5 통과 `318e823`. 두 건 합쳐 spec ~600줄 변경 중 기획자-가시 본문 변화는 **1줄**.

---

## ⚠️ 과대해석 금지 (핵심 인사이트)
G2/G5는 **NC-스키마 적합성 + 경량 모호성 스캔**이지 **기획자-대면 내용 품질 검증이 아니다**. 통과 ≠ 내용 개선.
- G2 본체(`requirement_links` ~2500줄)·G5 `decision_spec`은 **우리 렌더러(`render_preview.py`)가 0회 참조** — preview·splice 배포본에 미렌더(`grep -cE "decision_spec|topic_learning|source_requirement|requirement_links" tools/render_preview.py` → 0).
- 따라서 게이트 충족 작업은 **부가 메타 + 0날조 미러**다. 본문을 왜곡하지 않으므로 안심하고 자동화하되, 통과를 "정책 내용 품질"로 보고하지 말 것. (근거: `audit/nc_healthcheck_value_audit_2026-06-18.md`)

## G2 — 요구사항↔노드 연결
`enrich_spec.emit_requirement_links(spec, cfg)`가 `meta.topic_learning.requirement_links` + 노드 `source_requirement_ids`/`source_requirement_refs`를 임베드. config의 `requirement_links` 블록이 **없으면 no-op**(faq/store baseline 안전). tracked 매트릭스(`matrix_path`)에서 REQ→라이브 노드, NC식 ID는 `nc_coverage_path`를 요구명 정규화로 브리지, 미매치/범위밖은 `nc_only_dispositions`로 disposition. ⚠️ **NC는 빈-노드 verdict(범위밖/전략) 미수용** — 노드 ≥1 연결을 요구. config 키·플래그 → **[references/nc-gate-mechanics.md](references/nc-gate-mechanics.md)**.

## G5 — 정책 구체성 (decision_spec)
`enrich_policy_details`가 각 PI에 `decision_spec` 스켈레톤을 시드: `criteria_values`·`allow_rule`·`customer_notice` + `_route_axes(criteria, rule)`가 **원문을 키워드(`_AXIS_KEYWORDS`)로 판정축**(`restriction_rule`·`exception_deny`·`priority`·`history_logging`)에 라우팅. **원문 substring 재사용 = 날조 0**. **빈 축은 키 omit**(`"(없음)"` 리터럴 금지 — NC가 omit 수용). criteria의 모호 표현("필요 시" 등)은 override로 구체화. 축 라우팅 함정·키워드 오탐 → references.

## enrich 풀스키마 (게이트 전제)
`enrich()`가 NC 필수 필드를 결정론 충족: `processes.usecase_id`·`functions.details`·`mockup_*`·`rule_type`·`review_status`·`policy_groups.items` 등. 이게 빠지면 게이트 이전에 업로드가 깨진다.

## 감사 가드 (K·L)
`policy-integrity-audit`(④)의 그룹 **K**(NC 필수필드 존재, STRUCTURAL — `config.nc_required_fields` 구동, K1~K4)·그룹 **L**(요구↔노드: L1 dangling 0·L2 유일성/카운트·L4 양방향 일치, STRUCTURAL). 둘 다 **비활성 시 no-op**. 이 둘이 0이어야 게이트 충족이 회귀 없이 유지된다.

---

## 워크플로 (편집 1건 루프 안에서)
1. **config 블록 작성** — `requirement_links`(emit·matrix_path·nc_coverage_path·requirements_index_path·nc_only_dispositions) 추가. G5는 config 추가 불필요(`enrich`가 unit 무관 자동).
2. **빌드** — `build_spec.py`가 말미에 `enrich()` → `emit_requirement_links()` 자동 호출. emit 로그로 노드연결·범위밖 카운트 확인.
3. **감사** — `policy-integrity-audit`(④)로 **STRUCTURAL 0**(특히 K·L). 카운트 불변.
4. **모호 표현만 본문 수정** — G5 '빈 표현' 탐지가 잡는 criteria만 override로 구체화(나머지는 비렌더 메타라 본문 무변).
5. **재업로드 검증** — NC스튜디오에서 G2/G5 PASS 확인(사용자). 빈 축 omit·빈-노드 verdict 수용 여부는 NC 실제 응답으로 확정.

> 적대 검수: 큰 게이트 묶음 후 독립 에이전트로 dangling 0·가짜매핑 0·키워드 오라우팅을 반증 시도(참조 구현에서 `로그→로그인` 오탐 4건 검출·정정).

## 다른 스킬과의 연계
- 게이트 충족 후 K·L 포함 STRUCTURAL 0 검증 → `policy-integrity-audit`(④).
- 모호 criteria 본문 구체화 → `policy-detail-authoring`(③) (field_review 경계와 구분).
- config·도구 설치, unit 온보딩 → `policy-authoring-setup`(⑤).
- 게이트는 NC-적합성만 측정 — 내용 품질은 ③에서 별도 보증.
