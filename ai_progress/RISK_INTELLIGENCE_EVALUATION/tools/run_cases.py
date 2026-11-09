"""Isolated benchmark runner (owner: claude-b). Runs benchmark case JSONs through the REAL chat_turn()
pipeline (retrieval -> engineering/generic synthesis -> optional real Ollama -> M7) against a throwaway
SQLite DB per case. Never touches production data. Rubrics are NOT passed to the agent.

usage: python tools/run_cases.py --cases BENCHMARK_CASES/dev --out runs/NAME [--app-root <dir containing app/>] [--llm] [--only ID,ID]
  --llm needs OLLAMA_URL/OLLAMA_MODEL env (e.g. http://127.0.0.1:11434, qwen3:8b). Without --llm the deterministic
  path only runs and the output is labelled NOT-CALLED (never to be reported as a real-LLM result).
"""
import argparse, glob, hashlib, json, os, sys, tempfile, time
from pathlib import Path

ap = argparse.ArgumentParser()
ap.add_argument('--cases', required=True); ap.add_argument('--out', required=True)
ap.add_argument('--app-root', default=str(Path(__file__).resolve().parents[3]))
ap.add_argument('--llm', action='store_true'); ap.add_argument('--only', default='')
a = ap.parse_args()
sys.path.insert(0, a.app_root); sys.dont_write_bytecode = True
tmp = tempfile.mkdtemp(prefix='rs-bench-')
os.environ['AGENT_DB_PATH'] = os.path.join(tmp, 'x.sqlite3'); os.environ['AGENT_CREDENTIALS_PATH'] = os.path.join(tmp, 'x.json')
if not a.llm: os.environ['OLLAMA_URL'] = ''
from app import config, db            # noqa: E402
from app import chat as _chat          # noqa: E402
from app.chat import chat_turn         # noqa: E402
# Evaluation instrument only: record the model's RAW reply and M7's verdict (behaviour unchanged) so a
# rejected reply can still be inspected for what the model actually reasoned.
_RAW = {}
_orig_trust = _chat._reply_is_trustworthy
def _spy(text, *args, **kw):
    ok, reason = _orig_trust(text, *args, **kw)
    _RAW['text'], _RAW['m7_ok'], _RAW['m7_reason'] = text, ok, reason
    return ok, reason
_chat._reply_is_trustworthy = _spy
# Evaluation instrument #2 (2026-11-04): record EVERY model call the app makes (full prompt, raw response, diagnostic) so the app's input/context can be compared with the direct-Qwen prompt.
_CALLS = []
_orig_call = _chat.call_ollama
def _spy_call(prompt, *args, **kw):
    t0 = time.time(); text, diag = _orig_call(prompt, *args, **kw)
    _CALLS.append({'prompt': prompt, 'response': text, 'diag': diag, 'elapsed_s': round(time.time() - t0, 1)}); return text, diag
_chat.call_ollama = _spy_call

app_hash = hashlib.sha256(b''.join(p.read_bytes() for p in sorted(Path(a.app_root, 'app').glob('*.py')))).hexdigest()[:16]
out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
only = {x for x in a.only.split(',') if x}

def llm_state(r):
    s = r.get('llm_diagnostic', {}).get('reply', {}).get('status')
    if r.get('reply_source') == 'llm_phrased': return 'ACCEPTED'
    return 'M7-REJECTED' if s == 'rejected_inconsistent' else 'NOT-CALLED/FAILED(%s)' % s

def build_project(conn, case):
    pid = 'case-' + case['id'].lower()
    with db.transaction(conn):
        conn.execute('INSERT INTO projects VALUES (?,?,1)', (pid, case.get('domain', 'case')))
        conn.executemany('INSERT INTO project_members VALUES (?,?,?,1)', [('manager', pid, 'manager'), ('engineer', pid, 'editor')])
        for d in case.get('documents', []):
            db.add_doc(conn, d['id'], pid, d['title'], d.get('category', '專案'), '【模擬文件】' + d['body'],
                       allowed=tuple(d.get('allowed', ('manager', 'engineer'))), classification=d.get('classification', 'synthetic'))
        for k, v in (case.get('signals') or {}).items():
            conn.execute('INSERT INTO project_signals VALUES (?,?,?,NULL)', (pid, k, str(v)))
    return pid

files = sorted(glob.glob(os.path.join(a.cases, '*.json')))
summary = []
for f in files:
    case = json.load(open(f, encoding='utf-8'))
    if only and case['id'] not in only: continue
    path = os.path.join(tmp, case['id'] + '.sqlite3')
    conn = db.init_db(path=path, credentials_path=os.path.join(tmp, case['id'] + '.json')); 
    pid = build_project(conn, case)
    turns = case.get('turns') or [case['question']]
    rec = {'id': case['id'], 'domain': case.get('domain'), 'app_hash': app_hash, 'model': config.OLLAMA_MODEL if a.llm else None,
           'llm_enabled': a.llm, 'turns': []}
    for i, msg in enumerate(turns):
        t0 = time.time(); _RAW.clear(); _CALLS.clear()
        try:
            r = chat_turn(conn, 'engineer', pid, msg, 'bench-' + case['id'], focus=case.get('focus', 'custom'), use_local_llm=a.llm)
            rec['turns'].append({'user': msg, 'elapsed_s': round(time.time() - t0, 1), 'llm_state': llm_state(r) if a.llm else 'NOT-CALLED(no --llm)',
                                 'llm_calls': list(_CALLS), 'raw_model_reply': _RAW.get('text'), 'm7_verdict': {'accepted': _RAW.get('m7_ok'), 'reason': _RAW.get('m7_reason')} if _RAW else None,
                                 'reply': r['reply'], 'reply_source': r['reply_source'], 'llm_diagnostic': r.get('llm_diagnostic'),
                                 'facts': r.get('facts'), 'unknowns': r.get('unknowns'), 'risks': r.get('risks'), 'options': r.get('options'),
                                 'checks': r.get('checks'), 'impacts': r.get('impacts'), 'sources': [s.get('id') for s in r.get('sources', [])],
                                 'questions_to_manager': r.get('questions_to_manager')})
        except Exception as e:
            rec['turns'].append({'user': msg, 'error': '%s: %s' % (type(e).__name__, e)})
    json.dump(rec, open(out / (case['id'] + '.result.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    summary.append((case['id'], [t.get('llm_state', 'ERROR') for t in rec['turns']]))
    print(case['id'], summary[-1][1], flush=True)
    conn.close()
json.dump({'app_hash': app_hash, 'llm': a.llm, 'model': config.OLLAMA_MODEL if a.llm else None, 'cases': summary}, open(out / '_run.json', 'w'), indent=1)
