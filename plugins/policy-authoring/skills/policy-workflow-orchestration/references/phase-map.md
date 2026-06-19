# Phase 시퀀스 상세 (위임 스킬 · 완료 기준 · 실제 도구)

> 한 작성 단위(unit)를 `business_code=CS`로 자동초안→NC 합격본까지 끌고 가는 순서.
> 모든 도구는 `--config=policy_config.json --unit=<unit>` 규약(splice만 `--base=` 추가).

## Phase 0 — 세팅·자동초안 변환
- **위임**: `policy-authoring-setup`.
- **도구**: `python3 tools/convert_autodraft.py --config=policy_config.json --unit=<unit>` (NC AI 초안 v0.11 → CS baseline). 그다음 `build_spec.py`로 첫 build → `audit_id_integrity.py`로 STRUCTURAL 0 확인.
- **완료**: baseline spec JSON 존재, 첫 6섹션 미리보기 렌더, tracer STRUCTURAL 0.

## Phase 1 — FN 레이어 재설계 (화면-grounded)
- **위임**: `policy-hierarchy-decomposition`.
- **본질**: NC 변환기/자동초안의 PR↔FN 1:1·명칭충돌을 옵션 B 재-레벨(화면 FN→PR·위젯 sub_function→FN)로 해소. PR당 ≥`min_fn_per_pr`(기본 2) FN.
- **편집 위치**: 계층·PR/FN 신설·ID 부여는 **baseline 직접 편집**(override 아님).
- **완료**: 명칭충돌 0·배경PI 0·PI 본문 보존. 감사 그룹 **J**(J1 PR당 FN<min, J2 PR명==FN명) PASS.

## Phase 2 — 명칭·가독성
- **위임**: `policy-naming-readability`.
- **본질**: sub_functions 괄호 평문화·PI명 정리·내부코드 제거. `build_spec.py`의 `bake_pi_ids_into_names`/`normalize_pg_names`가 `명 (PI-CS-…)` 내장·`정책 정책` 중복 제거를 담당(렌더 이중표기 방지).
- **완료**: 감사 **I-group**(괄호·기호·banned token, I3 본문 rule/criteria/notice/표 스캔) PASS.

## Phase 3 — applies_to 매핑 (FN↔PI 그래프)
- **위임**: `policy-detail-authoring`.
- **본질**: 모든 PI를 FN 화면 세부기능(`FN#idx`)에 N:M 연결. override의 `applies_to[]`가 곧 FN↔PI 그래프. override에 없는 PI는 "배경 PI"(audit E6 SEMANTIC).
- **완료**: 배경 PI 0·진척도 = applies_to 보유 PI 비율 100%·무PI FN(E4) 0.

## Phase 4 — PI 본문 작성·팩트체크·to-be
- **위임**: `policy-detail-authoring`.
- **본질**: PG 단위(1 PG = 1 청크) `rule·criteria[]·notice·source_note·applies_to[]`(+선택 `tables[]`·`field_review`) 작성. as-is 팩트체크 후 불확실 값은 붉은 `field_review` 배지. to-be 후보는 **본문 미수정**, 별도 문서.
- **완료**: synthesize placeholder 0·PI 인용 전건·field_review 카탈로그.

## Phase 5 — enrich + 감사 STRUCTURAL 0
- **위임**: `policy-integrity-audit`.
- **enrich**: `build_spec.py`가 bake 후 `enrich_spec.enrich()` 호출 — NC 풀스키마(usecase_id·functions.details·PG.items·PI mockup_*/source_basis/review_status/rule_type/decision_spec) 충족. `enrich_policy_details`가 decision_spec 스켈레톤(빌링 8키 관례) 기계 시드.
- **감사**: `python3 tools/audit_id_integrity.py --config=policy_config.json --unit=<unit>` — 그룹 A~L. STRUCTURAL 위반 시 exit 1(거의 항상 stale 롤업 → `rebuild_rollups`).
- **완료**: STRUCTURAL 0·SEMANTIC은 의도분만 잔존·그룹 **K**(NC 필수필드, `nc_required_fields` 구동) PASS·`expected_counts` 고정.

## Phase 6 — 요구사항 커버리지 검토
- **위임**: 방법론 문서(전용 스킬 미분리, v0.2.1 연기). 대상 repo `audit/REQUIREMENT_COVERAGE_METHOD.md`.
- **도구**: `tools/coverage/prep_coverage_inputs.py`(`prep|inject|qa-input|finalize`)·`req_coverage_map.workflow.js`·`req_coverage_quality.workflow.js`·`coverage_gate.py`.
- **계약**: 매트릭스 4종 위반 합계 0 = `coverage_gate.py` PASS. decision ∈ {유지, 통합, 수정, 신설, 삭제(범위밖)}.
- **완료**: 매핑 누락 0·품질 4등급 판정표·갭 BACKLOG. 보강은 편집 1건 루프(신규 PI 0 지향, 기존 PI criteria/notice/표 흡수).

## Phase 7 — NC 게이트 G2·G5
- **위임**: `policy-nc-studio-gate`.
- **G2**(요구↔노드 연결): `enrich_spec.emit_requirement_links(spec, cfg)` — tracked 매트릭스에서 REQ→노드(dangling 0)·NC식 ID 요구명 정규화 브리지. config `units.<unit>.requirement_links.nc_only_dispositions`로 미매치 verdict. ⚠️ NC는 빈-노드 verdict 미수용(노드 ≥1 필수). 감사 그룹 **L**(L1 dangling STRUCTURAL).
- **G5**(decision_spec 판정축): `enrich_spec._route_axes(criteria, rule)` — `_AXIS_KEYWORDS`로 criteria/rule 원문을 판정축에 라우팅(원문 substring 재사용·날조 0). 빈 축은 `"(없음)"` 폐기→키 omit(NC 수용 확인).
- **완료**: NC 재업로드 G2·G5 PASS. 빈-표현·미해결 표현 0.

## Phase 8 — render + splice 배포본
- **위임**: `policy-render-deliver`.
- **render**: `python3 tools/render_preview.py --config=policy_config.json --unit=<unit> [--out=preview.html]` — 6섹션 HTML(빌링 템플릿 정합·유즈케이스/상태전이 mermaid 자동생성).
- **splice**: `python3 tools/splice_nc_html.py --unit=<unit> --base=<NC 변환 HTML> [--sections=4,5,6] [--out=...]` — NC 변환본의 섹션 5·6을 preview로 교체+리치 CSS 멱등 주입(비교체 섹션 byte 보존). 산출 `samples/deliverable/`.
- **완료**: 미리보기·spliced 육안 확인·json↔html 이격 0(수기 HTML 편집 금지).
