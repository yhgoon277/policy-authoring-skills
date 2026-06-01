# Codex 인수인계: `policy-authoring` 스킬 세트 — Codex 호환성 검증 및 문서 보강

> 이 문서는 **Codex(앱/CLI/IDE)** 에게 주는 작업 지시서다. Codex는 이 레포를 받은(클론한) 상태에서
> 아래를 **직접 실행·검증**하고, 필요한 문서 보강을 제안/반영한 뒤 결과를 보고한다.
> 이 스킬 세트는 Claude 환경에서 제작됐고 Codex에서의 실제 동작은 **아직 검증되지 않았다**(빌드 머신에 Codex 부재).

## 0. 당신(Codex)이 할 일
1. 이 레포의 스킬 5종을 **Codex에 설치**한다.
2. §4 체크리스트 A~G로 **인식·호출·스크립트 실행·재현**을 검증한다.
3. §6의 문서/배포 보강 후보를 **판단하고, 맞으면 적용**한다(README/INSTALL 등).
4. §7 형식으로 **결과를 보고**한다.

## 1. 대상물
- **레포(공개):** `https://github.com/yhgoon277/policy-authoring-skills`
- **스킬 5종**(모두 SKILL.md 포맷): `policy-hierarchy-decomposition`, `policy-naming-readability`, `policy-detail-authoring`, `policy-integrity-audit`, `policy-authoring-setup`
- **레포 구조:** 스킬은 `plugins/policy-authoring/skills/<name>/` 아래. 각 스킬 = `SKILL.md`(+ 일부 `references/`, `scripts/`, `assets/`). 루트의 `.claude-plugin/marketplace.json` 과 `dist/*.zip` 은 **Claude / claude.ai 전용** → Codex에선 무시.
- **번들 도구**(순수 Python 표준 라이브러리, pip 불필요): `audit_id_integrity.py`(ID 정합성 감사), `build_spec_template.py`(스펙 빌드), `render_preview.py`(HTML 렌더). 모두 `policy_config.json` 설정으로 동작.
- **용도:** 정책/요구사항 명세(UC→프로세스→기능→세부기능, 정책그룹→정책상세)를 일관 품질로 작성·검증하는 방법론. 표준 spec JSON 스키마가 인터페이스(정의: `plugins/policy-authoring/skills/policy-authoring-setup/assets/schema/canonical_spec_schema.md`).

## 2. 사전 파악(당신이 사실 확인할 것)
- Codex는 Claude와 **동일한 SKILL.md 포맷**을 지원(2025-12). → 내용 호환 예상.
- Codex 스킬 인식 경로(공식 문서 기준): 레포 `.agents/skills/`·`$REPO_ROOT/.agents/skills/`, 사용자 `~/.agents/skills/`, 관리자 `/etc/codex/skills/`. **당신 버전에서 `/skills`로 실제 경로를 확정**하라(일부 글은 `.codex/skills`라고도 함 — 버전 차이 가능).
- **Claude 마켓플레이스(`/plugin marketplace add`, `.claude-plugin/`)는 Codex가 안 씀.** → "플러그인 설치"가 아니라 **"스킬 폴더를 Codex 스킬 경로에 두기"** 가 설치다.

## 3. 설치(먼저 이대로)
**개인 스코프:**
```bash
git clone https://github.com/yhgoon277/policy-authoring-skills
mkdir -p ~/.agents/skills
cp -R policy-authoring-skills/plugins/policy-authoring/skills/* ~/.agents/skills/
```
**팀/레포 스코프(대안):** 위 5개 폴더를 작업 레포의 `.agents/skills/`에 체크인.
그 후 Codex 새로고침 → `/skills` 실행.
> `~/.agents/skills` 가 안 잡히면 Codex 문서/`/skills`로 해당 버전의 정확한 경로를 찾아 거기에 두라. **이 경로 확정이 검증 항목 1번이다.**

