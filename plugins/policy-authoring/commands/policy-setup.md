---
description: Set up a new policy module with the Policy Authoring skill set.
argument-hint: [module-or-project-context]
---

# Policy Authoring Setup

Use this command when the user wants to install, onboard, or apply the policy-authoring skills to a new policy/requirements module.

## Arguments

The user invoked this command with: $ARGUMENTS

## Instructions

1. Read `skills/policy-authoring-setup/SKILL.md`.
2. Follow the setup workflow for choosing `business_code`, creating project folders, copying tools, generating `policy_config.json`, and running the first build -> audit -> render smoke test.
3. If the user provides project/module context in `$ARGUMENTS`, use it as the starting context.
4. Keep the other policy skills in view as the handoff targets after setup.

## Example Usage

```text
/policy-setup 청구 정책서 새 모듈 세팅해줘
/policy-authoring:policy-setup 데이터 통화 정책 모듈 온보딩
```
