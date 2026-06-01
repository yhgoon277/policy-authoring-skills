---
name: policy-detail-authoring
description: Author the "정책 상세" (Policy Items / PI) of a policy spec — readable rule + criteria + tables + customer notice + provenance, mapped N:M to sub-functions — then fact-check them against as-is sources, flag uncertain values with a red review badge, and capture to-be improvement candidates separately. Use this whenever the user is writing or upgrading policy-detail content, wants matrix/multi-axis values rendered as tables, needs a "현업 검토 필요" flag for values that are system-migration-dependent or to-be-undefined, or wants to archive to-be revision candidates WITHOUT editing the policy body. Trigger on "정책 상세 작성", "PI 재작성", "표로 정리", "팩트체크", "현업 검토 필요", "field_review", "to-be 후보", "근거 표기". Prefer this skill when the work is about the content of individual policy items rather than the hierarchy shape or naming.
version: 0.1.0
---

# 정책 상세 작성·팩트체크·to-be (Policy Detail Authoring, Fact-Check & To-Be)

> **claude.ai에서**: 작성·점검할 PI와 as-is 근거를 대화에 붙여넣거나 업로드하고 적용을 요청하면 가이드대로 동작한다. 표 미리보기가 필요하면 Code Execution을 켜고 스펙 JSON을 올려 렌더 스크립트를 돌린다. 5개 스킬을 함께 업로드 권장.

정책 그룹(PG)의 각 정책 상세(PI)를 **기획자가 바로 이해하는 가독형**으로 쓰고, 세부기능에 N:M 매핑하고, as-is 사실과 대조해 **불확실한 값은 붉은 배지로 표면화**하고, to-be 개선안은 **본문을 건드리지 않고 따로 모은다**.

> **참조 구현**: 통신 "청구및수납관리"(`BIL`) 19 PG·210 PI. 표 32·field_review 72건을 이 방식으로 작성.

---

## 산출물 (PG 1개 = 1 청크)
그 PG의 **모든 PI**를 가독형으로 재작성하고, PI를 **세부기능(`FN#idx`) 단위**로 매핑한다. 빌드의 PI 내용 override(예: `PI_CONTENT_OVERRIDES[pi_id]`)에 각 PI를 다음 필드로 넣는다:

```
rule · criteria[] · notice · source_note · applies_to[]   (기본)
tables[] · field_review                                    (선택: 표 / 붉은 배지)
```

각 필드의 의미·렌더 형식·N:M 매핑·용어 치환 규칙 → **[references/pi-format.md](references/pi-format.md)** (작성 전 반드시 일독).

## 작성 원칙 (절대)
1. **풀어쓴다** — PI/FN 라벨·내부 용어를 그대로 옮기지 말고 뜻을 일상어로. (→ 가독성 세부는 `policy-naming-readability`(②))
2. **내부 코드·약어 제거/풀이**, 본문에 **PI/PG/PR ID 미참조**(ID는 매핑·근거 필드로만).
3. **할루시네이션 0** — 모든 값은 근거로 추적되는 사실. **표·수치는 원문을 직접 세어** 확인(추론 금지). 확실치 않으면 값을 만들지 말고 `field_review`로 플래그.
4. 정형 골격·번역투 금지.

## 팩트체크 + 불확실 표기 (가/나/다)
작성하며 각 값의 **확실성**을 분류한다:
- **가 = 확정** (as-is 명문 + 시스템 무관 규칙) → 표기 없음.
- **나 = 시스템 이관 미확정** (값/코드/필드가 특정 시스템 산출물 → 이관 후 동일 보장 안 됨) → **붉은 "현업 검토 필요" 배지** + 질문리스트.
- **다 = to-be 미정** (as-is 근거 없이 to-be가 설계 중) → 배지 + 질문리스트.

분류 기준·플래깅 경계·7항목 팩트체크 체크리스트 → **[references/factcheck-and-tobe.md](references/factcheck-and-tobe.md)**.

## to-be 수정후보 (본문 직접수정 금지)
현 PI를 to-be로 개선할 net-new 후보는 **별도 문서에만** 적는다(사용자가 추후 직접 반영). "미정 값"(현업 확인 대상=field_review)과 "개선 제안"(to-be 후보)을 구분한다. 6대 지향·후보 문서 템플릿 → [references/factcheck-and-tobe.md](references/factcheck-and-tobe.md).

---

## 워크플로 (청크마다)
1. **근거 로드** — 그 PG PI들의 출처(as-is 문서 해당 라인·수치 카탈로그·to-be 드래프트). **표/수치는 원문 직접 카운트.**
2. **PI 재작성 + 세부기능 매핑 + UI 표기** — override dict에. 순수 UI/표현·내부처리 세부기능은 정책 불필요(UI 표기) → 1:1 강제 금지.
3. **빌드** → 카운트 불변 확인(PI·세부기능 총수).
4. **감사** → `policy-integrity-audit`(④)로 **STRUCTURAL 0**. (applies_to 인덱스·커버리지·롤업)
5. **렌더** → 표·콜아웃·근거 muted·붉은 배지 확인. 본문에 시스템 원형 용어 누설 0(근거엔 보존).
6. **spot check → 커밋** (도구 + 정규 spec + 렌더 산출물 + 감사 문서만 선별 add).

> 큰 PG는 서브에이전트로 초안 → **메인이 원문 직접 대조 검증**(서브에이전트는 카운트·수치·이스케이프 오류 이력 → 표/수치는 반드시 직접 카운트).

## 커버리지 불변식
그 PG가 관할하는 모든 세부기능이 **≥1 PI 또는 UI**, 모든 FN이 **≥1 PI**. cross-PG(다른 PR/FN의 세부기능)도 매핑 가능하나 **타 PG 소관 정책을 그 청크에서 억지로 만들지 말 것**(가짜 매핑 금지). 전수 커버는 전 PG 완료 시점의 불변식.

## 다른 스킬과의 연계
- 문구·명칭 다듬기 → `policy-naming-readability`(②) / 세부기능 구조 → `policy-hierarchy-decomposition`(①).
- 작성 후 매핑·롤업 검증 → `policy-integrity-audit`(④) (STRUCTURAL 0).
- 렌더·빌드 도구·config 설치 → `policy-authoring-setup`(⑤).
