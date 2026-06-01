---
description: Audit a policy spec for ID, hierarchy, and trace-matrix integrity.
argument-hint: [spec-json-and-config-context]
---

# Policy Integrity Audit

Use this command when the user wants to check referential integrity, bidirectional links, rollups, coverage, counts, or trace matrix freshness in a policy spec.

## Arguments

The user invoked this command with: $ARGUMENTS

## Instructions

1. Read `skills/policy-integrity-audit/SKILL.md`.
2. If a spec JSON and `policy_config.json` are available, run `scripts/audit_id_integrity.py` from the skill or the project-local copied tool.
3. Report STRUCTURAL and SEMANTIC results separately. STRUCTURAL must reach 0.
4. If the audit reports stale rollups, recommend rebuilding with the setup skill's `build_spec_template.py` pattern.

## Example Usage

```text
/policy-audit samples/module_spec.json --config policy_config.json
/policy-authoring:policy-audit 이 정책 스펙 ID 정합성 감사해줘
```
