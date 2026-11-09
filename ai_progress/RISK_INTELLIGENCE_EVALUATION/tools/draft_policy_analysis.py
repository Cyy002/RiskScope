"""Offline policy simulation (claude-b): how often would a WHOLE-DRAFT-REJECT policy discard an analysis, versus a PER-ITEM policy that drops only the
failing calculation/statement? Replays saved prototype outputs (raw_model_json) through app/binding + app/ledger. Not the app's exact schema -- it
measures the policy on real model content. usage: python tools/draft_policy_analysis.py <run_dir> [judge.json]"""
import glob, json, os, re, sys, collections
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))); sys.dont_write_bytecode = True
from app.ledger import build_ledger, extract_quantities
from app.binding import verify_calculation
run = sys.argv[1]; judge = {}
if len(sys.argv) > 2 and os.path.exists(sys.argv[2]): judge = {x['id']: x for x in json.load(open(sys.argv[2]))}
cases = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'BENCHMARK_CASES', 'dev')
OK = 'INPUTS_BOUND_AND_ARITHMETIC_CHECKED'
rows = []; reasons_all = collections.Counter()
for f in sorted(glob.glob(os.path.join(run, '*.result.json'))):
    r = json.load(open(f)); c = json.load(open(os.path.join(cases, r['id'] + '.json')))
    docs = [{'id': d['id'], 'body': d['body'], 'version': 1} for d in c.get('documents', [])]; msgs = []
    for t, u in zip(r['turns'], (c.get('turns') or [c['question']])):
        msgs.append(u); L = build_ledger(list(msgs), docs)
        try: js = json.loads(t.get('raw_model_json') or '{}')
        except Exception: continue
        if not js: continue
        trusted = []; calc_bad = []; calc_ok = 0
        for k in js.get('calculations') or []:
            if k.get('kind') == 'critical_path':
                probe = verify_calculation({'formula': '0', 'inputs': {str(x.get('id')): x.get('duration') for x in k.get('tasks', [])}}, L)
                good = probe['status'] != 'REJECTED_BINDING' and probe['levels']['presence']
                (calc_bad.append(('critical_path:' + probe['status'])) if not good else None); calc_ok += good; continue
            v = verify_calculation(k, L)
            if v['status'] == OK: calc_ok += 1; trusted.append(v['value'])
            else: calc_bad.append(v['status'])
        items = []   # (section, text) statements carrying numbers
        for sec, key in (('fact', 'known_facts'), ('constraint', 'hard_constraints'), ('risk', 'risks'), ('option', 'options'), ('action', 'recommended_actions')):
            for it in js.get(key) or []:
                txt = it if isinstance(it, str) else json.dumps(it, ensure_ascii=False); items.append((sec, txt))
        bad_items = 0
        for sec, txt in items:
            for q in extract_quantities(txt, 'model'):
                ok = bool(L.grounds(q['value'], q['unit'])) or any(abs(float(q['canonical']) - float(x)) < 1e-6 * max(1, abs(float(x))) for x in trusted)
                if not ok: bad_items += 1; break
        W_reject = bool(calc_bad) or bad_items > 0
        why = [f'calc:{s}' for s in calc_bad] + ([f'ungrounded_text_numbers:{bad_items}'] if bad_items else [])
        for w in set(x.split(':')[0] + ':' + x.split(':')[1] if x.startswith('calc') else 'ungrounded_text_numbers' for x in why): reasons_all[w] += 1
        total_items = len(items) + len(js.get('unknowns') or []) + len(js.get('calculations') or [])
        kept_P = total_items - bad_items - len(calc_bad)
        rows.append({'id': r['id'], 'W_reject': W_reject, 'why': why, 'items_total': total_items, 'items_kept_under_P': kept_P, 'retained_fraction_P': round(kept_P / max(total_items, 1), 2),
                     'judge': (judge.get(r['id']) or {}).get('total_100')})
n = len(rows); rej = [x for x in rows if x['W_reject']]; acc = [x for x in rows if not x['W_reject']]
mean = lambda xs: round(sum(xs) / len(xs), 1) if xs else None
out = {'run': run, 'turns': n, 'whole_draft_rejected': len(rej), 'whole_draft_reject_rate': round(len(rej) / max(n, 1), 3),
       'reject_reasons': dict(reasons_all), 'mean_retainable_fraction_if_rejected_under_per_item': mean([x['retained_fraction_P'] for x in rej]),
       'judge_mean_of_whole_draft_rejected': mean([x['judge'] for x in rej if x['judge'] is not None]), 'judge_mean_of_whole_draft_accepted': mean([x['judge'] for x in acc if x['judge'] is not None]),
       'rejected_cases': [(x['id'], x['judge'], x['retained_fraction_P']) for x in rej]}
print(json.dumps(out, ensure_ascii=False, indent=1))
