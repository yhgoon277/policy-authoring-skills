#!/usr/bin/env python3
"""요구사항 커버리지 검토 — 워크플로우 보조(준비/주입/통합) 결정론 스크립트.

4-Phase 워크플로우(준비→①매핑→②품질→종합)에서 에이전트가 아닌 결정론 부분을 모은 것.
워크플로우 스크립트: req_coverage_map.workflow.js(①), req_coverage_quality.workflow.js(②).
방법론 전체: audit/REQUIREMENT_COVERAGE_METHOD.md.

사용:
  python3 tools/coverage/prep_coverage_inputs.py prep     --unit=hub   # 카탈로그·배치·힌트·node_bodies (①매핑 전)
  # → Workflow(req_coverage_map.workflow.js) 실행 → map_b{0..N}.json
  python3 tools/coverage/prep_coverage_inputs.py inject   --unit=hub   # 매핑 검증(환각/누락/미매핑) + 매트릭스 주입 + map_all.json
  python3 tools/coverage/prep_coverage_inputs.py qa-input --unit=hub   # qa_input_b{i}.json (②품질 전)
  # → Workflow(req_coverage_quality.workflow.js) 실행 → qa_b/adv_b
  python3 tools/coverage/prep_coverage_inputs.py finalize --unit=hub   # 최종등급(분쟁 하향) → final_grades.json

산출 위치: audit/_coverage_work(hub) 또는 audit/_coverage_work_<unit>.
hub 특수성·조정점은 audit/REQUIREMENT_COVERAGE_METHOD.md 참조.
"""
import argparse, json, os, re
from collections import Counter, defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
bare = lambda n: (n or '').split('#')[0]


def paths(unit):
    cfg = json.load(open(os.path.join(ROOT, 'policy_config.json'), encoding='utf-8'))
    sp = cfg['units'][unit]['spec_path']
    sp = sp if os.path.isabs(sp) else os.path.join(ROOT, sp)
    work = os.path.join(ROOT, 'audit', '_coverage_work' if unit == 'hub' else f'_coverage_work_{unit}')
    return sp, work, os.path.join(ROOT, 'audit', f'{unit}_coverage_matrix.md')


def load_spec(unit):
    sp, _, _ = paths(unit)
    return json.load(open(sp, encoding='utf-8'))


def reqs_of(unit):
    rs = [json.loads(l) for l in open(os.path.join(ROOT, 'data/index/requirements.jsonl'), encoding='utf-8')]
    return sorted([r for r in rs if r['unit'] == unit], key=lambda r: r['requirement_id'])


def all_ids(spec):
    s = set()
    for k in ('usecases', 'processes', 'functions', 'policy_groups', 'policy_details'):
        s |= {n['id'] for n in spec[k]}
    return s


