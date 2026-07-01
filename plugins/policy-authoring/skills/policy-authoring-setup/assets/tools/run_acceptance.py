#!/usr/bin/env python3
"""run_acceptance — 5원칙 통합 완료 게이트(플러그인이 스스로 검수·완료 확정하는 단일 진입점).

한 작성 단위의 (원천 HTML · spec JSON · 배포 HTML)을 받아 R1~R5를 각각 오라클로 검사하고
3-상태로 종합한다. "플러그인이 5원칙 기준으로 업무범위 산정→목표 설정→테스트 검수"의 실체.

원칙 → 오라클:
  R1 골든 스타일   compare_fidelity의 principle==R1 (STYLE_*·FN_NO_POLICY)   [§5~§6 본문]
  R2 입력 게이트   외부 validate_spec_input.py 실행 → errors==0              [spec JSON]
  R3 원천 보존     compare_fidelity의 principle==R3 (손실·헤드보존·발산)      [§0~§4 헤드+본문 매핑]
  R4 완료 정합     completion_audit (JSON↔HTML)
  R5 도메인코드    domain_code_normalize.check_r5(spec, target)

3-상태 종합:
  DONE    측정된 원칙 전부 PASS + 미해결 사람결정 0
  BLOCKED 결함(FAIL)은 없으나 측정 불가/결정 대기(미지원 포맷·게이트 부재·target 미매핑·MED 완료게이트)
  FAIL    자동으로 고칠 수 있는 원칙이 RED(손실·발산·스타일·정합·코드 위반)

미지원 포맷(원천이 ID 스킴 없는 판단축 prose 등)은 파싱 불가 → R1/R3/R4 = NA → BLOCKED(범위 밖),
FAIL로 오判하지 않는다.
"""
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import compare_fidelity as cf  # noqa: E402
import completion_audit as ca  # noqa: E402
import domain_code_normalize as dcn  # noqa: E402
import source_html_index as shi  # noqa: E402

try:
    import domain_code_map as dcm
except Exception:  # noqa: BLE001
    dcm = None


def _measurable(idx):
    """원천/배포 HTML이 ID 스킴으로 파싱되는가(미지원 포맷 판별)."""
    return bool((idx or {}).get("function_to_subfns") or (idx or {}).get("pg_to_pis"))


def _seg_of_spec(spec):
    """spec의 대표 엔티티에서 현재 도메인세그먼트 추출(R5 target 자동유도용)."""
    for k in ("functions", "processes", "policy_groups", "usecases"):
        for x in spec.get(k, []) or []:
            s = dcn.seg_of(x.get("id", ""))
            if s:
                return s
    return ""


def _resolve_target(spec, target_code):
    if target_code:
        return target_code, "explicit"
    if dcm is not None:
        cur = _seg_of_spec(spec)
        try:
            t = dcm.code_for_current(cur) if cur else None
        except Exception:  # noqa: BLE001
            t = None
        if t:
            return t, f"auto({cur}→{t})"
    return None, "unresolved"


def _run_gate(gate_path, spec_path):
    """외부 입력 게이트 실행 → (verdict, errors, detail). 게이트 없으면 NA."""
    if not gate_path or not os.path.exists(gate_path):
        return "NA", None, "게이트 파일 없음(policy_config.json spec_input_gate 또는 --gate 지정)"
    try:
        p = subprocess.run([sys.executable, gate_path, spec_path],
                           capture_output=True, text=True, timeout=120)
        out = p.stdout.strip()
        errors = None
        for line in out.splitlines():
            ls = line.strip().strip(",")
            if '"errors"' in ls:
                try:
                    errors = int(ls.split(":")[1].strip())
                except (ValueError, IndexError):
                    pass
        if errors is None:  # JSON 통째 파싱 재시도
            try:
                errors = int(json.loads(out).get("errors"))
            except Exception:  # noqa: BLE001
                return "NA", None, "게이트 출력에서 errors 파싱 실패"
        return ("PASS" if errors == 0 else "FAIL"), errors, f"errors={errors}"
    except Exception as e:  # noqa: BLE001
        return "NA", None, f"게이트 실행 오류: {e!r}"


