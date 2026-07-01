#!/usr/bin/env python3
"""completion_audit (T-R4) — 최종 산출물의 JSON↔HTML 상호 정합 검수.

배포쌍(<m>_auto_spec.json + <m>_auto.html)은 같은 deliverable의 두 표현이므로 서로
합치해야 한다. JSON이 선언한 엔티티가 HTML에 빠짐없이 렌더됐는지 확인한다(렌더/splice
누락 탐지). HTML 파싱은 `source_html_index` 재사용.

검사(JSON=기준, 누락=JSON−HTML):
  C_FN_COUNT     JSON 기능이 HTML §5 기능 정의에 미렌더(예: N:M→1:1 붕괴로 누락)   HIGH
  C_PG_COVERAGE  JSON 정책그룹이 HTML에 미표시                                      HIGH
  C_PI_COVERAGE  JSON 정책항목(PI)이 HTML에 미표시                                  HIGH

verdict: HIGH 1개라도 있으면 FAIL.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import source_html_index as shi  # noqa: E402


def _load(spec):
    if isinstance(spec, str):
        with open(spec, encoding="utf-8") as f:
            return json.load(f)
    return spec


def audit(spec, html_path, target_code=None):
    d = _load(spec)
    idx = shi.build_index(html_path)
    html_fns = set(idx["function_to_subfns"])
    html_pgs = set(idx["pg_to_pis"])
    html_pis = {pi for pis in idx["pg_to_pis"].values() for pi in pis}

    json_fns = {f["id"] for f in d.get("functions", []) or [] if f.get("id")}
    json_pgs = {g["id"] for g in d.get("policy_groups", []) or [] if g.get("id")}
    json_pis = {p["id"] for p in d.get("policy_details", []) or [] if p.get("id")}

    findings = []

    def add(inv, sev, detail, sample=None):
        findings.append({"invariant": inv, "severity": sev, "detail": detail, "sample": sample or []})

    miss_fn = sorted(json_fns - html_fns)
    if miss_fn:
        add("C_FN_COUNT", "HIGH",
            f"JSON 기능 {len(miss_fn)}개 HTML §5 미렌더 (JSON {len(json_fns)} vs HTML §5 {len(html_fns)})",
            miss_fn[:5])
    miss_pg = sorted(json_pgs - html_pgs)
    if miss_pg:
        add("C_PG_COVERAGE", "HIGH", f"JSON 정책그룹 {len(miss_pg)}개 HTML 미표시", miss_pg[:5])
    miss_pi = sorted(json_pis - html_pis)
    if miss_pi:
        add("C_PI_COVERAGE", "HIGH", f"JSON 정책항목 {len(miss_pi)}개 HTML 미표시", miss_pi[:5])

    highs = sum(1 for f in findings if f["severity"] == "HIGH")
    return {
        "findings": findings,
        "summary": {"high": highs,
                    "json_functions": len(json_fns), "html_functions": len(html_fns),
                    "json_pgs": len(json_pgs), "html_pgs": len(html_pgs),
                    "json_pis": len(json_pis), "html_pis": len(html_pis)},
        "verdict": "FAIL" if highs else "PASS",
    }


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("spec_json")
    ap.add_argument("html")
    a = ap.parse_args()
    r = audit(a.spec_json, a.html)
    print(json.dumps({"verdict": r["verdict"], "summary": r["summary"],
                      "findings": [{k: f[k] for k in ("invariant", "severity", "detail")} for f in r["findings"]]},
                     ensure_ascii=False, indent=2))
