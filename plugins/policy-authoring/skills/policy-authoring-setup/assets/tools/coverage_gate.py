#!/usr/bin/env python3
"""커버리지 게이트 — unit 커버리지 매트릭스가 '누락 없이' 채워졌는지 결정론 검사.

검사(unit 단위):
  1) 매트릭스 모든 행에 '통폐합 결정' 존재.
  2) unit 요구사항(requirements.jsonl) 전건이 매트릭스에 있고 ≥1 to-be 노드 매핑 OR 명시적 범위밖/삭제.
  3) 매트릭스가 참조한 to-be 노드 ID가 spec에 실존.
종료코드: 위반 있으면 1.

사용: python3 coverage_gate.py --config=policy_config.json --unit=<hub|faq|store>
"""
from __future__ import annotations
import json
import os
import re
import sys

DEFAULT_CONFIG = "policy_config.json"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NODE_RE = re.compile(r"\b(?:UC|PR|FN|PG|PI)-[A-Z]+-[A-Z]+-\d+(?:-\d+)?\b")
OUT_OF_SCOPE = ("범위밖", "삭제")


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


def parse_matrix(path):
    """md 표 → [{req_id, decision, nodes_cell, asis_cell}] (헤더/구분선 제외)."""
    rows = []
    if not os.path.exists(path):
        return rows
    for ln in open(path, encoding="utf-8"):
        ln = ln.rstrip("\n")
        if not ln.startswith("|"):
            continue
        cells = [c.strip() for c in ln.strip("|").split("|")]
        if len(cells) < 6 or cells[0] in ("#", "") or set(cells[0]) <= set("-: "):
            continue
        # 열: # | requirement_id | 요구사항명 | FO/BO | 통폐합 결정 | to-be 노드 | as-is 출처 | 메모
        rows.append({"req_id": cells[1], "decision": cells[4] if len(cells) > 4 else "",
                     "nodes_cell": cells[5] if len(cells) > 5 else "",
                     "asis_cell": cells[6] if len(cells) > 6 else ""})
    return rows


def main(argv):
    config_path, unit = DEFAULT_CONFIG, None
    for a in argv[1:]:
        if a.startswith("--config="):
            config_path = a.split("=", 1)[1].strip()
        elif a.startswith("--unit="):
            unit = a.split("=", 1)[1].strip()
    if not unit:
        print("ERROR: --unit 필요", file=sys.stderr)
        return 2
    cfg = overlay_unit(load_config(config_path), unit)

    spec = json.load(open(cfg["spec_path"], encoding="utf-8"))
    node_ids = set()
    for k in ("usecases", "processes", "functions", "policy_groups", "policy_details"):
        node_ids |= {n["id"] for n in spec.get(k, [])}

    reqs = [json.loads(l) for l in open(os.path.join(ROOT, "data", "index", "requirements.jsonl"), encoding="utf-8")]
    unit_reqs = [r["requirement_id"] for r in reqs if r["unit"] == unit]

    matrix = parse_matrix(os.path.join(ROOT, "audit", f"{unit}_coverage_matrix.md"))
    by_req = {}
    for row in matrix:
        by_req.setdefault(row["req_id"], []).append(row)

    miss_decision, unmapped, bad_nodes, missing_rows = [], [], [], []
    for row in matrix:
        if not row["decision"]:
            miss_decision.append(row["req_id"])
        for nid in NODE_RE.findall(row["nodes_cell"]):
            if nid not in node_ids:
                bad_nodes.append((row["req_id"], nid))
    for rid in unit_reqs:
        rows = by_req.get(rid)
        if not rows:
            missing_rows.append(rid)
            continue
        mapped = any(NODE_RE.search(r["nodes_cell"]) for r in rows)
        oos = any(any(t in r["decision"] for t in OUT_OF_SCOPE) for r in rows)
        if not mapped and not oos:
            unmapped.append(rid)

    print(f"=== 커버리지 게이트: {unit} ===")
    print(f"  요구사항(unit): {len(unit_reqs)} · 매트릭스 행: {len(matrix)} · spec 노드: {len(node_ids)}")
    print(f"  [1] 결정 누락 행: {len(miss_decision)}{'  예:'+str(miss_decision[:5]) if miss_decision else ''}")
    print(f"  [2a] 매트릭스 미등재 요구: {len(missing_rows)}{'  예:'+str(missing_rows[:5]) if missing_rows else ''}")
    print(f"  [2b] 미매핑(노드·범위밖 모두 없음) 요구: {len(unmapped)}{'  예:'+str(unmapped[:5]) if unmapped else ''}")
    print(f"  [3] 미존재 노드 참조: {len(bad_nodes)}{'  예:'+str(bad_nodes[:5]) if bad_nodes else ''}")
    total = len(miss_decision) + len(missing_rows) + len(unmapped) + len(bad_nodes)
    print(f"  === {'PASS ✓' if total == 0 else f'위반 {total} (커버리지 미완성)'} ===")
    return 1 if total else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
