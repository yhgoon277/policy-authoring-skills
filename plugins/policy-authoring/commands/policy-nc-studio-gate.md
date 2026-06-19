---
description: Prepare a spec to pass NC-studio upload gates — G2 requirement-to-node links and G5 decision-spec judgment axes.
argument-hint: [unit-and-gate-context]
---

# Policy NC-Studio Gate

Use this command when the user is preparing a spec for NC스튜디오 upload and needs to clear the schema-conformance gates — most often **G2** (requirements not linked to nodes) and **G5** (policy specificity — closed judgments with real values/conditions/counts/times/states).

## Arguments

The user invoked this command with: $ARGUMENTS

## Instructions

1. Read `skills/policy-authoring-setup/SKILL.md` (NC 게이트 절·6단계) and `skills/policy-authoring-setup/assets/schema/canonical_spec_schema.md` (NC 풀스키마 필드·requirement_links sections).
2. NC full-schema fields and links are emitted by `tools/enrich_spec.py` during `build_spec.py` (right after `enrich`), driven by `policy_config.json`:
   - **G2** — fill `units.<unit>.requirement_links` (`emit`, `matrix_path`, `nc_coverage_path`, `requirements_index_path`, `nc_only_dispositions{}`). `emit_requirement_links` writes `meta.topic_learning.requirement_links[]` and node `source_requirement_ids`/`refs`. ⚠️ NC does NOT accept empty-node verdicts — link ≥1 node wherever possible; record genuine out-of-scope items in `nc_only_dispositions` with a note.
   - **G5** — `enrich._route_axes(criteria, rule)` routes existing criteria/rule text into decision_spec axes (no fabrication; reuses source substrings; empty axes are omitted, which NC accepts). Deepen `decision_spec` only with as-is-grounded values; flag undefined to-be values via `field_review` instead of inventing them.
3. Rebuild and audit; the gate guards are audit groups **K** (NC required fields exist, STRUCTURAL — `nc_required_fields`) and **L** (requirement_links dangling/uniqueness/bidirectional). Both are no-op when their config blocks are absent:
   ```bash
   python3 tools/build_spec.py         --config=policy_config.json --unit=<unit>
   python3 tools/audit_id_integrity.py --config=policy_config.json --unit=<unit>   # K/L PASS
   python3 tools/coverage_gate.py      --config=policy_config.json --unit=<unit>   # requirement mapping
   ```
4. Confirm counts unchanged (`expected_counts`), STRUCTURAL 0, and rebuild/preview reproducibility before re-uploading to NC.

## Example Usage

```text
/policy-nc-studio-gate hub G2 요구사항 연결 채우고 재업로드 준비
/policy-authoring:policy-nc-studio-gate G5 decision_spec 판정축 채워줘
```
