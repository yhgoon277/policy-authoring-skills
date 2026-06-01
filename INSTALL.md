# 설치 & 온보딩 가이드

이 문서는 **스킬을 처음 받는 팀원**이 자기 환경(다른 프로젝트 폴더·다른 소스 형식)에서
`policy-authoring` 스킬 세트를 설치하고 새 정책 모듈에 적용하는 전 과정을 안내합니다.
대화형으로 진행하려면 설치 후 `/policy-authoring-setup` 을 실행하세요 — 이 문서는 그 과정의 읽기용 레퍼런스입니다.

## 0. 사전 요구사항
- **사용 환경 (둘 중 하나)**
  - **claude.ai / Claude Desktop** (Free~Enterprise) — Settings → Capabilities에서 **Code Execution·File Creation 켜기** 필수(스킬 스크립트 실행 전제). Team/Enterprise는 관리자가 Org 설정에서 Skills+Code Execution 활성화.
  - **Claude Code** (플러그인·스킬 지원 버전).
- **python3** (3.8+; 도구는 표준 라이브러리만 — 추가 설치 불필요). claude.ai는 내장 코드 실행을 사용.
- **git** (Claude Code 마켓플레이스 설치 또는 팀 배포 시).

---

## 1. 설치

### 방식 A — claude.ai / Claude Desktop (팀원 대부분 · Skills 업로드)
1. **Settings → Capabilities**에서 **Code Execution·File Creation을 켭니다**(없으면 스킬 스크립트가 안 돎). Team/Enterprise는 관리자가 Org 설정에서 Skills+Code Execution 활성화.
2. 배포물에서 **스킬 ZIP 5개**를 준비합니다(repo의 `dist/` 폴더, 또는 번들 `policy-authoring-skills-all.zip`을 풀면 5개가 나옴).
3. **Customize → Skills → "+" → Create skill → Upload a skill**(데스크탑: **Settings → Capabilities → Skills → Upload skill**)에서 ZIP을 **하나씩 5개** 업로드합니다(스킬 1개 = ZIP 1개).
4. 5개를 모두 올리면 스킬 간 상호 참조까지 완전해집니다.

### 방식 B — Claude Code (터미널/IDE · 마켓플레이스)
git 저장소로 올렸다면(아래 6장):
```bash
/plugin marketplace add <git-url>          # 예: github.com/<org>/policy-authoring-skills
/plugin install policy-authoring@mypart-skills
```
로컬 경로도 가능: `/plugin marketplace add /path/to/policy-authoring-skills`. CLI는 `claude plugin marketplace add <경로>` → `claude plugin install policy-authoring@mypart-skills`.

### 1-1. 설치 확인
- **claude.ai**: Skills 목록에 `policy-*` 5개가 보이면 OK.
- **Claude Code**: `claude plugin list` → `policy-authoring@mypart-skills : enabled`. 새 세션에서 5개 스킬(`policy-*`)이 사용 가능 목록에 노출.

---

## 2. 새 모듈 온보딩 (핵심 통찰: 표준 스키마가 인터페이스)
도구(audit·build·render)는 **표준 spec JSON** 하나를 입출력으로 씁니다. 내 소스를 그 형태로
한 번 변환하면 나머지가 다 돌아갑니다. 프로젝트별 값은 **`policy_config.json`** 으로만 바뀝니다.

### 2-1. 도메인·business_code 정하기
- 모듈 이름과 **`business_code`**(2~5자 대문자, 예 `DATA`·`ROAM`). 모든 ID가 `…-<BIZ>-<DOMAIN>-NN` 을 따릅니다.

### 2-2. 폴더 만들기 (내 프로젝트 루트)
```bash
mkdir -p <project>/{samples,tools,audit,schema}
```
| 폴더 | 용도 |
|---|---|
| `samples/` | baseline·산출 spec JSON, 미리보기 HTML |
| `tools/` | 설치할 build·audit·render 도구 |
| `audit/` | 현업 질문리스트·to-be 후보 등 산출 문서 |
| `schema/` | 표준 스키마 사본(참고) |

