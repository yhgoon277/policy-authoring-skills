#!/usr/bin/env python3
"""build_deliverable — 원천 HTML 기반 배포물 생성 + 5원칙 완료 게이트의 단일 진입점.

기본(골든 모드): §0~§4 원천 보존 + §5~§6 골든 렌더 splice(R1 측정).
  R1(골든 스타일)은 적극 검증 후 배포 완료 게이트의 일부로 포함된다.
--preserve(옵트인): 배포물 = 원천 HTML 완전보존 + R5 도메인코드 현행화(relabel)만.
  담당자가 원본 그대로의 §0~§6(다이어그램·케이스표·정책 상세 표 포함)을 원할 때의 특수 경로.
  R1(골든 스타일)은 WAIVED로 명시 기록되고 R2~R5는 동일하게 측정된다.

파이프라인:
  1) rebuild_policy_from_source  : 정책층·유즈케이스층·PG 설명을 원천 HTML 정본으로 재구성
  2) fn_pi_derive                : 빈 기능→정책상세를 PG경유 근사 파생(+검토 마커)
  3) normalize_spec_to (target)  : 전 계층 도메인세그먼트를 목표코드로 relabel(R5)
  4) render_preview 6섹션         : §0~§6 self-contained preview 생성(보존 모드에선 참고물)
  5) 배포물 조립                  : 골든=splice[5,6] / --preserve=relabel(원천) 그대로
  6) run_acceptance              : R1~R5 통합 게이트 → DONE / BLOCKED / FAIL (골든=R1 측정, 보존=R1 WAIVED)

target 코드는 --target-code, 없으면 domain_code_map 자동 유도(미매핑이면 R5 BLOCKED).
"""
import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rebuild_policy_from_source as rb  # noqa: E402
import fn_pi_derive as fpd  # noqa: E402
import render_preview as rp  # noqa: E402
import splice_nc_html as S  # noqa: E402
import domain_code_normalize as dcn  # noqa: E402
import run_acceptance as ra  # noqa: E402

try:
    import domain_code_map as dcm
except Exception:  # noqa: BLE001
    dcm = None


def _render_preview(spec, out_path):
    """render_preview 6섹션을 config 없이 조립(도너 preview)."""
    body = "".join([
        rp.render_header(spec), rp.render_history(spec), rp.render_overview(spec), rp.render_terms(spec),
        rp.render_usecases_section(spec), rp.render_processes(spec), rp.render_functions(spec),
        rp.render_policy_list(spec), rp.render_policy_details(spec), rp.render_final_check(spec)])
    m = spec.get("meta") or {}
    title = " ".join(x for x in [rp._doc_title(m), m.get("version", "")] if x).strip()
    html = (f'<!DOCTYPE html>\n<html lang="ko">\n<head>\n<meta charset="utf-8"/>\n'
            f'<meta content="width=device-width, initial-scale=1" name="viewport"/>\n'
            f"<title>{rp._e(title)}</title>\n{rp.load_css()}\n</head>\n<body>\n"
            f'<div class="page">\n{body}\n</div>\n{rp._mermaid_assets()}</body>\n</html>\n')
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)


def _resolve_target(spec, target_code):
    if target_code:
        return target_code
    if dcm is not None:
        for k in ("functions", "processes", "policy_groups", "usecases"):
            for x in spec.get(k, []) or []:
                seg = dcn.seg_of(x.get("id", ""))
                if seg:
                    try:
                        t = dcm.resolve_target(seg)
                    except Exception:  # noqa: BLE001
                        t = None
                    if t:
                        return t
                    break
    return None


