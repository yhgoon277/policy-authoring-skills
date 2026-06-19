#!/usr/bin/env python3
"""계층 ID 연결관계 정합성 전수 감사 (read-only, 결정론) — 이식 가능 config 구동판.

UC→PR→FN→세부기능, PR→PG→PI, FN↔PI 간 ID 매핑이 누락·불일치 없이
정합한지 모든 불변식(A~K)을 결정론적으로 검사하고 분류된 리포트를 낸다.

이 파일은 어떤 정책 모듈에도 그대로 쓰도록 일반화돼 있다. 프로젝트별로 달라지는 값
(business_code · expected_counts · known_pr_only · 금지토큰 · min_fn_per_pr ·
nc_required_fields)은 모두 policy_config.json 에서 읽는다.

사용:
  python3 audit_id_integrity.py [spec.json] [--config=policy_config.json] [--json] [--only=STRUCTURAL|SEMANTIC]
  # spec.json 미지정 시 config.spec_path 사용.

분류:
  STRUCTURAL = 진실원천(subfn_pis·group_id·override)에서 결정론 재계산 가능 → 자동수정 대상(목표 0)
  SEMANTIC   = 사람 판단 필요 (PR_only 매핑·고아 노드·표현 가독성)

종료코드: STRUCTURAL 위반 있으면 1, 없으면 0.
대상 = build 산출물 spec JSON.
"""
from __future__ import annotations
import json
import os
import re
import sys

# ───────────────────────── config 로드 ─────────────────────────
DEFAULT_CONFIG = "policy_config.json"

# config.naming_banned_tokens 미설정 시 기본값(표현 표준; 그룹 I2 정책상세명·I3 본문)
DEFAULT_BANNED_TOKENS = ["×", "↔", "→", "매트릭스", "CTA", "cross-distinction", "sub-", "T0~T9"]

# config.term_skip_keys 미설정 시 기본값(provenance·근거 필드 — I3 본문 스캔에서 제외)
DEFAULT_TERM_SKIP_KEYS = ["source_note", "source_refs", "source_basis",
                          "global_standard_ref", "v1.0_match", "field_review"]

# 검사 함수들이 참조하는 전역(config 적용 후 채워짐)
BUSINESS_CODE = "BIL"
EXPECTED_COUNTS: dict = {}
PREFIX_BY_KEY: dict = {}
ID_RE: dict = {}
KNOWN_PR_ONLY: set = set()
BANNED_TOKENS: list = list(DEFAULT_BANNED_TOKENS)
TERM_SKIP_KEYS: set = set(DEFAULT_TERM_SKIP_KEYS)


def load_config(path):
    if path and os.path.isfile(path):
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    return {}


def overlay_unit(cfg, unit):
    """config.units[unit] 블록을 top-level 키로 끌어올린다(있으면)."""
    units = cfg.get("units") or {}
    if not unit:
        return cfg
    if unit not in units:
        raise SystemExit(f"--unit={unit} 가 units 에 없습니다. 가능: {sorted(units)}")
    merged = dict(cfg)
    merged.update(units[unit])
    return merged


def apply_config(cfg):
    """config dict → 전역 규약(PREFIX_BY_KEY·ID_RE·EXPECTED_COUNTS·KNOWN_PR_ONLY·BANNED_TOKENS
    ·TERM_SKIP_KEYS·MIN_FN_PER_PR·NC_REQUIRED_FIELDS)."""
    global BUSINESS_CODE, EXPECTED_COUNTS, PREFIX_BY_KEY, ID_RE, KNOWN_PR_ONLY, BANNED_TOKENS
    global TERM_SKIP_KEYS, MIN_FN_PER_PR, NC_REQUIRED_FIELDS
    BUSINESS_CODE = cfg.get("business_code", "BIL")
    biz = re.escape(BUSINESS_CODE)
    PREFIX_BY_KEY = {
        "usecases": "UC-", "processes": "PR-", "functions": "FN-",
        "policy_groups": "PG-", "policies": "PG-", "policy_details": "PI-",
    }
    # ID 패턴: <TYPE>-<BIZ>-<DOMAIN>-NN, PI 는 두 단계 suffix(-NN-NN)
    ID_RE = {
        "usecases": re.compile(rf"^UC-{biz}-[A-Z]+-\d+$"),
        "processes": re.compile(rf"^PR-{biz}-[A-Z]+-\d+$"),
        "functions": re.compile(rf"^FN-{biz}-[A-Z]+-\d+$"),
        "policy_groups": re.compile(rf"^PG-{biz}-[A-Z]+-\d+$"),
        "policy_details": re.compile(rf"^PI-{biz}-[A-Z]+-\d+-\d+$"),
    }
    EXPECTED_COUNTS = dict(cfg.get("expected_counts") or {})  # 비면 H3 카운트 검사 생략(실측만 보고)
    KNOWN_PR_ONLY = {tuple(pair) for pair in (cfg.get("known_pr_only") or [])}
    BANNED_TOKENS = list(cfg.get("naming_banned_tokens") or DEFAULT_BANNED_TOKENS)
    TERM_SKIP_KEYS = set(cfg.get("term_skip_keys") or DEFAULT_TERM_SKIP_KEYS)
    MIN_FN_PER_PR = int(cfg.get("min_fn_per_pr") or 2)
    NC_REQUIRED_FIELDS = dict(cfg.get("nc_required_fields") or {})  # 비면 그룹 K 생략


