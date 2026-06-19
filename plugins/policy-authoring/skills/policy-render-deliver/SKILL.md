---
name: policy-render-deliver
description: Render a policy spec to its self-contained HTML preview, and splice the rich policy-detail sections into an NC스튜디오 converted HTML for the golden-grade deliverable. Use when regenerating the 6-section preview, building the final deliverable HTML, fixing a json↔html 이격 from hand-edited HTML, or asked why the NC download renders policy detail flat. Trigger on "렌더", "render_preview", "배포 HTML", "splice", "NC 변환본", "골든 샘플", "평면 렌더", "수기 HTML 편집".
version: 0.2.0
---

# 렌더·배포 (Policy Render & Deliver)

> **Claude/Codex에서**: spec JSON과 (배포 시) NC스튜디오 변환 HTML을 준비하고 적용을 요청하면 가이드대로 동작한다. `policy-*` 스킬을 함께 설치하는 것을 권장한다.

spec JSON을 **단일 진실원천**으로 두고, HTML은 `render_preview.py`로 100% 생성한다. **수기 HTML 편집 금지** — json↔html 이격을 원천 차단한다. 배포본은 NC 변환 HTML에 preview의 리치 정책 상세를 **splice**해 골든급으로 만든다.

> **참조 구현**: 통신 "청구및수납관리"(`BIL`) 최종본 `v1.1.119.html` — NC 변환본에 자체 렌더 섹션을 이식한 가공본.

---

## 꼬리 워크플로 (편집 1건 루프의 마지막 두 단계)
override 편집 → `build_spec` → `audit_id_integrity`(STRUCTURAL 0, → `policy-integrity-audit`) **다음**에 온다:

```
python3 tools/render_preview.py --unit=<unit>          # 6-섹션 self-contained HTML 재생성
python3 tools/splice_nc_html.py --unit=<unit> --base=<NC 변환 HTML>   # 배포본(섹션 5·6 교체 + 리치 CSS 주입)
```

## 1. render_preview — preview 생성
`render_preview.py --config=<path> --unit=<unit> [--out=<path>]` (out 미지정 시 `cfg.preview_out`). spec JSON에서 **6 섹션**을 생성: 0 히스토리·1 개요·2 용어·3 유즈케이스(액터·UC·상태전이)·4 프로세스·5 기능·6 정책(목록·상세) + 최종 점검. CSS는 `tools/preview_style.css`(빌링 추출본). 유즈케이스·상태전이는 **mermaid 다이어그램** 자동생성(CDN + HTML 폴백).

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

## 다른 스킬과의 연계
- 정책 상세 내용·배지(`field_review`/`internal_integration`)는 본문에서 → `policy-detail-authoring`(③). 렌더는 spec 필드를 비출 뿐.
- render·splice **앞단** STRUCTURAL 0 보장 → `policy-integrity-audit`(④). audit 미통과면 렌더하지 말 것.
- NC 업로드 게이트(G2 요구사항 연결·G5 decision_spec) 적합성은 → `policy-nc-studio-gate`. splice는 **배포본 뷰** 문제, 게이트는 **업로드 spec** 문제로 별개.
- 도구·`preview_style.css`·config(`preview_out`) 설치 → `policy-authoring-setup`(⑤).
