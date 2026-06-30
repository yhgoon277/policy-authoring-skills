#!/usr/bin/env python3
"""Deferred-work manifest + enforced close-gate (plugin governance).

format+render+consistency is the automatable 'done'; anything the pass could NOT
complete (FN-graph STRUCTURAL violations, render loss, NC upload blockers) is
captured here as an EXPLICIT, 담당자-decidable artifact — never a silent skip.

  generate : run audit (--json) [+ optional preview parity] → group violations into
             actionable items {what, why, impact, ids, options, disposition:null}
             → write audit/<module>_deferred_manifest.json + .md, print status.
  close    : --close-check → exit 1 if ANY item has no disposition (강제 게이트).

NO auto-resolve: this tool only SURFACES + TRACKS. 담당자 sets dispositions via
--set (author_now|defer|out_of_scope) with a reason; close-gate enforces clearance.

Usage:
  python3 deferred_manifest.py generate --config=policy_config.json [--preview=<html>] [--module=<name>]
  python3 deferred_manifest.py close    --manifest=audit/<module>_deferred_manifest.json
  python3 deferred_manifest.py set --manifest=<f> --item=DEF-A9 --disposition=defer --reason="render-only delivery; FN graph is 담당자 track"
"""
from __future__ import annotations
import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ID_RE = re.compile(r"(?:UC|PR|FN|PG|PI|POL)-[A-Z0-9]+(?:-[A-Z0-9]+)+(?:#\d+)?")

# invariant → (category, what, why, impact). Grouping = the actionable unit; every
# affected id is still listed under the item so nothing is hidden.
INV_META = {
    "A9": ("fn_graph", "PI→FN applies_to#idx references a sub_function index beyond the FN's sub_functions",
           "NC export has applies_to links but function_details.sub_functions are empty (no FN decomposition)",
           "blocks NC G2 upload (FN↔PI graph incomplete); does NOT affect html/json render consistency"),
    "B3": ("fn_graph", "FN↔PI applies_to link is not bidirectional",
           "PI.applies_to and function_details mirror are out of sync (FN decomposition incomplete)",
           "blocks NC G2 upload; does NOT affect html/json render consistency"),
    "K": ("nc_upload", "NC required field missing (decision_spec/rule_type/mockup_binding/review_status)",
          "policy_details lacks an NC-schema field needed for upload",
          "blocks NC G5 upload"),
    "L": ("nc_upload", "requirement_links integrity (dangling/uniqueness/bidirectional)",
          "requirement↔node coverage incomplete", "blocks NC G2 upload"),
}
DEFAULT_META = ("structural_other", "STRUCTURAL invariant violation",
                "internal JSON graph inconsistency", "may block NC upload; review per item")
OPTIONS = ["author_now (plugin-assisted: policy-hierarchy-decomposition + policy-detail-authoring)",
           "defer (record reason)", "out_of_scope (record reason)"]


def run_diff_json(config_dir, spec_path, html_path):
    cmd = [sys.executable, os.path.join(HERE, "diff_nc_html_json.py"),
           spec_path, "--html", html_path, "--format", "json"]
    out = subprocess.run(cmd, capture_output=True, text=True, cwd=config_dir or ".")
    txt = out.stdout.strip()
    start = txt.find("{")
    if start < 0:
        return None
    return json.loads(txt[start:])