class Violation:
    __slots__ = ("inv", "cls", "detail")

    def __init__(self, inv, cls, detail):
        self.inv = inv      # 불변식 ID (예: "A3")
        self.cls = cls      # "STRUCTURAL" | "SEMANTIC"
        self.detail = detail

    def as_dict(self):
        return {"inv": self.inv, "class": self.cls, "detail": self.detail}


def build_indexes(s):
    idx = {}
    idx["uc"] = {u["id"]: u for u in s.get("usecases", [])}
    idx["pr"] = {p["id"]: p for p in s.get("processes", [])}
    idx["prd"] = {d.get("process_id"): d for d in s.get("process_details", [])}
    idx["fn"] = {f["id"]: f for f in s.get("functions", [])}
    idx["fd"] = {d.get("function_id"): d for d in s.get("function_details", [])}
    idx["pg"] = {g["id"]: g for g in s.get("policy_groups", [])}
    idx["pi"] = {p["id"]: p for p in s.get("policy_details", [])}
    idx["UC"] = set(idx["uc"]); idx["PR"] = set(idx["pr"])
    idx["FN"] = set(idx["fn"]); idx["PG"] = set(idx["pg"]); idx["PI"] = set(idx["pi"])
    idx["pi_to_pg"] = {pid: (p.get("group_id") or p.get("policy_id"))
                       for pid, p in idx["pi"].items()}
    return idx


def parse_ref(ref):
    """'FN-BIL-CHRG-002#4' -> ('FN-BIL-CHRG-002', 4)"""
    if "#" not in ref:
        return ref, None
    fn, i = ref.rsplit("#", 1)
    try:
        return fn, int(i)
    except ValueError:
        return fn, None


# ───────────────────────── 그룹 A: 참조 존재성 ─────────────────────────
def check_A(s, idx):
    V = []
    def chk(coll, field, valid, label):
        for n in coll:
            for t in (n.get(field) or []):
                tid = t["id"] if isinstance(t, dict) else t
                if tid not in valid:
                    V.append(Violation(label, "STRUCTURAL",
                        f"{n.get('id') or n.get('function_id') or n.get('process_id')}.{field} -> 없는 ref {tid}"))
    chk(s.get("usecases", []), "related_processes", idx["PR"], "A1")
    for p in s.get("processes", []):
        for uc in ([p.get("usecase_id")] if p.get("usecase_id") else []) + (p.get("usecase_ids") or []):
            if uc not in idx["UC"]:
                V.append(Violation("A2", "STRUCTURAL", f"{p['id']} usecase ref -> 없는 {uc}"))
    chk(s.get("processes", []), "related_functions", idx["FN"], "A3")
    for f in s.get("functions", []):
        for pr in ([f.get("process_id")] if f.get("process_id") else []) + (f.get("process_ids") or []):
            if pr not in idx["PR"]:
                V.append(Violation("A4", "STRUCTURAL", f"{f['id']} process ref -> 없는 {pr}"))
    chk(s.get("processes", []), "related_policies", idx["PG"], "A5")
    chk(s.get("processes", []), "related_policy_details", idx["PI"], "A6")
    chk(s.get("functions", []), "related_policies", idx["PG"], "A7")
    chk(s.get("functions", []), "related_policy_details", idx["PI"], "A8")
    # A9: PI.applies_to_functions / applies_to#idx
    for pi in s.get("policy_details", []):
        for fn in (pi.get("applies_to_functions") or []):
            if fn not in idx["FN"]:
                V.append(Violation("A9", "STRUCTURAL", f"{pi['id']}.applies_to_functions -> 없는 {fn}"))
        for ref in (pi.get("applies_to") or []):
            fn, i = parse_ref(ref)
            if fn not in idx["FN"]:
                V.append(Violation("A9", "STRUCTURAL", f"{pi['id']}.applies_to -> 없는 FN {ref}"))
            elif i is not None:
                n = len(idx["fd"].get(fn, {}).get("sub_functions") or [])
                if not (1 <= i <= n):
                    V.append(Violation("A9", "STRUCTURAL", f"{pi['id']}.applies_to {ref} idx 범위초과(sub={n})"))
    # A10: PG.items -> PI
    for g in s.get("policy_groups", []):
        for it in (g.get("items") or []):
            pid = it["id"] if isinstance(it, dict) else it
            if pid not in idx["PI"]:
                V.append(Violation("A10", "STRUCTURAL", f"{g['id']}.items -> 없는 PI {pid}"))
    # A11: PI.group_id / policy_id -> PG
    for pi in s.get("policy_details", []):
        for fld in ("group_id", "policy_id"):
            v = pi.get(fld)
            if v and v not in idx["PG"]:
                V.append(Violation("A11", "STRUCTURAL", f"{pi['id']}.{fld} -> 없는 PG {v}"))
    # A12: subfn_pis -> PI
    for fd in s.get("function_details", []):
        for lst in (fd.get("subfn_pis") or []):
            for pid in (lst or []):
                if pid not in idx["PI"]:
                    V.append(Violation("A12", "STRUCTURAL", f"{fd.get('function_id')}.subfn_pis -> 없는 PI {pid}"))
    return V


