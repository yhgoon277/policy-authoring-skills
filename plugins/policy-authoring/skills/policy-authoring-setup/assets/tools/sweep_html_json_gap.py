#!/usr/bin/env python3
"""디렉토리 내 모듈별 HTML↔JSON 정책항목 수 점검 — NC 부분변환 결함 탐지.

각 모듈의 짝 HTML에서 정책항목(PI) 정의 수를 `nc_html_link`(변형 1~6)로 추출하고
JSON `policy_details` 수와 비교한다. 큰 갭(HTML >> JSON)은 ncstudio가 HTML→JSON 변환에서
정책 내용을 떨어뜨린 부분실패 신호다(주문계약 v0.51 = 284 vs 156이 그 사례).

게이트는 연결(items/policy_id)만 보고 내용 완전성은 안 보므로, 게이트 PASS여도
이 갭이 클 수 있다. 읽기 전용 — 아무것도 수정하지 않는다.

사용:
  python3 sweep_html_json_gap.py DIR [--format md|json]
  DIR: HTML과 _spec.json 짝 파일이 같이 있는 디렉토리(필수)
"""
import argparse
import json
import os
import re
import sys
import unicodedata

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import nc_html_link  # noqa: E402

# 변형 무관 PI id 추출(정의·교차참조 무관, HTML 어디든) — 파서 미지원 변형도 잡는다.
PI_ID = re.compile(r'(PI-[A-Z0-9]+(?:-[A-Z0-9]+)+)')


def _html_for(spec_path):
    cand = spec_path.replace("_spec.json", ".html")
    return cand if os.path.exists(cand) else None


def sweep(directory):
    rows = []
    for fn in sorted(os.listdir(directory)):
        if not fn.endswith("_spec.json") or "_fixed" in fn:
            continue
        spec_path = os.path.join(directory, fn)
        d = json.load(open(spec_path, encoding="utf-8"))
        json_pi = {x["id"] for x in (d.get("policy_details") or [])}
        html_path = _html_for(spec_path)
        html_text = open(html_path, encoding="utf-8").read() if html_path else ""
        # 변형 무관 고유 PI id(권위 측정) — 파서가 변형 미지원이어도 누락 안 됨.
        html_pi = set(PI_ID.findall(html_text))
        # 파서가 이름·본문까지 복원 가능한 수(변형 1~6 인식 지표).
        parsed = 0
        if html_path:
            m = nc_html_link.parse_file(html_path)
            parsed = len({x["id"] for v in m.values() for x in v})
        shared = html_pi & json_pi
        html_only = html_pi - json_pi
        json_only = json_pi - html_pi
        gap_pct = round(100 * len(html_only) / len(html_pi)) if html_pi else None
        rows.append({
            # macOS 파일명은 NFD 한글 → NFC 정규화(소비측 키 매칭 안정).
            "module": unicodedata.normalize("NFC", fn.split("_")[1]),
            "html_pi": len(html_pi),
            "parsed": parsed,
            "json_pi": len(json_pi),
            "shared": len(shared),
            "html_only": len(html_only),
            "json_only": len(json_only),
            "gap_pct": gap_pct,
            "has_html": bool(html_path),
        })
    return rows


def render_md(rows):
    L = ["# 모듈별 HTML↔JSON 정책항목 수 점검 — NC 부분변환 결함 스윕",
         "",
         "**HTML고유PI** = HTML 어디서든 등장하는 고유 PI id(변형 무관 regex — 파서 미지원 변형도 포착). "
         "**파서** = 이름·본문까지 복원 가능한 수(변형 1~6 인식). **HTML전용(갭)**이 크면 ncstudio가 "
         "HTML 정책항목을 JSON으로 못 옮긴 부분변환 결함. 게이트는 내용 완전성을 안 보므로 PASS여도 "
         "갭이 클 수 있음. HTML고유PI=0 → 진짜 prose(구조적 PI 없음).",
         "",
         "| 모듈 | HTML고유PI | 파서 | JSON | 공유 | HTML전용(누락) | JSON전용 | 갭% | 판정 |",
         "|---|---:|---:|---:|---:|---:|---:|---:|---|"]
    for r in rows:
        if not r["html_pi"]:
            verdict = "prose(구조PI 없음)"
        elif r["gap_pct"] is not None and r["gap_pct"] >= 40:
            verdict = "⚠️ 부분변환 의심"
        elif r["gap_pct"] is not None and r["gap_pct"] >= 15:
            verdict = "주의"
        else:
            verdict = "양호(JSON⊆HTML)"
        gp = "—" if r["gap_pct"] is None else f"{r['gap_pct']}%"
        L.append(f"| {r['module']} | {r['html_pi']} | {r['parsed']} | {r['json_pi']} | {r['shared']} | "
                 f"{r['html_only']} | {r['json_only']} | {gp} | {verdict} |")
    L.append("")
    flagged = [r["module"] for r in rows if r["html_pi"] and r["gap_pct"] is not None and r["gap_pct"] >= 40]
    L.append(f"**부분변환 의심(갭≥40%): {len(flagged)}개** — {', '.join(flagged) if flagged else '없음'}")
    L.append("")
    L.append("> 주: `파서`가 `HTML고유PI`보다 현저히 작으면 본문 복원이 안 되는 미지원 마크업 변형이다"
             "(카운트 정합은 HTML고유PI로 판정하므로 갭% 신뢰 가능). 결제·상품상세는 JSON이 HTML과 "
             "다른 PI id 체계라 공유 0(트랙 A 재구성 대상). 동일 모듈 2행은 폴더에 버전이 2개.")
    return "\n".join(L)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("directory", help="HTML과 _spec.json 짝 파일이 같이 있는 디렉토리")
    ap.add_argument("--format", choices=["md", "json"], default="md")
    args = ap.parse_args()
    rows = sweep(args.directory)
    if args.format == "json":
        print(json.dumps(rows, ensure_ascii=False, indent=2))
    else:
        print(render_md(rows))


if __name__ == "__main__":
    main()
