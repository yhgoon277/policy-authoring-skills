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

# 치환 대상 ID 접두(엔티티만 — 본문/설명의 임의 대문자열 오염 방지)
_PREFIX = r"(?:UC|US|PR|FN|PG|PI|POL|ST|ACT|TM)"
# PREFIX-SEG-rest 형태에서 SEG만 캡처(뒤에 -... 가 반드시 옴; applies_to '...#3' 접미는 보존)
_ID_SEG = re.compile(r"\b(" + _PREFIX + r"-)([A-Z0-9]+)(-[A-Z0-9\-]+)")


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
        return {k: _walk(v, target) for k, v in obj.items()}
    return obj


def normalize_spec_to(spec, target):
    """spec의 전 ID·참조 도메인세그먼트를 target으로 relabel하고 business_code 설정.
    원본은 변형하지 않음(deepcopy)."""
    out = _walk(copy.deepcopy(spec), target)
    out.setdefault("meta", {})
    out["meta"]["business_code"] = target
    return out


_ID_KEYS = ("usecases", "processes", "functions", "policy_groups", "policy_details",
            "states", "actors", "terms")


def _has_domain_seg(i):
    """도메인세그먼트를 가진 ID인가(PREFIX-SEG-rest, SEG=알파). ACT-001 같은 모듈-로컬
    번호 스킴은 도메인코드 대상이 아니므로 R5 검사에서 제외(relabel_to도 이를 건드리지 않음)."""
    parts = (i or "").split("-")
    return len(parts) >= 3 and parts[1].isalpha()


def check_r5(spec, target):
    """T-R5 오라클: 세그먼트 != target 인 정의 ID 목록 + business_code 일치 여부.
    도메인세그 없는 모듈-로컬 ID(ACT-001 등)는 대상 밖(제외)."""
    bad = []
    for k in _ID_KEYS:
        for x in spec.get(k, []) or []:
            i = x.get("id")
            if i and _has_domain_seg(i) and seg_of(i) != target:
                bad.append(i)
    return {
        "bad_ids": bad,
        "business_code_ok": (spec.get("meta") or {}).get("business_code") == target,
        "verdict": "PASS" if not bad and (spec.get("meta") or {}).get("business_code") == target else "FAIL",
    }


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
