# 편집 1건 루프 (Single-Edit Loop) — 근거·규율

모든 **내용 변경**(PI 본문·applies_to·계층·명칭)은 이 루프를 1회 돈다. 빌링 프로젝트에서 정착한 규율로, json↔html 이격·stale 롤업·카운트 누수를 구조적으로 차단한다.

## 6단계
```
1. 편집
   - PI 본문·applies_to·rule_type·decision_spec → tools/overrides/<unit>.py
   - 계층·명칭·PR/FN 신설·신규 PG/PI → baseline spec JSON 직접 편집
2. build   : python3 tools/build_spec.py         --config=policy_config.json --unit=<unit>
             (apply_overrides → rebuild_rollups → bake_pi_ids_into_names/normalize_pg_names → enrich)
3. audit   : python3 tools/audit_id_integrity.py --config=policy_config.json --unit=<unit>
             STRUCTURAL 0 (exit 0) 필수. 아니면 이 편집을 폐기하고 직전 커밋으로.
4. render  : python3 tools/render_preview.py     --config=policy_config.json --unit=<unit>
5. splice  : python3 tools/splice_nc_html.py     --unit=<unit> --base=<NC 변환 HTML>   (배포본 필요 시)
6. 확인·커밋: 미리보기·spliced 육안 확인 → 선별 add → (사용자 요청 시) 커밋
```
보조 게이트: `python3 tools/coverage_gate.py --config=policy_config.json --unit=<unit>`.

## 왜 build가 audit·render보다 먼저인가
- `build_spec.py`가 override를 적용한 뒤 **`rebuild_rollups`를 PI override 적용 직후(멱등)** 호출해야 PR/FN의 `related_policy_details`·UC 역참조·trace_matrix가 stale하지 않다. 순서가 틀리면 감사 B/C/G 그룹 위반이 폭증한다(→ `policy-integrity-audit`).
- 즉 **STRUCTURAL 위반은 거의 항상 "롤업을 다시 계산하라"는 신호** — 손으로 매핑을 고치지 말고 build가 돌게 한 뒤 재감사.

## 폐기 기준 (안전)
- audit STRUCTURAL > 0 → 이 편집 폐기, 원인 진단 후 재시도.
- `expected_counts`(예 hub 10/21/64/23/121) 와 어긋남 → 카운트 누수(stale id 등). 신규 편집이 아니면 폐기.
- 재빌드 시 spec/preview **byte 동일**이 재현성 증거. 의도치 않은 diff는 부작용 신호.

## 선별 커밋 (절대)
- `git add -A` 금지. **편집한 override + 재빌드 spec + preview**(필요 시 deliverable·감사 문서)만 stage.
- 중간 산출물(`audit/_coverage_work*/` 등)은 커밋 제외(gitignore).
- 커밋·푸시는 **사용자가 요청할 때만**. 기본 브랜치면 먼저 브랜치를 판다.

## 재편집 시 고정 규칙
한 번 완주한 unit(예 hub)을 다시 손댈 땐 **FN 레이어·명칭·applies_to·PI group_id 고정**. 값 확정/배지 제거만 하고 본문 구조는 안 바꾼다. `expected_counts` 고정으로 카운트 누수가 자동 검출된다.

## 내부 메모 처리
- 작업 메모는 `source_note`(렌더됨)가 아니라 **build 스크립트의 `#` 주석**에.
- to-be 개선안은 본문 직접수정 금지 → `field_review`·`internal_integration`·후보 문서로(→ `policy-detail-authoring`).
