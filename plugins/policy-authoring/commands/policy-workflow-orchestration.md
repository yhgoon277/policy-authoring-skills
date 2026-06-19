---
description: Fan-out requirement-coverage analysis — map requirements to spec nodes, grade reflection quality, and adversarially re-verify via parallel agents.
argument-hint: [unit-and-coverage-context]
---

# Policy Workflow Orchestration

Use this command when the user wants to run the requirement-coverage workflows — mapping each requirement to spec nodes, grading how faithfully each is reflected, and adversarially re-checking the grades — as parallel/pipelined agent fan-outs.

## Arguments

The user invoked this command with: $ARGUMENTS

## Instructions

1. Read `skills/policy-authoring-setup/SKILL.md` (6단계 — orchestration entry) and the workflow scripts in `skills/policy-authoring-setup/assets/tools/coverage/`:
   - `prep_coverage_inputs.py` — builds the per-unit WORK inputs (node catalog, batches, qa inputs with node bodies).
   - `req_coverage_map.workflow.js` — ①매핑: fan-out requirement→node mapping (schema-validated), writes per-batch JSON.
   - `req_coverage_quality.workflow.js` — ②품질평가→적대검증 pipeline: 4-grade reflection quality, then a skeptical adversarial pass targeting over-graded "충실 반영".
2. ⚠️ Each `*.workflow.js` requires **manual edit of the WORK·NB constants per unit** (top-of-file comment) — this avoids the Workflow args-passing bug. The copied templates derive `WORK` from env `COVERAGE_WORK` or fall back to `audit/_coverage_work_<unit>`; set `COVERAGE_UNIT`/`COVERAGE_WORK` or edit in place, and set `NB` to the batch count.
3. Typical flow (project-local copies under `tools/coverage/`):
   ```bash
   python3 tools/coverage/prep_coverage_inputs.py --config=policy_config.json --unit=<unit>
   # then run the two .workflow.js via your workflow runner (after editing WORK/NB)
   python3 tools/coverage_gate.py --config=policy_config.json --unit=<unit>   # PASS check
   ```
4. Consolidate batch outputs into the coverage matrix / backlog under `audit/`, keeping intermediate `audit/_coverage_work_<unit>/` git-ignored. Method reference: the reference project's `audit/REQUIREMENT_COVERAGE_METHOD.md`.

## Example Usage

```text
/policy-workflow-orchestration hub 요구 커버리지 매핑·품질·적대검증 돌려줘
/policy-authoring:policy-workflow-orchestration faq 유닛 커버리지 워크플로 준비
```