def cmd_prep(unit):
    sp, work, _ = paths(unit); os.makedirs(work, exist_ok=True)
    spec = load_spec(unit)
    UC = {u['id']: u for u in spec['usecases']}; PR = {p['id']: p for p in spec['processes']}
    FN = {f['id']: f for f in spec['functions']}; PG = {g['id']: g for g in spec['policy_groups']}; PI = {d['id']: d for d in spec['policy_details']}
    tm = spec['trace_matrix']; uc2pr = tm['uc_to_process']; pr2fn = tm['process_to_function']; fn2pi = tm['function_to_policy_detail']
    ids = all_ids(spec)
    pg_pis = defaultdict(list)
    for d in spec['policy_details']: pg_pis[d['group_id']].append(d['id'])
    L = [f'# {unit} 노드 카탈로그 — 요구사항 매핑용 유일 진실원천',
         f'\n총 {len(ids)} ID = UC {len(UC)}·PR {len(PR)}·FN {len(FN)}·PG {len(PG)}·PI {len(PI)}',
         '⚠️ 아래에 없는 ID는 존재하지 않는다. 매핑은 반드시 여기 있는 ID만 사용.\n',
         '## 계층: UC → PR → FN (→ FN이 끌고 오는 PI)']
    for uc in spec['usecases']:
        L.append(f"\n### {uc['id']} {uc['name']} (actor={uc.get('actor', '-')}, process_target={uc.get('process_target', '-')})")
        if uc.get('description'): L.append(f"  desc: {uc['description']}")
        for prid in uc2pr.get(uc['id'], []):
            p = PR.get(prid)
            if not p: continue
            L.append(f"  - {prid} {p['name']}")
            for fnid in pr2fn.get(prid, []):
                f = FN.get(fnid)
                if not f: continue
                pis = fn2pi.get(fnid, [])
                L.append(f"      · {fnid} {f['name']} → PI: {', '.join(pis) if pis else '(없음)'}")
                if f.get('details'): L.append(f"          세부기능: {' / '.join(f['details'])}")
    L.append('\n## 정책: PG → PI (rule 요약)')
    for g in spec['policy_groups']:
        L.append(f"\n### {g['id']} {g['name']}")
        for pid in pg_pis.get(g['id'], []):
            d = PI[pid]; rule = (d.get('rule_statement') or d.get('content') or '').replace('\n', ' ')
            L.append(f"  - {pid} {d['name'].split(' (')[0]}: {rule}")
    L.append('\n## 평면 ID 인덱스'); L.append(' '.join(sorted(ids)))
    open(os.path.join(work, 'node_catalog.md'), 'w', encoding='utf-8').write('\n'.join(L))

    rs = reqs_of(unit); size = 12
    batches = [rs[i:i + size] for i in range(0, len(rs), size)]
    json.dump(batches, open(os.path.join(work, 'batches.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)

    stale_p = os.path.join(ROOT, 'data/index', f'{unit}_requirement_coverage.jsonl')
    hints = {}
    if os.path.exists(stale_p):
        stale = [json.loads(l) for l in open(stale_p, encoding='utf-8')]
        norm = lambda s: re.sub(r'[^가-힣a-z0-9]', '', (s or '').lower())
        sbn = defaultdict(list)
        for s in stale:
            live = [n for n in s.get('mapped_to', []) if n in ids]
            nm = norm(s.get('detail_name', ''))
            if nm: sbn[nm] += live
        for r in rs:
            nm = norm(r['name']); cand = list(sbn.get(nm, []))
            if not cand:
                for sn, nodes in sbn.items():
                    if nm and len(nm) > 3 and (nm in sn or sn in nm): cand += nodes
            if cand: hints[r['requirement_id']] = sorted(set(cand))
    json.dump(hints, open(os.path.join(work, 'stale_hints.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)

    bodies = {}
    for d in spec['policy_details']:
        bodies[d['id']] = {'type': 'PI', 'name': d['name'].split(' (')[0], 'rule': d.get('rule_statement'), 'criteria': d.get('criteria_values'), 'notice': d.get('customer_notice'), 'tables': d.get('detail_tables')}
    for f in spec['functions']: bodies[f['id']] = {'type': 'FN', 'name': f['name'], 'desc': f.get('description'), 'details': f.get('details')}
    for p in spec['processes']: bodies[p['id']] = {'type': 'PR', 'name': p['name'], 'desc': p.get('description')}
    for u in spec['usecases']: bodies[u['id']] = {'type': 'UC', 'name': u['name'], 'desc': u.get('description')}
    for g in spec['policy_groups']: bodies[g['id']] = {'type': 'PG', 'name': g['name'], 'desc': g.get('description')}
    json.dump(bodies, open(os.path.join(work, 'node_bodies.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print(f'[prep] {unit}: 카탈로그 {len(ids)}ID · 배치 {[len(b) for b in batches]} · 힌트 {len(hints)} · node_bodies {len(bodies)} → {work}')


def _load_map(work, n):
    decs = []
    for i in range(n):
        p = os.path.join(work, f'map_b{i}.json')
        if not os.path.exists(p): continue
        d = json.load(open(p, encoding='utf-8')); d = d if isinstance(d, list) else d.get('decisions', [])
        decs += d
    return decs


def cmd_inject(unit):
    sp, work, matrix = paths(unit); spec = load_spec(unit); ids = all_ids(spec)
    batches = json.load(open(os.path.join(work, 'batches.json'), encoding='utf-8'))
    decs = _load_map(work, len(batches)); by = {d['requirement_id']: d for d in decs}
    rids = [d['requirement_id'] for d in decs]; exp = {r['requirement_id'] for r in reqs_of(unit)}
    halluc = [(d['requirement_id'], n) for d in decs for n in d.get('tobe_nodes', []) if bare(n) not in ids]
    unmapped = [d['requirement_id'] for d in decs if '삭제' not in d['decision'] and '범위밖' not in d['decision'] and not d.get('tobe_nodes')]
    missing = sorted(exp - set(rids))
    print(f'[inject] {unit}: {len(decs)}건 · 누락 {missing or 0} · 환각 {len(halluc)} · 미매핑 {len(unmapped)}')
    if halluc or missing or unmapped:
        print('  ⚠️ 검증 실패 — 주입 중단. 환각 예:', halluc[:8], '미매핑:', unmapped[:8]); return
    json.dump(sorted(decs, key=lambda d: d['requirement_id']), open(os.path.join(work, 'map_all.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    clean = lambda s: (s or '').replace('|', '/').strip()
    out = []; filled = 0
    for ln in open(matrix, encoding='utf-8').read().split('\n'):
        if ln.startswith('|') and re.match(r'\|\s*\d+\s*\|', ln):
            c = [x.strip() for x in ln.strip('|').split('|')]; d = by.get(c[1])
            if d:
                nodes = ', '.join(bare(n) for n in d.get('tobe_nodes', [])) or '-'
                c = [c[0], c[1], c[2], c[3], d['decision'], nodes, clean(d.get('asis_source', '-')) or '-', clean(d.get('rationale', ''))]
                ln = '| ' + ' | '.join(c) + ' |'; filled += 1
        out.append(ln)
    open(matrix, 'w', encoding='utf-8').write('\n'.join(out))
    print(f'  ✓ 매트릭스 {filled}행 주입 (이후 coverage_gate.py --unit={unit} 로 PASS 확인)')


def cmd_qa_input(unit):
    sp, work, _ = paths(unit); spec = load_spec(unit); fn2pi = spec['trace_matrix']['function_to_policy_detail']
    batches = json.load(open(os.path.join(work, 'batches.json'), encoding='utf-8'))
    mapall = {d['requirement_id']: d for d in json.load(open(os.path.join(work, 'map_all.json'), encoding='utf-8'))}
    bodies = json.load(open(os.path.join(work, 'node_bodies.json'), encoding='utf-8'))
    for i, batch in enumerate(batches):
        items = []
        for r in batch:
            d = mapall[r['requirement_id']]; nb = {}
            for n in d.get('tobe_nodes', []):
                bn = bare(n); nb[bn] = bodies.get(bn)
                if bn.startswith('FN-'):
                    for pi in fn2pi.get(bn, []): nb.setdefault(pi, bodies.get(pi))
            items.append({'requirement_id': r['requirement_id'], 'name': r['name'], 'description': r['description'], 'fo_bo': r.get('fo_bo'), 'decision': d['decision'], 'tobe_nodes': [bare(n) for n in d.get('tobe_nodes', [])], 'mapping_rationale': d.get('rationale', ''), 'node_bodies': nb})
        json.dump(items, open(os.path.join(work, f'qa_input_b{i}.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print(f'[qa-input] {unit}: {len(batches)} 배치 생성 → {work}')


def cmd_finalize(unit):
    sp, work, _ = paths(unit); batches = json.load(open(os.path.join(work, 'batches.json'), encoding='utf-8'))
    GR = ['충실 반영', '부분 반영', '이름만 반영', '미반영', '범위밖']

    def norm(s):
        t = (s or '').strip().replace(' ', '')
        for g in GR:
            if g.replace(' ', '') == t: return g
        for g in GR:
            if g.replace(' ', '') in t: return g
        return s or '?'

    def ld(pre):
        m = {}
        for i in range(len(batches)):
            p = os.path.join(work, f'{pre}_b{i}.json')
            if not os.path.exists(p): continue
            d = json.load(open(p, encoding='utf-8')); d = d if isinstance(d, list) else (d.get('grades') or d.get('reviews') or [])
            for x in d: m[x['requirement_id']] = x
        return m

    qa = ld('qa'); adv = ld('adv'); final = []
    for rid in sorted(qa):
        g = qa[rid]; a = adv.get(rid, {}); qg = norm(g.get('grade')); ch = a.get('challenge', '동의'); rg = norm(a.get('revised_grade', ''))
        fg = rg if ch in ('강등 제안', '승급 제안') and rg in GR else qg
        final.append({'rid': rid, 'qa': qg, 'challenge': ch, 'final': fg, 'rep': g.get('representative_node', ''), 'evidence': g.get('evidence', ''), 'gap': g.get('gap', ''), 'bl': g.get('proposed_backlog') or '-', 'counter': a.get('counter_evidence', '')})
    json.dump(final, open(os.path.join(work, 'final_grades.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print(f'[finalize] {unit}: 최종등급', dict(Counter(f['final'] for f in final)))


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description='요구사항 커버리지 검토 결정론 보조 스크립트')
    ap.add_argument('cmd', choices=['prep', 'inject', 'qa-input', 'finalize'])
    ap.add_argument('--unit', required=True)
    a = ap.parse_args()
    {'prep': cmd_prep, 'inject': cmd_inject, 'qa-input': cmd_qa_input, 'finalize': cmd_finalize}[a.cmd](a.unit)