def intake_items(diff):
    """diff_nc_html_json ③content_loss / ②phantom / ①drift → deferred items."""
    items = []
    cl = diff.get("content_loss")
    cl = cl if isinstance(cl, list) else []
    if cl:
        items.append({
            "id": "DEF-INTAKE-LOSS", "category": "intake_content_loss", "invariant": "DIFF③",
            "what": "HTML has policy-item body that the JSON lacks (NC export dropped content)",
            "why": "ncstudio JSON conversion lost content present in the source HTML",
            "impact": "incomplete JSON — needs 담당자-confirmed reconcile (HTML→JSON, html-json-check)",
            "count": len(cl), "pi_ids": sorted(e.get("id", "") for e in cl), "fn_ids": [],
            "options": OPTIONS, "disposition": None, "reason": None})
    ph = diff.get("phantom")
    ph = ph if isinstance(ph, list) else []
    if ph:
        items.append({
            "id": "DEF-INTAKE-PHANTOM", "category": "intake_phantom", "invariant": "DIFF②",
            "what": "JSON references a PI defined neither in JSON nor HTML (phantom ref)",
            "why": "conversion left a dangling reference",
            "impact": "broken reference — 담당자 resolve (remove or define)",
            "count": len(ph), "pi_ids": sorted(str(e) for e in ph)[:200], "fn_ids": [],
            "options": OPTIONS, "disposition": None, "reason": None})
    drift = (diff.get("drift") or {})
    dn = drift.get("count", 0) if isinstance(drift, dict) else 0
    if dn:
        ex = drift.get("examples", []) if isinstance(drift, dict) else []
        items.append({
            "id": "DEF-INTAKE-DRIFT", "category": "intake_drift", "invariant": "DIFF①",
            "what": "HTML div anchor id ≠ title (PI-…) — markup hygiene drift",
            "why": "NC HTML div id= attribute drifted from the title canonical id",
            "impact": "HTML hygiene; title (PI-…) is the canonical source — 담당자/기획자 fix in HTML",
            "count": dn, "pi_ids": sorted({e.get("title_canonical", "") for e in ex}), "fn_ids": [],
            "options": OPTIONS, "disposition": None, "reason": None})
    return items


def run_audit_json(config, unit):
    cmd = [sys.executable, os.path.join(HERE, "audit_id_integrity.py"), f"--config={config}", "--json"]
    if unit:
        cmd.append(f"--unit={unit}")
    out = subprocess.run(cmd, capture_output=True, text=True, cwd=os.path.dirname(config) or ".")
    txt = out.stdout.strip()
    start = txt.find("{")
    if start < 0:
        raise SystemExit(f"audit --json produced no JSON:\n{out.stdout}\n{out.stderr}")
    return json.loads(txt[start:])


def ids_in(detail):
    return sorted(set(ID_RE.findall(detail or "")))


def group_items(structural):
    by_inv = {}
    for v in structural:
        by_inv.setdefault(v["inv"], []).append(v)
    items = []
    for inv in sorted(by_inv):
        vs = by_inv[inv]
        cat, what, why, impact = INV_META.get(inv, DEFAULT_META)
        ids = sorted({i for v in vs for i in ids_in(v["detail"])})
        pi_ids = [i for i in ids if i.startswith("PI-")]
        fn_ids = [i.split("#")[0] for i in ids if i.startswith("FN-")]
        items.append({
            "id": f"DEF-{inv}", "category": cat, "invariant": inv,
            "what": what, "why": why, "impact": impact,
            "count": len(vs), "pi_ids": pi_ids, "fn_ids": sorted(set(fn_ids)),
            "options": OPTIONS, "disposition": None, "reason": None,
        })
    return items


def parity(spec_path, preview_html):
    """No-loss check: every JSON policy_details id must appear in the rendered HTML.
    Substring presence is format-agnostic (golden uses <span class=mono>(PI-…)</span>,
    other renders use id="pi-…") and directly answers 'was this PI rendered at all'."""
    spec = json.load(open(spec_path, encoding="utf-8"))
    json_ids = {p["id"] for p in spec.get("policy_details", [])}
    html = open(preview_html, encoding="utf-8").read()
    missing = sorted(pid for pid in json_ids if pid not in html)
    return json_ids, json_ids - set(missing), missing


def _bizdom(pid):
    """PI-<BIZ>-<DOM>-… / PG-<BIZ>-<DOM>-… → 'BIZ-DOM' (스킴 비교 키). 없으면 None."""
    parts = str(pid or "").split("-")
    return "-".join(parts[1:3]) if len(parts) >= 3 and parts[0] in ("PI", "PG") else None


def _derive_pg(pid):
    """PI-<BIZ>-<DOM>-<NNN>-<II> → 'PG-<BIZ>-<DOM>-<NNN>' (마지막 항목 일련번호 제거)."""
    parts = str(pid or "").split("-")
    return "PG-" + "-".join(parts[1:-1]) if len(parts) >= 4 and parts[0] == "PI" else None