def build(input_spec, source_html, out_dir, target_code=None, gate=None, approved=None, preserve=False):
    os.makedirs(out_dir, exist_ok=True)
    if isinstance(input_spec, str):
        with open(input_spec, encoding="utf-8") as _f:
            spec_in = json.load(_f)
    else:
        spec_in = input_spec
    stem = os.path.splitext(os.path.basename(source_html))[0]
    target = _resolve_target(spec_in, target_code)

    # 1~3) 원천 정본 재구성 → FN→PI 파생 → R5 전체 relabel
    spec = rb.rebuild(spec_in, source_html, target_code=target)
    spec, _ = fpd.derive_fn_pi(spec)
    if target:
        spec = dcn.normalize_spec_to(spec, target)
    spec_path = os.path.join(out_dir, stem + "_spec.json")
    with open(spec_path, "w", encoding="utf-8") as _f:
        json.dump(spec, _f, ensure_ascii=False, indent=2)

    # 4) preview(도너 — 보존 모드에선 참고 산출물) → 5) 배포물 조립
    prev_path = os.path.join(out_dir, stem + "_preview.html")
    _render_preview(spec, prev_path)
    # 보존 모드는 원천의 줄끝(CRLF 등)까지 보존 — 무번역(newline="") 입출력. 골든은 기존 그대로.
    nl = "" if preserve else None
    with open(source_html, encoding="utf-8", newline=nl) as _f:
        base = _f.read()
    if target:
        base = dcn.relabel_to(base, target)
    if preserve:
        # 보존 모드(--preserve 옵트인): 배포물 = relabel(원천) 그대로 — §0~§6 전체 원천 완전보존
        deliv = base
    else:
        # 골든 경로(기본): 헤드 §0~§4 보존 + §5~§6 골든 이식 (R1 측정)
        with open(prev_path, encoding="utf-8") as _f:
            prev_txt = _f.read()
        base2, _ = S.inject_css(base, S.extract_rich_css(prev_txt))
        with open(prev_path, encoding="utf-8") as _f:
            prev_txt2 = _f.read()
        deliv = S.splice_sections(base2, prev_txt2, [5, 6])
    deliv_path = os.path.join(out_dir, stem + "_deliverable.html")
    with open(deliv_path, "w", encoding="utf-8", newline=nl) as f:
        f.write(deliv)

    # 6) 5원칙 완료 게이트
    verdict = ra.run(source_html, spec_path, deliv_path, target_code=target, gate=gate,
                     approved=approved, mode=("preserve" if preserve else "golden"))
    return {"spec": spec_path, "deliverable": deliv_path, "preview": prev_path,
            "target": target, "acceptance": verdict}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--spec", required=True, help="입력 spec JSON(디자인/기존)")
    ap.add_argument("--source", required=True, help="원천(진실원천) HTML")
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--target-code", default=None, help="R5 목표 도메인코드(미지정 시 자동 유도)")
    ap.add_argument("--gate", default=None, help="R2 게이트 경로(미지정 시 번들 validate_nc_input.py 자동 사용)")
    ap.add_argument("--approved", default=None, help="승인된 발산 id JSON(list) 경로")
    ap.add_argument("--preserve", action="store_true",
                    help="원본 보존 배포물(배포물=relabel(원천), R1 WAIVED) — 특수 요구용. 기본은 §5~§6 골든 렌더(R1 측정)")
    ap.add_argument("--format", default="text", choices=("text", "json"))
    a = ap.parse_args()
    approved = None
    if a.approved and os.path.exists(a.approved):
        with open(a.approved, encoding="utf-8") as _f:
            approved = json.load(_f)
    r = build(a.spec, a.source, a.out_dir, target_code=a.target_code, gate=a.gate,
              approved=approved, preserve=a.preserve)
    acc = r["acceptance"]
    if a.format == "json":
        print(json.dumps(r, ensure_ascii=False, indent=2))
    else:
        icon = {"DONE": "✅", "BLOCKED": "⛔", "FAIL": "❌"}
        print(f"  [build] target={r['target']} → {r['deliverable']}")
        print(f"  {icon.get(acc['verdict'], '')} 완료판정: {acc['verdict']}  "
              + " ".join(f"{p}={acc['summary'][p]}" for p in ('R1', 'R2', 'R3', 'R4', 'R5')))
        for d in acc["decisions"]:
            print(f"     - [{d['principle']}] {d['kind']}: {d['detail'][:80]}")
    sys.exit(0 if acc["verdict"] == "DONE" else (2 if acc["verdict"] == "BLOCKED" else 1))
