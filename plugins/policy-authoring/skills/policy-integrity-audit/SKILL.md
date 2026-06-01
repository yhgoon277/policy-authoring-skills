---
name: policy-integrity-audit
description: Audit a policy spec's ID and hierarchy integrity end-to-end (UC→PR→FN→sub-function, PR→PG→PI, FN↔PI) and repair stale rollups. Use this whenever the user wants to verify referential and bidirectional consistency, coverage, counts, and trace-matrix freshness of a policy/requirements spec, or sees broken links, orphaned items, or mismatched counts after editing. The audit separates STRUCTURAL violations (deterministically fixable, must reach 0) from SEMANTIC ones (need human judgment). Trigger on "정합성 검토", "ID 감사", "연결관계 확인", "rollup 재계산", "STRUCTURAL", "consistency check", "audit the spec", "기능-PI 연결", or run it automatically after any bulk edit to a spec to confirm nothing broke. Prefer this skill whenever correctness/consistency of the spec graph is in question.
version: 0.1.0
---

# ID 정합성 감사 (Policy Spec Integrity Audit)

> **claude.ai에서**: Settings → Capabilities에서 **Code Execution을 켜고**, 점검할 스펙 JSON을 대화에 업로드한 뒤 이 스킬의 동봉 스크립트(`scripts/audit_id_integrity.py`) 실행을 요청한다. 5개 스킬을 함께 업로드하면 상호참조가 완전해진다.

정책 명세의 계층 ID 연결을 **전수·결정론적으로** 검사하고, 어긋난 롤업을 고치는 방법.

- **대상** = build 산출물 spec JSON. 한 번의 실행으로 UC→PR→FN→세부기능 · PR→PG→PI · FN↔PI 의 참조·역참조·롤업·커버리지·카운트·trace_matrix를 모두 검사한다.
- **도구** = 이 스킬에 동봉된 `scripts/audit_id_integrity.py` (config 구동, 이식 가능).

> **참조 구현**: 통신 "청구및수납관리"(`BIL`). STRUCTURAL 132→0 정화 후 SEMANTIC 39 잔존(전부 의도된 건).

---

## 실행

```bash
python3 <skill>/scripts/audit_id_integrity.py [spec.json] [--config=policy_config.json] [--json] [--only=STRUCTURAL]
```

- 프로젝트별 값(business_code · expected_counts · known_pr_only · 금지토큰)은 **모두 `policy_config.json`에서 읽는다** — 코드 수정 불필요. (config는 `policy-authoring-setup`(⑤)이 생성.)
- `spec.json` 생략 시 `config.spec_path` 사용. 보통 타깃 프로젝트의 `tools/`에 복사해 두고 호출.
- **종료코드**: STRUCTURAL 위반 있으면 1, 없으면 0 → CI/커밋 게이트로 직결.

## 두 종류의 위반

| | 의미 | 조치 | 게이트 |
|---|---|---|---|
| **STRUCTURAL** | 진실원천(subfn_pis·group_id·applies_to override)에서 **결정론적으로 재계산 가능** | 빌드의 롤업 재계산으로 자동 수정 | **반드시 0** (아니면 커밋 금지) |
| **SEMANTIC** | 사람 판단 필요 (PR-레벨 직접 매핑·고아·표현 가독성) | 의도면 화이트리스트로 인정, 아니면 수정 | 0 아니어도 됨(의도된 잔존 관리) |

검사 불변식 A~I의 **상세 정의와 각 항목의 분류**는 → [references/invariants.md](references/invariants.md).

---

## 핵심 원인과 수정 — stale 롤업

가장 흔한 STRUCTURAL 대량 위반의 원인은 **롤업 계산 순서**다.

- **증상**: PI override(applies_to)로 cross-PG 매핑을 추가했는데, PR/FN의 `related_policy_details`·`related_policies`, UC 역참조, trace_matrix가 옛 값 그대로 → B/C/G 그룹 위반 폭증.
- **원인**: 빌드가 롤업을 **override 적용보다 먼저** 계산해서 stale.
- **수정**: `rebuild_rollups(spec)` 를 **PI override 적용 직후**(멱등) 호출. 진실원천(`subfn_pis`·`group_id`·`applies_to`)에서 PR/FN 롤업·PG파생·양방향·trace_matrix를 전부 재생성. PI 본문·세부기능·매핑은 **불변**, 파생 필드만 갱신.
- 이 패턴의 구현 골격은 `policy-authoring-setup`(⑤)이 설치하는 `build_spec_template.py`에 들어 있다. 패턴 설명 → [references/invariants.md](references/invariants.md) 의 "롤업 재계산".

> 즉 **STRUCTURAL은 거의 항상 "롤업을 다시 계산하라"는 신호** — 손으로 매핑을 고치지 말고 빌드의 rebuild_rollups가 돌게 한 뒤 재감사한다.

## 의도된 SEMANTIC 관리

- **PR_only 매핑**(C2 SEMANTIC): PR이 직접 선언했으나 FN 세부기능엔 없는 PI. 의미상 정상이면 `policy_config.json`의 `known_pr_only`에 `[PR-id, PI-id]` 쌍으로 등록 → "알려진 정상"으로 표시. 없는 쌍이 새로 생기면 **★미검토**로 부각되어 검토를 강제.
- **고아/배경 PI**(E4·E6 SEMANTIC): 어떤 FN에도 안 붙는 PI는 "배경/위임/미구현" 의도일 수 있음. 의도면 그대로 두되, 사유는 **렌더에 노출되지 않는 내부 코드 주석**으로 남긴다(근거 필드 X — 기획자 혼란 방지).
- **비프로세스 UC**(E1 SEMANTIC): `process_target=N` UC는 PR이 없도록 의도된 설계(예: 외부 연계).

## 회귀 가드 (편집 후 항상)

1. 빌드 → `audit_id_integrity.py` 실행 → **STRUCTURAL 0** 확인.
2. 실측 카운트가 직전과 같은지(신규 외): 안정화됐으면 `expected_counts`를 config에 고정 → 이후 카운트 누수(stale id 등) 자동 검출.
3. 신규 FN ID 부여 후엔 다른 PR의 FN description이 안 바뀌었는지 diff(① 규칙 5와 연계).
4. 미작업 영역의 내용·매핑은 (용어 치환 외) 불변인지 확인.

---

## 다른 스킬과의 연계
- 위반이 **이름 표현**(그룹 I) → `policy-naming-readability`(②).
- 위반이 **FN ID 충돌·세부기능 커버리지**(A·E·F) → `policy-hierarchy-decomposition`(①).
- 위반이 **PI 매핑·applies_to 인덱스**(A9·B5) → `policy-detail-authoring`(③).
- 빌드/롤업 파이프라인 설치·config 생성 → `policy-authoring-setup`(⑤).
