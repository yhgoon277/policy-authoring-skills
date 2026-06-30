# policy-authoring — 정책서 작성 방법론 스킬 세트

통신 정책서 한 모듈("청구및수납관리")을 수개월에 걸쳐 정비하며 정착한 **작성·검증 방법론**을
재사용 가능한 **Claude/Codex Skill 세트**로 묶은 것입니다 — **claude.ai / Claude Desktop**(Skills 업로드),
**Claude Code**(플러그인), **Codex app/CLI**(Codex 플러그인 또는 `.agents/skills`)에서 씁니다.
**다른 정책 모듈에도 동일 품질로** 적용하고 **팀원과 공유**하기 위한 것입니다.

## 무엇이 들어있나 (10개 스킬)

| 스킬 | 용도 |
|---|---|
| **policy-intake-router** | **첫 접촉** 분류 — 신규 작성 / 외부 HTML 수입 / 기존 spec 수정 중 무엇인지 가려 알맞은 시작 스킬로 핸드오프 |
| **policy-authoring-setup** | 새 모듈 **온보딩·설치** (이 세트를 내 프로젝트에 배선하는 진입점) |
| **policy-hierarchy-decomposition** | UC→PR→FN→세부기능 계층 설계와 **기능 분화** (6규칙 + 다자 1:N 배정 게이트) |
| **policy-naming-readability** | 명칭·설명을 기획자가 바로 이해하게 — "명칭 (ID)", 세부기능명 간결화, 설명 풀어쓰기 |
| **policy-detail-authoring** | **정책 상세(PI)** 작성 — 표·콜아웃·근거, N:M 매핑, **가/나/다/라 팩트체크 + 붉은 배지**(라=일반정책 추론 opt-in), to-be 후보 |
| **policy-integrity-audit** | **ID 정합성 감사** — 불변식 A~L, STRUCTURAL/SEMANTIC, stale 롤업 재계산 |
| **policy-render-deliver** | 6섹션 **미리보기 렌더** + NC 변환본에 **배포본 splice**(골든급) |
| **policy-nc-studio-gate** | **NC스튜디오 업로드 게이트** 대비 — G2(요구사항↔노드 연결)·G5(decision_spec 판정축) |
| **policy-html-json-check** | 외부 **HTML↔JSON 사전 검토** + 사용자 확인 후 조건부 복원 |
| **policy-workflow-orchestration** | 전체 **phase 시퀀스·편집 1건 루프** 컨덕터 (어느 스킬을 언제) |

## 빠른 시작

### claude.ai / Claude Desktop (팀원 대부분)
1. **Settings → Capabilities**에서 **Code Execution·File Creation 켜기**(스크립트 실행 전제).
2. **Customize → Skills**(데스크탑: Settings → Capabilities → Skills) → **Upload skill** → `dist/`의 번들 `policy-authoring-skills-all.zip`을 풀어 나오는 **10개 스킬 ZIP을 각각** 업로드(스킬 1개 = ZIP 1개).
3. 자연어로 트리거 — "이 프로세스를 기능으로 분화", "정책 상세 표로 정리하고 팩트체크", "정합성 감사" 등. 스펙 점검·렌더는 스펙 JSON을 대화에 올린 뒤 요청.

### Claude Code (터미널/IDE)
```bash
/plugin marketplace add yhgoon277/policy-authoring-skills@release   # github · release 핀 · 자동업데이트
/plugin install policy-authoring@mypart-skills
/policy-authoring-setup        # 새 모듈 세팅 단계별 안내
```
> repo가 private면 백그라운드 자동업데이트에 `GITHUB_TOKEN`(repo read scope)이 필요합니다. 마이그레이션·autoUpdate·private 접근 상세 → [DEPLOY.md](DEPLOY.md).

### Codex app (같은 workspace 팀원)
1. 배포자가 이 repo의 Codex 플러그인(`policy-authoring`)을 설치합니다.
2. Codex app의 plugin details에서 **Share**를 눌러 workspace 팀원에게 공유합니다.
3. 팀원은 공유된 플러그인을 설치한 뒤 새 대화에서 `policy-*` 10개 스킬이 보이는지 확인합니다.

### Codex CLI (GitHub marketplace)
```bash
codex plugin marketplace add yhgoon277/policy-authoring-skills --ref release   # 안정 핀(최신 개발은 --ref main)
codex plugin add policy-authoring@policy-authoring-skills
codex plugin list
```

설치 후 새 대화에서 slash command도 사용할 수 있습니다. 초기 5종 단축형:
`/policy-setup`, `/policy-audit`, `/policy-detail`, `/policy-naming`, `/policy-hierarchy`.
나머지 5종(intake-router·render-deliver·nc-studio-gate·html-json-check·workflow-orchestration)을 포함한 10종 전부는 자연어 또는 네임스페이스 형식 `/policy-authoring:<스킬명>`(예 `/policy-authoring:policy-setup`)으로 호출합니다.

### Codex 직접 설치 (`.agents/skills`)
```bash
mkdir -p ~/.agents/skills
cp -R plugins/policy-authoring/skills/* ~/.agents/skills/
```

팀 repo에 함께 두려면 10개 스킬 폴더를 해당 repo의 `.agents/skills/`에 체크인합니다. 플러그인 배포를 쓰지 않는 임시·개인 설치에 적합합니다.

## 이식성 — 어떻게 내 프로젝트에 맞추나
도구(audit·build·render)는 **표준 spec JSON 스키마**를 인터페이스로 씁니다. 내 소스(스프레드시트·문서 등)를
그 형태의 baseline spec으로 한 번 변환하면 도구가 그대로 동작합니다. 프로젝트별로 다른 값
(business_code·카운트·용어 치환·예외 목록)은 전부 **`policy_config.json`** 에서 읽으므로 코드 수정이 필요 없습니다.
- 스키마: `plugins/policy-authoring/skills/policy-authoring-setup/assets/schema/canonical_spec_schema.md`
- 설치·온보딩 상세: [INSTALL.md](INSTALL.md)

## 표준 작업 루프
**(작성/편집) → build → audit (STRUCTURAL 0) → render → 커밋**

## 참조 구현
통신 "청구및수납관리"(`business_code=BIL`): 12 UC·39 PR·124 FN·19 PG·210 PI, 표 32·현업검토 72.
이 세트의 도구는 이 프로젝트에서 STRUCTURAL 0·SEMANTIC 39, 렌더 19/210/32/72를 재현하도록 검증됨.
실제 config 예시: `…/policy-authoring-setup/assets/policy_config.example.json`.