# ───────────────────────── 그룹 B: 양방향 일치 ─────────────────────────
def check_B(s, idx):
    V = []
    # B1 UC.related_processes <-> PR.usecase_ids
    pr_uc = {p["id"]: set(p.get("usecase_ids") or []) for p in s.get("processes", [])}
    for u in s.get("usecases", []):
        for pr in (u.get("related_processes") or []):
            if pr in idx["pr"] and u["id"] not in pr_uc.get(pr, set()):
                V.append(Violation("B1", "STRUCTURAL", f"{u['id']}→{pr} 있으나 PR.usecase_ids 역참조 없음"))
    for p in s.get("processes", []):
        for uc in (p.get("usecase_ids") or []):
            u = idx["uc"].get(uc)
            if u and p["id"] not in (u.get("related_processes") or []):
                V.append(Violation("B1", "STRUCTURAL", f"{p['id']}.usecase_ids={uc} 있으나 UC.related_processes 없음"))
    # B2 PR.related_functions <-> FN.process_id(s)
    fn_pr = {f["id"]: set(([f.get("process_id")] if f.get("process_id") else []) + (f.get("process_ids") or []))
             for f in s.get("functions", [])}
    for p in s.get("processes", []):
        for fn in (p.get("related_functions") or []):
            if fn in idx["fn"] and p["id"] not in fn_pr.get(fn, set()):
                V.append(Violation("B2", "STRUCTURAL", f"{p['id']}→{fn} 있으나 FN.process_id 역참조 없음"))
    for f in s.get("functions", []):
        for pr in fn_pr.get(f["id"], set()):
            p = idx["pr"].get(pr)
            if p and f["id"] not in (p.get("related_functions") or []):
                V.append(Violation("B2", "STRUCTURAL", f"{f['id']}→{pr} 있으나 PR.related_functions 없음"))
    # B3 FN.related_policy_details <-> PI.applies_to_functions
    pi_fn = {pi["id"]: set(pi.get("applies_to_functions") or []) for pi in s.get("policy_details", [])}
    fn_pi = {f["id"]: set(f.get("related_policy_details") or []) for f in s.get("functions", [])}
    for pid, fns in pi_fn.items():
        for fn in fns:
            if fn in fn_pi and pid not in fn_pi[fn]:
                V.append(Violation("B3", "STRUCTURAL", f"{pid}.applies_to_functions={fn} 있으나 FN.related_policy_details 없음"))
    for fn, pis in fn_pi.items():
        for pid in pis:
            if pid in pi_fn and fn not in pi_fn[pid]:
                V.append(Violation("B3", "STRUCTURAL", f"{fn}.related_policy_details={pid} 있으나 PI.applies_to_functions 없음"))
    # B4 PG.items <-> PI.group_id
    pg_items = {g["id"]: {(it["id"] if isinstance(it, dict) else it) for it in (g.get("items") or [])}
                for g in s.get("policy_groups", [])}
    pi_by_pg = {}
    for pi in s.get("policy_details", []):
        pi_by_pg.setdefault(pi.get("group_id"), set()).add(pi["id"])
    for g in s.get("policy_groups", []):
        a = pg_items[g["id"]]; b = pi_by_pg.get(g["id"], set())
        if a != b:
            V.append(Violation("B4", "STRUCTURAL", f"{g['id']}: items_only={sorted(a-b)} gid_only={sorted(b-a)}"))
    # B5 PI.applies_to#idx <-> FD.subfn_pis[idx]
    for pi in s.get("policy_details", []):
        for ref in (pi.get("applies_to") or []):
            fn, i = parse_ref(ref)
            if i is None:
                continue
            fd = idx["fd"].get(fn)
            if not fd:
                continue
            sp = fd.get("subfn_pis") or []
            if not (1 <= i <= len(sp)) or pi["id"] not in (sp[i-1] or []):
                V.append(Violation("B5", "STRUCTURAL", f"{pi['id']}.applies_to {ref} 있으나 subfn_pis[{i}]에 미포함"))
    # B6 usecase_id(단수) ⊆ usecase_ids(복수)
    for p in s.get("processes", []):
        u1 = p.get("usecase_id")
        if u1 and u1 not in (p.get("usecase_ids") or []):
            V.append(Violation("B6", "STRUCTURAL", f"{p['id']}.usecase_id={u1} 가 usecase_ids에 없음"))
    return V


