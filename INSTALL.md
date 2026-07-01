# 설치 & 온보딩 가이드

이 문서는 **스킬을 처음 받는 팀원**이 자기 환경(다른 프로젝트 폴더·다른 소스 형식)에서
`policy-authoring` 스킬 세트를 설치하고 새 정책 모듈에 적용하는 전 과정을 안내합니다.
대화형으로 진행하려면 설치 후 `/policy-authoring-setup` 을 실행하세요 — 이 문서는 그 과정의 읽기용 레퍼런스입니다.

## 0. 사전 요구사항
- **사용 환경 (둘 중 하나)**
  - **claude.ai / Claude Desktop** (Free~Enterprise) — Settings → Capabilities에서 **Code Execution·File Creation 켜기** 필수(스킬 스크립트 실행 전제). Team/Enterprise는 관리자가 Org 설정에서 Skills+Code Execution 활성화.
  - **Claude Code** (플러그인·스킬 지원 버전).
  - **Codex app / Codex CLI** (Codex 플러그인 또는 `.agents/skills` 지원 버전).
- **python3** (3.8+; 도구는 표준 라이브러리만 — 추가 설치 불필요). claude.ai는 내장 코드 실행을 사용.
- **git** (Claude Code 마켓플레이스 설치 또는 팀 배포 시).

---

## 1. 설치

> ⚠️ **마켓플레이스 이름은 도구별로 다릅니다(정상 — 오류 아님)**: 각 도구가 자기 매니페스트를 읽기 때문입니다.
> - **Claude Code**: `mypart-skills` → `policy-authoring@mypart-skills`
> - **Codex**: `policy-authoring-skills` → `policy-authoring@policy-authoring-skills`
>
> **autoUpdate는 Claude 전용**입니다(마켓플레이스 entry `autoUpdate:true`). **Codex엔 autoUpdate가 없으니** 갱신은 수동 `codex plugin marketplace upgrade policy-authoring-skills`로 합니다. 두 도구 모두 **`release` 핀**을 씁니다(검증 커밋만).

### 방식 A — claude.ai / Claude Desktop (팀원 대부분 · Skills 업로드)
1. **Settings → Capabilities**에서 **Code Execution·File Creation을 켭니다**(없으면 스킬 스크립트가 안 돎). Team/Enterprise는 관리자가 Org 설정에서 Skills+Code Execution 활성화.
2. 배포물에서 **스킬 ZIP 10개**를 준비합니다(repo의 `dist/` 폴더, 또는 번들 `policy-authoring-skills-all.zip`을 풀면 10개가 나옴).
3. **Customize → Skills → "+" → Create skill → Upload a skill**(데스크탑: **Settings → Capabilities → Skills → Upload skill**)에서 ZIP을 **하나씩 10개** 업로드합니다(스킬 1개 = ZIP 1개).
4. 10개를 모두 올리면 스킬 간 상호 참조까지 완전해집니다.

### 방식 B — Claude Code (터미널/IDE · 마켓플레이스)
git 저장소로 올렸다면(아래 6장):
```bash
/plugin marketplace add yhgoon277/policy-authoring-skills@release   # github · release 핀 · 자동업데이트
/plugin install policy-authoring@mypart-skills
```
로컬 경로도 가능: `/plugin marketplace add /path/to/policy-authoring-skills`. CLI는 `claude plugin marketplace add yhgoon277/policy-authoring-skills@release` → `claude plugin install policy-authoring@mypart-skills`.
> 기존에 directory 소스로 추가했다면 `claude plugin marketplace remove mypart-skills` 후 위 github 형식으로 다시 add 합니다. private repo·autoUpdate·`GITHUB_TOKEN` 등 마이그레이션 상세 → [DEPLOY.md](DEPLOY.md).

### 방식 C — Codex app (workspace 공유 · 권장)
같은 ChatGPT/Codex workspace 팀원에게는 Codex 플러그인 공유가 가장 간단합니다.

1. 배포자가 Codex app에서 이 repo의 Codex 플러그인(`policy-authoring`)을 설치합니다.
2. plugin details에서 **Share**를 눌러 workspace 팀원에게 공유합니다.
3. 팀원은 공유된 플러그인을 설치한 뒤 새 대화에서 `policy-*` 10개 스킬이 보이는지 확인합니다.

GitHub repo는 source of truth로 유지하고, app 공유는 팀원 설치 UX를 단순하게 만드는 배포면으로 봅니다.

### 방식 D — Codex CLI (GitHub marketplace · 재현 가능한 설치)
repo 루트의 `.agents/plugins/marketplace.json`이 Codex marketplace entry입니다.

```bash
codex plugin marketplace add yhgoon277/policy-authoring-skills --ref release   # 안정 핀(최신 개발은 --ref main)
codex plugin add policy-authoring@policy-authoring-skills
codex plugin list
```

