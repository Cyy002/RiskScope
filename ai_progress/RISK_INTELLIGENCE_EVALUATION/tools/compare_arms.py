"""Same-case, same-judge comparison table (claude-b). All arms judged by tools/judge_answers.py (judge qwen3.6:27b, blind, deterministic caps). Never mixes the old mechanical scorer."""
import json, glob, os, statistics as st
R = 'runs'
IDS12 = 'BB01,BB02,BB04,BB05,BB06,BB07,BB10,BB11,BB13,BB14,BB16,BB23'.split(','); A5 = 'BB03,BB17,BB20,BB21,BB27'.split(',')
def load(*dirs):
    out = {}
    for d in dirs:
        p = os.path.join(R, d, '_judge.json')
        if not os.path.exists(p): p = os.path.join(R, d, '_judge_subset.json')
        if os.path.exists(p):
            for x in json.load(open(p)): out[x['id']] = x
    return out
arms = {
 '8B': {'A0 old RiskScope': load('_baseline_8b_all30'), 'A1 direct Qwen': load('direct_qwen3-8b'), 'B-v1 LLM-led': load('proto_qwen3-8b'), 'B-v2 +binding': load('protoV2_qwen3-8b')},
 '27B': {'A0 old RiskScope': load('baseline12_qwen3.6-27b', 'claude-b_real_qwen3.6-27b_5cases_v2'), 'A1 direct Qwen': load('direct_qwen3.6-27b'), 'B-v1 LLM-led': load('proto_qwen3.6-27b'), 'B-v2 +binding': load('protoV2_qwen3.6-27b')},
}
res = {}
for m, a in arms.items():
    ids = [i for i in IDS12 if all(i in v for v in a.values())]
    print(f'\n### {m}: common cases ({len(ids)}): {",".join(ids)}')
    print('| arm | mean /100 | cases ≥80 | derived answers found | judge-listed critical failures (cases) | judged-by-27B self-bias |')
    print('|---|---|---|---|---|---|')
    for name, d in a.items():
        xs = [d[i] for i in ids if d[i].get('total_100') is not None]
        if not xs: print(f'| {name} | n/a | | | | |'); continue
        dv = sum(len(x['derived_found']) for x in xs); rq = sum(len(x['required_derived']) for x in xs)
        cf = sum(1 for x in xs if x.get('judge_critical'))
        print(f"| {name} | {st.mean(x['total_100'] for x in xs):.1f} | {sum(x['total_100']>=80 for x in xs)}/{len(xs)} | {dv}/{rq} | {cf}/{len(xs)} | {'yes' if m=='27B' else 'no (judge is a different, larger model)'} |")
        res[(m, name)] = {i: d[i]['total_100'] for i in ids}
json.dump({f'{k[0]}|{k[1]}': v for k, v in res.items()}, open('COMPARISON_PER_CASE.json', 'w'), ensure_ascii=False, indent=1)
# per-case table for 27B and 8B
for m in ('8B', '27B'):
    names = list(arms[m]); ids = [i for i in IDS12 if all(i in v for v in arms[m].values())]
    print(f'\nper-case {m}: ' + ' | '.join(names)); 
    for i in ids: print(i, [arms[m][n][i].get('total_100') for n in names])