def _load(spec):
    if isinstance(spec, str):
        with open(spec, encoding="utf-8") as f:
            return json.load(f)
    return spec


def run(source_html, spec, deliverable_html, target_code=None, gate=None, approved=None):
    spec_obj = _load(spec)
    spec_path = spec if isinstance(spec, str) else None
    principles, decisions = {}, []

    # 측정 가능성(미지원 포맷 판별)
    try:
        o_idx = shi.build_index(source_html)
    except Exception:  # noqa: BLE001
        o_idx = {}
    measurable = _measurable(o_idx)

    # R1 + R3 : compare_fidelity (principle 태그로 버킷팅)
    if measurable:
        cmp = cf.compare(source_html, deliverable_html, target_code=target_code, approved=approved)
        r1 = [f for f in cmp["findings"] if f.get("principle") == "R1"]
        r3 = [f for f in cmp["findings"] if f.get("principle") == "R3"]
        r1_high = [f for f in r1 if f["severity"] == "HIGH"]
        r1_med = [f for f in r1 if f["severity"] == "MED"]
        # R3 손실(FN_DROPPED·HEAD 등)=자동수정 대상 결함→FAIL. R3 발산(*_ADDED)=입력전용
        # 승인/제외 사람결정→decisions(BLOCKED). (fabrication 아님: 원천 부재 콘텐츠 유입)
        r3_div = [f for f in r3 if f["invariant"].endswith("_ADDED")]
        r3_loss = [f for f in r3 if not f["invariant"].endswith("_ADDED")]
        principles["R1"] = {"verdict": "FAIL" if r1_high else "PASS",
                            "findings": [_slim(f) for f in r1]}
        principles["R3"] = {"verdict": "FAIL" if any(f["severity"] == "HIGH" for f in r3_loss) else "PASS",
                            "findings": [_slim(f) for f in r3]}
        for f in r1_med:  # 완료게이트(FN_NO_POLICY 등) = 저작 필요 결정
            decisions.append({"principle": "R1", "kind": "authoring_needed", "detail": f["detail"]})
        for f in r3_div:  # 원천 부재 엔티티 유입 = 승인 또는 제외 사람결정
            decisions.append({"principle": "R3", "kind": "source_divergence",
                              "detail": f"{f['invariant']}: {f['detail']} (승인 시 approved 등재, 아니면 제외)"})
        for f in r3_loss:  # 원천 내부 불일치(FN_SOURCE_ORPHAN 등 MED) = 사람 확인
            if f["severity"] == "MED":
                decisions.append({"principle": "R3", "kind": "source_inconsistency", "detail": f["detail"]})
    else:
        principles["R1"] = {"verdict": "NA", "findings": [], "note": "미지원 포맷(파싱 불가)"}
        principles["R3"] = {"verdict": "NA", "findings": [], "note": "미지원 포맷(파싱 불가)"}
        decisions.append({"principle": "R1/R3", "kind": "unsupported_format",
                          "detail": "원천 HTML이 ID 스킴 없는 포맷 → 자동 정합 불가(수동 매핑 필요)"})

    # R2 : 외부 입력 게이트. 실패=spec 저작 미완(usecase_id 등) → 사람 authoring 결정(BLOCKED).
    # 플러그인은 spec을 날조로 채워 게이트를 통과시키지 않음(R3) → 배포물 결함(R1/R3/R4/R5)만 FAIL.
    if spec_path:
        v, errors, detail = _run_gate(gate, spec_path)
    else:
        v, errors, detail = "NA", None, "spec 경로 필요(게이트는 파일 입력)"
    principles["R2"] = {"verdict": v, "detail": detail}
    if v == "NA":
        decisions.append({"principle": "R2", "kind": "gate_unavailable", "detail": detail})
    elif v == "FAIL":
        decisions.append({"principle": "R2", "kind": "gate_authoring",
                          "detail": f"설계 게이트 미통과(spec 저작 필요): {detail}"})

    # R4 : 완료 정합(JSON↔HTML)
    if measurable:
        aud = ca.audit(spec_obj, deliverable_html, target_code=target_code)
        principles["R4"] = {"verdict": aud["verdict"],
                            "findings": [{"invariant": f["invariant"], "detail": f["detail"]}
                                         for f in aud["findings"]]}
    else:
        principles["R4"] = {"verdict": "NA", "note": "미지원 포맷(파싱 불가)"}

    # R5 : 도메인코드 현행화
    target, how = _resolve_target(spec_obj, target_code)
    if target:
        chk = dcn.check_r5(spec_obj, target)
        principles["R5"] = {"verdict": chk["verdict"], "target": target, "resolved": how,
                            "bad_ids": chk["bad_ids"][:5], "business_code_ok": chk["business_code_ok"]}
    else:
        principles["R5"] = {"verdict": "NA", "note": "target 코드 미결(domain_code_map 미매핑)"}
        decisions.append({"principle": "R5", "kind": "target_unresolved",
                          "detail": "도메인 코드 target을 확정할 수 없음 → 사람 결정(권위표 매핑)"})

    # 종합. FAIL은 배포물 원칙(R1/R3/R4/R5)만 — R2(설계 게이트)는 spec 저작 결정으로 BLOCKED.
    # 미지원 포맷은 어떤 원칙 FAIL이어도 BLOCKED(범위 밖 — 포맷 파서·수동 매핑이 선결).
    deliverable_verdicts = [principles[p]["verdict"] for p in ("R1", "R3", "R4", "R5")]
    any_na = "NA" in [p["verdict"] for p in principles.values()]
    if any(d["kind"] == "unsupported_format" for d in decisions):
        overall = "BLOCKED"
    elif "FAIL" in deliverable_verdicts:
        overall = "FAIL"
    elif any_na or decisions:
        overall = "BLOCKED"
    else:
        overall = "DONE"

    return {"verdict": overall,
            "principles": principles,
            "decisions": decisions,
            "summary": {p: principles[p]["verdict"] for p in ("R1", "R2", "R3", "R4", "R5")}}