로컬 clone으로 검증할 때는 현재 사용자 설정을 오염시키지 않도록 임시 `CODEX_HOME`을 권장합니다.

```bash
CODEX_HOME=/tmp/codex-policy-test codex plugin marketplace add /path/to/policy-authoring-skills
CODEX_HOME=/tmp/codex-policy-test codex plugin add policy-authoring@policy-authoring-skills
CODEX_HOME=/tmp/codex-policy-test codex plugin list
```

### 방식 E — Codex 직접 설치 (`.agents/skills` · 임시/개인)
플러그인 공유나 marketplace 없이 10개 스킬 폴더를 직접 둘 수도 있습니다.

```bash
mkdir -p ~/.agents/skills
cp -R plugins/policy-authoring/skills/* ~/.agents/skills/
```

팀 repo에 함께 두려면 해당 작업 repo의 `.agents/skills/`에 10개 스킬 폴더를 체크인합니다.

### 1-1. 설치 확인
- **claude.ai**: Skills 목록에 `policy-*` 10개가 보이면 OK.
- **Claude Code**: `claude plugin list` → `policy-authoring@mypart-skills : enabled`. 새 세션에서 10개 스킬(`policy-*`)이 사용 가능 목록에 노출.
- **Codex app/CLI**: `codex plugin list`에 `policy-authoring@policy-authoring-skills`가 installed/enabled로 보이고, 새 대화의 스킬 목록에 `policy-*` 10개가 노출되면 OK. 플러그인 설치라면 초기 5종 단축형 `/policy-setup`, `/policy-audit`, `/policy-detail`, `/policy-naming`, `/policy-hierarchy`와 나머지 5종의 네임스페이스 형식 `/policy-authoring:<스킬명>` slash command가 자동완성됩니다. 직접 설치라면 `~/.agents/skills` 또는 repo `.agents/skills` 아래 10개 폴더가 있으면 됩니다.

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
- `pi_content_overrides`·`ui_subfns`·`fn_desc_overrides`: 처음엔 비움(스모크 테스트나 소규모 모듈은 config에 직접 작성 가능)
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

Codex CLI 설치를 쓴 경우:
```bash
codex plugin marketplace upgrade policy-authoring-skills
codex plugin remove policy-authoring@policy-authoring-skills
codex plugin add policy-authoring@policy-authoring-skills
```

제거만 할 때:
```bash
codex plugin remove policy-authoring@policy-authoring-skills
codex plugin marketplace remove policy-authoring-skills
```

## 6. 팀 배포 (배포자용)
> 버전 핀(`release`)·autoUpdate·directory→github 마이그레이션·private 접근(`GITHUB_TOKEN`)의 단계별 런북 → **[DEPLOY.md](DEPLOY.md)**.
1. `policy-authoring-skills/` 디렉터리를 **독립 git 저장소**로 올립니다. 이 폴더가 Claude marketplace 루트(`.claude-plugin/marketplace.json`)이면서 Codex marketplace 루트(`.agents/plugins/marketplace.json`)입니다.
2. Codex app 팀원에게는 배포자가 플러그인을 설치한 뒤 plugin details의 **Share**로 공유합니다.
3. CLI 중심 팀원에게는 `방식 D` 명령을 안내합니다.
4. claude.ai / Claude Desktop 팀원에게는 기존 `dist/`의 스킬 ZIP 10개 또는 `policy-authoring-skills-all.zip`을 안내합니다.
5. 스킬 개선 시 저장소에 push → Codex/Claude Code 사용자는 각자 marketplace update로 갱신하고, app 공유 플러그인은 새 버전 설치·공유 흐름으로 갱신합니다.

## 7. 트러블슈팅
- **스킬이 안 뜸**: `claude plugin list` 로 enabled 확인 → 새 세션 시작. 마켓플레이스 검증 실패 시 `marketplace update` 출력의 오류(주로 SKILL.md frontmatter 또는 JSON 문법) 확인.
- **Codex 플러그인이 안 뜸**: `codex plugin marketplace list`에서 `policy-authoring-skills`가 보이는지 확인 → 없으면 `codex plugin marketplace add ...` 재실행. `codex plugin list`에서 installed/enabled인지 확인한 뒤 새 대화를 시작합니다.
- **audit STRUCTURAL>0**: 거의 항상 롤업 재계산 누락 또는 참조 오타 → `policy-integrity-audit` 스킬로 진단(보통 build의 rebuild_rollups가 정정).
- **카운트가 매 빌드 +1로 샘**: baseline을 다시 빌드 입력으로 쓰는 구성에서 옛/새 id 불일치 PI가 생기는 경우 — `pr_pi_remove`/정리로 끝단 차단.
- **본문에 레거시 용어 잔존**: `term_replacements` 확인. 근거(`source_note` 등)는 의도적으로 치환 제외(원형 보존).
