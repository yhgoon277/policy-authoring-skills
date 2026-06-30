---
name: policy-authoring-setup
description: Set up a NEW policy/requirements module to use the policy-authoring skill set, even when the team's project folders and source-document formats differ from the reference project. Use this when a teammate first installs these skills, onboards a new policy module, asks "how do I use these skills on my project", needs to convert their source docs into the canonical spec JSON schema, pick a business code, lay out the project folders, install the build/audit/render tool templates, generate policy_config.json, or run the first build→audit→render smoke test. Trigger on "스킬 설치", "온보딩", "새 모듈 세팅", "프로젝트 세팅", "setup", "how to use these skills", "다른 정책에 적용", "처음 시작". This is the entry point that wires up the other nine skills for a project.
---

# 정책서 작성 온보딩·설치 (Setup & Onboarding)

> **Claude/Codex에서**: 디렉터리·터미널 절차는 로컬 프로젝트 기준. claude.ai에서는 Code Execution에 spec JSON을 올려 `assets/tools/` 스크립트(build·audit·render·enrich·splice) 실행을 요청, Codex/Claude Code는 로컬 셸. 스키마(`assets/schema/`)·config(`assets/policy_config.template.json`)는 공통.

새 정책 모듈을 **임의의 프로젝트 폴더·소스 형식**에서 이 스킬 세트로 작업할 수 있게 세팅한다.
핵심: 도구는 **표준 spec JSON**을 인터페이스로 쓴다 — 소스를 그 형태의 baseline으로 한 번 변환하면 build→audit→render→(enrich)→splice 전체가 돈다. 한 프로젝트가 여러 **작성 단위(unit)**를 가질 수 있고(`policy_config.json`의 `units.<unit>`), 모든 도구는 `--config=… --unit=…`로 단위를 고른다.

> 이 스킬은 **대화형**이다. 단계마다 사용자에게 확인하고 다음으로.

## 사전 점검
- 스킬 설치됨(이 스킬이 떴으면 OK). 자산은 `assets/` 아래.
- 작업 대상은 **사용자 프로젝트 루트**.

---

## 1단계 — 도메인·business_code 결정
- **모듈 이름** + **`business_code`**(2~5자 대문자, 예 `DATA`·`ROAM`). 모든 ID가 `…-<BIZ>-<DOMAIN>-…`.
- **작성 단위(unit)**: 한 모듈이 도메인별 독립 spec 여러 개로 갈리면 unit을 나눈다(예 `hub`·`faq`·`store`). 단일이면 unit 1개.
- **소스 형식**: (a) 구조화 데이터(스프레드시트/JSON/DB), (b) as-is 문서(HTML/MD)만, (c) 처음부터, (d) **NC AI 자동초안**(있으면 `convert_autodraft.py`로 baseline 변환).

## 2단계 — 디렉터리 구조
```
<project>/
├── samples/{baseline,preview,NC_auto}/   # spec JSON·미리보기 HTML·자동초안
├── tools/{,coverage,overrides}/          # 설치 도구 + unit별 override
├── audit/                                # 커버리지 매트릭스·현업 질문·to-be 후보
├── data/index/                           # 지식 인덱스·요구 커버리지 jsonl
├── schema/                               # 표준 스키마 사본
└── policy_config.json
```
```bash
mkdir -p <project>/{samples/{baseline,preview,NC_auto},tools/{coverage,overrides},audit,data/index,schema}
```

## 3단계 — 표준 스키마 학습 + baseline 변환 (가장 중요)
1. **스키마부터 읽는다** → [assets/schema/canonical_spec_schema.md](assets/schema/canonical_spec_schema.md): top-level 키·ID 패턴·노드 필드·**NC 풀스키마 필드(decision_spec·rule_type·mockup_binding·review_status·usecase_id·details)**·**requirement_links**·최소 예시. 사본을 `<project>/schema/`에 둔다.
2. 소스를 **baseline spec JSON**(`samples/baseline/<module>_<unit>_v1.0_spec.json`)으로:
   - (a) 구조화: 컬럼→필드 매핑 1회용 스크립트.
   - (b) as-is만: 계층(UC→PR→FN→PG) 골격 → 정책 상세는 작성 스킬로.
   - (c) 처음부터: 최소 예시 시드.
   - (d) NC 자동초안: `python3 tools/convert_autodraft.py …`로 baseline 변환(unit당 1회).
   - **검증**: `subfn_pis`·`subfn_ui`·`sub_functions` 3 배열 길이 일치, `policies`=`policy_groups` alias, ID가 `business_code` 따름.

