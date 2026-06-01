---
name: policy-authoring-setup
description: Set up a NEW policy/requirements module to use the policy-authoring skill set, even when the team's project folders and source-document formats differ from the reference project. Use this when a teammate first installs these skills, onboards a new policy module, asks "how do I use these skills on my project", needs to convert their source docs into the canonical spec JSON schema, pick a business code, lay out the project folders, install the build/audit/render tool templates, generate policy_config.json, or run the first build→audit→render smoke test. Trigger on "스킬 설치", "온보딩", "새 모듈 세팅", "프로젝트 세팅", "setup", "how to use these skills", "다른 정책에 적용", "처음 시작". This is the entry point that wires up the other four skills for a project.
version: 0.1.0
---

# 정책서 작성 온보딩·설치 (Setup & Onboarding)

> **claude.ai에서**: 이 스킬의 디렉터리·터미널 절차는 **Claude Code(로컬 프로젝트)** 기준이다. claude.ai에서는 로컬 `tools/` 대신 — Settings → Capabilities에서 **Code Execution을 켜고**, 스펙 JSON을 대화에 업로드한 뒤 이 스킬 `assets/tools/`의 스크립트(audit·build·render) 실행을 요청하면 된다. 표준 스키마(`assets/schema/`)·config(`assets/policy_config.*.json`) 안내는 양쪽 공통.

새 정책 모듈을, 팀원의 **임의의 프로젝트 폴더·소스 형식**에서 이 스킬 세트로 작업할 수 있게 세팅한다.
핵심 통찰: 도구(audit·build·render)는 **표준 spec JSON 스키마**를 인터페이스로 쓴다 — 팀원 소스를
그 형태로 한 번 변환하면 나머지가 다 돌아간다. 이 스킬은 그 변환과 배선을 단계별로 돕는다.

> 이 스킬은 **대화형**이다. 아래 순서대로 진행하되, 각 단계에서 사용자에게 확인하고 다음으로 간다.

## 사전 점검
- 스킬이 설치돼 있어야 한다(이 스킬이 떴다면 설치됨). 설치 방법은 배포 패키지의 INSTALL.md / README 참고(claude.ai = Skills 업로드 / Claude Code = 마켓플레이스 추가).
- 작업 대상은 **사용자의 프로젝트 루트**. 이 스킬의 자산은 `assets/` 아래에 있다(아래에서 복사해 쓴다).

---

## 1단계 — 도메인·business_code 결정
사용자에게 묻는다(모르면 추천):
- 모듈 이름(예: "데이터·통화 관리")과 **`business_code`**(2~5자 대문자, 예: `DATA`·`ROAM`). 모든 ID 프리픽스가 이 코드를 따른다(`PI-<BIZ>-<DOMAIN>-NN-NN`).
- 어떤 **소스 문서**를 갖고 있는지: (a) 이미 구조화된 데이터(스프레드시트·JSON·DB), (b) as-is 문서(HTML/MD)만, (c) 처음부터 설계.

## 2단계 — 디렉터리 구조 생성
사용자 프로젝트 루트에 표준 레이아웃을 만든다(없는 것만):
```
<project>/
├── samples/        # baseline·산출 spec JSON, 미리보기 HTML
├── tools/          # 이 스킬이 설치하는 build·audit·render 도구
├── audit/          # 현업 질문리스트·to-be 후보 등 산출 문서
├── schema/         # 표준 스키마 사본(참고)
└── policy_config.json
```
```bash
mkdir -p <project>/{samples,tools,audit,schema}
```

