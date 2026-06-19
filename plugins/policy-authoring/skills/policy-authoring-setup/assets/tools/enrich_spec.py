"""NC-네이티브 스키마 보강 — 빌링 enrich_spec.py 이식·파라미터화(hub).

build_spec.py가 빌드 말미에 enrich(spec, business_code) 를 호출해 NC스튜디오가 읽는
풀 스키마의 빈 필드를 자동 보강한다. 자동 가능한 필드만 채우고, 의미 판단이 필요한
값(decision_spec 내용·FN 본문 input/processing/output/bdd 등)은 작성 worklist로 남긴다.

NC 렌더 결함 직격 fixer:
  - processes[].usecase_id (단수)   ← UC 그룹핑(섹션4) — 빌링 enrich엔 없던 hub 추가분
  - functions[].details             ← '세부 기능 구성'(섹션5) = function_details.sub_functions 복사
  - functions[].mockup_component_level / function_type / granularity
  - process_details[].related_functions·usecase_ids·case_branches·process_role_by_usecase·process_policy_role
  - policies[]/policy_groups[].items = [{id,name}]   ← 정책 목록 셀
  - policy_details[].mockup_binding·mockup_impact·source_basis(=source_note)·review_status(skeleton)

빌링 대비 차이: BIL 리터럴 → business_code 파라미터화. usecase_id 단수 파생 추가.
"""
from __future__ import annotations

import json
import os
import re
import sys
import unicodedata
from collections import defaultdict

PROCESS_POLICY_ROLE_STANDARD = (
    "프로세스는 상태별 화면군을 포괄하며, 관련 기능과 정책상세를 통해 "
    "목업의 컴포넌트·CTA·예외 케이스를 결정한다."
)


# ── hub 추가: NC가 읽는 단수/미러 필드 (빌링은 to_be_draft에서 이미 보유) ──
def enrich_nc_aliases(spec: dict) -> dict:
    """NC 네이티브 단수·미러 필드 보강. UC 그룹핑·process_details 조인 키."""
    pr_by_id = {p["id"]: p for p in spec.get("processes", [])}
    uc_added = 0
    for p in spec.get("processes", []):
        ucs = p.get("usecase_ids") or ([p["usecase_id"]] if p.get("usecase_id") else [])
        if ucs and not p.get("usecase_id"):
            p["usecase_id"] = ucs[0]            # ← NC 섹션4 UC 그룹핑 키 (확증된 fix)
            uc_added += 1
    pd_mirror = 0
    for pd in spec.get("process_details", []):
        pr = pr_by_id.get(pd.get("process_id")) or {}
        if not pd.get("related_functions") and pr.get("related_functions"):
            pd["related_functions"] = list(pr["related_functions"])
            pd_mirror += 1
        if not pd.get("usecase_ids") and pr.get("usecase_ids"):
            pd["usecase_ids"] = list(pr["usecase_ids"])
    print(f"  [enrich_nc_aliases] usecase_id 단수 {uc_added}건 · process_details.related_functions 미러 {pd_mirror}건")
    return spec


def enrich_process_details(spec: dict) -> dict:
    """process_details 빈 필드 자동 보강(case_branches·role)."""
    pr_to_uc = defaultdict(list)
    for p in spec.get("processes", []):
        for uc in p.get("usecase_ids", []) or ([p.get("usecase_id")] if p.get("usecase_id") else []):
            if uc:
                pr_to_uc[p["id"]].append(uc)
    fd_by_id = {f.get("function_id"): f for f in spec.get("function_details", [])}
    for pd in spec.get("process_details", []):
        pid = pd["process_id"]
        if not pd.get("case_branches"):
            branches = []
            for fn_id in pd.get("related_functions", []):
                fd = fd_by_id.get(fn_id)
                if fd:
                    for bdd in fd.get("bdd_scenarios", []):
                        if isinstance(bdd, dict):
                            label = bdd.get("scenario") or bdd.get("name") or bdd.get("then") or bdd.get("given", "")
                            if label:
                                branches.append(str(label)[:80])
            pd["case_branches"] = branches[:6]
        if not pd.get("process_role_by_usecase"):
            pd["process_role_by_usecase"] = {uc: "primary" for uc in pr_to_uc.get(pid, [])}
        if not pd.get("process_policy_role"):
            pd["process_policy_role"] = PROCESS_POLICY_ROLE_STANDARD
    return spec


