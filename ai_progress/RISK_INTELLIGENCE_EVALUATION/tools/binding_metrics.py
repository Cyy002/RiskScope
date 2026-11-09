"""Offline (no model) replay of saved prototype outputs through app/binding.py -> binding error metrics. usage: python tools/binding_metrics.py <proto_run_dir> [--json out]
Measures what the v1 prototype stamped '工具驗算' versus what the stricter verifier would accept: wrong/ambiguous binding rate, assumed-input rate,
arithmetic-failure rate (incl. the BB07 eager-pow bug), and the 'false verified' rate = v1-stamped calculations that the new verifier REJECTS."""
import glob, json, os, sys, collections
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))); sys.dont_write_bytecode = True
from app.ledger import build_ledger
from app.binding import verify_calculation
run = sys.argv[1]; cases = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'BENCHMARK_CASES', 'dev')
rows, cnt = [], collections.Counter()
for f in sorted(glob.glob(os.path.join(run, '*.result.json'))):
    r = json.load(open(f)); c = json.load(open(os.path.join(cases, r['id'] + '.json')))
    docs = [{'id': d['id'], 'body': d['body'], 'version': 1} for d in c.get('documents', [])]; msgs = []
    for t, u in zip(r['turns'], (c.get('turns') or [c['question']])):
        msgs.append(u); L = build_ledger(list(msgs), docs)
        try: js = json.loads(t.get('raw_model_json') or '{}')
        except Exception: continue
        old_errs = {x.get('name'): x for x in (t.get('verification') or {}).get('calc', [])}
        for calc in js.get('calculations') or []:
            v = verify_calculation(calc, L); old = old_errs.get(calc.get('name'), {})
            v1_stamped = 'error' not in old
            cnt['calcs'] += 1; cnt['v1_stamped'] += v1_stamped; cnt['v1_arith_error'] += (not v1_stamped)
            cnt['new_' + v['status']] += 1
            cnt['false_verified'] += (v1_stamped and v['status'] == 'REJECTED_BINDING')
            rows.append({'case': r['id'], 'name': calc.get('name'), 'v1_stamped': v1_stamped, 'new_status': v['status'], 'issues': v['issues'][:3]})
n = max(cnt['calcs'], 1)
summary = {'run': run, 'calculations': cnt['calcs'], 'v1_stamped_verified': cnt['v1_stamped'], 'v1_arithmetic_errors(eager-pow bug etc.)': cnt['v1_arith_error'],
           'new_status_counts': {k[4:]: v for k, v in cnt.items() if k.startswith('new_')},
           'wrong_or_ambiguous_binding_rate': round(cnt['new_REJECTED_BINDING'] / n, 3), 'assumed_input_rate': round(cnt['new_UNVERIFIED_ASSUMED_INPUT'] / n, 3),
           'false_verified_rate_of_v1_stamps': round(cnt['false_verified'] / max(cnt['v1_stamped'], 1), 3)}
print(json.dumps(summary, ensure_ascii=False, indent=1))
if '--json' in sys.argv: json.dump({'summary': summary, 'rows': rows}, open(sys.argv[sys.argv.index('--json') + 1], 'w'), ensure_ascii=False, indent=1)
