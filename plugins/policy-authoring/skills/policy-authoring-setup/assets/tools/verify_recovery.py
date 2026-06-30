#!/usr/bin/env python3
"""복원 검증 — _fixed.json에 HTML로부터 복원된 policy_details(content)가 정말 자기
소유 HTML 구획에서 나왔는지 *독립적으로* 재검사한다(제로-날조 게이트).

fix_nc_input.recover_content_loss는 복원한 entry에 source_note="recovered_from_html:
owning_block_pass"를 남긴다. 이 스크립트는 그 마커가 붙은 entry만 골라, HTML을
nc_owning_block으로 다시 슬라이스해 각 entry.content가 자기 PI 구획 평문의
부분문자열인지 재확인한다(파서의 귀속을 신뢰하지 않는 독립 검사).

PASS-rate를 출력한다. fix가 PASS만 기록하므로 정상 산출물은 100%여야 하며,
하나라도 FAIL이면 복원 로직 회귀 신호다.

사용:
  python3 tools/verify_recovery.py FIXED.json --html HTML [--format md|json]
"""
from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import nc_owning_block  # noqa: E402

RECOVER_NOTE = "recovered_from_html:owning_block_pass"


def verify(fixed_path, html_path):
    spec = json.load(open(fixed_path, encoding="utf-8"))
    html = open(html_path, encoding="utf-8").read()
    segs = nc_owning_block.owning_segments(html)

    recovered = [d for d in (spec.get("policy_details") or [])
                 if (d.get("source_note") or "") == RECOVER_NOTE]
    passed, failed = [], []
    for d in recovered:
        pid = d.get("id")
        seg = segs.get(pid)
        if nc_owning_block.is_faithful(d.get("content") or "", seg):
            passed.append(pid)
        else:
            failed.append({"pi_id": pid,
                           "reason": "no_owning_segment" if seg is None else "owning_block_fail"})
    n = len(recovered)
    return {
        "fixed": os.path.basename(fixed_path),
        "html": os.path.basename(html_path),
        "recovered_total": n,
        "owning_block_pass": len(passed),
        "owning_block_fail": len(failed),
        "pass_rate": (len(passed) / n) if n else 1.0,
        "failures": failed,
    }


def render_md(r):
    pct = f"{r['pass_rate'] * 100:.1f}%"
    L = [f"# 복원 검증 — {r['fixed']}",
         "",
         f"- HTML: `{r['html']}`",
         f"- 복원 entry(source_note 마커): **{r['recovered_total']}**",
         f"- owning-block PASS: **{r['owning_block_pass']}** / FAIL: **{r['owning_block_fail']}**",
         f"- PASS-rate: **{pct}**"]
    if r["failures"]:
        L.append("")
        L.append("## FAIL (회귀 신호 — fix는 PASS만 기록해야 함)")
        for f in r["failures"][:50]:
            L.append(f"- `{f['pi_id']}` ({f['reason']})")
    return "\n".join(L)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("fixed")
    ap.add_argument("--html", required=True)
    ap.add_argument("--format", choices=["md", "json"], default="md")
    args = ap.parse_args()
    r = verify(args.fixed, args.html)
    if args.format == "json":
        print(json.dumps(r, ensure_ascii=False, indent=2))
    else:
        print(render_md(r))
    # 비정상(FAIL 존재) → exit 1
    sys.exit(0 if r["owning_block_fail"] == 0 else 1)


if __name__ == "__main__":
    main()
