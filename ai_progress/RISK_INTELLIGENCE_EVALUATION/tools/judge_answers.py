"""Independent rubric judge + deterministic overlay (claude-b). Judge model is NOT the answerer's pipeline; judge sees question, documents,
the case's reference rubric (incl. correct calculations) and ONE answer, blind to which system/model produced it.
Final score per case = judge dims, but CAPPED by deterministic evidence: reasoning<=5 if no derived required number appears in the answer;
any forbidden phrase hit => critical_failure. The judge cannot raise scores above what the deterministic checks allow.
usage: JUDGE_MODEL=qwen3.6:27b python tools/judge_answers.py --kind direct|riskscope --run <dir> --out <file.json> [--cases ...]"""
import argparse, glob, json, os, re, httpx
ap = argparse.ArgumentParser(); ap.add_argument('--kind', required=True); ap.add_argument('--run', required=True); ap.add_argument('--out', required=True); ap.add_argument('--cases', default=os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'BENCHMARK_CASES', 'dev')); ap.add_argument('--only', default='')
a = ap.parse_args(); URL = os.environ.get('OLLAMA_URL', 'http://127.0.0.1:11434'); JM = os.environ.get('JUDGE_MODEL', 'qwen3.6:27b')
DIMS = {'facts': 20, 'reasoning': 20, 'priority': 15, 'options': 15, 'constraints': 10, 'uncertainty': 10, 'traceability': 10}
only = {x for x in a.only.split(',') if x}
def final_text(rec):
    if a.kind == 'direct': return '\n\n'.join('【第%d輪】%s' % (i + 1, t['answer']) for i, t in enumerate(rec['turns']))
    return '\n\n'.join('【第%d輪】%s' % (i + 1, t.get('reply', '')) for i, t in enumerate(rec['turns']))   # what the USER sees
def judge(case, ans):
    rub = case['rubric']; given = '\n'.join(d['title'] + '：' + d['body'] for d in case.get('documents', []))
    q = case.get('question') or '\n'.join('第%d輪：%s' % (i + 1, t) for i, t in enumerate(case.get('turns', [])))
    p = ('你是嚴格的獨立評審。依參考答案(rubric)為下列「回答」評分，只看內容品質，不因長度、術語、排版加分；回答若只是空泛建議、未使用題目資料、未做必要計算，必須給低分。\n'
         f'【問題】{q}\n【專案文件】{given}\n【參考rubric】{json.dumps({k: rub.get(k) for k in ["known_facts","unknowns","hard_constraints","key_risks","risk_links","reasonable_options","forbidden_recommendations","required_calculations","must_not_fabricate","decision_content","critical_errors"]}, ensure_ascii=False)}\n'
         f'【待評回答】\n{ans[:7000]}\n\n'
         '只輸出JSON：{"facts":0-20,"reasoning":0-20,"priority":0-15,"options":0-15,"constraints":0-10,"uncertainty":0-10,"traceability":0-10,"critical_failures":["…"],"justification":"≤80字"}。'
         'facts=事實與依據正確；reasoning=因果與推理深度(含必要計算是否正確)；priority=風險重要性排序；options=方案比較與決策價值；constraints=遵守硬限制；uncertainty=不確定性與資訊缺口；traceability=可追溯到題目資料。')
    r = httpx.post(URL + '/api/generate', json={'model': JM, 'prompt': p, 'stream': False, 'think': False, 'options': {'temperature': 0}}, timeout=420).json()['response']
    m = re.search(r'\{.*\}', r, re.S)
    try: return json.loads(m.group(0)), r
    except Exception: return None, r
res = []
suffix = '.direct.json' if a.kind == 'direct' else '.result.json'
for f in sorted(glob.glob(os.path.join(a.run, '*' + suffix))):
    rec = json.load(open(f)); case = json.load(open(os.path.join(a.cases, rec['id'] + '.json')))
    if only and rec['id'] not in only: continue
    ans = final_text(rec); rub = case['rubric']
    given = case.get('question', '') + ' '.join(case.get('turns') or []) + ' '.join(d['body'] for d in case.get('documents', []))
    req = [n for n in rub.get('required_numbers', []) if not re.search(r'(?<![\d.])' + re.escape(n) + r'(?![\d.])', given)]
    got = [n for n in req if n in ans]; forb = [x for x in rub.get('forbidden_phrases', []) if x in ans]
    try: j, raw = judge(case, ans)
    except Exception as e: j, raw = None, 'judge_error:%s' % type(e).__name__
    row = {'id': rec['id'], 'model': rec.get('model'), 'kind': a.kind, 'required_derived': req, 'derived_found': got, 'forbidden_hits': forb, 'judge_model': JM, 'judge_raw_ok': j is not None}
    if j:
        d = {k: max(0, min(DIMS[k], float(j.get(k, 0)))) for k in DIMS}
        if req and not got: d['reasoning'] = min(d['reasoning'], 5)        # deterministic cap
        row.update({'dims': d, 'total_100': round(sum(d.values()), 1), 'judge_critical': j.get('critical_failures', []), 'critical_failure': bool(forb) or bool(j.get('critical_failures')), 'justification': j.get('justification')})
    print(row['id'], row.get('total_100'), 'derived', len(got), '/', len(req), flush=True); res.append(row)
json.dump(res, open(a.out, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