def classify_parity_miss(spec_path, missing, html_path):
    """build의 정준-PG 연결 후에도 렌더에 안 나오는 PI를 ROOT CAUSE 별로 묶어 담당자 결정 항목으로 라우팅.

    자의적 ID 재작성 금지. 두 분류 모두 disposition:null (담당자가 author_now/defer/out_of_scope 결정):
      - id_scheme_mismatch : JSON policy_detail ID 스킴이 소스 HTML PI 스킴과 불일치
                             (예: 결제 JSON PI-PAY-PARTNER-* vs HTML METHOD/SCOPE; 상품상세 PDD vs PRD).
                             어느 ID가 정준인지(JSON vs HTML)는 담당자 결정 — 우리가 한쪽으로 덮어쓰지 않는다.
      - missing_policy_group: PI가 가리키는(또는 ID상 귀속되는) PG가 policy_groups에 정의돼 있지 않음.
                             스킴은 HTML과 일치 → PG 헤더 누락/dangling. PG 신설·재태깅은 담당자 결정.
    """
    spec = json.load(open(spec_path, encoding="utf-8"))
    pi_by = {p["id"]: p for p in spec.get("policy_details", [])}
    pg_ids = {g["id"] for g in spec.get("policy_groups", [])}
    pg_domains = {d for d in (_bizdom(g) for g in pg_ids) if d}
    html_domains = set()
    html_txt = ""
    if html_path and os.path.exists(html_path):
        html_txt = open(html_path, encoding="utf-8").read()
        for tok in set(re.findall(r"PI-[A-Z0-9]+-[A-Z0-9]+(?:-\d+)+", html_txt)):
            d = _bizdom(tok)
            if d:
                html_domains.add(d)

    scheme, missing_pg = [], []
    sch_refpg, mpg_refpg = set(), set()
    for pid in missing:
        pi = pi_by.get(pid, {})
        ref = pi.get("group_id") or pi.get("policy_id") or _derive_pg(pid)
        dom = _bizdom(pid)
        # 소스 HTML이 있으면 'HTML이 이 PI 도메인을 쓰는가'가 1차 판정축; 없으면 PG 스킴으로 폴백.
        if html_domains:
            same_scheme = dom in html_domains
        else:
            same_scheme = dom in pg_domains
        if same_scheme:
            missing_pg.append(pid)
            if ref and ref not in pg_ids:
                mpg_refpg.add(ref)
        else:
            scheme.append(pid)
            if ref and ref not in pg_ids:
                sch_refpg.add(ref)

    items = []
    if scheme:
        items.append({
            "id": "DEF-IDSCHEME", "category": "id_scheme_mismatch", "invariant": "RENDER",
            "what": "JSON policy_detail ID 스킴이 소스 HTML PI ID 스킴과 불일치(둘 중 무엇이 정준인지 담당자 결정 필요)",
            "why": "NC 변환본/소스 HTML과 spec JSON이 서로 다른 ID 체계를 사용 — 자동 정규화는 금지(자의적 ID 재작성)",
            "impact": "render-from-JSON parity FAIL · NC 업로드 BLOCKED — 정준 ID 스킴 확정 전까지 보류",
            "count": len(scheme), "pi_ids": sorted(scheme)[:200], "fn_ids": [],
            "evidence": {
                "json_pi_samples": sorted(scheme)[:8],
                "pg_id_samples": sorted(pg_ids)[:8],
                "html_pi_domain_samples": sorted(html_domains)[:12],
                "json_pi_domain_samples": sorted({_bizdom(p) for p in scheme if _bizdom(p)})[:12],
                "referenced_pgs_absent": sorted(sch_refpg)[:12],
            },
            "options": ["author_now (담당자 확정 스킴으로 한쪽 정렬 — 우리가 임의 결정 금지)",
                        "defer (record reason)", "out_of_scope (record reason)"],
            "disposition": None, "reason": None})
    if missing_pg:
        items.append({
            "id": "DEF-MISSINGPG", "category": "missing_policy_group", "invariant": "RENDER",
            "what": "PI가 귀속되는 policy group이 policy_groups에 정의돼 있지 않음(헤더 누락/dangling ref)",
            "why": "PI ID 스킴은 소스 HTML과 일치하나 해당 PG 정의가 spec에 없음 — PG 신설/재태깅은 담당자 판단",
            "impact": "render-from-JSON parity FAIL · NC 업로드 BLOCKED — PG 정의 보강 또는 재태깅 결정 필요",
            "count": len(missing_pg), "pi_ids": sorted(missing_pg)[:200], "fn_ids": [],
            "evidence": {
                "json_pi_samples": sorted(missing_pg)[:8],
                "referenced_pgs_absent": sorted(mpg_refpg)[:12],
                "existing_pg_samples": sorted(pg_ids)[:8],
            },
            "options": OPTIONS, "disposition": None, "reason": None})
    return items