def enrich_function_details(spec: dict, business_code: str) -> dict:
    """function_details 빈 필드 자동 보강(component_policy_role)."""
    for fd in spec.get("function_details", []):
        if not fd.get("component_policy_role"):
            cats = set()
            for pi in fd.get("related_policy_details", []):
                parts = pi.split("-")  # PI-CS-ACC-01-01 → cat = ACC
                if len(parts) >= 3 and parts[1] == business_code:
                    cats.add(parts[2])
                elif len(parts) >= 2:
                    cats.add(parts[1])
            fd["component_policy_role"] = {
                "cat_coverage": sorted(cats),
                "role": "본 함수는 위 카테고리 정책 상세를 컴포넌트 동작 조건으로 적용한다.",
            }
        if "sub_functions" not in fd:
            fd["sub_functions"] = []
    return spec


def enrich_processes(spec: dict) -> dict:
    """processes 본문 빈 필드 보강(process_unit·state_variants 기본값)."""
    for p in spec.get("processes", []):
        if not p.get("process_unit"):
            p["process_unit"] = "메뉴/서브메뉴 또는 한 화면"
        if not p.get("state_variants"):
            p["state_variants"] = []
    return spec


def synthesize_sub_functions(fn: dict) -> list[str]:
    """FN name에서 UI element 추론(빈 sub_functions 폴백)."""
    name = fn.get("name", "")
    for keyword, elements in _UI_ELEMENT_PATTERNS:
        if keyword in name:
            return list(elements)
    return ["주요 정보 표시 영역", "사용자 입력·선택 컨트롤", "실행·확인 액션", "결과·실패 안내"]


_UI_ELEMENT_PATTERNS = [
    ("위젯", ["데이터 표시 영역", "실시간 새로고침 트리거", "위젯 진입 액션", "에러·로딩 상태 표시"]),
    ("배너", ["배너 텍스트 영역", "강조 색상·아이콘", "다음 행동 CTA", "닫기·숨김 컨트롤"]),
    ("카드", ["카드 헤더", "카드 본문 컨텐츠", "카드 액션 영역", "확장·상세 진입 링크"]),
    ("리스트", ["리스트 행 표시", "정렬·필터 컨트롤", "행 선택·클릭 액션", "페이지네이션·더보기"]),
    ("입력 폼", ["입력 필드", "실시간 검증 메시지", "필수 항목 표시", "제출 CTA"]),
    ("입력", ["입력 필드", "입력값 검증", "도움말·안내 텍스트", "제출 CTA"]),
    ("폼", ["입력 필드 그룹", "검증 메시지", "필수·선택 표시", "제출·취소 버튼"]),
    ("모달", ["모달 헤더·닫기", "본문 컨텐츠 영역", "확인·취소 액션", "백드롭 영역"]),
    ("토글", ["ON/OFF 스위치", "상태 라벨", "변경 confirm", "비활성 안내 텍스트"]),
    ("선택", ["선택 옵션 표시", "선택 상태 강조", "선택 변경 액션", "다음 단계 CTA"]),
    ("버튼", ["버튼 라벨", "활성·비활성 상태", "클릭 핸들러", "처리 중 표시"]),
    ("진입", ["진입 트리거 액션", "권한·조건 검증", "진입 후 화면 전환", "진입 실패 안내"]),
    ("조회", ["조회 조건 입력", "결과 데이터 표시", "조회 실패·빈 결과 안내", "다음 행동 CTA"]),
    ("검증", ["검증 조건 체크", "검증 결과 메시지", "실패 시 입력 강조", "재시도 액션"]),
    ("표시", ["주요 데이터 표시", "추가 정보 토글", "상태별 강조 스타일", "빈 데이터 fallback"]),
    ("안내", ["안내 텍스트 영역", "강조 아이콘", "관련 액션 링크", "닫기·확인"]),
    ("결과", ["결과 요약 표시", "성공·실패 분기 표현", "다음 행동 CTA", "에러 사유 안내"]),
    ("등록", ["등록 입력 폼", "등록 가능 여부 검증", "등록 완료 안내", "등록 실패 사유"]),
    ("동의", ["동의 항목 목록", "동의·미동의 체크", "약관 상세 링크", "동의 제출 CTA"]),
    ("인증", ["인증 입력 필드", "재전송·타이머", "인증 시도 결과", "인증 실패 안내"]),
    ("이력", ["이력 행 목록", "기간·유형 필터", "행 상세 진입", "다운로드·내보내기"]),
    ("관리", ["대상 목록 표시", "추가·변경·삭제 액션", "권한 확인 표시", "변경 이력"]),
    ("처리", ["처리 진행 표시", "단계별 상태", "결과 안내", "실패 시 재시도"]),
]


