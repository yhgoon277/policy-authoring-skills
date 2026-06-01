# 정합성 불변식 A~I (상세)

`audit_id_integrity.py`가 검사하는 9개 그룹의 불변식. 각 항목의 **분류**(STRUCTURAL=자동수정 대상·목표 0 / SEMANTIC=사람 판단)와 의미.

## 목차
- [A 참조 존재성 (dangling)](#a-참조-존재성-dangling)
- [B 양방향 일치](#b-양방향-일치)
- [C 롤업/파생](#c-롤업파생)
- [D PG 멤버십](#d-pg-멤버십)
- [E 커버리지/고아](#e-커버리지고아)
- [F 세부기능 배열](#f-세부기능-배열)
- [G trace_matrix ↔ 컬렉션](#g-trace_matrix--컬렉션)
- [H 형식·유일성·카운트](#h-형식유일성카운트)
- [I 표현 표준(가독성)](#i-표현-표준가독성)
- [롤업 재계산 (rebuild_rollups) 패턴](#롤업-재계산-rebuild_rollups-패턴)

---

## A 참조 존재성 (dangling)
모든 전방 참조가 실재하는지. **전부 STRUCTURAL.**

| ID | 검사 |
|---|---|
| A1 | UC.related_processes → PR 존재 |
| A2 | PR.usecase_id(s) → UC 존재 |
| A3 | PR.related_functions → FN 존재 |
| A4 | FN.process_id(s) → PR 존재 |
| A5 | PR.related_policies → PG 존재 |
| A6 | PR.related_policy_details → PI 존재 |
| A7 | FN.related_policies → PG 존재 |
| A8 | FN.related_policy_details → PI 존재 |
| A9 | PI.applies_to_functions → FN 존재 / PI.applies_to `FN#idx` → FN 존재 + idx가 sub_functions 범위 내 |
| A10 | PG.items → PI 존재 |
| A11 | PI.group_id / policy_id → PG 존재 |
| A12 | FD.subfn_pis → PI 존재 |

## B 양방향 일치
한쪽 링크가 있으면 반대쪽 역참조도 있어야. **전부 STRUCTURAL.**

| ID | 검사 |
|---|---|
| B1 | UC.related_processes ↔ PR.usecase_ids |
| B2 | PR.related_functions ↔ FN.process_id(s) |
| B3 | FN.related_policy_details ↔ PI.applies_to_functions |
| B4 | PG.items ↔ PI.group_id (집합 동일) |
| B5 | PI.applies_to `FN#idx` ↔ FD.subfn_pis[idx] 에 그 PI 포함 |
| B6 | PR.usecase_id(단수) ⊆ usecase_ids(복수) |

## C 롤업/파생
파생 필드가 진실원천과 일치하는지.

| ID | 검사 | 분류 |
|---|---|---|
| C1 | FN.related_policy_details == ∪(FD.subfn_pis) | STRUCTURAL |
| C2 | PR.related_policy_details == ∪(소속 FN.rpd). **FN_only**(FN엔 있는데 PR 누락)=STRUCTURAL / **PR_only**(PR 직접선언, FN엔 없음)=**SEMANTIC** | 혼합 |
| C3 | FN.related_policies ⊇ derive_PG(FN.rpd) (누락만 위반, 초과는 fallback 허용) | STRUCTURAL |
| C4 | PR.related_policies ⊇ derive_PG(PR.rpd) (누락만) | STRUCTURAL |
| C5 | FD.related_policy_details == FN.related_policy_details (미러) | STRUCTURAL |

> C2 PR_only = "PR이 직접 PI를 가리키지만 어느 FN 세부기능에도 없음". 의미상 정상이면 `known_pr_only`에 등록(→ "알려진 정상"), 아니면 ★미검토.

## D PG 멤버십
| D1 | PG.items 집합 == 그 PG를 group_id로 가진 PI 집합. (B4의 독립 재구현) | STRUCTURAL |

## E 커버리지/고아
| ID | 검사 | 분류 |
|---|---|---|
| E1 | 모든 UC에 연결 PR 존재 | STRUCTURAL (단 `process_target=N` UC는 SEMANTIC=의도된 비프로세스) |
| E2 | 모든 PR에 FN 존재 | STRUCTURAL |
| E3 | 모든 PR에 UC 존재 | STRUCTURAL |
| E4 | 모든 FN에 PI ≥1 | SEMANTIC (고아 후보) |
| E5 | 모든 PG에 PI ≥1 | STRUCTURAL |
| E6 | 모든 PI가 ≥1 FN에 적용 | SEMANTIC (배경/위임/미구현 PI 후보) |

> E4·E6은 의도된 배경 항목일 수 있다. 의도면 사유를 **렌더 비노출 내부 코드 주석**으로 남기고 그대로 둔다(근거 필드에 적으면 기획자에게 노출돼 혼란).

## F 세부기능 배열
| ID | 검사 |
|---|---|
| F1 | len(sub_functions) == len(subfn_pis) == len(subfn_ui) (STRUCTURAL) |
| F2 | subfn_ui 는 **불리언 배열**(위치별 UI여부) — 인덱스 리스트 아님 (STRUCTURAL) |

> ⚠️ subfn_pis/subfn_ui는 **위치(인덱스) 기반**. 세부기능 이름을 바꾸느라 배열 길이·순서를 건드리면 F1과 A9/B5가 동시에 깨진다(②의 인덱스 보존 가드 참조).

## G trace_matrix ↔ 컬렉션
| ID | 검사 |
|---|---|
| G0 | trace_matrix 가 dict |
| G1 | uc_to_process 키가 현 UC id 체계와 일치(옛 short-id면 stale) |
| G2 | process_to_function 키가 현 PR id와 일치 |
| G3 | function_to_policy_detail 존재 + FN.rpd와 일치 |
| G4 | policy_detail_to_function 존재 |
| G6 | coverage 카운트 == 실측 |

전부 STRUCTURAL. trace_matrix는 보통 rebuild_rollups가 재생성하므로 G 위반 = 재생성 누락 신호.

## H 형식·유일성·카운트
| ID | 검사 |
|---|---|
| H1 | id prefix 규약(UC-/PR-/FN-/PG-/PI-) |
| H2 | 전역 id 유일성(중복 금지) |
| H3 | 컬렉션 카운트 == `config.expected_counts` (미설정 시 검사 생략, 실측만 보고) |
| H4 | id 정규식 `<TYPE>-<BIZ>-<DOMAIN>-NN` (PI는 `-NN-NN`). BIZ = config.business_code |
| H5 | policies == policy_groups (alias 일치) |

전부 STRUCTURAL.

## I 표현 표준(가독성)
| ID | 검사 | 분류 |
|---|---|---|
| I1 | 세부기능명에 괄호 `(` 없음 | SEMANTIC |
| I2 | PI명(끝단 `(ID)` 제외 base)에 금지 토큰(×·→·매트릭스·CTA·link 등, `config.naming_banned_tokens`) 없음 | SEMANTIC |

`policy-naming-readability`(②) 규칙의 자동 검출기. exit 1을 유발하지 않는다.

---

## 롤업 재계산 (rebuild_rollups) 패턴

STRUCTURAL B/C/G 대량 위반의 표준 해결책. **순서가 핵심**: 모든 내용 override를 적용한 **뒤** 파생 필드를 재계산한다.

빌드 파이프라인 순서:
```
1) baseline 로드 → 2) PI/FN/PR/PG override 적용 (내용·매핑)
3) rebuild_rollups(spec)   ← override 직후, 멱등
4) 용어 치환 (apply_term_replacements) ← 맨 마지막
```

`rebuild_rollups`가 진실원천에서 재생성하는 것(이 순서대로):
1. `FN.related_policy_details = ∪(FD.subfn_pis)` — 세부기능에 붙은 PI를 FN으로 합산.
2. `PR.related_policy_details = ∪(소속 FN.rpd) + PR_only(의도된 직접선언)`.
3. `FN.related_policies = derive_PG(FN.rpd)` — PI를 부모 PG로 매핑.
4. `PR.related_policies = merge(기존, 파생, 수동 fallback)`.
5. `FD ↔ FN` 미러 동기화.
6. `PI ↔ FN` 양방향 동기화 / `UC ← PR` 역참조 생성.
7. `trace_matrix` 재생성 + coverage 카운트 갱신.

성질: **멱등**(여러 번 돌려도 동일), PI 본문·sub_functions·subfn_pis(진실원천)는 **불변**, 파생/롤업 필드만 갱신. 구현 골격은 `build_spec_template.py`(⑤가 설치)에 포함.
