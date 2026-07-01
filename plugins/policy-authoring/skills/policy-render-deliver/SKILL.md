---
name: policy-render-deliver
description: Render a policy spec to its self-contained HTML preview, and splice the rich policy-detail sections into an NC스튜디오 converted HTML for the golden-grade deliverable. Use when regenerating the 6-section preview, building the final deliverable HTML, running the 5-principle acceptance gate (run_acceptance / build_deliverable), fixing a json↔html 이격 from hand-edited HTML, or asked why the NC download renders policy detail flat. Trigger on "렌더", "render_preview", "배포 HTML", "splice", "build_deliverable", "run_acceptance", "완료 게이트", "5원칙", "NC 변환본", "골든 샘플", "평면 렌더", "수기 HTML 편집".
version: 0.3.0
---

# 렌더·배포 (Policy Render & Deliver)

> **Claude/Codex에서**: spec JSON과 (배포 시) NC스튜디오 변환 HTML을 준비하고 적용을 요청하면 가이드대로 동작한다. `policy-*` 스킬을 함께 설치하는 것을 권장한다.

HTML은 `render_preview.py`로 100% 생성한다(**수기 HTML 편집 금지** — json↔html 이격 원천 차단). 배포본은 원천 HTML에 preview의 리치 정책 상세를 **splice**해 골든급으로 만든다.

> **진실원천(R3)**: 기존/외부 HTML에서 편집을 시작하면 **그 원천 HTML이 진실원천**이다(짝 JSON은 없거나 stale일 수 있음). spec은 원천에서 재구성하며(`rebuild_policy_from_source`), 원천의 UC/PR/FN/PG/PI 매핑·콘텐츠를 **사용자 승인 없이 바꾸지 않는다**(발산 금지).

## 배포물 구조 (R1 골든 + R3 원천 완전보존, 구간 분리)
- **§0~§4**(문서히스토리·개요·주요용어·유즈케이스/상태전이 **다이어그램**·프로세스 정의 케이스표) = **원천 HTML 완전보존**(NC가 골든보다 풍부한 구간; 손으로 그린 인라인 SVG·케이스표 유지).
- **§5 기능·§6 정책** = **골든 스타일 렌더**(NC 평면텍스트→골든 리치). → `splice_nc_html --sections=5,6`(기본).
- 즉 render_preview는 §0~§6 전체를 만들지만 **배포물엔 §5·§6만 이식**된다(§0~§4는 원천 그대로).

## 5원칙 완료 게이트 — 이 스킬의 산출은 `run_acceptance`로 검수·확정한다
플러그인은 배포물을 **R1(골든 스타일)·R2(입력 게이트)·R3(원천 보존)·R4(완료 정합)·R5(도메인코드 현행화)** 5원칙으로 자동 검수한다. **단일 진입점 `build_deliverable.py`**가 아래 파이프라인을 묶어 `run_acceptance`로 3-상태(DONE/BLOCKED/FAIL) 판정을 낸다:
```
python3 tools/build_deliverable.py --spec=<입력 spec.json> --source=<원천 HTML> \
    --out-dir=<dir> [--target-code=<R5코드>] [--gate=<validate_spec_input.py>]
# 파이프라인: rebuild_policy_from_source → fn_pi_derive → normalize_spec_to(R5)
#           → render_preview(§0~§6) → splice_nc_html[5,6] → run_acceptance
```
- **DONE** = 5원칙 전부 PASS. **BLOCKED** = 결함 없으나 사람결정 대기(미지원 포맷·usecase_id 저작·정책상세 저작·원천 §4↔§5 불일치·발산 승인/제외·R5 target 미매핑). **FAIL** = 배포물 원칙(R1/R3/R4/R5) RED(자동 수정 대상). **완료는 DONE(또는 BLOCKED 항목을 사람이 처리)** 후 확정.

> **참조 구현**: 통신 "청구및수납관리"(`BIL`) 최종본 `v1.1.119.html` — 원천에 자체 렌더 섹션을 이식한 가공본.

---

## 꼬리 워크플로 (편집 1건 루프의 마지막 단계)
override 편집 → `build_spec` → `audit_id_integrity`(STRUCTURAL 0, → `policy-integrity-audit`) **다음**에 온다.

**원천 HTML 기반 배포**(권장, 한 번에): `build_deliverable.py`(위 참조) — 재구성·렌더·splice·5원칙 게이트를 묶는다.

**개별 단계**(디버깅·부분 실행 시):
```
python3 tools/render_preview.py <spec.json> --out=<preview>    # 6-섹션 self-contained HTML
python3 tools/splice_nc_html.py --unit=<unit> --base=<원천 HTML>   # 배포본(§5·6 교체 + 리치 CSS 주입)
python3 tools/run_acceptance.py --source=<원천> --spec=<spec> --deliverable=<배포> [--target-code=..] [--gate=..]
```

