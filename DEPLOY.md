# 배포 · 마켓플레이스 마이그레이션 (v0.4.0) — GitHub private + release 핀 + autoUpdate

> 이 문서는 **배포자**용 런북이다. 일반 설치는 [INSTALL.md](INSTALL.md)·[README.md](README.md). 스키마/명령은 Claude Code 플러그인 마켓플레이스 공식 문서(code.claude.com, 2026-06-30 확인)에 근거한다.

## 버전 전략 (확정)
- **명시 semver `0.4.0`** + **`release` 브랜치/태그 핀**. `omit→commit SHA`는 채택 안 함(autoUpdate가 반쪽 커밋을 배포하는 위험).
- **일상 개발은 `main`**, **autoUpdate 클라이언트는 `release`만** 본다. `release`는 검증 끝난 커밋만 fast-forward로 올린다.
- 카운트: 10 스킬 · claude/codex `plugin.json` 둘 다 `version: 0.4.0`(`validate_plugin.py`가 강제).

## 0. 사전 게이트 (배포 전 필수)
- [ ] `python3 validate_plugin.py --expect-version=0.4.0 --expect-skills=10` → PASS.
- [ ] Phase 4 독립 적대 검수 A+B+C **전건 PASS**(차단 게이트 — 미통과 시 배포 금지).
- [ ] 형제 Track A(`assets/tools/**`·`scripts/**`)가 `main`에 머지됐으면 `main`을 `release/v0.4.0`에 머지(파일경계 달라 충돌 0).

## 1. Git 릴리스 (커밋/푸시는 사용자 승인 시에만)
`gh` 미설치 → plain `git` 사용. 현재 `origin = https://github.com/yhgoon277/policy-authoring-skills`(remote 존재), `release/v0.4.0`가 미푸시 `origin/main`보다 앞섬.

```bash
# release/v0.4.0의 검증 완료 커밋을 main에 반영 후 release 브랜치/태그로 승급
git checkout main
git merge --ff-only release/v0.4.0          # 또는 의도한 머지 전략
git push origin main

git branch -f release main                   # release 브랜치를 main 끝으로 ff
git push origin release
git tag -a v0.4.0 -m "policy-authoring v0.4.0 — 10 skills (intake-router, P5 opt-in)"
git push origin v0.4.0
```
- ⚠️ `release`는 항상 **검증 통과 커밋만**. autoUpdate 클라이언트가 즉시 받는다.

## 2. repo private 전환 (사용자 액션 — 웹 UI)
`gh` 미설치이므로 **GitHub 웹 UI**에서: `Settings → General → Danger Zone → Change visibility → Make private`.
- private 후엔 마켓플레이스 접근에 인증 필요(§4).

## 3. 클라이언트 마켓플레이스 마이그레이션 (directory → github)
현재 `mypart-skills`는 **directory 소스**(`~/.claude/settings.json`의 `extraKnownMarketplaces`·`~/.claude/plugins/known_marketplaces.json` 둘 다 로컬 경로). github+release+autoUpdate로 전환.

### 3-1. 권장 = CLI 명령 (스키마 검증·캐시 셋업 자동)
> ⚠️ `known_marketplaces.json` **수기 편집 금지**(캐시/경로 셋업 누락 → "marketplace not found"). 명령을 쓴다.
```bash
claude plugin marketplace remove mypart-skills                              # 기존 directory 소스 제거(설치 플러그인도 함께 제거됨)
claude plugin marketplace add yhgoon277/policy-authoring-skills@release      # github + release 핀
claude plugin install policy-authoring@mypart-skills
claude plugin marketplace list --json                                       # 소스=github·ref=release 확인
```
- 대화형 동등: `/plugin marketplace remove mypart-skills` → `/plugin marketplace add yhgoon277/policy-authoring-skills@release` → `/plugin install policy-authoring@mypart-skills`.

### 3-2. 팀 공유 선언 (`.claude/settings.json` — 수기 편집 안전)
팀 repo의 `.claude/settings.json`(또는 개인 `~/.claude/settings.json`)의 `extraKnownMarketplaces["mypart-skills"]`를 교체:
```jsonc
"mypart-skills": {
  "source": { "source": "github", "repo": "yhgoon277/policy-authoring-skills", "ref": "release" },
  "autoUpdate": true
}
```
(현재 값은 `{"source":{"source":"directory","path":"…/policy-authoring-skills"}}` — 이 블록만 위로 교체.)

## 4. private 접근 인증
- **수동 add/update(대화형)**: 기존 git 자격증명 헬퍼 사용(`gh auth login`/macOS Keychain/credential-store). 터미널에서 `git clone https://github.com/yhgoon277/policy-authoring-skills.git`가 되면 OK.
- **백그라운드 autoUpdate(시작 시)**: 대화형 헬퍼 불가 → **환경변수 토큰 필요**:
  ```bash
  export GITHUB_TOKEN=ghp_xxx   # 또는 GH_TOKEN. repo(read) scope. .zshrc/.bashrc에.
  ```
  토큰 없으면 시작 시 autoUpdate를 **조용히 건너뜀**(마지막 상태 유지). 수동 update는 자격증명 프롬프트.
- SSH 대안: `git@github.com:yhgoon277/policy-authoring-skills.git`(키가 ssh-agent에, host known_hosts에).

## 5. autoUpdate 동작
- 마켓플레이스 entry `autoUpdate: true` → 시작 시 최신 카탈로그 fetch. 설치 플러그인에 신버전 있으면 `/reload-plugins` 프롬프트.
- 기본값: 공식 마켓플레이스=on, 서드파티/로컬=off → **우리는 명시 `autoUpdate: true` 필요**.
- 전역 차단: `DISABLE_AUTOUPDATER=1`(+ 플러그인만 유지 시 `FORCE_AUTOUPDATE_PLUGINS=1`).
- 수동: `claude plugin marketplace update mypart-skills`.

## 6. 검증 (clean-room)
별도 설정(2nd config)에서:
```bash
# 임시 config로 오염 없이 검증
claude plugin marketplace add yhgoon277/policy-authoring-skills@release
claude plugin install policy-authoring@mypart-skills
claude plugin list           # policy-authoring@mypart-skills : enabled, version 0.4.0
# 새 세션에서 policy-* 10개 스킬 노출 확인
```
- **autoUpdate가 `release`만 반영**: `main`에 새 커밋을 올려도 클라이언트 무반응, `release` ff 후에야 갱신되는지 확인.
- Codex: `codex plugin marketplace add yhgoon277/policy-authoring-skills --ref release` → `codex plugin add policy-authoring@policy-authoring-skills` → `/skills` 10개.

## 7. 롤백
- `release` 브랜치를 직전 태그로 되돌리고 force-push: `git branch -f release v0.3.x && git push -f origin release`.
- 클라이언트는 다음 autoUpdate/`marketplace update`에서 이전 버전으로 수렴.
