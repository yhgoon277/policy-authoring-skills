#!/usr/bin/env python3
"""decision_guide.py — HTML↔JSON reconcile 후 *사람이 결정·수정해야 할 부분*을
케이스별로 명확히 안내하는 결정 가이드 생성기 (결정론적·stdlib).

reconcile 신호(diff_nc_html_json 진단 + fix_nc_input 산출물: _crosswalk.json·
_recovery_deferred.json)를 케이스로 분류해 각 케이스의
  '무슨 상태 / 해당 항목 / 무엇을 결정 / 어떻게 수정(이 세션에서)'
를 markdown(+json)으로 낸다. ⚠️ 에이전트는 reconcile 후 *반드시* 이 가이드를
생성해 사용자에게 제시한다 — '조용히 통과' 금지. 자동으로 끝나지 않는 케이스
(미지원 포맷·스킴상이·충실성미달·JSON전용)를 사용자가 명확히 인지하게 한다.

사용:
  python3 decision_guide.py <spec.json> --html <HTML> [--fixed <auto_spec.json>]
                            [--out <guide.md>] [--format md|json]
  (--fixed 를 주면 그 옆의 <stem>_crosswalk.json·<stem>_recovery_deferred.json도 읽는다)
"""
import json
import os
import sys


def _load(p):
    try:
        return json.load(open(p, encoding="utf-8"))
    except Exception:
        return None


def _n(x):
    if x is None:
        return 0
    if isinstance(x, dict):
        return x.get("count", len(x))
    return len(x)


def build_guide(spec_path, html_path, fixed_path=None):
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import diff_nc_html_json
    diag = json.loads(diff_nc_html_json.diagnose(spec_path, html_path, fmt="json"))
    c = diag.get("counts", {})
    cl, jo = _n(diag.get("content_loss")), _n(diag.get("json_only"))
    ph, dr = _n(diag.get("phantom")), _n(diag.get("drift"))
    emptyrow = c.get("content_loss_emptyrow", 0)
    unmeasurable = bool(diag.get("unmeasurable"))

    base = fixed_path[:-5] if (fixed_path and fixed_path.endswith(".json")) else None
    crosswalk = _load(base + "_crosswalk.json") if base else None
    deferred = _load(base + "_recovery_deferred.json") if base else None
    cw_n = (crosswalk or {}).get("count", 0)
    df_n = (deferred or {}).get("count", 0)
    cw_file = os.path.basename(base + "_crosswalk.json") if base else "<auto_spec>_crosswalk.json"
    df_file = os.path.basename(base + "_recovery_deferred.json") if base else "<auto_spec>_recovery_deferred.json"

    cases = []
    if unmeasurable:
        cases.append({"id": "UNMEASURABLE", "sev": "⛔ 차단",
            "state": "미지원 HTML 포맷 — 자동 진단 불가",
            "detail": f"파서가 HTML 정책 항목을 0개 인식(JSON엔 {c.get('json_policy_details')}건). "
                      "content_loss=0은 '무손실'이 아니라 *측정 불가*다(HTML에 정책 본문이 있어도 못 읽음).",
            "decide": "이 포맷을 다룰지, 어떻게 매핑할지.",
            "how": ["(a) 파서 확장: nc_html_link/dev_format_vendor에 이 HTML 포맷의 PI/PG 앵커 규칙을 추가(개발 작업).",
                    "(b) 수동 매핑: HTML 정책 상세를 직접 읽어 JSON policy_details에 항목별로 입력(이 세션에서).",
                    "⚠️ 현재 상태로는 reconcile 신뢰 불가 — 사람 개입 필수."]})
    if cw_n:
        cases.append({"id": "CROSSWALK", "sev": "⚠️ 검토",
            "state": f"스킴 상이 자동 병합 {cw_n}건",
            "detail": "HTML과 JSON의 PI id 스킴이 달라(예 APPROVAL↔APR) *같은 이름*의 정책을 자동 매칭해 "
                      "중복 추가를 막았다.",
            "decide": "오매칭(실은 다른 정책인데 이름만 같음)이 없는지.",
            "how": [f"`{cw_file}`의 pairs(html_id ↔ json_id · name)를 확인.",
                    "잘못 병합된 쌍이 있으면 그 HTML 항목을 별도 PI로 분리(수동)."]})
    if df_n:
        cases.append({"id": "DEFERRED", "sev": "🟡 수동작성",
            "state": f"충실성 미달 복원 보류 {df_n}건",
            "detail": "HTML 본문이 owning-block 충실성(원문 substring) 미달 → 자동복원하면 날조 위험이라 보류했다.",
            "decide": "수동 저작할지 / 범위밖으로 둘지.",
            "how": [f"`{df_file}` 항목별로 HTML 원문을 확인한 뒤 직접 작성(자동복원 금지 — 날조 방지)."]})
    if emptyrow:
        cases.append({"id": "EMPTYROW", "sev": "🟢 검증",
            "state": f"빈 본문 충전 {emptyrow}건",
            "detail": "JSON에 PI는 있으나 content가 공란이던 것을 HTML 본문으로 충전(owning-block 검증 통과).",
            "decide": "충전 내용이 적절한지(가벼운 확인).",
            "how": ["충전된 항목 표본을 렌더(auto.html)에서 확인."]})
    if jo:
        cases.append({"id": "JSON_ONLY", "sev": "🔵 검토",
            "state": f"JSON 전용 {jo}건",
            "detail": "JSON엔 있고 HTML엔 없는 PI. 의도된 NC 정제분일 수도, 누락일 수도 있다.",
            "decide": "유지 vs 제거.",
            "how": ["diff의 json_only 항목명을 검토 — HTML에서 의도적으로 뺀 것인지 확인."]})
    if ph or dr:
        cases.append({"id": "MECHANICAL", "sev": "🔧 기계적",
            "state": f"phantom {ph} · drift {dr}",
            "detail": "dangling 참조 / div앵커-제목 ID 드리프트 — 기계적 정정 대상(대개 fix가 자동 처리).",
            "decide": "-",
            "how": ["fix의 phantom/ref_format 패스로 자동 처리. 잔여만 확인."]})

    summary = {"module": diag.get("module"),
               "html_pi": c.get("html_canonical_pi"), "json_pi": c.get("json_policy_details"),
               "needs_human": bool(unmeasurable or cw_n or df_n or jo),
               "blocking": bool(unmeasurable),
               "case_count": len(cases)}
    return {"summary": summary, "cases": cases}


