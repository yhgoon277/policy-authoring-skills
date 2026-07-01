---
name: policy-workflow-orchestration
description: Top-level conductor that routes a policy/requirements 작성 단위(unit) through the full phase sequence, the "편집 1건 루프" discipline, and the 5-principle completion gate (run_acceptance → DONE/BLOCKED/FAIL). Use when the user asks where to start, what comes next, how the pieces fit, when a unit is "done", or to drive a unit end-to-end — "작성 단위 시작", "전체 흐름", "다음 단계", "phase 순서", "워크플로우", "완료 기준", "5원칙", "run_acceptance", "어느 스킬 써야 해", "오케스트레이션", "end to end", "편집 루프", "선별 커밋", "NC 업로드 준비", "faq 착수", "store 착수". Prefer this when the question is sequencing/which-skill-when across the whole pipeline, not one phase's 내용.
version: 0.3.0
---

# 정책서 워크플로우 오케스트레이션 (Policy Workflow Orchestration)

> **Claude/Codex에서**: 한 작성 단위(unit)를 처음부터 끝까지 끌고 갈 때 진입점. 이 스킬은 **무엇을·어느 순서로·어느 스킬로** 하는지만 정하고, 각 phase의 실제 작업은 형제 스킬로 위임한다. `policy-*` 스킬 전부를 함께 설치하면 라우팅이 완전해진다.

> **미분류 첫 접촉이면 라우터가 먼저**: "신규냐 수정이냐, 받은 HTML을 들이냐"가 아직 안 정해진 **첫 접촉**은 이 스킬이 아니라 `policy-intake-router`가 분류해 알맞은 시작점으로 넘긴다. 진입 경로가 이미 정해졌으면 바로 이 오케스트레이션으로 온다.

한 unit(예 `hub`·`faq`·`store`, 전부 `business_code=CS`)을 **자동초안 → NC 업로드 합격본**까지 끌고 가는 최상위 컨덕터. 핵심 통찰: 모든 내용 변경은 **단일 진실원천(spec JSON)** 을 거치고, 손으로 HTML을 고치지 않으며, 변경 1건마다 **편집 1건 루프**로 검증한다.

> **참조 구현**: `MyPart_CustomerCenter` hub 단위 — 10UC·21PR·64FN·23PG·121PI, STRUCTURAL 0, NC G2·G5 통과까지 이 시퀀스로 완주.

---

## Phase 시퀀스 (unit 1개)
각 phase는 전담 형제 스킬로 위임한다. 상세 매핑·완료 기준 → **[references/phase-map.md](references/phase-map.md)**.

| # | Phase | 위임 스킬 |
|---|---|---|
| 0 | 세팅·자동초안 변환(`convert_autodraft.py --unit=`) | `policy-authoring-setup` |
| 1 | FN 재설계(화면-grounded PR↔FN) | `policy-hierarchy-decomposition` |
| 2 | 명칭·가독성 | `policy-naming-readability` |
| 3 | applies_to 매핑(FN↔PI 그래프) | `policy-detail-authoring` |
| 4 | PI 본문 작성·팩트체크·field_review·to-be | `policy-detail-authoring` |
| 5 | enrich(NC 풀스키마·decision_spec 시드) + 감사 STRUCTURAL 0 | `policy-integrity-audit` |
| 6 | 요구사항 커버리지 검토(매핑·품질 갭) | 방법론 문서(아래) |
| 7 | NC 게이트 G2(요구↔노드)·G5(decision_spec 판정축) | `policy-nc-studio-gate` |
| 8 | render(6섹션 HTML) + splice(배포본) | `policy-render-deliver` |
| 9 | **완료 게이트 — 5원칙 검수**(`build_deliverable`/`run_acceptance` → DONE) | `policy-render-deliver` |

> 순서는 의존성 순(앞 phase 출력이 뒤 phase 입력). hub처럼 한 번 완주한 unit을 재편집할 때는 **FN 레이어·명칭·applies_to·PI group_id를 고정**하고 값 확정/배지 제거만 한다.

> **외부 HTML 점검(2 지점)**: 외부/레거시/타팀 HTML로 시작하면 Phase 0 전에, NC 업로드(Phase 7) 후엔 NC 변환본 누락 점검으로 → `policy-html-json-check`(HTML↔JSON 사전 검토·조건부 복원·사용자 확인 게이트). 편집 1건 루프 밖.

