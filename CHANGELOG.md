# Changelog — policy-authoring

모든 주요 변경을 기록한다. 버전은 [SemVer](https://semver.org/lang/ko/)를 따른다.

## [0.4.0] — 2026-06-30

5운영원칙 반영(첫 접촉 라우팅 + 일반정책 추론 opt-in) · 10스킬 · GitHub private 마켓플레이스 + autoUpdate 배포.

### Added
- **신규 스킬 `policy-intake-router`** (10번째) — 작성 단위 첫 접촉을 **NEW-FROM-SOURCE / REVISE-from-HTML / REVISE-spec** 3 경로로 분류해 알맞은 시작 스킬로 핸드오프한다(워크플로우 미소유). gap-fill 오버레이(P3 제로추론 기본 / P4 field_review / P5 일반정책 opt-in)·음성 케이스(중간 어휘 재트리거 금지)·혼합 신호 시 사용자 확인 규율 포함.
- **`policy-detail-authoring` 라-축(일반정책 추론) opt-in** — as-is 무근거 빈칸을 **사용자 명시 요청 시에만** 통신·글로벌 앱/웹 일반 관행으로 *제안*. **새 필드 없이** `field_review`(붉은 배지) + `source_note` `[일반정책 근거·검토필요]` 프리픽스 재사용(render 코드 변경 0). 가/나/다 → **가/나/다/라** 택소노미.
- **Codex `agents/openai.yaml`** 4종 신설(html-json-check·nc-studio-gate·render-deliver·workflow-orchestration) + 라우터 = **10/10 스킬 완비**.
- **`validate_plugin.py`** (stdlib) — 패키징 검증자: 10 스킬 각 SKILL.md+openai.yaml 존재·frontmatter 유효성·claude/codex `plugin.json` 버전 일치(`--expect-version`·`--expect-skills`).
- **`DEPLOY.md`** — GitHub private 마켓플레이스 마이그레이션 런북(버전 전략·release 핀·directory→github·autoUpdate·`GITHUB_TOKEN`·검증·롤백).
- **`build_dist.sh`** — `dist/` ZIP(10 개별 + all + codex) 재현 빌드 스크립트.

### Changed
- **P3 제로추론 가드 강화** — 라-축이 "유일한 예외"로 한정·항상 배지+근거·무뱃지 라-값 경로 0(날조 동급) 명문화.
- **매니페스트 0.4.0** — claude(`.claude-plugin/plugin.json`)·codex(`.codex-plugin/plugin.json`)·루트 마켓플레이스 모두 9→10스킬·`version: 0.4.0`.
- **설치 문서를 github+release+autoUpdate로** — README/INSTALL의 설치 명령을 `@release` 핀·autoUpdate·private 접근(`GITHUB_TOKEN`)으로 갱신.
- **워크플로우 오케스트레이션 배선** — "미분류 첫 접촉이면 라우터가 먼저" 양방향 연결.

### Fixed
- **문서 스킬 카운트 드리프트 제거** — README/INSTALL/CODEX_HANDOFF/매니페스트의 "5종/9종/four skills" → **10종**으로 동기화. 감사 불변식 표기 `A~I` → `A~L` 정정.

### Verified
- 독립 적대 검수(신규-컨텍스트 에이전트 10) **A 원칙작동·B 회귀·C 음성테스트 검출력 전건 PASS** — 배포 차단 게이트 통과.
- `validate_plugin.py --expect-version=0.4.0 --expect-skills=10` PASS · 빌드/렌더 도구 무접촉(재현성 불변) · 형제 Track A(`assets/tools/**`·`scripts/**`) 무충돌.

## [0.3.0] — 2026-06
- `policy-html-json-check` 추가(외부 HTML↔JSON 사전 검토·조건부 복원). 9스킬.

## [0.2.0] — 2026-05
- 워크플로우 후반부 자산화: `policy-render-deliver`·`policy-nc-studio-gate`·`policy-workflow-orchestration`. Codex 플러그인 스캐폴딩(`.codex-plugin/`·`.agents/`).

## [0.1.0] — 2026-04
- 최초 5스킬: hierarchy-decomposition·naming-readability·detail-authoring·integrity-audit·authoring-setup.