### 2-3. 도구 복사
플러그인 설치 위치의 `skills/` 에서 도구 3종을 내 `tools/` 로 복사:
```
skills/policy-integrity-audit/scripts/audit_id_integrity.py   → tools/audit_id_integrity.py
skills/policy-authoring-setup/assets/tools/build_spec_template.py → tools/build_spec.py
skills/policy-authoring-setup/assets/tools/render_preview.py  → tools/render_preview.py
```
(`/policy-authoring-setup` 을 실행하면 이 복사를 대신 해줍니다.)

### 2-4. policy_config.json 작성
`assets/policy_config.template.json` 을 프로젝트 루트로 복사해 채웁니다:
- `business_code`·`module_title`
- `baseline_spec_path`·`spec_path`·`preview_out`
- `term_replacements`: 레거시→최종 용어(없으면 `{}`)
- `expected_counts`: **처음엔 `{}`** — 안정화 후 실측치 고정(회귀 가드)
- `known_pr_only`·`pr_pi_remove`·`manual_pg_fallback`: 처음엔 비움(감사 보고 채움)
- 막히면 채워진 실제 예시: `assets/policy_config.example.json`

### 2-5. 첫 스모크 테스트
```bash
cd <project>
python3 tools/build_spec.py --config=policy_config.json
python3 tools/audit_id_integrity.py --config=policy_config.json   # STRUCTURAL 0 목표
python3 tools/render_preview.py --config=policy_config.json
```

---

## 3. 소스 → 표준 spec 변환 가이드
스키마 정의: `assets/schema/canonical_spec_schema.md` (top-level 키·ID 패턴·필드·최소 예시).

| 내 소스 | 변환 방법 |
|---|---|
| **구조화 데이터**(스프레드시트·JSON·DB) | 컬럼/필드 → 스키마 필드로 매핑하는 **1회용 변환 스크립트** 작성 |
| **as-is 문서**(HTML/MD)만 | 계층(UC→PR→FN→PG)을 먼저 추출해 **골격 spec** 생성 → 정책 상세는 작성 스킬로 채움 |
| **처음부터** | 스키마 최소 예시를 시드로 점진 확장 |

검증 포인트: `sub_functions`·`subfn_pis`·`subfn_ui` 3 배열 길이 일치 · `policies`=`policy_groups` alias · ID가 `business_code` 준수.

---

## 4. 표준 작업 루프
**(작성/편집) → build → audit (STRUCTURAL 0) → render → 커밋**
- 작성/편집은 4개 방법론 스킬(분화·가독성·정책상세·감사)이 담당.
- 커밋은 **선별 add**(`git add -A` 금지). 도구·spec·산출 HTML·감사 문서만.

---

## 5. 업데이트 / 제거
```bash
claude plugin marketplace update mypart-skills   # 최신 스킬 받기
claude plugin uninstall policy-authoring@mypart-skills
claude plugin marketplace remove mypart-skills
```

## 6. 팀 배포 (배포자용)
1. `policy-authoring-skills/` 디렉터리를 **독립 git 저장소**로 올립니다(이 폴더가 마켓플레이스 루트 = `.claude-plugin/marketplace.json` 포함).
2. 팀원에게 저장소 URL 공유 → 각자 `1장 방식 A`로 설치.
3. 스킬 개선 시 저장소에 push → 팀원은 `marketplace update` 로 갱신.

## 7. 트러블슈팅
- **스킬이 안 뜸**: `claude plugin list` 로 enabled 확인 → 새 세션 시작. 마켓플레이스 검증 실패 시 `marketplace update` 출력의 오류(주로 SKILL.md frontmatter 또는 JSON 문법) 확인.
- **audit STRUCTURAL>0**: 거의 항상 롤업 재계산 누락 또는 참조 오타 → `policy-integrity-audit` 스킬로 진단(보통 build의 rebuild_rollups가 정정).
- **카운트가 매 빌드 +1로 샘**: baseline을 다시 빌드 입력으로 쓰는 구성에서 옛/새 id 불일치 PI가 생기는 경우 — `pr_pi_remove`/정리로 끝단 차단.
- **본문에 레거시 용어 잔존**: `term_replacements` 확인. 근거(`source_note` 등)는 의도적으로 치환 제외(원형 보존).