def enrich_functions(spec: dict) -> dict:
    """functions 본문 빈 필드 보강(mockup_component_level·function_type·granularity·sub_functions 폴백)."""
    sub_filled = 0
    for f in spec.get("functions", []):
        if not f.get("mockup_component_level"):
            f["mockup_component_level"] = "component"
        if not f.get("function_type"):
            f["function_type"] = "screen_component"
        if not f.get("granularity"):
            f["granularity"] = "function"
    for fd in spec.get("function_details", []):
        if not fd.get("sub_functions"):
            fn = next((x for x in spec.get("functions", []) if x["id"] == fd["function_id"]), None)
            if fn:
                fd["sub_functions"] = synthesize_sub_functions(fn)
                sub_filled += 1
    if sub_filled:
        print(f"  [enrich_functions] sub_functions 폴백 채움: {sub_filled}건")
    return spec


# decision_spec 판정축 파생용 키워드(criteria/rule 원문을 축으로 라우팅 — 날조 0)
_AXIS_KEYWORDS = {
    "restriction_rule": ("제한", "불가", "초과", "한도", "만료", "금지", "차단", "미허용", "한정", "제외", "최대", "최소",
                         "이내", "범위", "경우에만", "충족된 경우", "확인된 경우", "확인한 경우", "한해", "에 한",
                         "처리 전", "전 본인확인"),
    "exception_deny": ("예외", "실패 시", "실패하면", "미충족", "안 되면", "불충족", "거부", "반려", "오류 시", "불가 시",
                       "없거나", "부족하면", "않으면", "지나면", "초과하면", "종결하지", "바뀌거나"),
    "priority": ("우선", "먼저", "순위", "긴급", "선제"),
    "history_logging": ("이력", "저장", "기록"),
}


def _route_axes(criteria, rule):
    """criteria/rule 원문을 키워드로 decision_spec 판정축에 라우팅(다축 허용·원문 재사용·날조 0).
    매칭 없는 축은 반환하지 않음(빈 축 omit → '(없음)' 리터럴 폐기)."""
    sources = [c for c in (criteria or []) if c]
    if rule:
        sources.append(rule)
    out = {}
    for axis, kws in _AXIS_KEYWORDS.items():
        matched = [s for s in sources if any(k in s for k in kws)]
        if matched:
            out[axis] = " / ".join(matched)
    return out


def enrich_policy_details(spec: dict) -> dict:
    """policy_details 본문 빈 필드 보강(mockup_binding·mockup_impact·source_basis·review_status·
    rule_type·decision_spec skeleton).

    decision_spec 스켈레톤(빌링 8키 관례): override 작성본이 없으면 기존 criteria_values·
    rule_statement·customer_notice에서 기계적으로 시드. 스켈레톤 존재 = STRUCTURAL(K4) 충족용,
    내용 품질은 배치별 override 작성·검토(SEMANTIC)."""
    ds_seeded = 0
    for pd in spec.get("policy_details", []):
        rule = pd.get("rule_statement", "") or pd.get("content", "")
        if not pd.get("rule_type"):
            pd["rule_type"] = "기준값"
        if not pd.get("decision_spec"):
            crit_list = pd.get("criteria_values") or []
            notice = pd.get("customer_notice") or ""
            ds = {}
            cv = " / ".join(crit_list) or (rule[:160] if rule else "")
            if cv:
                ds["criteria_values"] = cv
            if rule:
                ds["allow_rule"] = rule
            ds.update(_route_axes(crit_list, rule))      # 판정축 파생(빈 축 omit·criteria 원문 재사용·날조 0)
            if notice:
                ds["customer_notice"] = f"“{notice}”"
            pd["decision_spec"] = ds or {"criteria_values": "(기준 정의 예정)"}
            ds_seeded += 1
        if not pd.get("mockup_binding"):
            pd["mockup_binding"] = {
                "affects_visibility": [], "affects_cta_state": [], "affects_copy": [],
                "affected_components": [], "affected_states": [], "affected_ctas": [],
            }
        if not pd.get("mockup_impact"):
            pd["mockup_impact"] = rule[:200] if rule else ""
        if not pd.get("source_basis") and pd.get("source_note"):
            pd["source_basis"] = pd["source_note"]          # 기존 source_note 매핑
        if not pd.get("review_status"):
            pd["review_status"] = "review" if pd.get("field_review") else "draft"
    if ds_seeded:
        print(f"  [enrich_policy_details] decision_spec 스켈레톤 시드: {ds_seeded}건")
    return spec