## 4. ✅ 검증 체크리스트(각 항목 PASS/FAIL + 근거 보고)
| # | 테스트 | 방법 | 기대 결과 |
|---|---|---|---|
| **A. 인식** | 5개가 보이나 | `/skills` | `policy-*` 5개 노출, 이름·설명 표시 |
| **B. 명시 호출** | `$`/선택 호출 | `$policy-integrity-audit` (또는 /skills 선택) | 해당 SKILL.md 로드 |
| **C. 암시 호출** | 자연어 자동 선택 | "이 정책 스펙 ID 정합성 감사해줘" / "이 프로세스를 기능으로 분화" / "정책 상세를 표로 정리하고 불확실 값 표시" / "세부기능 이름 기획자가 이해하게 다듬어" / "이 스킬들로 새 모듈 세팅하려면?" | 각각 audit / hierarchy / detail / naming / setup 선택 |
| **D. 참조 로드** | references 읽히나 | detail-authoring 발동 시 | `references/pi-format.md`·`factcheck-and-tobe.md` 읽어 표/배지 규칙 적용 |
| **E. 스크립트 실행** ★핵심 | 번들 Python 실행 | 아래 §5 | 감사 리포트 출력(exit 0/1); 렌더 HTML 생성 |
| **F. 방법론 재현** | 가이드대로 결과 | naming 스킬 + 세부기능명 5개 → 간결화 요청 | 치환 규칙 적용·개수/순서 보존·핵심 숫자 보존 |
| **G. 설정 반영** | config 동작 | `policy_config.json`의 business_code·expected_counts·term_replacements·known_pr_only | 스크립트가 값 반영(프리픽스·카운트·치환·화이트리스트) |

## 5. 스크립트 실행 테스트 상세(항목 E)
1. **테스트용 spec:** `…/policy-authoring-setup/assets/schema/canonical_spec_schema.md` 의 "최소 예시" JSON을 복사해 `test_spec.json` 으로 저장(business_code 예: `BIZ`).
2. **최소 config:** `policy_config.json` = `{"business_code":"BIZ","spec_path":"test_spec.json"}` (expected_counts 비우면 카운트 검사 생략).
3. **감사 실행:**
   ```bash
   python3 ~/.agents/skills/policy-integrity-audit/scripts/audit_id_integrity.py --config=policy_config.json test_spec.json
   ```
   기대: A~I 불변식 리포트, STRUCTURAL/SEMANTIC 카운트, 실측 카운트. (정합한 최소 스펙이면 STRUCTURAL 0)
4. **렌더 실행:**
   ```bash
   python3 ~/.agents/skills/policy-authoring-setup/assets/tools/render_preview.py --out=/tmp/preview.html test_spec.json
   ```
   기대: `/tmp/preview.html` 생성, "PG n·PI n" 요약.
5. **확인 포인트:** Codex 샌드박스가 (a) `python3` 사용 가능, (b) 작업 디렉터리 읽기/쓰기 허용인지. 막히면 어떤 승인/권한이 필요했는지 기록.
> 참고 기대치(원 프로젝트 business_code BIL): 감사 STRUCTURAL 0 / SEMANTIC 39, 렌더 PG 19·PI 210·표 32·현업검토 72. (BIL 원본 스펙은 이 레포에 없음 — 위 최소 스펙으로 대체 검증)

## 6. 문서/배포 보강 후보(판단 후 가능하면 적용)
1. **README/INSTALL에 "Codex" 설치 섹션 추가**: "스킬 폴더 5개를 `~/.agents/skills/`(개인) 또는 레포 `.agents/skills/`(팀)에 둔다. `.claude-plugin/`은 Claude 전용이라 Codex는 무시. 스크립트는 Codex 샌드박스/터미널에서 실행." (현 문서는 claude.ai·Claude Code 2종만 안내 → Codex 포함 3-way로)
2. **Codex 번들 추가 검토**: `dist/policy-authoring-skills-codex.zip`(5개 스킬 폴더 flat → 풀어서 `.agents/skills/`에 복사) + `dist/CODEX_HOWTO.txt`. 폴더 복사가 번거로우면 유용. (claude.ai용 기존 zip은 유지)
3. **스킬 본문 노트 도구 중립화**: 각 SKILL.md 상단 "claude.ai에서" 블록이 Codex 사용자에게 혼동되면 "claude.ai·Codex 등"으로 일반화.
4. **`agents/openai.yaml` 필요성 판단**: Codex 암시 호출 제어용. 기본(암시 호출 on)이 적절하면 불필요 — 부적절 케이스만 보고.

## 7. 보고 형식
- 체크리스트 A~G 각각 **PASS/FAIL + 무엇을 실행했고 무엇이 나왔는지**.
- **Codex 정확 스킬 경로**(확정값).
- **권장 문서 변경** 목록(또는 적용 시 diff).
- 막힌 점/권한 이슈/포맷 비호환을 구체적으로.

## 8. 알아둘 점
- 스크립트 = 순수 Python 표준 라이브러리(pip 불필요), `python3` 필요.
- 스킬들이 **서로 이름으로 참조** → 5개 다 설치해야 완전 동작.
- `.claude-plugin/`·`dist/*.zip` 은 Claude/claude.ai용 → Codex에선 사용 금지.
- 표준 spec 스키마가 인터페이스(`canonical_spec_schema.md`). 참조 구현 = 통신 청구(business_code BIL): 12 UC / 39 PR / 124 FN / 19 PG / 210 PI.