def cmd_generate(opts):
    config = opts.get("config", "policy_config.json")
    unit = opts.get("unit")
    cfg = json.load(open(config, encoding="utf-8"))
    if unit and cfg.get("units", {}).get(unit):
        cfg = {**cfg, **cfg["units"][unit]}
    module = opts.get("module") or cfg.get("module_title") or "module"
    spec_path = os.path.join(os.path.dirname(config) or ".", cfg["spec_path"])

    audit = run_audit_json(config, unit)
    structural = audit.get("structural", [])
    items = group_items(structural)

    # intake gaps (HTML↔JSON) — same close-gate governs them
    if opts.get("html"):
        cdir = os.path.dirname(config) or "."
        html_path = os.path.join(cdir, opts["html"])
        diff = run_diff_json(cdir, cfg["spec_path"], html_path)
        if diff:
            items = intake_items(diff) + items

    # B's recovery owning-block FAILs (would-be fabrication) — governed by the same gate
    rdp = opts.get("recovery-deferred") or opts.get("recovery_deferred")
    if rdp:
        rdpath = os.path.join(os.path.dirname(config) or ".", rdp)
        if os.path.exists(rdpath):
            rd = json.load(open(rdpath, encoding="utf-8"))
            its = rd.get("items", [])
            if its:
                items.insert(0, {
                    "id": "DEF-RECOVER-FAIL", "category": "intake_content_loss_deferred", "invariant": "RECOVER",
                    "what": "content_loss PI whose HTML content FAILED owning-block faithfulness (would be fabrication)",
                    "why": "malformed nesting / no own HTML segment — cannot prove content belongs to this PI",
                    "impact": "left as content_loss — 담당자 manual reconcile or accept the gap",
                    "count": len(its), "pi_ids": sorted(e.get("pi_id", "") for e in its), "fn_ids": [],
                    "options": OPTIONS, "disposition": None, "reason": None})

    consistency = "PASS"
    if opts.get("preview"):
        preview = os.path.join(os.path.dirname(config) or ".", opts["preview"])
        json_ids, rendered, missing = parity(spec_path, preview)
        if missing:
            consistency = "FAIL"
            html_path = None
            if opts.get("html"):
                html_path = os.path.join(os.path.dirname(config) or ".", opts["html"])
            routed = classify_parity_miss(spec_path, missing, html_path)
            if routed:
                for it in reversed(routed):
                    items.insert(0, it)
            else:  # classifier가 분류하지 못한 잔여(스킴/HTML 정보 부재 등)는 generic으로 보존
                items.insert(0, {
                    "id": "DEF-RENDER", "category": "render_loss", "invariant": "RENDER",
                    "what": "JSON policy_details not present in rendered HTML",
                    "why": "render/parity gap (item dropped or id-format mismatch)",
                    "impact": "html/json consistency FAIL — must resolve before delivery",
                    "count": len(missing), "pi_ids": missing, "fn_ids": [],
                    "options": OPTIONS, "disposition": None, "reason": None,
                })

    fn_open = sum(1 for it in items if it["category"] == "fn_graph")
    intake_open = sum(it["count"] for it in items if it["category"] == "intake_content_loss")
    nc_blockers = sum(1 for it in items if it["category"] in
                      ("fn_graph", "nc_upload", "structural_other", "intake_content_loss", "intake_phantom",
                       "render_loss", "id_scheme_mismatch", "missing_policy_group", "intake_content_loss_deferred"))
    status = {
        "consistency": consistency,
        "intake": "OK" if intake_open == 0 else f"CONTENT_LOSS({intake_open})",
        "fn_graph": "OK" if fn_open == 0 else f"PENDING({fn_open})",
        "nc_upload": "READY" if nc_blockers == 0 else "BLOCKED",
        "open_items": sum(1 for it in items if it["disposition"] is None),
    }
    manifest = {
        "module": module, "spec": cfg["spec_path"],
        "summary": {"structural": len(structural), "by_invariant": audit.get("by_invariant", {})},
        "status": status, "items": items,
    }
    base = os.path.join(os.path.dirname(config) or ".", "audit", f"{module}_deferred_manifest")
    os.makedirs(os.path.dirname(base), exist_ok=True)
    json.dump(manifest, open(base + ".json", "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    write_md(manifest, base + ".md")
    print(f"[manifest] {base}.json  status={status}")
    return 0


def write_md(m, path):
    L = [f"# 이월 작업 매니페스트 — {m['module']}", "",
         f"**상태**: consistency: **{m['status']['consistency']}** / "
         f"FN-graph: **{m['status']['fn_graph']}** / NC-upload: **{m['status']['nc_upload']}** "
         f"· 미결 항목 {m['status']['open_items']}", "",
         f"STRUCTURAL {m['summary']['structural']} · by_invariant {m['summary']['by_invariant']}", "",
         "> 각 항목은 담당자가 결정해야 한다(author_now / defer / out_of_scope). "
         "disposition 미설정 항목이 있으면 close-gate가 'NC 업로드 준비'로 승격을 막는다(강제).", ""]
    for it in m["items"]:
        L += [f"## {it['id']} — {it['what']}  ({it['count']}건)",
              f"- **분류**: {it['category']} · 불변식 {it['invariant']}",
              f"- **원인**: {it['why']}",
              f"- **영향**: {it['impact']}",
              f"- **대상 PI**({len(it['pi_ids'])}): {', '.join(it['pi_ids'][:20])}{' …' if len(it['pi_ids'])>20 else ''}",
              f"- **대상 FN**({len(it['fn_ids'])}): {', '.join(it['fn_ids'][:20])}{' …' if len(it['fn_ids'])>20 else ''}"]
        if it.get("evidence"):
            ev = it["evidence"]
            L += [f"- **증거**: " + " · ".join(f"{k}={v}" for k, v in ev.items())]
        L += [f"- **선택지**: {' | '.join(it['options'])}",
              f"- **결정(disposition)**: {it['disposition'] or '⛔ 미설정'} {('— '+it['reason']) if it.get('reason') else ''}", ""]
    open(path, "w", encoding="utf-8").write("\n".join(L))


def cmd_set(opts):
    mf = opts["manifest"]
    m = json.load(open(mf, encoding="utf-8"))
    target, disp, reason = opts["item"], opts["disposition"], opts.get("reason")
    if disp not in ("author_now", "defer", "out_of_scope"):
        raise SystemExit("disposition must be author_now|defer|out_of_scope")
    if disp in ("defer", "out_of_scope") and not reason:
        raise SystemExit(f"{disp} requires --reason")
    hit = False
    for it in m["items"]:
        if it["id"] == target:
            it["disposition"] = disp
            it["reason"] = reason
            hit = True
    if not hit:
        raise SystemExit(f"item {target} not found")
    m["status"]["open_items"] = sum(1 for it in m["items"] if it["disposition"] is None)
    json.dump(m, open(mf, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    write_md(m, mf[:-5] + ".md")
    print(f"[set] {target} -> {disp}; open_items={m['status']['open_items']}")
    return 0


def cmd_close(opts):
    m = json.load(open(opts["manifest"], encoding="utf-8"))
    open_items = [it["id"] for it in m["items"] if it["disposition"] is None]
    if open_items:
        print(f"[close-gate] FAIL — {len(open_items)} 미결 항목, NC 업로드 준비 승격 차단: {open_items}")
        return 1
    if m["status"]["consistency"] != "PASS":
        print("[close-gate] FAIL — consistency != PASS")
        return 1
    print(f"[close-gate] PASS — {m['module']}: 모든 이월 항목 결정됨, consistency PASS")
    return 0


def main(argv):
    if len(argv) < 2:
        raise SystemExit(__doc__)
    cmd = argv[1]
    opts = {}
    for a in argv[2:]:
        if a.startswith("--") and "=" in a:
            k, v = a[2:].split("=", 1)
            opts[k] = v
    return {"generate": cmd_generate, "close": cmd_close, "set": cmd_set}[cmd](opts)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
