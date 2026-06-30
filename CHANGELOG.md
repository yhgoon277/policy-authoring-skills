# Changelog — policy-authoring

모든 주요 변경을 기록한다. 버전은 [SemVer](https://semver.org/lang/ko/)를 따른다.

## [0.4.2] — 2026-06-30

진단 정직성 + 출력 품질 (효과성 테스트 백로그 B/C 반영).

### Fixed
- **`diff_nc_html_json` 거짓음성 해소(B)** — content_loss가 'JSON 부재'만 잡던 것을 'JSON row 존재·content 공란'까지 포함(`counts.content_loss_emptyrow` 분리). 파서가 HTML PI 0개 인식 + JSON엔 PI 존재 시 `unmeasurable: true`로 표기 → '무손실' 오판 차단(통합알림 등 미지원 포맷).
- **`render_preview` 출처마커 비노출(C)** — 내부 복원 표식 `recovered_from_html:…`를 화면 '근거'에 "HTML 정책서 본문에서 복원"으로 표시(verify_recovery용 spec 표식은 유지).

### Notes
- 실측 재확인: 통합알림 `unmeasurable=true` · 이벤트미션 content_loss 0→37(공란 row) · 전시 무변경(회귀 0). 잔여 백로그: D 보고분해(데이터 카운트는 이미 제공) · 퍼지 크로스워크.

## [0.4.1] — 2026-06-30

NC '간소화' 정책서 포맷 호환성 + reconcile 과복원 차단 (실측 NC 1차 정책서 10쌍 효과성 테스트에서 도출).

### Fixed
- **`nc_html_link.parse_pg_pi` 포맷 폴백** — '간소화' 포맷(텍스트 PG 헤딩 `<h4>…(PG-…)</h4>` + `policy-item-title`+`<span class="mono">(PI-…)</span>`)을 레거시 6변형이 못 읽어 진단을 0으로 오보 → `dev_format_vendor`로 폴백(레거시보다 더 찾을 때만, 회귀 0). diff/sweep 진단 정상화(5쌍 0→실측).
- **`splice_nc_html.section_span` 속성 헤딩** — `<h2 id="6.-정책-정의">`처럼 속성 붙은 섹션 헤딩을 못 찾아 splice 실패 → `<h2[^>]*>` 허용. 골든 렌더 정상화.
- **`fix_nc_input.recover` id-스킴 크로스워크** — HTML↔JSON PI id 스킴 상이(예 APPROVAL↔APR) 시 같은 논리 정책을 신규 PI로 중복 추가(과복원)하던 것을 *정규화 이름 매칭*으로 차단(빈 본문이면 충실 충전). 결제 −100·상품상세 −55, PASS 쌍 회귀 0.

### Notes
- 실측 검증: NC '1차 정책서' 10쌍 — **날조 0**(owning-block 게이트), 골든 렌더 10/10. 백로그(미적용): content_loss 빈본문/미지원 포맷 거짓음성, 퍼지 크로스워크, 출처마커 비노출.

## [0.4.0] — 2026-06-30

5운영원칙 반영(첫 접촉 라우팅 + 일반정책 추론 opt-in) · 10스킬 · GitHub private 마켓플레이스 + autoUpdate 배포.

### Added
- **신규 스킬 `policy-intake-router`** (10번째) — 작성 단위 첫 접촉을 **NEW-FROM-SOURCE / REVISE-from-HTML / REVISE-spec** 3 경로로 분류해 알맞은 시작 스킬로 핸드오프한다(워크플로우 미소유). gap-fill 오버레이(P3 제로추론 기본 / P4 field_review / P5 일반정책 opt-in)·음성 케이스(중간 어휘 재트리거 금지)·혼합 신호 시 사용자 확인 규율 포함.
- **`policy-detail-authoring` 라-축(일반정책 추론) opt-in** — as-is 무근거 빈칸을 **사용자 명시 요청 시에만** 통신·글로벌 앱/웹 일반 관행으로 *제안*. **새 필드 없이** `field_review`(붉은 배지) + `source_note` `[일반정책 근거·검토필요]` 프리픽스 재사용(render 코드 변경 0). 가/나/다 → **가/나/다/라** 택소노미.
- **Codex `agents/openai.yaml`** 4종 신설(html-json-check·nc-studio-gate·render-deliver·workflow-orchestration) + 라우터 = **10/10 스킬 완비**.
- **`validate_plugin.py`** (stdlib) — 패키징 검증자: 10 스킬 각 SKILL.md+openai.yaml 존재·frontmatter 유효성·claude/codex `plugin.json` 버전 일치(`--expect-version`·`--expect-skills`).
- **`DEPLOY.md`** — GitHub private 마켓플레이스 마이그레이션 런북(버전 전략·release 핀·directory→github·autoUpdate·`GITHUB_TOKEN`·검증·롤백).
- **`build_dist.sh`** — `dist/` ZIP(10 개별 + all + codex) 재현 빌드 스크립트.
- **도구 하드닝 (Track A)** — 브라운필드 인테이크 보강 + 강제 deferred-추적: `deferred_manifest.py`·`nc_owning_block.py`·`verify_recovery.py` 신설, `fix_nc_input.py`(content_loss 소유-구획 복원)·`build_spec_template.py` 보강. content_loss 복원 파서 `dev_format_vendor.py`(vendored·stdlib) 포함.

### Changed
- **P3 제로추론 가드 강화** — 라-축이 "유일한 예외"로 한정·항상 배지+근거·무뱃지 라-값 경로 0(날조 동급) 명문화.
- **매니페스트 0.4.0** — claude(`.claude-plugin/plugin.json`)·codex(`.codex-plugin/plugin.json`)·루트 마켓플레이스 모두 9→10스킬·`version: 0.4.0`.
- **설치 문서를 github+release+autoUpdate로** — README/INSTALL의 설치 명령을 `@release` 핀·autoUpdate·private 접근(`GITHUB_TOKEN`)으로 갱신.
- **워크플로우 오케스트레이션 배선** — "미분류 첫 접촉이면 라우터가 먼저" 양방향 연결.

### Fixed
- **문서 스킬 카운트 드리프트 제거** — README/INSTALL/CODEX_HANDOFF/매니페스트의 "5종/9종/four skills" → **10종**으로 동기화. 감사 불변식 표기 `A~I` → `A~L` 정정.

### Verified
- 독립 적대 검수(신규-컨텍스트 에이전트 10) **A 원칙작동·B 회귀·C 음성테스트 검출력 전건 PASS** — 배포 차단 게이트 통과.
- `validate_plugin.py --expect-version=0.4.0 --expect-skills=10` PASS · `render_preview.py` 무접촉(P5 field_review/source_note 계약 불변) · Track A 머지 충돌 0(파일경계 분리).

### Notes
- `dev_format_vendor.py`(~152KB)는 `fix_nc_input` content_loss 복원의 **lazy 의존**(함수 내 import·stdlib)이라 core 배포에 유지한다. 죽은 코드 아님 — 제외 시 HTML→JSON 복원이 깨진다. 추후 minor에서 **optional 분리**(별도 dev 번들 + graceful `ImportError` 안내) 검토 여지.

## [0.3.0] — 2026-06
- `policy-html-json-check` 추가(외부 HTML↔JSON 사전 검토·조건부 복원). 9스킬.

## [0.2.0] — 2026-05
- 워크플로우 후반부 자산화: `policy-render-deliver`·`policy-nc-studio-gate`·`policy-workflow-orchestration`. Codex 플러그인 스캐폴딩(`.codex-plugin/`·`.agents/`).

## [0.1.0] — 2026-04
- 최초 5스킬: hierarchy-decomposition·naming-readability·detail-authoring·integrity-audit·authoring-setup.
