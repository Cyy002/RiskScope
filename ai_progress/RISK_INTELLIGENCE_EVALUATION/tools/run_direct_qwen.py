"""CONTROL experiment (claude-b): ask the bare local Qwen the same case WITHOUT RiskScope (no scaffold, no M7, no extractor).
Same inputs as run_cases.py (question/turns + case documents), neutral consultant prompt, no rubric, no hints.
usage: OLLAMA_MODEL=qwen3:8b python tools/run_direct_qwen.py --cases BENCHMARK_CASES/dev --out runs/direct_qwen3-8b --only BB01,...
Records raw answers; scoring is done separately (deterministic checks + independent judge) -- never self-assessed by the answerer."""
import argparse, glob, json, os, time, httpx
ap = argparse.ArgumentParser(); ap.add_argument('--cases', required=True); ap.add_argument('--out', required=True); ap.add_argument('--only', default='')
a = ap.parse_args()
URL = os.environ.get('OLLAMA_URL', 'http://127.0.0.1:11434'); MODEL = os.environ['OLLAMA_MODEL']
os.makedirs(a.out, exist_ok=True); only = {x for x in a.only.split(',') if x}
SYS = ('你是資深的跨領域專案風險分析顧問。請根據使用者提供的專案文件（模擬資料）與問題，做出有決策價值的風險評估：'
       '釐清核心問題、已知事實與未知、硬性限制與衝突、關鍵風險與成因、可行與不可行方案及其代價、需要時做必要計算並寫出算式，'
       '資料不足時明說缺什麼，不要編造文件中沒有的數據。請用繁體中文，條理清楚。')
for f in sorted(glob.glob(os.path.join(a.cases, '*.json'))):
    c = json.load(open(f, encoding='utf-8'))
    if only and c['id'] not in only: continue
    docs = '\n'.join('[文件 %s｜%s]\n%s' % (d['id'], d['title'], d['body']) for d in c.get('documents', []))
    turns = c.get('turns') or [c['question']]
    hist, outs = '', []
    for u in turns:
        prompt = SYS + '\n\n=== 專案文件 ===\n' + docs + '\n\n' + hist + '=== 使用者問題 ===\n' + u
        t0 = time.time()
        try:
            r = httpx.post(URL + '/api/generate', json={'model': MODEL, 'prompt': prompt, 'stream': False, 'think': False, 'keep_alive': '10m', 'options': {'num_predict': 4000}}, timeout=420)
            ans, st = r.json().get('response', ''), 'success'
        except Exception as e:
            ans, st = '', 'error:%s' % type(e).__name__
        outs.append({'user': u, 'answer': ans, 'status': st, 'elapsed_s': round(time.time() - t0, 1)})
        hist += '=== 使用者問題 ===\n' + u + '\n=== 顧問回覆 ===\n' + ans + '\n\n'
    json.dump({'id': c['id'], 'model': MODEL, 'mode': 'DIRECT_QWEN_NO_RISKSCOPE', 'turns': outs}, open(os.path.join(a.out, c['id'] + '.direct.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print(c['id'], [o['status'] for o in outs], [o['elapsed_s'] for o in outs], flush=True)