## 1. render_preview — preview 생성
`render_preview.py --config=<path> --unit=<unit> [--out=<path>]` (out 미지정 시 `cfg.preview_out`). spec JSON에서 **6 섹션**을 생성: 0 히스토리·1 개요·2 용어·3 유즈케이스(액터·UC·상태전이)·4 프로세스·5 기능·6 정책(목록·상세) + 최종 점검. CSS는 `tools/preview_style.css`(빌링 추출본). 유즈케이스·상태전이는 **mermaid 다이어그램** 자동생성(CDN + HTML 폴백) — 단 이는 **standalone preview용**이며, 배포물의 §3 다이어그램은 **원천의 손그림 SVG를 완전보존**(§0~§4 원천 유지)한다.

- **배지는 spec 필드로만** 나온다: `field_review` → 붉은 'BSS/현업 검토 필요', `internal_integration` → 앰버 '내부 통합 필요'. 본문에 배지를 수기로 넣지 말 것(→ `policy-detail-authoring`).
- 정책 상세는 PI의 `rule_statement`/`content`·`detail_tables`·`criteria_values`·`customer_notice`·`source_note`·`applies_to`를 리치 클래스(`policy-stmt`·`policy-detail-table`·`policy-criteria`·`policy-notice`·`policy-meta`)로 렌더.
- **HTML을 직접 고치지 말 것** — 내용 변경은 override→build→render로만. (이격 차단)

## 2. splice_nc_html — 배포본 생성
**핵심 인사이트**: NC스튜디오 변환기는 어떤 JSON이든 정책 상세를 **평면 텍스트**(`<span class="policy-item-line">` 나열)로만 렌더한다 — 표·콜아웃·기준 리스트·💬 고객 안내 불가. 설계상 한계이며 **빌링도 동일**했다. 골든 샘플은 NC가 만든 게 아니라 렌더 후처리 산출물이다. 따라서 골든급 배포본은 **preview를 donor로** NC 변환본에 splice한다.

`splice_nc_html.py --unit=<unit> --base=<NC 변환 HTML> [--sections=5,6] [--out=<path>]`:
1. preview `<style>`에서 리치 클래스 CSS를 발췌해 base `</body>` 직전 마커 블록으로 **멱등 주입**(재실행 시 교체, cascade 최후순위).
2. `--sections`(기본 **5,6** = 기능·정책)의 `<h2>N. …</h2>`~다음 `<h2>` 범위를 preview 동일 섹션으로 교체. **섹션 0–4는 NC 원본 byte 보존**(4장 프로세스는 NC 케이스 분기·다이어그램이 더 풍부 → 기본 보존).
3. `samples/deliverable/<base 파일명>_spliced.html` 저장 + 리치 클래스·💬 카운트 보고.

> `--base`는 입력 자료(예: Downloads의 NC 변환본) — **커밋 금지**. preview가 최신이어야 함(먼저 render).

## 검증 (verification-before-completion)
배포본이 골든처럼 리치인지 확인 — 단정 전 실제로 grep:
```
grep -c policy-stmt <deliverable>           # > 0 (리치 복구)
grep -c policy-detail-table <deliverable>   # > 0
```
- `policy-stmt`·`policy-criteria`·`policy-notice`·`policy-detail-table` **존재** + 섹션 5·6 내 `policy-item-line` **0**(평면 잔재 없음).
- splice가 base의 `<h2>` 섹션 경계를 정확히 매칭했는지 확인(헤딩 속성 차이 → 정규식/`--sections` 조정).
- 재빌드 시 preview byte 동일(재현성). NC 인-툴 뷰는 여전히 평면 — 골든급 = **별도 배포 파일**.
- **최종 완료 판정은 `run_acceptance`(또는 `build_deliverable`)** — 5원칙 DONE(또는 BLOCKED 항목을 사람이 처리)이어야 확정. 육안 grep은 보조 확인일 뿐, 게이트가 계약이다.

## 다른 스킬과의 연계
- 정책 상세 내용·배지(`field_review`/`internal_integration`)는 본문에서 → `policy-detail-authoring`(③). 렌더는 spec 필드를 비출 뿐.
- render·splice **앞단** STRUCTURAL 0 보장 → `policy-integrity-audit`(④). audit 미통과면 렌더하지 말 것.
- NC 업로드 게이트(G2 요구사항 연결·G5 decision_spec) 적합성은 → `policy-nc-studio-gate`. splice는 **배포본 뷰** 문제, 게이트는 **업로드 spec** 문제로 별개.
- 도구·`preview_style.css`·config(`preview_out`) 설치 → `policy-authoring-setup`(⑤).