## 완료 정의 — 5원칙 게이트 (플러그인이 스스로 검수·확정)
작성 단위의 **완료는 5원칙 통합 게이트 `run_acceptance`(진입점 `build_deliverable`)가 판정**한다. 육안·부분 grep은 보조일 뿐 계약이 아니다.
- **R1 골든 스타일**(§5~§6 골든 렌더) · **R2 입력 게이트**(`validate_spec_input` errors=0) · **R3 원천 보존**(원천 HTML 정본 대비 무손실·무단발산 0·헤드 §0~§4 완전보존) · **R4 완료 정합**(JSON↔HTML) · **R5 도메인코드 현행화**(권위표 `policy domain code.xlsx`→ 전 ID 세그먼트 relabel).
- **3-상태**: **DONE**(5원칙 PASS) / **BLOCKED**(결함 없으나 사람결정 대기 — 미지원 포맷·usecase_id·정책상세 저작·원천 §4↔§5 불일치·발산 승인/제외·R5 target 미매핑) / **FAIL**(배포물 원칙 RED = 자동 수정 대상).
- **BLOCKED은 실패가 아니라 사람 결정 요청** — `policy-html-json-check`/`decision_guide`로 처리 후 재검수. **원칙·목표가 바뀌면 이 게이트(오라클·도구)에 반드시 반영**한다(플러그인이 산출물).

## 편집 1건 루프 (모든 내용 변경 — 절대 규율)
내용을 한 건 바꿀 때마다 아래를 **순서대로** 돈다. 어긋나면 폐기하고 직전 커밋으로 복귀.
```
tools/overrides/<unit>.py 편집(PI 본문·applies_to·rule_type·decision_spec)
  [계층·명칭·PR/FN 신설은 baseline 직접 편집]
→ python3 tools/build_spec.py         --config=policy_config.json --unit=<unit>
→ python3 tools/audit_id_integrity.py --config=policy_config.json --unit=<unit>   # STRUCTURAL 0 (exit 0) 필수
→ python3 tools/render_preview.py      --config=policy_config.json --unit=<unit>
→ python3 tools/splice_nc_html.py      --unit=<unit> --base=<원천 HTML>           # 배포본만(§5·6)
→ python3 tools/run_acceptance.py      --source=<원천> --spec=<spec> --deliverable=<배포> [--gate=..]  # 5원칙 DONE
→ 미리보기·spliced 육안 확인 → 선별 커밋
```
> 원천 HTML 기반 신규 배포는 위 3개(render→splice→accept)를 묶은 **`build_deliverable.py`** 한 번으로 대체 가능.
보조 게이트: `python3 tools/coverage_gate.py --config=policy_config.json --unit=<unit>`. 루프의 근거·규율 상세 → **[references/edit-loop.md](references/edit-loop.md)**.

## 상시 규율 (전 phase 공통)
- **선별 커밋** — `git add -A` 금지. 편집한 override + 재빌드 spec + preview만 stage. **커밋/푸시는 사용자가 요청할 때만.**
- **날조 0** — 표·수치는 원문 직접 카운트. 값 불확실하면 만들지 말고 `field_review`로 플래그.
- **to-be 본문 직접수정 금지** → `field_review`(붉음)·`internal_integration`(앰버)·후보 문서로 분리.
- **카운트 불변** — `expected_counts` 고정 후 누수 자동 검출. 재빌드 byte 동일이 재현성 증거.
- **컨텍스트 한도 임박** 시 안전 체크포인트(직전 커밋)에서 멈추고 사용자에게 알림.

## 큰 묶음 후 적대 검수 (cross-cutting)
BL 보강·PI 배치 등 **큰 묶음**을 끝내면, 편집자와 분리된 **독립 신규-컨텍스트 에이전트**로 `계획(BACKLOG/플랜) vs 실제 diff` 충실도를 검증한다(날조 0·제안 누락 0·노드 오편집 0·banned token 0·to-be 무배지). 패턴·체크리스트 → **[references/adversarial-verify.md](references/adversarial-verify.md)**.

## 요구사항 커버리지 검토 (Phase 6 — 전용 스킬 미분리)
요구 정의서 vs 현 spec의 **①매핑 누락 · ②반영 품질** 전수 검토. 본문은 안 고치고 갭 리포트(BACKLOG)만 산출 → 갭은 편집 1건 루프로 보강. 자산: `tools/coverage/prep_coverage_inputs.py`(`prep|inject|qa-input|finalize`)·두 `*.workflow.js`·`coverage_gate.py`. 방법론 전문은 대상 repo의 `audit/REQUIREMENT_COVERAGE_METHOD.md`를 따른다. ⚠️ **전용 스킬화는 Rule of Three(faq/store 2차 적용 후)로 v0.2.1 연기** — 지금은 이 문서가 라우팅 지점.

---

## 다른 스킬과의 연계
- 미분류 첫 접촉(신규/수정/외부 HTML) 분류·핸드오프 → `policy-intake-router`.
- 세팅·자동초안·config 생성 → `policy-authoring-setup`.
- 계층·FN 분화(①) → `policy-hierarchy-decomposition` / 명칭·가독성(②) → `policy-naming-readability`.
- applies_to·PI 본문·팩트체크(③) → `policy-detail-authoring`.
- 감사 STRUCTURAL 0·롤업 재계산(④) → `policy-integrity-audit`.
- render·splice 배포본 → `policy-render-deliver` / NC 게이트 G2·G5 → `policy-nc-studio-gate`.
- 외부 HTML↔JSON 사전 검토·조건부 복원(인테이크·NC 라운드트립) → `policy-html-json-check`.
