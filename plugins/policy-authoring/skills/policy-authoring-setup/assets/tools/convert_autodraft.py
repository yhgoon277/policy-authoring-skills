#!/usr/bin/env python3
"""NC 자동초안(v0.11) → CS baseline 1회성 변환기 (unit당 1회).

자동초안은 우리 정본 스키마와 거의 동일하지만 (1) business_code가 unit별로 다름
(PIN/FAQ/YMX) (2) ID 형식이 audit 정규식 위반(US-·FN 접미사·PR 2단계·자릿수) (3) 필드가
별칭(policy_id/content)이고 function_details/process_details가 비어 있음 (4) trace_matrix가
요구사항 LIST. 이 변환기는 그 4가지를 결정론적으로 정규화해 build/audit가 도는 baseline을 만든다.

원칙: 콘텐츠 판단은 하지 않는다(통폐합·삭제는 Phase 1 작성에서). 여기선 ID 정규화 + 스키마 정렬만.

  ID 규칙: <TYPE>-CS-<DOMAIN>-NN  (PI 는 소속 PG 기준 -NN-NN, PR/FN 는 -NNN)
  PI 번호 = 소속 PG(remap)별 순차 → PI-CS-<DOM>-<PG2>-<seq2> (1단계 PI도 PG로 흡수)
  trace_matrix(LIST) → data/index/<unit>_requirement_coverage.jsonl (mapped_to remap)
  baseline.trace_matrix = {} (build가 dict 재생성)

사용: python3 convert_autodraft.py --config=policy_config.json --unit=<hub|faq|store>
"""
from __future__ import annotations
import ast
import json
import os
import re
import sys

DEFAULT_CONFIG = "policy_config.json"