# ───────────────────────── 그룹 C: 롤업/파생 ─────────────────────────
def _derive_pgs(pi_ids, pi_to_pg):
    return sorted({pi_to_pg[p] for p in pi_ids if pi_to_pg.get(p)})


def check_C(s, idx):
    V = []
    fd_by = idx["fd"]; pi_to_pg = idx["pi_to_pg"]
    fn_pi = {}
    # C1 FN.related_policy_details == union(subfn_pis)
    for f in s.get("functions", []):
        fd = fd_by.get(f["id"], {})
        union = set()
        for lst in (fd.get("subfn_pis") or []):
            union |= set(lst or [])
        decl = set(f.get("related_policy_details") or [])
        fn_pi[f["id"]] = decl
        if union != decl:
            V.append(Violation("C1", "STRUCTURAL", f"{f['id']}: union_only={sorted(union-decl)} decl_only={sorted(decl-union)}"))
    # C2 PR.related_policy_details == union(FN)
    for p in s.get("processes", []):
        union = set()
        for fn in (p.get("related_functions") or []):
            union |= fn_pi.get(fn, set())
        decl = set(p.get("related_policy_details") or [])
        for pid in sorted(union - decl):  # FN_only = STRUCTURAL (PR 롤업 누락)
            V.append(Violation("C2", "STRUCTURAL", f"{p['id']} FN_only(PR누락): {pid}"))
        for pid in sorted(decl - union):  # PR_only (전부 SEMANTIC — 사람 판단)
            tag = "알려진 정상" if (p["id"], pid) in KNOWN_PR_ONLY else "★미검토"
            V.append(Violation("C2", "SEMANTIC", f"{p['id']} PR_only(FN에없음): {pid} [{tag}]"))
    # C3 FN.related_policies == derive_PG(FN.rpd)  (fallback 허용=초과는 OK, 누락만 위반)
    for f in s.get("functions", []):
        derived = set(_derive_pgs(fn_pi.get(f["id"], set()), pi_to_pg))
        decl = set(f.get("related_policies") or [])
        if derived - decl:
            V.append(Violation("C3", "STRUCTURAL", f"{f['id']}: PG누락={sorted(derived-decl)}"))
    # C4 PR.related_policies == derive_PG(PR.rpd) (누락만)
    for p in s.get("processes", []):
        derived = set(_derive_pgs(set(p.get("related_policy_details") or []), pi_to_pg))
        decl = set(p.get("related_policies") or [])
        if derived - decl:
            V.append(Violation("C4", "STRUCTURAL", f"{p['id']}: PG누락={sorted(derived-decl)}"))
    # C5 FD.related_policy_details == FN.related_policy_details
    for f in s.get("functions", []):
        fd = fd_by.get(f["id"], {})
        if set(fd.get("related_policy_details") or []) != fn_pi.get(f["id"], set()):
            V.append(Violation("C5", "STRUCTURAL", f"{f['id']}: FD미러 != FN.related_policy_details"))
    return V


# ───────────────────────── 그룹 D: PG 멤버십 (B4 독립 재구현) ─────────────────────────
def check_D(s, idx):
    V = []
    members = {}
    for pi in s.get("policy_details", []):
        members.setdefault(pi.get("group_id"), set()).add(pi["id"])
    for g in s.get("policy_groups", []):
        declared = {(it["id"] if isinstance(it, dict) else it) for it in (g.get("items") or [])}
        actual = members.get(g["id"], set())
        if declared != actual:
            V.append(Violation("D1", "STRUCTURAL", f"{g['id']}: items={len(declared)} vs group_id매칭={len(actual)} diff={sorted(declared^actual)}"))
    return V