def enrich_functions_details_alias(spec: dict) -> dict:
    """NC 호환: functions[].details = function_details[fn].sub_functions 복사 (세부 기능 구성 컬럼 fix)."""
    sub_by_fid = {fd["function_id"]: fd.get("sub_functions", []) for fd in spec.get("function_details", [])}
    copied = 0
    for fn in spec.get("functions", []):
        subs = sub_by_fid.get(fn["id"], [])
        if subs:
            fn["details"] = list(subs)
            copied += 1
    print(f"  [enrich_functions_details_alias] functions[].details 채움: {copied}건")
    return spec


def enrich_policies_items(spec: dict) -> dict:
    """NC 호환: policies[]/policy_groups[].items = [{id,name}] (정책 목록 셀)."""
    items_by_pg: dict[str, list] = {}
    for pi in spec.get("policy_details", []):
        gid = pi.get("group_id") or pi.get("policy_id")
        if gid:
            items_by_pg.setdefault(gid, []).append({"id": pi["id"], "name": pi.get("name", "")})
    total = 0
    for pg_key in ("policies", "policy_groups"):
        for pg in spec.get(pg_key, []):
            pg["items"] = items_by_pg.get(pg["id"], [])
            total += len(pg["items"])
    print(f"  [enrich_policies_items] PG.items 채움: {total}건")
    return spec


def enrich(spec: dict, business_code: str = "CS") -> dict:
    """모든 enrichment 일괄 적용 (build_spec.py에서 bake/normalize 후 호출)."""
    spec = enrich_nc_aliases(spec)
    spec = enrich_process_details(spec)
    spec = enrich_function_details(spec, business_code)
    spec = enrich_processes(spec)
    spec = enrich_functions(spec)
    spec = enrich_functions_details_alias(spec)
    spec = enrich_policy_details(spec)
    spec = enrich_policies_items(spec)
    return spec


def _norm_req_name(s: str) -> str:
    """요구명 정규화(브리지 키): NFKC·소문자·구분자 제거. NC식 요구명 ↔ REQ-HUB 매칭용."""
    s = unicodedata.normalize("NFKC", s or "").lower().replace("1:1", "1대1")
    return re.sub(r"[\s/·•(),'\"\-:&’‘“”]+", "", s)