def _slim(f):
    return {"invariant": f["invariant"], "severity": f["severity"], "key": f.get("key"),
            "detail": f["detail"]}


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", required=True)
    ap.add_argument("--spec", required=True)
    ap.add_argument("--deliverable", required=True)
    ap.add_argument("--target-code", default=None)
    ap.add_argument("--gate", default=None)
    ap.add_argument("--approved", default=None, help="승인된 발산 id JSON(list) 경로")
    ap.add_argument("--format", default="text", choices=("text", "json"))
    a = ap.parse_args()
    approved = None
    if a.approved and os.path.exists(a.approved):
        with open(a.approved, encoding="utf-8") as f:
            approved = json.load(f)
    r = run(a.source, a.spec, a.deliverable, target_code=a.target_code, gate=a.gate, approved=approved)
    if a.format == "json":
        print(json.dumps(r, ensure_ascii=False, indent=2))
    else:
        icon = {"DONE": "✅", "BLOCKED": "⛔", "FAIL": "❌"}
        print(f"{icon.get(r['verdict'], '')} 종합: {r['verdict']}")
        for p in ("R1", "R2", "R3", "R4", "R5"):
            print(f"  {p}: {r['principles'][p]['verdict']}")
        if r["decisions"]:
            print("  결정 대기:")
            for d in r["decisions"]:
                print(f"    - [{d['principle']}] {d['kind']}: {d['detail']}")
    sys.exit(0 if r["verdict"] == "DONE" else (2 if r["verdict"] == "BLOCKED" else 1))