# ───────────────────────── 그룹 E: 커버리지/고아 ─────────────────────────
def check_E(s, idx):
    V = []
    pr_uc_all = set()
    for p in s.get("processes", []):
        pr_uc_all |= set(p.get("usecase_ids") or [])
    for u in s.get("usecases", []):
        if u["id"] not in pr_uc_all and not (u.get("related_processes")):
            # process_target=='N' UC는 프로세스를 갖지 않도록 의도된 설계 (예: 외부연계)
            if str(u.get("process_target", "")).upper() == "N":
                V.append(Violation("E1", "SEMANTIC", f"{u['id']} 연결 PR 없음 (process_target=N, 의도된 비프로세스 UC)"))
            else:
                V.append(Violation("E1", "STRUCTURAL", f"{u['id']} UC에 연결된 PR 없음"))
    for p in s.get("processes", []):
        if not (p.get("related_functions")):
            V.append(Violation("E2", "STRUCTURAL", f"{p['id']} PR에 FN 없음"))
        if not (p.get("usecase_ids") or p.get("usecase_id")):
            V.append(Violation("E3", "STRUCTURAL", f"{p['id']} PR에 UC 없음"))
    fn_pi_any = {f["id"]: bool(f.get("related_policy_details")) for f in s.get("functions", [])}
    for f in s.get("functions", []):
        if not fn_pi_any[f["id"]]:
            V.append(Violation("E4", "SEMANTIC", f"{f['id']} FN에 PI 없음(고아 후보)"))
    members = {}
    for pi in s.get("policy_details", []):
        members.setdefault(pi.get("group_id"), set()).add(pi["id"])
    for g in s.get("policy_groups", []):
        if not members.get(g["id"]):
            V.append(Violation("E5", "STRUCTURAL", f"{g['id']} PG에 PI 없음"))
    for pi in s.get("policy_details", []):
        if not (pi.get("applies_to_functions")):
            V.append(Violation("E6", "SEMANTIC", f"{pi['id']} PI가 어떤 FN에도 적용 안됨(배경 PI 후보)"))
    return V


# ───────────────────────── 그룹 F: 세부기능 배열 ─────────────────────────
def check_F(s, idx):
    V = []
    for fd in s.get("function_details", []):
        sf = fd.get("sub_functions") or []
        sp = fd.get("subfn_pis") or []
        su = fd.get("subfn_ui") or []
        if not (len(sf) == len(sp) == len(su)):
            V.append(Violation("F1", "STRUCTURAL", f"{fd.get('function_id')}: len sub={len(sf)} pis={len(sp)} ui={len(su)}"))
        for j, val in enumerate(su):
            if not isinstance(val, bool):
                V.append(Violation("F2", "STRUCTURAL", f"{fd.get('function_id')}.subfn_ui[{j}] bool 아님: {val!r}"))
    return V


# ───────────────────────── 그룹 G: trace_matrix ↔ 컬렉션 ─────────────────────────
def check_G(s, idx):
    V = []
    tm = s.get("trace_matrix")
    if not isinstance(tm, dict):
        V.append(Violation("G0", "STRUCTURAL", f"trace_matrix가 dict 아님: {type(tm).__name__}"))
        return V
    # G6 coverage 카운트 == 실측
    cov = tm.get("coverage") or {}
    real = {"uc_count": len(s.get("usecases", [])),
            "process_count": len(s.get("processes", [])),
            "function_count": len(s.get("functions", [])),
            "policy_detail_count": len(s.get("policy_details", []))}
    for k, rv in real.items():
        if k in cov and cov.get(k) != rv:
            V.append(Violation("G6", "STRUCTURAL", f"coverage.{k}={cov.get(k)} != 실측 {rv}"))
    # G1 uc_to_process 키가 현 UC id 체계와 맞는지(stale 검출)
    u2p = tm.get("uc_to_process") or {}
    stale_uc = [k for k in u2p if k not in idx["UC"]]
    if stale_uc:
        V.append(Violation("G1", "STRUCTURAL", f"uc_to_process 키 {len(stale_uc)}개가 현 UC id와 불일치(stale): {stale_uc[:3]}"))
    # G2 process_to_function 키
    p2f = tm.get("process_to_function") or {}
    stale_pr = [k for k in p2f if k not in idx["PR"]]
    if stale_pr:
        V.append(Violation("G2", "STRUCTURAL", f"process_to_function 키 {len(stale_pr)}개가 현 PR id와 불일치(stale): {stale_pr[:3]}"))
    # G3 function_to_policy_detail 일치 (전부 미매핑이면 빈 맵=정상; stale/불일치/누락만 STRUCTURAL)
    f2p = tm.get("function_to_policy_detail") or {}
    fn_pi = {f["id"]: set(f.get("related_policy_details") or []) for f in s.get("functions", [])}
    expected_f2p = {fn for fn, pis in fn_pi.items() if pis}
    for fn, pis in f2p.items():
        if set(pis) != fn_pi.get(fn, set()):
            V.append(Violation("G3", "STRUCTURAL", f"f2p[{fn}] != FN.related_policy_details"))
    missing_f2p = sorted(expected_f2p - set(f2p))
    if missing_f2p:
        V.append(Violation("G3", "STRUCTURAL", f"function_to_policy_detail 누락/stale {len(missing_f2p)}: {missing_f2p[:3]}"))
    # G4 policy_detail_to_function (전부 배경 PI면 빈 맵=정상)
    p2fn = tm.get("policy_detail_to_function") or {}
    pi_fn = {pi["id"]: set(pi.get("applies_to_functions") or []) for pi in s.get("policy_details", [])}
    expected_p2fn = {pi for pi, fns in pi_fn.items() if fns}
    for pi, fns in p2fn.items():
        if set(fns) != pi_fn.get(pi, set()):
            V.append(Violation("G4", "STRUCTURAL", f"p2fn[{pi}] != PI.applies_to_functions"))
    missing_p2fn = sorted(expected_p2fn - set(p2fn))
    if missing_p2fn:
        V.append(Violation("G4", "STRUCTURAL", f"policy_detail_to_function 누락/stale {len(missing_p2fn)}: {missing_p2fn[:3]}"))
    return V