## 4단계 — 전체 toolchain 설치 + policy_config.json
**도구 전체를 `<project>/tools/`로 복사**(assets/tools/* 전부, coverage/ 포함):
```bash
A=assets/tools
cp $A/build_spec_template.py <project>/tools/build_spec.py
cp $A/audit_id_integrity.py  <project>/tools/audit_id_integrity.py
cp $A/render_preview.py      <project>/tools/render_preview.py
cp $A/preview_style.css      <project>/tools/preview_style.css   # render가 인라인
cp $A/enrich_spec.py         <project>/tools/enrich_spec.py      # NC 풀스키마·requirement_links
cp $A/splice_nc_html.py      <project>/tools/splice_nc_html.py   # NC 변환본에 리치 섹션 이식
cp $A/convert_autodraft.py   <project>/tools/convert_autodraft.py
cp $A/extract_index.py       <project>/tools/extract_index.py    # 지식 인덱스 jsonl
cp $A/coverage_gate.py       <project>/tools/coverage_gate.py    # 요구 매핑 보조 게이트
cp $A/validate_nc_input.py   <project>/tools/validate_nc_input.py   # 입력 spec 사전 게이트
cp $A/diff_nc_html_json.py   <project>/tools/diff_nc_html_json.py   # HTML↔JSON 이격 진단
cp $A/nc_html_link.py        <project>/tools/nc_html_link.py        # HTML→PG/PI 매핑 파서
cp $A/sweep_html_json_gap.py <project>/tools/sweep_html_json_gap.py # PI 수 갭 스캔(인자: DIR 디렉토리)
cp $A/fix_nc_input.py        <project>/tools/fix_nc_input.py        # HTML 근거 보수적 복원(비파괴)
cp $A/decision_guide.py      <project>/tools/decision_guide.py      # 사람 결정·수정 안내 가이드(케이스별)
mkdir -p <project>/tools/coverage
cp $A/coverage/*.py $A/coverage/*.workflow.js <project>/tools/coverage/
```
- audit 도구는 `policy-integrity-audit` 스킬의 것과 동일 검증본.
- ⚠️ `coverage/*.workflow.js`는 **유닛당 WORK·NB 2상수 수동 편집**(파일 상단 주석 참조; Workflow args 전달 버그 회피). 기본 `audit/_coverage_work_<unit>` 또는 env `COVERAGE_WORK`.

**`policy_config.json` 생성**: [assets/policy_config.template.json](assets/policy_config.template.json) 복사. multi-unit shape:
- top-level: `business_code`·`module_title`·`term_replacements`·`term_skip_keys`·`naming_banned_tokens`·`min_fn_per_pr`·`nc_required_fields`.
- `units.<unit>`: `domain`·`title`·`autodraft_spec`·`baseline_spec_path`·`spec_path`·`preview_out`·`expected_counts{}`·`known_pr_only[]`·(NC 업로드 시) `requirement_links{}`.
- 막히면 실제 예시 → [assets/policy_config.example.json](assets/policy_config.example.json).

### 유닛 온보딩 체크리스트 (unit 추가마다)
- [ ] `units.<unit>` 블록 추가(template의 `<UNIT>`/`<DOMAIN>` 치환, 경로 채움).
- [ ] `tools/overrides/<unit>.py` 스텁 생성 — PI 본문·`applies_to`·`UI_SUBFNS`·`rule_type`/`decision_spec` override 딕셔너리(처음엔 빈 채). 계층·명칭·PR/FN 신설은 baseline 직접 편집.
- [ ] (NC 자동초안 있으면) `convert_autodraft`로 baseline 생성.
- [ ] (지식관리) `extract_index`로 `data/index/*.jsonl` 생성.
- [ ] (NC 업로드 대비) `requirement_links` 블록은 **placeholder**로(`matrix_path`·`nc_coverage_path`·`requirements_index_path`·`nc_only_dispositions{}` 빈 채). 매트릭스·jsonl 준비되면 채운다.
- [ ] `expected_counts`는 **빈 채로**(`{}`) — 5단계 안정화 후 실측 고정(회귀 가드).
- [ ] `known_pr_only`·`pr_pi_remove`·`manual_pg_fallback` 빈 채(감사 보고 채운다).

## 5단계 — 첫 스모크 테스트: build → audit(A–L) → render → splice
```bash
cd <project>
python3 tools/build_spec.py         --config=policy_config.json --unit=<unit>   # baseline→spec_path (apply_overrides→rollups→bake→enrich)
python3 tools/audit_id_integrity.py --config=policy_config.json --unit=<unit>   # 그룹 A–L, STRUCTURAL 0 목표
python3 tools/render_preview.py     --config=policy_config.json --unit=<unit>   # preview_out HTML (6섹션)
python3 tools/splice_nc_html.py     --config=policy_config.json --unit=<unit> --base=<NC 변환 HTML or 스텁>   # 배포본(섹션 5·6 교체+리치 CSS)
```
- **audit 그룹**: A–I 기본 정합, **J**(PR당 FN<min·PR명==FN명, SEMANTIC), **K**(NC 필수필드 존재, STRUCTURAL — `nc_required_fields` 구동), **L**(requirement_links dangling·유일성·양방향). ⚠️ **K/L은 config에 `nc_required_fields`/`requirement_links`가 없으면 no-op** — NC 업로드 전이면 자연히 건너뛴다.
- override가 비면 정책 상세 매핑이 안 채워진다. 골격만 볼 땐 빈 채, 정합성까지 보려면 PI 1개에 `applies_to` 지정.
- STRUCTURAL>0이면 대개 롤업 재계산 누락·참조 오타 → `policy-integrity-audit`로 진단.
- splice의 `--base`는 NC 변환 HTML이 아직 없으면 render 산출 preview를 스텁 base로 줘 파이프라인만 확인.
- 안정화되면 audit 실측 카운트를 `expected_counts`에 고정.

## 6단계 — 방법론·도구 스킬로 인계
세팅 후 실제 작성:
- 계층·기능 분화 → **`policy-hierarchy-decomposition`**
- 명칭·설명 가독성 → **`policy-naming-readability`**
- 정책 상세(PI)·팩트체크·to-be → **`policy-detail-authoring`**
- 편집 후 정합성 → **`policy-integrity-audit`**(STRUCTURAL 0)

추가 스킬(슬래시 `/policy-…` 또는 자동 트리거):
- **`policy-render-deliver`** — render→splice 배포본 생성(리치 섹션 이식).
- **`policy-nc-studio-gate`** — NC스튜디오 업로드 게이트 대비(G2 requirement_links·G5 decision_spec 판정축, enrich·audit K/L).
- **`policy-html-json-check`** — 외부/NC 변환 HTML↔JSON 사전 정합 검토 + (사용자 확인 후) 보수적 복원.
- **`policy-workflow-orchestration`** — 전체 phase 시퀀스·편집 1건 루프 컨덕터(어느 스킬을 언제).

권장 루프: **(작성/편집 override) → build → audit(STRUCTURAL 0) → render → splice → 선별 커밋**.

---

## 운영 가드 (참조 구현에서 정착)
- 커밋은 **선별 add**(`git add -A` 금지). 편집 override + 재빌드 spec + preview만.
- 표/수치는 **원문 직접 카운트**(롤업·서브에이전트 초안 검증 전 신뢰 금지).
- to-be 개선안은 **본문 직접수정 금지** — `field_review`(붉은 배지)·`internal_integration`·별도 문서로.
- 내부 메모는 렌더되는 `source_note` 말고 build 스크립트 `#` 주석에.
- 컨텍스트 한도 임박 시 안전 체크포인트(직전 커밋)에서 멈추고 알린다.
