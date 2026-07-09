#!/usr/bin/env python3
"""domain_code_normalize — R5 도메인코드 현행화: ID 도메인세그먼트 relabel + T-R5 오라클.

한 모듈의 모든 엔티티 ID(UC/PR/FN/PG/PI/POL/ST/ACT/TM 접두)와 그 참조(applies_to·
related_*·policy_id·group_id·process_id·usecase_id·items[].id 등 spec 곳곳의 ID 문자열)의
**도메인세그먼트(2번째 토큰)를 목표 코드로 일괄 치환**한다. 관계구조(그래프)는 그대로,
라벨만 바뀐다(relationship-preserving relabel). meta.business_code도 목표 코드로 설정.

목표 코드는 `domain_code_map`이 권위표(xlsx)에서 산출('/' 제거형). 모호 모듈은 사람 결정.

T-R5 오라클: check_r5(spec, target) → 세그먼트 != target 인 ID 목록(위반). 빈 목록 = GREEN.
"""
import copy
import re

# 치환 대상 ID 접두(엔티티만 — 본문/설명의 임의 대문자열 오염 방지). ACT를 AC 앞에(명시 순서).
# FC=final_check(검수 ID) 추가. SEG는 알파(도메인코드)만 → 숫자세그(ACT-001·PM-20 모듈-로컬)
# 는 자동 제외. rest는 선택(POL-MYI 같은 2토막 문서ID도 매치). '#3' 등 접미는 group3에 보존.
_PREFIX = r"(?:UC|US|PR|FN|PG|PI|POL|ST|ACT|AC|TM|FC)"
_ID_SEG = re.compile(r"\b(" + _PREFIX + r"-)([A-Z]+)((?:-[A-Z0-9\-]+)?)")


def seg_of(id_str):
    """ID의 도메인세그먼트(2번째 토큰). 형식 불명이면 ''."""
    parts = (id_str or "").split("-")
    return parts[1] if len(parts) >= 2 else ""


def relabel_to(s, target):
    """문자열 내 모든 엔티티 ID의 도메인세그먼트를 target으로 치환."""
    return _ID_SEG.sub(lambda m: m.group(1) + target + m.group(3), s or "")


def _walk(obj, target):
    if isinstance(obj, str):
        return relabel_to(obj, target)
    if isinstance(obj, list):
        return [_walk(x, target) for x in obj]
    if isinstance(obj, dict):
        # 키도 relabel — trace_matrix 등 ID-keyed 매핑의 키↔값 정합(F4)
        return {(relabel_to(k, target) if isinstance(k, str) else k): _walk(v, target)
                for k, v in obj.items()}
    return obj


def normalize_spec_to(spec, target):
    """spec의 전 ID·참조 도메인세그먼트를 target으로 relabel하고 business_code 설정.
    원본은 변형하지 않음(deepcopy)."""
    out = _walk(copy.deepcopy(spec), target)
    out.setdefault("meta", {})
    out["meta"]["business_code"] = target
    return out


def _has_domain_seg(i):
    """도메인세그먼트를 가진 ID인가(PREFIX-SEG-rest, SEG=알파). ACT-001 같은 모듈-로컬
    번호 스킴은 도메인코드 대상이 아니므로 R5 검사에서 제외(relabel_to도 이를 건드리지 않음)."""
    parts = (i or "").split("-")
    return len(parts) >= 3 and parts[1].isalpha()


def scan_residual_segs(obj, target):
    """obj(스펙 dict/list/str) 또는 HTML 문자열 전체를 재귀 순회하며, _ID_SEG 매치 중
    도메인세그가 target과 다른 엔티티 ID를 수집한다. 숫자세그(ACT-001·PM-20 등 모듈-로컬)는
    _ID_SEG가 애초에 매치하지 않으므로 자동 제외. dict 키도 검사한다.
    반환: [{"id": "<PREFIX-SEG(-rest)>", "seg": "<SEG>"}] (id 기준 중복제거·정렬)."""
    found = {}

    def _scan_text(s):
        for m in _ID_SEG.finditer(s or ""):
            if m.group(2) != target:
                found[m.group(1) + m.group(2) + m.group(3)] = m.group(2)

    def _walk_scan(o):
        if isinstance(o, str):
            _scan_text(o)
        elif isinstance(o, list):
            for x in o:
                _walk_scan(x)
        elif isinstance(o, dict):
            for k, v in o.items():
                if isinstance(k, str):
                    _scan_text(k)
                _walk_scan(v)

    _walk_scan(obj)
    return [{"id": i, "seg": s} for i, s in sorted(found.items())]


def check_r5(spec, target):
    """T-R5 오라클: 스펙 전체(전 필드·dict키)에서 도메인세그 != target 인 엔티티 ID 목록 +
    business_code 일치. 숫자세그 모듈-로컬 ID(ACT-001 등)는 _ID_SEG 미매치로 자동 제외."""
    bad = [d["id"] for d in scan_residual_segs(spec, target)]
    bc_ok = (spec.get("meta") or {}).get("business_code") == target
    return {"bad_ids": bad, "business_code_ok": bc_ok,
            "verdict": "PASS" if not bad and bc_ok else "FAIL"}


if __name__ == "__main__":
    import json
    import sys
    ap = sys.argv[1:]
    if len(ap) >= 2:
        spec = json.load(open(ap[0], encoding="utf-8"))
        target = ap[1]
        v = check_r5(spec, target)
        print(json.dumps({"target": target, "verdict": v["verdict"],
                          "bad_count": len(v["bad_ids"]), "business_code_ok": v["business_code_ok"],
                          "sample_bad": v["bad_ids"][:5]}, ensure_ascii=False, indent=2))
