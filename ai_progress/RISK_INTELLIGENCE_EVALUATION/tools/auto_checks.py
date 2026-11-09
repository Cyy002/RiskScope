"""Deterministic (judge-free) checks against each case's rubric: required numbers present in the USER-VISIBLE reply / in the model's RAW reply,
forbidden phrases, M7 state. Output is evidence for scoring, not the score itself."""
import json, sys, glob, os
run = sys.argv[1]; cases = sys.argv[2] if len(sys.argv) > 2 else 'BENCHMARK_CASES/dev'
rows = []
for f in sorted(glob.glob(os.path.join(run, '*.result.json'))):
    r = json.load(open(f)); c = json.load(open(os.path.join(cases, r['id'] + '.json'))); rub = c['rubric']
    t = r['turns'][-1]; vis = t.get('reply') or ''; raw = t.get('raw_model_reply') or ''
    req = rub.get('required_numbers', [])
    rows.append({'id': r['id'], 'model': r['model'], 'llm_state': t.get('llm_state'), 'elapsed_s': t.get('elapsed_s'),
                 'required_numbers': req, 'in_visible_reply': [n for n in req if n in vis], 'in_raw_model_reply': [n for n in req if n in raw],
                 'forbidden_hits_visible': [p for p in rub.get('forbidden_phrases', []) if p in vis],
                 'visible_reply_chars': len(vis), 'm7': t.get('m7_verdict')})
print(json.dumps(rows, ensure_ascii=False, indent=1))
