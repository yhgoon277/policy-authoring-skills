---
name: policy-html-json-check
description: 외부에서 받은 HTML(타팀·레거시·NC 변환본)과 spec JSON의 구조 정합을 사전 점검하고, 이격이 있으면 사용자 확인 후 보수적으로 JSON을 복원한다. Use when intaking external/legacy/NC-converted HTML into the JSON pipeline, when HTML and JSON diverge (PI↔PG 매핑·항목 수 누락), or to verify NC's converted output didn't drop content. Trigger on "HTML↔JSON", "이격", "구조 정합성 검증", "외부 HTML 수입", "NC 변환본 검증", "사전 검토", "조건부 복원", "html json 동기화", "부분변환".
version: 0.3.0
---

# HTML↔JSON 사전 검토·조건부 복원 (HTML/JSON Consistency Check & Reconcile)

> **Claude/Codex에서**: spec JSON과 대조할 HTML(또는 둘이 든 디렉토리)을 준비해 적용을 요청하면 가이드대로 동작한다. `policy-*` 스킬을 함께 설치하면 인계가 완전해진다.

외부에서 들어온 HTML(다른 팀 작성·레거시·NC 변환본)과 우리 spec JSON의 **구조 정합**을 *사전에* 점검하고, 이격이 있으면 **사용자 확인 후에만** 보수적으로 복원한다. ⚠️ **HTML이 자동으로 진실원천이 아니다 — 복원 전 반드시 묻는다.**

> 왜 필요한가: JSON-first 규율(`policy-render-deliver`)은 *우리가* JSON에서 렌더할 때 이격을 막지만, *외부에서 받은* HTML(타팀이 손으로 쓴·NC가 부분변환한)이 JSON과 다를 수 있다. 그 역방향 갭을 잡는 게 이 스킬이다(`policy-integrity-audit`는 JSON 내부만 본다).

## 언제 (워크플로 두 지점)
- **인테이크 게이트** — 외부 HTML을 파이프라인에 들일 때(Phase 0 직전, 1회). reconciled baseline → 빌드. 첫 접촉이 "이 HTML 받았어"면 `policy-intake-router`가 **REVISE-from-HTML**로 분류해 이 스킬로 핸드오프한다(여기가 그 진입점).
- **NC 라운드트립** — NC 업로드(`policy-nc-studio-gate`) 후, NC 변환본이 우리 JSON과 안 맞는지(부분변환 누락) 재점검.

## 1. CHECK (사전 검토 — 읽기 전용, 아무것도 안 고침)
```bash
python3 tools/validate_nc_input.py <spec.json>                                  # 입력 게이트(5 ERROR exit1·2 WARN)
python3 tools/sweep_html_json_gap.py <DIR> [--format md|json]                   # (디렉토리 다건) PI 수 갭 — 부분변환 탐지
python3 tools/diff_nc_html_json.py  <spec.json> --html <HTML> [--format md|json] # 이격 5분류
```
diff의 **5 유형**: ① div앵커-제목 드리프트 ② phantom 참조(정의·HTML 어디에도 없는 ref) ③ **실내용 손실**(HTML PI엔 본문, JSON엔 없음 — 핵심 복원 후보) ④ 이름만(둘 다 본문 없음) ⑤ JSON-only(NC 추가/재번호). 리포트는 `audit/html_json_mismatch_<날짜>.md`로 저장.

## 2. 카테고리별 확인 게이트 (⚠️ 절대 규율 — 승인 전 복원 금지)
이격 유형마다 **HTML이 진실원천인지 사용자에게 묻는다**(`policy-detail-authoring`의 field_review 가/나/다 모델):

| 유형 | 판단 | 처리 |
|---|---|---|
| 가 = 무손실(④·⑤ 다수) | 손실 아님 | 표기만, 진행 |
| 나 = 이격(③ 실내용 손실·② phantom) | HTML이 더 맞나? | **사용자 확인**: "이 유형은 HTML을 진실원천으로 삼아 JSON을 보강할까요?" |
| 다 = 구조 난해(① 드리프트·스키마 비호환) | 자동 불가 | 수동 매핑·플래그(현업 검토 문서) |

