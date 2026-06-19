---
description: Top-level conductor — route a 작성 단위(unit) through the full phase sequence and the 편집 1건 루프, deciding which skill to use when.
argument-hint: [unit-and-phase-context]
---

# Policy Workflow Orchestration

Use this command when the user asks where to start, what comes next, how the skills fit together, or wants to drive a 작성 단위(unit) end-to-end — not when they are already inside one phase's content.

## Arguments

The user invoked this command with: $ARGUMENTS

## Instructions

1. Read `skills/policy-workflow-orchestration/SKILL.md` and its references (`phase-map.md`, `edit-loop.md`, `adversarial-verify.md`).
2. Identify the unit's current phase and route to the responsible sibling skill:
   - 세팅·자동초안 변환 → `policy-authoring-setup`
   - FN 재설계(화면-grounded PR↔FN) → `policy-hierarchy-decomposition`
   - 명칭·가독성 → `policy-naming-readability`
   - applies_to 매핑·PI 본문·팩트체크 → `policy-detail-authoring`
   - enrich + 감사 STRUCTURAL 0 → `policy-integrity-audit`
   - NC 게이트 G2(요구↔노드)·G5(decision_spec 판정축) → `policy-nc-studio-gate`
   - render(6섹션) + splice(배포본) → `policy-render-deliver`
3. Enforce the **편집 1건 루프** (override 편집 → build_spec → audit STRUCTURAL 0 → render → splice → 선별 커밋) and 상시 규율 (선별 커밋·날조 0·to-be 분리·카운트 불변·재빌드 byte 동일). After a large batch, run the independent adversarial-verification pass (plan vs diff) per `references/adversarial-verify.md`.
4. Phase 6 요구사항 커버리지 검토는 문서화된 방법론으로 안내한다 — 자산 `tools/coverage/*` + 대상 repo의 `audit/REQUIREMENT_COVERAGE_METHOD.md`. ⚠️ 전용 커버리지 스킬은 Rule of Three(faq/store 2차 적용 후)로 후속 버전 연기.

## Example Usage

```text
/policy-workflow-orchestration faq 작성 단위 시작 — 어디서부터 할까?
/policy-authoring:policy-workflow-orchestration hub 다음 단계가 뭐야?
```