# ───────────────────────── 그룹 H: 형식·유일성·카운트 ─────────────────────────
def check_H(s, idx):
    V = []
    # H1 prefix + H4 정규식
    for key, prefix in PREFIX_BY_KEY.items():
        for n in s.get(key, []):
            nid = n.get("id", "")
            if not nid.startswith(prefix):
                V.append(Violation("H1", "STRUCTURAL", f"{key} '{nid}' prefix != {prefix}"))
            rx = ID_RE.get(key)
            if rx and nid and not rx.match(nid):
                V.append(Violation("H4", "STRUCTURAL", f"{key} '{nid}' 형식 위반 (business_code={BUSINESS_CODE})"))
    # H2 전역 유일성
    seen = {}
    for key in ("usecases", "processes", "functions", "policy_groups", "policy_details"):
        for n in s.get(key, []):
            nid = n.get("id")
            if not nid:
                continue
            if nid in seen:
                V.append(Violation("H2", "STRUCTURAL", f"중복 id {nid} ({key}, 최초={seen[nid]})"))
            else:
                seen[nid] = key
    # H3 카운트 (config.expected_counts 설정 시에만 — 미설정이면 main에서 실측만 보고)
    for key, exp in EXPECTED_COUNTS.items():
        got = len(s.get(key, []))
        if got != exp:
            V.append(Violation("H3", "STRUCTURAL", f"{key} count {got} != {exp}"))
    # H5 policies == policy_groups alias
    a = [g.get("id") for g in s.get("policy_groups", [])]
    b = [g.get("id") for g in s.get("policies", [])]
    if a != b:
        V.append(Violation("H5", "STRUCTURAL", "policy_groups != policies (alias 불일치)"))
    return V


# ───────────────────────── 그룹 I: 표현 표준(가독성) ─────────────────────────
def check_I(s, idx):
    """SEMANTIC. exit 1 유발 안 함. 기호·외국어·괄호 잔존 가시화.
    I1: 세부기능명(sub_functions)에 괄호 없음.
    I2: 정책상세명(PI name, 끝단 (ID) 제외 base)에 금지 토큰 없음.
    I3: PI 본문(rule_statement·criteria_values·customer_notice·detail_tables 셀/note)에 금지 토큰 없음.
        근거 필드(config.term_skip_keys: source_note·field_review 등)는 → 등 허용이므로 스캔 제외,
        파생 미러(content·decision_spec)도 작성자 원본이 아니므로 제외(이중보고 방지).
    금지 토큰은 config.naming_banned_tokens (기본값 DEFAULT_BANNED_TOKENS)."""
    V = []
    for fd in s.get("function_details", []):
        for sub in fd.get("sub_functions", []) or []:
            if "(" in sub or "（" in sub:
                V.append(Violation("I1", "SEMANTIC",
                    f"{fd.get('function_id')}.sub_functions 괄호 잔존: {sub!r}"))

    # I3 본문 스캔 대상 = 작성자가 직접 쓰는 본문 필드만. term_skip_keys 에 든 근거 필드는 제외.
    body_str_fields = [f for f in ("rule_statement", "customer_notice") if f not in TERM_SKIP_KEYS]
    scan_criteria = "criteria_values" not in TERM_SKIP_KEYS
    scan_tables = "detail_tables" not in TERM_SKIP_KEYS

    def flag_I3(pid, field, text):
        if not isinstance(text, str):
            return
        for b in BANNED_TOKENS:
            if b in text:
                V.append(Violation("I3", "SEMANTIC",
                    f"{pid}.{field} 본문 금지 토큰 '{b}': {text[:50]!r}"))

    for pi in s.get("policy_details", []):
        pid = pi["id"]
        base = re.sub(r"\s*\([^)]*\)\s*$", "", pi.get("name", ""))  # 끝단 (ID) 제거
        for b in BANNED_TOKENS:
            if b in base:
                V.append(Violation("I2", "SEMANTIC", f"{pid}.name 표현 잔존 '{b}': {base!r}"))
        if re.search(r"\blink\b", base):
            V.append(Violation("I2", "SEMANTIC", f"{pid}.name 'link' 잔존: {base!r}"))
        # I3: 본문 필드 금지 토큰 스캔
        for f in body_str_fields:
            flag_I3(pid, f, pi.get(f))
        if scan_criteria:
            for c in (pi.get("criteria_values") or []):
                flag_I3(pid, "criteria_values", c)
        if scan_tables:
            for t in (pi.get("detail_tables") or []):
                flag_I3(pid, "detail_tables.caption", t.get("caption"))
                flag_I3(pid, "detail_tables.note", t.get("note"))
                for h in (t.get("headers") or []):
                    flag_I3(pid, "detail_tables.headers", h)
                for row in (t.get("rows") or []):
                    for cell in row:
                        flag_I3(pid, "detail_tables.cell", cell)
    return V


