# 정책 상세(PI) 스키마·렌더·매핑

PI 내용 override의 필드 정의, 렌더 형식, 세부기능 N:M 매핑, 용어 치환 규칙.

## PI override 스키마

빌드의 PI 내용 override(예: `PI_CONTENT_OVERRIDES[pi_id]`)에 PI 1개를 다음 필드로:

```python
"<PI-id>": {
  "rule":     "한 줄 평서문. 이 정책이 정하는 핵심 동작 기준.",
  "criteria": [ "라벨: 값", "라벨: 값" ],   # 정의해야 할 값들. 도식 금지, '섹션 참조' 금지(실제 값으로 전개)
  "notice":   "\"고객 안내 문구\"",          # 없으면 ""
  "source_note": "근거 + 맥락 한 줄",         # 출처 시스템·문서·법령. 원형 보존(치환 제외)
  "applies_to": ["FN-<BIZ>-XXX-001#1", "FN-...#3"],  # 이 PI가 관할하는 세부기능 ref (idx 1-based)

  # 선택
  "tables": [ { "caption": "...", "headers": [...], "rows": [[...],[...]], "note": "..." } ],
  "field_review": "불확실 사유·현재 가정·질문"   # 있으면 붉은 '현업 검토 필요' 배지
}
```

## 렌더 형식 (가독형)

렌더 순서와 시각 위계 — **정책문·표를 위에 강조, 근거는 아래 작게**:

1. 제목 `명칭 (ID)` (+ `field_review` 있으면 붉은 **현업 검토 필요** 배지)
2. **정책문**(rule) — 본문 강조
3. **표**(`tables`) — `<table class="policy-detail-table">` (+ note 한 줄). 0/1/N개.
4. 단순 기준값(`criteria`) → 불릿(`<ul>`). 표가 있으면 생략 가능.
5. **고객 안내**(notice) → 콜아웃(`.policy-notice`, 예: 💬 파란 박스).
6. **근거·관련기능**(source_note·applies_to) → 하단 muted 푸터(`.policy-meta`).
7. `field_review` 사유 → 하단 붉은 줄.

**언제 표를 쓰나**: **다차원(≥2축) 기준값만** 표로(예: 회선종류 × 조회시점, 대분류 × 중분류). 단순 '라벨: 값'은 깔끔한 불릿 유지. 한 PI에 표 0/1/N개 + 불릿 공존 가능.

> 표는 **이미 검증된 값을 재구조화만** — 표 만들면서 새 수치 생성 금지(팩트체크는 별도). 원문에 한 PI로 다 안 적힌 항목은 표로 만들지 말고 불릿으로.

CSS(`.policy-detail-table`·`.policy-notice`·`.policy-meta`·`.policy-review-flag`)는 렌더러(splice 도구)가 `<head>`에 1회 주입(멱등). 상세는 `policy-authoring-setup`(⑤)의 렌더 도구.

## 세부기능 ↔ PI 매핑 (N:M)

- 매핑 단위 = **세부기능**(`function_details[].sub_functions`의 각 항목), ref = `FN-id#idx`(idx 1-based).
- **N:M**: 한 PI가 여러 세부기능을, 한 세부기능에 여러 PI가 붙을 수 있다.
- **순수 UI/표현·내부처리 세부기능**(버튼 활성화·로딩·선택 컨트롤·내부 이력 저장)은 정책 불필요 → UI 표기(예: `UI_SUBFNS`). **1:1 강제 금지**(인위적 정책 양산 X).
- 빌드가 `applies_to`로 `FD.subfn_pis` / `FN.related_policy_details` / `PI.applies_to_functions`를 자동 파생 → 검증은 `policy-integrity-audit`(④) B5/A9/C1.

> ⚠️ **인덱스 보존**: `FN#idx`는 sub_functions 배열의 위치. 세부기능 이름을 바꾸더라도 **개수·순서 불변**이어야 매핑이 유지된다(②의 인덱스 보존 가드).

## 용어 치환 규칙 (중요)

빌드의 용어 치환(`apply_term_replacements`)은 본문 전역에서 레거시 용어를 최종 용어로 바꾼다(예: 구 시스템명 → 신 시스템명). 단 **provenance 필드는 치환 제외**(`source_note`·`source_refs`·`field_review` 등 — config의 `term_skip_keys`).

따라서:
- **표 셀·rule·criteria(=치환 대상)에는 최종 용어만** 쓴다(예: 신 시스템명). 레거시 원형을 쓰면 자동 치환돼 사라진다.
- **레거시 시스템 출처는 `source_note`/`field_review`(=치환 제외)에만** 원형으로 보존(예: "구 시스템명 기준 분류").
- 검증: 렌더 본문에 레거시 원형 용어 누설 0 (근거엔 보존).

> *예(BIL)*: 본문은 BSS·Next Channel, 근거는 "SWING"·"Next Channel(구 T world)" 원형.