def emit_requirement_links(spec: dict, cfg: dict) -> dict:
    """요구사항↔노드 연결을 NC 네이티브 meta.topic_learning + 노드 필드에 결정적 임베드.
    소스: tracked 매트릭스(coverage_gate.parse_matrix + NODE_RE) → REQ-HUB→노드(라이브 필터),
          nc_coverage_path(NC식 요구 ID·명) → 요구명 정규화로 REQ-HUB 브리지.
    미매치 NC 요구는 cfg.requirement_links.nc_only_dispositions(범위밖/타모듈/전략/의미연결)로 verdict.
    타깃: emit{meta,nodes} 플래그. dangling 0(라이브 노드만 emit)·멱등·sorted. 설정 없으면 no-op.
    build_spec.main 에서 enrich() 직후·json.dump 직전 호출(cfg 전달)."""
    rl = (cfg or {}).get("requirement_links") or {}
    if not rl:
        return spec
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from coverage_gate import parse_matrix, NODE_RE

    live = set()
    for c in ("usecases", "processes", "functions", "policy_groups", "policy_details"):
        live |= {o["id"] for o in spec.get(c, [])}

    # REQ-HUB → {decision, 라이브 노드}  (노드는 tracked 매트릭스에서만, 라이브 필터로 dangling 0)
    matrix = {}
    for row in parse_matrix(rl["matrix_path"]):
        nodes = sorted({n for n in NODE_RE.findall(row.get("nodes_cell") or "") if n in live})
        matrix[row["req_id"]] = {"decision": (row.get("decision") or "").strip(), "nodes": nodes}

    # 요구명 정규화 → REQ-HUB (브리지, 해당 unit 한정)
    unit_lc = (cfg.get("domain") or "").lower()
    name_to_reqhub = {}
    with open(rl["requirements_index_path"], encoding="utf-8") as fh:
        for line in fh:
            r = json.loads(line)
            if r.get("unit") == unit_lc:
                name_to_reqhub[_norm_req_name(r.get("name"))] = r["requirement_id"]

    disp = rl.get("nc_only_dispositions") or {}
    links = []
    node_ids, node_refs = defaultdict(set), defaultdict(set)
    with open(rl["nc_coverage_path"], encoding="utf-8") as fh:
        for line in fh:
            nc = json.loads(line)
            ncid, name = nc["requirement_id"], nc.get("detail_name", "")
            reqhub = name_to_reqhub.get(_norm_req_name(name))
            if ncid in disp:                                     # 명시 disposition(매뉴얼 오버라이드) 우선
                decision = disp[ncid].get("decision", "범위밖")
                nodes = sorted(n for n in (disp[ncid].get("nodes") or []) if n in live)
                # reqhub(브리지된 게 있으면)는 our_requirement_ref 정보로 유지
            elif reqhub and reqhub in matrix:                    # 브리지 매치 → 매트릭스 노드
                decision, nodes = matrix[reqhub]["decision"], matrix[reqhub]["nodes"]
            else:
                decision, nodes, reqhub = "미매핑", [], None
            links.append({"requirement_id": ncid, "requirement_name": name,
                          "our_requirement_ref": reqhub, "decision": decision, "nodes": nodes})
            for n in nodes:
                node_ids[n].add(ncid)
                if reqhub:
                    node_refs[n].add(reqhub)
    links.sort(key=lambda x: x["requirement_id"])

    emit = rl.get("emit") or {}
    if emit.get("meta"):
        tl = spec.setdefault("meta", {}).setdefault("topic_learning", {})
        tl["requirements_count"] = len(links)
        tl.setdefault("prelearned_knowledge", {}).setdefault("source_profile", {})["requirement_ids"] = \
            sorted(l["requirement_id"] for l in links)
        tl["requirement_implications"] = [
            f"{l['requirement_id']} ({l['requirement_name']}): "
            + ("·".join(l["nodes"]) + "에 연결" if l["nodes"] else l["decision"])
            for l in links
        ]
        tl["requirement_links"] = links
    if emit.get("nodes"):
        for c in ("usecases", "processes", "functions", "policy_groups", "policy_details"):
            for o in spec.get(c, []):
                if o["id"] in node_ids:
                    o["source_requirement_ids"] = sorted(node_ids[o["id"]])
                    o["source_requirement_refs"] = sorted(node_refs[o["id"]])
    linked = sum(1 for l in links if l["nodes"])
    print(f"  [emit_requirement_links] NC요구 {len(links)} "
          f"(노드연결 {linked}·범위밖/전략/타모듈 {len(links) - linked}) · 노드참조 {len(node_ids)}")
    return spec


def main(argv) -> int:
    """스탠드얼론 스모크: config의 spec_path를 읽어 enrich 후 핵심 필드 충족률 보고(미저장)."""
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from build_spec import load_config, overlay_unit
    config_path, unit = "policy_config.json", None
    for a in argv[1:]:
        if a.startswith("--config="):
            config_path = a.split("=", 1)[1].strip()
        elif a.startswith("--unit="):
            unit = a.split("=", 1)[1].strip()
    cfg = overlay_unit(load_config(config_path), unit)
    spec = json.load(open(cfg["spec_path"], encoding="utf-8"))
    spec = enrich(spec, cfg.get("business_code", "CS"))
    uc = sum(1 for p in spec["processes"] if p.get("usecase_id"))
    det = sum(1 for f in spec["functions"] if f.get("details"))
    print(f"  [smoke] processes.usecase_id: {uc}/{len(spec['processes'])} · "
          f"functions.details: {det}/{len(spec['functions'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