- **HTML이 항상 옳다고 가정하지 말 것.** NC가 추가한 ⑤나 우리가 의도적으로 정리한 항목은 JSON이 맞을 수 있다.
- 사용자가 "아니오/모름"이면 **복원하지 않고 리포트만** 남긴다.

## 3. RECONCILE (승인된 유형만 — 보수적·비파괴)
```bash
python3 tools/fix_nc_input.py <spec.json> --html <HTML> --passes <승인유형 매핑> --out <spec_fixed.json>
python3 tools/validate_nc_input.py <spec_fixed.json>                            # 재게이트(통과 확인)
```
- `fix_nc_input`은 **원본 미수정**, `_fixed.json` 신규 작성(멱등). 패스는 보수적(HTML 근거 있는 것만): 실내용 손실→`rebuild`, phantom→`phantom`, ID 형식→`ref_format`·`split_refs`·`module_code`, usecase 조인→`usecase_join`.
- ⚠️ `rebuild`은 HTML이 커버하는 PG의 policy_details를 **전면 대체**(병합 아님) — 그 PG의 JSON-only 항목(⑤)이 빠질 수 있다. ⑤가 의도된 항목이면 `rebuild` 승인을 신중히(병합 필요 시 수동).
- 복원본을 baseline/override에 반영한 뒤 **편집 1건 루프로 검증**: build_spec → audit STRUCTURAL 0 → render. **커밋은 사용자 요청 시만.**
- 미확정 복원은 본문 강제수정 말고 별도 후보 문서(현업 검토)로 분리.

## 4. 사람 결정 게이트 — `decision_guide` (⚠️ 조용히 통과 금지)
reconcile(또는 진단만) 후 **반드시** 결정 가이드를 생성해 **사용자에게 케이스별로 제시**한다. 자동으로 끝나지 않는 상태(특히 미지원 포맷)를 사용자가 명확히 인지하고 무엇을 어떻게 고칠지 알게 하는 것이 이 게이트의 목적이다.
```bash
python3 tools/decision_guide.py <spec.json> --html <HTML> --fixed <auto_spec.json> --out audit/decision_guide_<날짜>.md
```
출력은 케이스별로 **무슨 상태 / 해당 항목 / 무엇을 결정 / 어떻게 수정(이 세션에서)**:
- **⛔ UNMEASURABLE(미지원 포맷)** — 파서가 HTML PI를 0개 인식. `content_loss=0`은 '무손실'이 아니라 **측정불가**(HTML에 정책 본문이 있어도 못 읽음). → (a) 파서 확장 or (b) 수동 매핑. **이 케이스는 절대 '정합/무손실'로 넘기지 말 것.**
- **⚠️ CROSSWALK(스킴 상이 자동병합)** — `_crosswalk.json`의 쌍(html_id↔json_id·name)을 보고 오매칭이 없는지 검토.
- **🟡 DEFERRED(충실성 미달)** — `_recovery_deferred.json`을 HTML 원문과 대조해 **수동 작성**(자동복원 금지=날조 방지).
- **🔵 JSON_ONLY** — 의도된 NC 정제 vs 누락 검토. **🟢 EMPTYROW** 충전 검증 · **🔧 MECHANICAL** 기계적 정정.

> **규율**: 가이드의 `needs_human=예`면 산출물을 '완료'로 표기하지 말고 **사용자 결정을 받는다**. 특히 `blocking`(⛔)이면 reconcile 신뢰 불가로 보고 사람 개입을 명시 요청한다.

## 다른 스킬과의 연계
- **방향 구분(모순 아님)**: 이 스킬 = HTML→JSON(외부 HTML 수입·역방향 점검/복원). `policy-render-deliver` = JSON→HTML(정방향 렌더·수기편집 금지). 이 스킬로 JSON을 confirm/복원한 *뒤*엔 JSON이 단일 진실원천이 되고 render-deliver가 그걸 렌더만 한다.
- 복원 후 JSON 내부 정합(ID·롤업·커버리지) → `policy-integrity-audit`(JSON 내부 전용, 외부 HTML 무관).
- 전체 순서·점검 지점(인테이크·NC 라운드트립) → `policy-workflow-orchestration`.
- 첫 접촉 분류(외부 HTML 수입 = REVISE-from-HTML) → `policy-intake-router`가 이 스킬로 보낸다.
- 도구·config 설치 → `policy-authoring-setup`.