def to_md(g):
    s = g["summary"]
    L = [f"# 결정 가이드 — {s['module']}", "",
         f"HTML PI {s['html_pi']} ↔ JSON PI {s['json_pi']} · "
         f"사람 결정 필요: **{'예' if s['needs_human'] else '아니오'}**"
         + ("(⛔ 차단 케이스 포함)" if s["blocking"] else "") + f" · 케이스 {s['case_count']}", ""]
    if not g["cases"]:
        L.append("✅ 사람이 결정할 항목 없음 — HTML/JSON 정합. 자동 reconcile로 충분.")
        return "\n".join(L)
    L.append("> 아래 각 케이스를 사용자에게 그대로 제시하고, '어떻게 수정'을 함께 진행한다.")
    L.append("")
    for ca in g["cases"]:
        L += [f"## {ca['sev']} — {ca['state']}  `[{ca['id']}]`",
              f"- **무슨 상태**: {ca['detail']}",
              f"- **무엇을 결정**: {ca['decide']}",
              "- **어떻게 수정(이 세션에서)**:"]
        L += [f"    - {h}" for h in ca["how"]]
        L.append("")
    return "\n".join(L)


def main(argv):
    spec = None
    opts = {}
    i = 1
    while i < len(argv):
        a = argv[i]
        if a.startswith("--"):
            if "=" in a:
                k, v = a.split("=", 1)
                opts[k] = v
            elif i + 1 < len(argv) and not argv[i + 1].startswith("--"):
                opts[a] = argv[i + 1]
                i += 1
            else:
                opts[a] = True
        elif spec is None:
            spec = a
        i += 1
    if not spec or not opts.get("--html"):
        print("사용: decision_guide.py <spec.json> --html <HTML> [--fixed <auto_spec.json>] "
              "[--out <guide.md>] [--format md|json]", file=sys.stderr)
        return 2
    g = build_guide(spec, opts["--html"], opts.get("--fixed"))
    out = json.dumps(g, ensure_ascii=False, indent=2) if opts.get("--format") == "json" else to_md(g)
    if opts.get("--out"):
        open(opts["--out"], "w", encoding="utf-8").write(out)
        print(f"[decision_guide] {opts['--out']} · 케이스 {g['summary']['case_count']} · "
              f"사람결정 {'필요' if g['summary']['needs_human'] else '불필요'}")
    else:
        print(out)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