# ───────────────────────── 그룹 J: 계위 건전성 (PR↔FN) ─────────────────────────
def check_J(s, idx):
    """SEMANTIC. 재-레벨링 회귀 가드 — exit 1 유발 안 함, 사인오프 전 0 목표.
    J1: PR당 FN 수 < config.min_fn_per_pr (기본 2) — PR↔FN 1:1 계위 결함 재발 감지.
    J2: PR명 == 소속 FN명 — 화면/위젯 레벨 미분화 신호."""
    V = []
    fn_names = {f["id"]: (f.get("name") or "").strip() for f in s.get("functions", [])}
    for pr in s.get("processes", []):
        fns = pr.get("related_functions") or []
        if len(fns) < MIN_FN_PER_PR:
            V.append(Violation("J1", "SEMANTIC",
                f"{pr['id']} FN {len(fns)}개 < min_fn_per_pr({MIN_FN_PER_PR})"))
        pname = (pr.get("name") or "").strip()
        for fid in fns:
            if pname and fn_names.get(fid) == pname:
                V.append(Violation("J2", "SEMANTIC", f"{pr['id']}명 == {fid}명: {pname!r}"))
    return V


# ───────────────────────── 그룹 K: NC 필수필드(스키마 완성도) ─────────────────────────
def check_K(s, idx):
    """STRUCTURAL — enrich_spec.py가 빌드에서 결정론으로 채우므로 0이어야 정상.
    config.nc_required_fields = {컬렉션: [필드,...]} 구동. 비면 전체 생략.
    K1 processes 필드(usecase_id 등) · K2 functions 필드(details 등)
    K3 process_details 필드(키 존재 검사 — 빈 리스트 허용) · K4 policy_details 필드(decision_spec·rule_type 등).
    decision_spec은 스켈레톤 존재만 STRUCTURAL(내용 품질은 별도 검토 대상)."""
    V = []
    req = NC_REQUIRED_FIELDS
    for fld in req.get("processes", []):
        for p in s.get("processes", []):
            if not p.get(fld):
                V.append(Violation("K1", "STRUCTURAL", f"{p['id']}.{fld} 없음/빈값"))
    for fld in req.get("functions", []):
        for f in s.get("functions", []):
            if not f.get(fld):
                V.append(Violation("K2", "STRUCTURAL", f"{f['id']}.{fld} 없음/빈값"))
    for fld in req.get("process_details", []):
        for d in s.get("process_details", []):
            if fld not in d:  # case_branches 등은 빈 리스트 허용(키 존재만)
                V.append(Violation("K3", "STRUCTURAL", f"{d.get('process_id')}.{fld} 키 없음"))
    for fld in req.get("policy_details", []):
        for p in s.get("policy_details", []):
            if not p.get(fld):
                V.append(Violation("K4", "STRUCTURAL", f"{p['id']}.{fld} 없음/빈값"))
    return V


# ───────────────────────── 그룹 L: 요구사항↔노드 연결 정합성 ─────────────────────────
def check_L(s, idx):
    """요구사항↔노드 연결(emit_requirement_links 산출) 정합성. 기능 비활성 시 [] (가산-안전).
    L1 STRUCTURAL: meta.topic_learning.requirement_links[].nodes 전부 라이브 노드 실존(dangling 0).
    L2 STRUCTURAL: NC requirement_id 유일 · requirements_count == len(links).
    L4 STRUCTURAL: 양방향 일치 — link.nodes ⇄ node.source_requirement_ids."""
    V = []
    tl = (s.get("meta") or {}).get("topic_learning") or {}
    links = tl.get("requirement_links")
    nodes_emitted = any(o.get("source_requirement_ids")
                        for c in ("usecases", "processes", "functions", "policy_groups", "policy_details")
                        for o in s.get(c, []))
    if not links and not nodes_emitted:
        return V  # 기능 비활성 — baseline STRUCTURAL 0 유지
    links = links or []
    allids = idx["UC"] | idx["PR"] | idx["FN"] | idx["PG"] | idx["PI"]

    seen = set()
    for l in links:
        rid = l.get("requirement_id")
        if rid in seen:
            V.append(Violation("L2", "STRUCTURAL", f"requirement_links 중복 id {rid}"))
        seen.add(rid)
    rc = tl.get("requirements_count")
    if rc is not None and rc != len(links):
        V.append(Violation("L2", "STRUCTURAL", f"requirements_count {rc} != links {len(links)}"))

    fwd = {}  # node_id -> set(requirement_id) (link.nodes 기준)
    for l in links:
        rid = l.get("requirement_id")
        for n in (l.get("nodes") or []):
            if n not in allids:
                V.append(Violation("L1", "STRUCTURAL", f"{rid}.nodes -> 없는 노드 {n}"))
            else:
                fwd.setdefault(n, set()).add(rid)

    for c in ("usecases", "processes", "functions", "policy_groups", "policy_details"):
        for o in s.get(c, []):
            sids = set(o.get("source_requirement_ids") or [])
            exp = fwd.get(o["id"], set())
            if sids != exp:
                V.append(Violation("L4", "STRUCTURAL",
                    f"{o['id']} 양방향 불일치 — 링크기준 {sorted(exp)} vs 노드 {sorted(sids)}"))
    return V