def load_config(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def overlay_unit(cfg, unit):
    units = cfg.get("units") or {}
    if unit not in units:
        raise SystemExit(f"--unit={unit} 가 units 에 없습니다. 가능: {sorted(units)}")
    merged = dict(cfg)
    merged.update(units[unit])
    return merged


def dom_after_biz(old, biz_old):
    """'US-YMX-CS-001'->'CS' · 'FN-YMX-RQCOV-001-INF'->'RQCOV' · 'PR-YMX-CS-001-RQCOV-002'->'CS'."""
    m = re.match(rf"^[A-Z]+-{re.escape(biz_old)}-([A-Z]+)-", old)
    return m.group(1) if m else "MISC"


def seqmap(ids, biz_old, biz_new, new_type, width):
    """타입의 old id 리스트(문서순) → {old:new}, 도메인별 순차 번호."""
    counters, m = {}, {}
    for old in ids:
        dom = dom_after_biz(old, biz_old)
        counters[dom] = counters.get(dom, 0) + 1
        m[old] = f"{new_type}-{biz_new}-{dom}-{counters[dom]:0{width}d}"
    return m


def flatmap(ids, biz_old, biz_new, new_type, width):
    """도메인 없는 타입(ACT/TM/ST) → 순차. ACT는 prefix AC 로 축약."""
    m = {}
    for i, old in enumerate(ids, 1):
        m[old] = f"{new_type}-{biz_new}-{i:0{width}d}"
    return m


def main(argv):
    config_path, unit = DEFAULT_CONFIG, None
    for a in argv[1:]:
        if a.startswith("--config="):
            config_path = a.split("=", 1)[1].strip()
        elif a.startswith("--unit="):
            unit = a.split("=", 1)[1].strip()
    if not unit:
        print("ERROR: --unit=<hub|faq|store> 필요", file=sys.stderr)
        return 2
    cfg = overlay_unit(load_config(config_path), unit)
    biz_new = cfg.get("business_code", "CS")
    src = cfg["autodraft_spec"]
    out = cfg["baseline_spec_path"]
    d = json.load(open(src, encoding="utf-8"))
    biz_old = (d.get("meta") or {}).get("business_code") or "XXX"
    print(f"[convert] unit={unit} biz {biz_old}→{biz_new}  src={os.path.basename(src)}")

    ucs = d.get("usecases", [])
    prs = d.get("processes", [])
    fns = d.get("functions", [])
    pgs = d.get("policy_groups", [])
    pis = d.get("policy_details", [])
    acts = d.get("actors", [])
    tms = d.get("terms", [])
    sts = d.get("states", [])

    # ── 1) 타입별 remap (PI 제외) ──
    uc_map = seqmap([u["id"] for u in ucs], biz_old, biz_new, "UC", 2)
    pr_map = seqmap([p["id"] for p in prs], biz_old, biz_new, "PR", 3)
    fn_map = seqmap([f["id"] for f in fns], biz_old, biz_new, "FN", 3)
    pg_map = seqmap([g["id"] for g in pgs], biz_old, biz_new, "PG", 2)
    act_map = flatmap([a["id"] for a in acts], biz_old, biz_new, "AC", 2)
    tm_map = flatmap([t["id"] for t in tms], biz_old, biz_new, "TM", 3)
    st_map = flatmap([s["id"] for s in sts], biz_old, biz_new, "ST", 2)

    # ── 2) PI remap = 소속 PG(remap) 기준 순차. policy_id 미해결 PI는 MISC PG로 흡수 ──
    MISC_PG = f"PG-{biz_new}-MISC-01"
    pi_groups, orphan = {}, []
    for pi in pis:
        old_pg = pi.get("policy_id") or pi.get("group_id")
        new_pg = pg_map.get(old_pg)
        if not new_pg:
            new_pg = MISC_PG
            orphan.append(pi["id"])
        pi_groups.setdefault(new_pg, []).append(pi)
    pi_map = {}
    for new_pg, members in pi_groups.items():
        pi_base = "PI" + new_pg[2:]            # 'PG-CS-ACC-01' -> 'PI-CS-ACC-01'
        for j, pi in enumerate(members, 1):
            pi_map[pi["id"]] = f"{pi_base}-{j:02d}"

    all_map = {**uc_map, **pr_map, **fn_map, **pg_map, **pi_map, **act_map, **tm_map, **st_map}

    def R(x):
        return all_map.get(x, x)

    def Rlist(xs):
        return [R(x) for x in (xs or [])]

    # ── 3) 새 컬렉션 작성 ──
    new_uc = [{"id": R(u["id"]), "name": u.get("name", ""),
               "actor": R(u.get("actor")) if u.get("actor") in act_map else u.get("actor"),
               "description": u.get("description", ""),
               "process_target": u.get("process_target", "Y"),
               "related_processes": []} for u in ucs]

    new_pr, new_prd = [], []
    for p in prs:
        ucid = p.get("usecase_id")
        uids = p.get("usecase_ids") or ([ucid] if ucid else [])
        nid = R(p["id"])
        new_pr.append({"id": nid, "name": p.get("name", ""), "description": p.get("description", ""),
                       "usecase_ids": Rlist(uids),
                       "related_functions": Rlist(p.get("related_functions")),
                       "related_policies": Rlist(p.get("related_policies"))})
        new_prd.append({"process_id": nid})

    new_fn, new_fd = [], []
    for f in fns:
        nid = R(f["id"])
        pid = f.get("process_id")
        pids = f.get("process_ids") or ([pid] if pid else [])
        subs = list(f.get("details") or [])
        if not subs:
            subs = [f.get("name", "기능")]
        new_fn.append({"id": nid, "name": f.get("name", ""), "description": f.get("description", ""),
                       "process_id": R(pids[0]) if pids else R(pid),
                       "process_ids": Rlist(pids),
                       "related_policies": Rlist(f.get("related_policies"))})
        new_fd.append({"function_id": nid, "sub_functions": subs,
                       "subfn_pis": [[] for _ in subs], "subfn_ui": [False] * len(subs)})

    # PG: items 는 소속 PI 로 재구성(양방향 일치 보장) + MISC PG 필요 시 생성
    new_pi = []
    for pi in pis:
        nid = pi_map[pi["id"]]
        npg = R(pi.get("policy_id") or pi.get("group_id"))
        if pi["id"] in orphan:
            npg = MISC_PG
        new_pi.append({"id": nid, "name": pi.get("name", ""),
                       "group_id": npg, "policy_id": npg,
                       "rule_statement": pi.get("content", ""), "content": pi.get("content", "")})
    pi_by_pg = {}
    for npi in new_pi:
        pi_by_pg.setdefault(npi["group_id"], []).append({"id": npi["id"], "name": npi["name"]})

    new_pg = []
    for g in pgs:
        nid = R(g["id"])
        new_pg.append({"id": nid, "name": g.get("name", ""), "description": g.get("description", ""),
                       "items": pi_by_pg.get(nid, [])})
    if orphan:
        new_pg.append({"id": MISC_PG, "name": "미분류(변환 흡수)",
                       "description": "policy_id 미해결 PI 임시 수용. Phase 1에서 재배치.",
                       "items": pi_by_pg.get(MISC_PG, [])})

    new_policies = [{"id": g["id"], "name": g["name"], "items": list(g["items"])} for g in new_pg]

    new_actors = [{"id": R(a["id"]), "name": a.get("name", ""), "description": a.get("description", "")} for a in acts]
    new_terms = [{"id": R(t["id"]), "name": t.get("name", ""), "description": t.get("description", "")} for t in tms]
    new_states = [{"id": R(s["id"]), "name": s.get("name", ""), "description": s.get("description", ""),
                   "next_action": s.get("next_action", "")} for s in sts]
    new_strans = [{"usecase_ids": Rlist(s.get("usecase_ids")), "current_state": s.get("current_state", ""),
                   "event": s.get("event", ""), "next_state": s.get("next_state", ""),
                   "criteria": s.get("criteria", "")} for s in d.get("state_transitions", [])]

    m0 = d.get("meta") or {}
    new_meta = {"title": m0.get("topic_display") or m0.get("topic") or cfg.get("title", unit),
                "business_code": biz_new, "version": "v1.0",
                "topic": m0.get("topic", ""), "document_type": m0.get("document_type", "간소화 버전"),
                "date": m0.get("date", ""), "source_autodraft": os.path.basename(src),
                "_note": "자동초안 변환본(baseline). 콘텐츠 정제 전. PI 본문=자동초안 content."}

    spec = {
        "meta": new_meta,
        "history": d.get("history", []),
        "overview": d.get("overview", {}),
        "actors": new_actors,
        "terms": new_terms,
        "usecases": new_uc,
        "processes": new_pr, "process_details": new_prd,
        "functions": new_fn, "function_details": new_fd,
        "policy_groups": new_pg, "policies": new_policies,
        "policy_details": new_pi,
        "states": new_states, "state_transitions": new_strans,
        "final_check": d.get("final_check", []),
        "trace_matrix": {},
    }

    # ── 4) trace_matrix(LIST) → requirement_coverage.jsonl ──
    tm_in = d.get("trace_matrix")
    cov_path = os.path.join("data", "index", f"{unit}_requirement_coverage.jsonl")
    os.makedirs(os.path.dirname(cov_path), exist_ok=True)
    n_cov = 0
    with open(cov_path, "w", encoding="utf-8") as fh:
        if isinstance(tm_in, list):
            for e in tm_in:
                mt = e.get("mapped_to")
                if isinstance(mt, str):
                    try:
                        mt = ast.literal_eval(mt)
                    except Exception:
                        mt = [mt]
                fh.write(json.dumps({
                    "requirement_id": e.get("requirement_id") or e.get("detail_id"),
                    "detail_name": e.get("detail_name", ""),
                    "detail_description": e.get("detail_description", ""),
                    "requirement_group": e.get("requirement_group", ""),
                    "depth4": e.get("depth4", ""), "priority": e.get("priority", ""),
                    "source": e.get("source", ""), "owner_team": e.get("owner_team", ""),
                    "coverage": e.get("coverage", ""),
                    "mapped_to": Rlist(mt) if isinstance(mt, list) else mt,
                    "rationale": e.get("rationale", ""),
                }, ensure_ascii=False) + "\n")
                n_cov += 1

    # ── 5) 저장 + id_remap + 진단 ──
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    json.dump(spec, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    remap_path = os.path.join(os.path.dirname(out), f"{unit}_id_remap.json")
    json.dump(all_map, open(remap_path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)

    # 교차참조 미해결 점검
    valid = set(all_map.values()) | {MISC_PG}
    dangling = []
    for p in new_pr:
        for x in p["related_functions"] + p["related_policies"] + p["usecase_ids"]:
            if re.match(r"^(UC|PR|FN|PG|PI)-", x) and x not in valid:
                dangling.append((p["id"], x))
    for f in new_fn:
        for x in [f["process_id"]] + f["process_ids"]:
            if x and re.match(r"^(UC|PR|FN|PG|PI)-", x) and x not in valid:
                dangling.append((f["id"], x))

    print(f"  counts: UC {len(new_uc)} · PR {len(new_pr)} · FN {len(new_fn)} · PG {len(new_pg)} · PI {len(new_pi)}")
    print(f"  orphan PI(→MISC): {len(orphan)}  | trace→coverage: {n_cov}건 ({cov_path})")
    print(f"  dangling refs: {len(dangling)}" + (f"  예: {dangling[:5]}" if dangling else ""))
    print(f"  [write] {out}")
    print(f"  [write] {remap_path}")
    print("  다음: build_spec.py --unit 으로 build → audit_id_integrity.py 로 STRUCTURAL 0 확인.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
