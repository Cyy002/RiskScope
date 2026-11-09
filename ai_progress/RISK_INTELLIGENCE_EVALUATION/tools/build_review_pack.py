"""Builds per-case human review packs (original question, documents, reference conclusion/calculations from the case rubric, every arm's ACTUAL answer, judge scores and reasons, checklist).
No judge score is presented without the raw answer next to it. usage: python tools/build_review_pack.py BB01,BB10,..."""
import json, os, sys
ids = sys.argv[1].split(','); out = 'HUMAN_REVIEW'; os.makedirs(out, exist_ok=True)
ARMS = [('Batch J app FINAL 8B r1 (user saw)', 'appFIXED_j_r1_qwen3-8b', 'rs'), ('Batch J app FINAL 8B r2 (user saw)', 'appFIXED_j_r2_qwen3-8b', 'rs'), ('Batch J app FINAL 8B r3 (user saw)', 'appFIXED_j_r3_qwen3-8b', 'rs'), ('Batch J app FINAL 27B (user saw, self-judged)', 'appFIXED_j_r1_qwen3.6-27b', 'rs'), ('NEW app RAW free-form 8B r1 (before safety layer)', 'appNEW_g_r1_qwen3-8b_RAWFREEFORM', 'rs'), ('NEW app FINAL 8B r1 (what the user saw)', 'appNEW_g_r1_qwen3-8b', 'rs'), ('NEW app RAW free-form 27B (before safety layer)', 'appNEW_g_r1_qwen3.6-27b_RAWFREEFORM', 'rs'), ('NEW app FINAL 27B (what the user saw)', 'appNEW_g_r1_qwen3.6-27b', 'rs'), ('A1 direct 8B', 'direct_qwen3-8b', 'direct'), ('A1 direct 27B', 'direct_qwen3.6-27b', 'direct'), ('C direct+audit 8B', 'armC_qwen3-8b', 'rs'), ('D isolation+prompt 8B', 'armD_qwen3-8b', 'rs'), ('D isolation+prompt 27B', 'armD_qwen3.6-27b', 'rs'),
        ('B-v2 structured 8B', 'protoV2_qwen3-8b', 'rs'), ('A0 old RiskScope 8B', '_baseline_8b_all30', 'rs')]
def ans(d, kind, i):
    p = f'runs/{d}/{i}.' + ('direct.json' if kind == 'direct' else 'result.json')
    if not os.path.exists(p): return None
    r = json.load(open(p)); return '\n\n'.join((t.get('answer') if kind == 'direct' else t.get('reply')) or '' for t in r['turns'])
def judge(d, i):
    for n in ('_judge.json', '_judge_subset.json'):
        p = f'runs/{d}/{n}'
        if os.path.exists(p):
            for x in json.load(open(p)):
                if x['id'] == i: return x
for i in ids:
    c = json.load(open(f'BENCHMARK_CASES/dev/{i}.json')); R = c['rubric']
    L = [f"# Human review pack — {i} ({c.get('domain')})", '', '> Purpose: independent HUMAN verification. Judge scores below come from `qwen3.6:27b` (self-bias on 27B answers) and are NOT ground truth. The reference conclusion is the case author\'s (computed in tools/gen_cases_*.py / rubric); challenge it if wrong.', '',
         '## 1. Original question', '', c.get('question') or '\n'.join(f'- turn {k}: {t}' for k, t in enumerate(c.get('turns', []), 1)), '', '## 2. Source documents (simulated)', '']
    for d in c.get('documents', []): L += [f"**[{d['id']}] {d['title']}**", '', '> ' + d['body'].replace('\n', '\n> '), '']
    L += ['## 3. Reference answer (case author)', '', f"- known facts: {R.get('known_facts')}", f"- hard constraints: {R.get('hard_constraints')}", f"- required calculations / correct results: {R.get('required_calculations')}",
          f"- must not fabricate: {R.get('must_not_fabricate')}", f"- forbidden recommendations: {R.get('forbidden_recommendations')}", f"- reasonable options: {R.get('reasonable_options')}", f"- decision content expected: {R.get('decision_content')}", f"- critical errors: {R.get('critical_errors')}", '',
          '## 4. Actual answers and judge results', '']
    for name, d, k in ARMS:
        a = ans(d, k, i); j = judge(d, i)
        L += [f'### {name}', '', (f"judge total **{j['total_100']}** · dims {j['dims']} · derived answers found {j['derived_found']}/{j['required_derived']} · judge-listed critical: {j.get('judge_critical')}\n\njudge reason: {j.get('justification')}" if j else 'judge: not available for this arm/case'), '', '<details><summary>full answer</summary>', '', (a or '(no answer file)'), '', '</details>', '']
    L += ['## 5. Reviewer checklist (fill in)', '', '| check | pass / fail / n.a. | notes |', '|---|---|---|', '| every number in the answer traceable to the documents or to a shown calculation | | |', '| each calculation re-done by hand and correct | | |', '| every hard constraint respected / violation flagged | | |',
          '| conclusion matches the reference (or reviewer\'s own correct conclusion) | | |', '| no invented data presented as fact | | |', '| judge score fair? (reviewer\'s score 0-100) | | |', '']
    open(f'{out}/{i}.md', 'w', encoding='utf-8').write('\n'.join(L))
open(f'{out}/README.md', 'w', encoding='utf-8').write('# Human review packs\nCases: ' + ', '.join(ids) + '\nEach file: question → documents → reference → ALL arms\' actual answers + judge text → checklist. Reviewer notes by claude-b (AI, preliminary, NOT independent) are in `PRELIMINARY_AI_REVIEW.md`; a human must fill the checklists.\n')
print('built', ids)