CHECKS = [
    ("A 참조 존재성(dangling)", check_A),
    ("B 양방향 일치", check_B),
    ("C 롤업/파생", check_C),
    ("D PG 멤버십", check_D),
    ("E 커버리지/고아", check_E),
    ("F 세부기능 배열", check_F),
    ("G trace_matrix↔컬렉션", check_G),
    ("H 형식·유일성·카운트", check_H),
    ("I 표현 표준(가독성)", check_I),
    ("J 계위 건전성(PR-FN)", check_J),
    ("K NC 필수필드", check_K),
    ("L 요구사항↔노드 연결", check_L),
]


def _by_inv(vs):
    d = {}
    for v in vs:
        d[v.inv] = d.get(v.inv, 0) + 1
    return dict(sorted(d.items()))


def main(argv):
    args = [a for a in argv[1:] if not a.startswith("--")]
    opts = [a for a in argv[1:] if a.startswith("--")]
    config_path = DEFAULT_CONFIG
    unit = None
    for o in opts:
        if o.startswith("--config="):
            config_path = o.split("=", 1)[1].strip()
        elif o.startswith("--unit="):
            unit = o.split("=", 1)[1].strip()
    cfg = overlay_unit(load_config(config_path), unit)
    apply_config(cfg)

    spec_path = args[0] if args else cfg.get("spec_path")
    if not spec_path:
        print("ERROR: spec 경로를 지정하거나 policy_config.json 에 spec_path 를 설정하세요.", file=sys.stderr)
        return 2
    as_json = "--json" in opts
    only = None
    for o in opts:
        if o.startswith("--only="):
            only = o.split("=", 1)[1].strip().upper()

    s = json.load(open(spec_path, encoding="utf-8"))
    idx = build_indexes(s)

    all_v = []
    group_results = []
    for label, fn in CHECKS:
        vs = fn(s, idx)
        if only:
            vs = [v for v in vs if v.cls == only]
        all_v.extend(vs)
        group_results.append((label, vs))

    struct = [v for v in all_v if v.cls == "STRUCTURAL"]
    seman = [v for v in all_v if v.cls == "SEMANTIC"]

    actual_counts = {k: len(s.get(k, [])) for k in
                     ("usecases", "processes", "functions", "policy_groups", "policy_details")}

    if as_json:
        print(json.dumps({
            "spec": spec_path,
            "business_code": BUSINESS_CODE,
            "actual_counts": actual_counts,
            "expected_counts": EXPECTED_COUNTS or "(미설정 — H3 카운트 검사 생략)",
            "structural": [v.as_dict() for v in struct],
            "semantic": [v.as_dict() for v in seman],
            "by_invariant": _by_inv(all_v),
        }, ensure_ascii=False, indent=2))
        return 1 if struct else 0

    print(f"=== ID 정합성 감사: {spec_path} (business_code={BUSINESS_CODE}) ===")
    print(f"실측 카운트: {actual_counts}")
    if not EXPECTED_COUNTS:
        print("  ⚠️ expected_counts 미설정 → H3 카운트 검사 생략. 안정화 후 위 실측치를 policy_config.json 에 고정하면 회귀 가드가 됩니다.")
    for label, vs in group_results:
        st = sum(1 for v in vs if v.cls == "STRUCTURAL")
        se = sum(1 for v in vs if v.cls == "SEMANTIC")
        tag = "PASS" if not vs else f"위반 {len(vs)} (구조 {st} / 의미 {se})"
        print(f"\n[{label}] {tag}")
        for v in vs[:40]:
            print(f"  {v.cls[0]} {v.inv}: {v.detail}")
        if len(vs) > 40:
            print(f"  ... {len(vs)-40} more")

    print(f"\n=== 요약 ===")
    print(f"  STRUCTURAL 위반: {len(struct)}  (목표 0)")
    print(f"  SEMANTIC 위반: {len(seman)}  (사람 판단 — 의도된 건은 known_pr_only 등으로 관리)")
    print(f"  불변식별 카운트: {_by_inv(all_v)}")
    return 1 if struct else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