## 3단계 — 표준 spec 스키마 학습 + baseline 변환 (가장 중요)
1. **스키마를 먼저 읽는다** → [assets/schema/canonical_spec_schema.md](assets/schema/canonical_spec_schema.md). top-level 키·ID 패턴·각 노드 필드·최소 예시가 있다. 사본을 `<project>/schema/`에 복사해두면 편하다.
2. 소스를 **baseline spec JSON**(`samples/<module>_v1.0_spec.json`)으로 변환한다:
   - (a) 구조화 데이터: 컬럼/필드 → 스키마 필드로 매핑하는 **1회용 변환 스크립트**를 작성해 돌린다.
   - (b) as-is 문서만: 계층(UC→PR→FN→PG)을 먼저 추출해 **골격 spec**을 만든다. 정책 상세는 비워두고 4단계 이후 작성 스킬로 채운다.
   - (c) 처음부터: 스키마 최소 예시를 시드로 점진 확장.
   - **검증**: `subfn_pis`·`subfn_ui`·`sub_functions` 3 배열 길이 일치, `policies`=`policy_groups` alias, ID가 `business_code`를 따르는지.

## 4단계 — 도구 설치 + policy_config.json 생성
1. 도구 3종을 `<project>/tools/`로 복사:
   ```bash
   cp assets/tools/build_spec_template.py <project>/tools/build_spec.py
   cp assets/tools/audit_id_integrity.py  <project>/tools/audit_id_integrity.py
   cp assets/tools/render_preview.py      <project>/tools/render_preview.py
   ```
   (audit 도구는 `policy-integrity-audit` 스킬의 것과 동일한 검증본이다.)
2. **`policy_config.json` 생성**: [assets/policy_config.template.json](assets/policy_config.template.json)을 복사해 채운다. 채울 값:
   - `business_code`·`module_title`
   - `baseline_spec_path`·`spec_path`·`preview_out`
   - `term_replacements`(레거시→최종 용어. 예 `{"구시스템":"신시스템"}`. 없으면 `{}`)
   - `expected_counts`는 **처음엔 비워둔다**(`{}`) — 5단계에서 안정화 후 실측치를 넣어 회귀 가드로.
   - `known_pr_only`·`pr_pi_remove`·`manual_pg_fallback`은 처음엔 비워둔다(감사 결과 보고 채운다).
   - 막히면 채워진 실제 예시 참고 → [assets/policy_config.example.json](assets/policy_config.example.json).

## 5단계 — 첫 build → audit → render 스모크 테스트
```bash
cd <project>
python3 tools/build_spec.py --config=policy_config.json        # baseline → spec_path
python3 tools/audit_id_integrity.py --config=policy_config.json # STRUCTURAL 0 목표
python3 tools/render_preview.py --config=policy_config.json     # preview_out HTML
```
- **build_spec.py**의 `PI_CONTENT_OVERRIDES`는 비어 있으면 정책 상세가 안 채워진다. 골격만 통과시키려면 빈 채로 돌려 파이프라인(롤업·trace_matrix·카운트)이 도는지 본다.
- audit가 STRUCTURAL>0이면 거의 항상 **롤업 재계산 누락**이나 **참조 오타** → `policy-integrity-audit` 스킬로 진단.
- 안정화되면 audit가 출력한 **실측 카운트**를 `expected_counts`에 고정 → 이후 누수 자동 검출.

## 6단계 — 방법론 스킬로 인계
세팅이 끝나면 실제 작성은 4개 방법론 스킬로:
- 계층·기능을 만든다/다듬는다 → **`policy-hierarchy-decomposition`**
- 명칭·설명을 기획자 친화적으로 → **`policy-naming-readability`**
- 정책 상세(PI)를 쓰고 팩트체크·to-be → **`policy-detail-authoring`**
- 편집 후 정합성 검증 → **`policy-integrity-audit`** (STRUCTURAL 0)

권장 루프: **(작성/편집) → build → audit(STRUCTURAL 0) → render → 커밋**.

---

## 운영 가드 (참조 구현에서 정착)
- 커밋은 **선별 add** — `git add -A` 금지(무관 파일 혼입 방지). 도구·spec·산출 HTML·감사 문서만.
- 표/수치는 **원문 직접 카운트**(서브에이전트 초안은 검증 전 신뢰 금지).
- to-be 개선안은 **본문 직접수정 금지** — 별도 문서에 후보만(작성 스킬 참조).
- 컨텍스트 한도가 다가오면 안전 체크포인트(커밋)에서 멈추고 알린다.
