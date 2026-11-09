"""Reproducible strict scoring + root-cause tagging for a run directory (owner: claude-b).
Judge-free parts are computed from the saved evidence only; anything that would need semantic judgement of a NON-template reply is
returned as manual_review=True with no invented score (honest: currently every observed reply is the fixed scaffold).
usage: python tools/score_run.py <run_dir> [--cases BENCHMARK_CASES/dev] > scores.json
Dimensions (100): facts 20, reasoning 20, priority 15, options 15, constraints 10, uncertainty 10, traceability 10."""
import json, glob, os, re, sys
run = sys.argv[1]; cases = 'BENCHMARK_CASES/dev'
if '--cases' in sys.argv: cases = sys.argv[sys.argv.index('--cases') + 1]
TEMPLATE_RISK = 'R-UNVALIDATED-ANALYSIS'
nums = lambda s: set(re.findall(r'\d+(?:\.\d+)?', s))
def is_template(t):
    risks = t.get('risks') or []; opts = t.get('options') or []
    return (bool(risks) and all(r.get('id') == TEMPLATE_RISK for r in risks) and
            {o.get('id') for o in opts} <= {'G-A', 'G-B', 'G-C'} and not (t.get('facts') and any('專案訊號' not in f.get('claim', '') for f in t['facts'])))
out = []
for f in sorted(glob.glob(os.path.join(run, '*.result.json'))):
    r = json.load(open(f)); c = json.load(open(os.path.join(cases, r['id'] + '.json'))); rub = c['rubric']
    turns = r['turns']; t = turns[-1]; vis = t.get('reply') or ''; raw = t.get('raw_model_reply') or ''
    tmpl = all(is_template(x) for x in turns if 'error' not in x)
    given = ' '.join([c.get('question', '')] + (c.get('turns') or []) + [d['body'] for d in c.get('documents', [])])
    # a required number that is merely an INPUT echoed from the user's own text is not evidence of a derived result
    req = [n for n in rub.get('required_numbers', []) if not re.search(r'(?<![\d.])' + re.escape(n) + r'(?![\d.])', given)]
    got = [n for n in req if n in vis]
    kf = set().union(*[nums(k) for k in rub.get('known_facts', [])]) if rub.get('known_facts') else set()
    echo = len([n for n in kf if n in nums(vis)]) / len(kf) if kf else 0
    forb = [p for p in rub.get('forbidden_phrases', []) if p in vis]
    states = [x.get('llm_state') for x in turns]
    reasons = [(x.get('m7_verdict') or {}).get('reason') or '' for x in turns]
    tags = []
    if tmpl: tags += ['generic advice / fixed 3-option scaffold', 'reasoning too shallow', 'cannot compare options', 'risk ranking absent']
    if req and not got: tags.append('numeric derivation absent (required answer not produced)')
    if any(('工期、天數或金額' in x or '百分比' in x) for x in reasons):
        user_nums = nums(c.get('question', '') + ' '.join(c.get('turns') or []) + ' '.join(d['body'] for d in c.get('documents', [])))
        if any(n in user_nums for rs in reasons for n in re.findall(r'（(\d+(?:\.\d+)?)', rs)): tags.append('M7 over-rejection (user-supplied number rejected)')
        else: tags.append('M7 rejected an ungrounded number (legit or unclear)')
    if len(turns) > 1 and len({x.get('reply') for x in turns}) == 1: tags.append('multi-turn context not reflected (identical replies)')
    if any('已記錄您這一輪提供的數值' in (x.get('reply') or '') for x in turns) and 'continuous' not in c.get('domain', ''):
        tags.append('extraction role confusion (values filed into motor/power fields)')
    if re.search(r'矛盾|不一致|較新|更新', ' '.join(rub.get('key_risks', []) + rub.get('known_facts', []))) and not re.search(r'矛盾|不一致', vis): tags.append('contradiction undetected')
    if rub.get('hard_constraints') and tmpl: tags.append('hard constraints not engaged')
    if not rub.get('required_calculations') is None and rub.get('required_calculations') and not got: tags.append('professional-knowledge/calculation not applied')
    if tmpl:
        d = {'facts': round(min(5, 20 * echo), 1), 'reasoning': round(20 * len(got) / len(req), 1) if req else 0, 'priority': 0, 'options': 0,
             'constraints': 0 if rub.get('hard_constraints') else 2, 'uncertainty': 3 if ('尚未' in vis or '未知' in vis or '缺少' in vis) else 0, 'traceability': 1 if t.get('sources') else 0}
        total, manual = round(sum(d.values()), 1), False
    else:
        d, total, manual = None, None, True
    out.append({'id': r['id'], 'domain': r['domain'], 'model': r['model'], 'turn_states': states, 'template_only': tmpl, 'manual_review': manual,
                'dims': d, 'total_100': total, 'required_numbers_found': f'{len(got)}/{len(req)}', 'forbidden_hits': forb, 'root_cause_tags': tags,
                'critical_failure': bool(forb)})
print(json.dumps(out, ensure_ascii=False, indent=1))
