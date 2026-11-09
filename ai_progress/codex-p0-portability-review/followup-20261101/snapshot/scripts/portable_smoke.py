"""Real-Agent smoke test, run INSIDE the container (stdlib only, so no host
Python is needed on Windows/Linux/macOS):  podman exec <ctr> python scripts/portable_smoke.py
Passes only if a real LLM call succeeded (reply_source == llm_phrased and
llm_diagnostic.reply.status == success) -- a deterministic fallback is a FAIL
unless SMOKE_ALLOW_FALLBACK=1 (then it is reported as NO-LLM, never as PASS)."""
import json, os, sys, time, urllib.request, urllib.error
BASE = 'http://127.0.0.1:8000'
CRED = os.getenv('AGENT_CREDENTIALS_PATH', '/app/runtime/demo_credentials.json')
fails = []
def check(name, ok, detail=''):
    print(('PASS ' if ok else 'FAIL ') + name, detail)
    if not ok: fails.append(name)
def call(path, token=None, body=None, timeout=300):
    h = {'Content-Type': 'application/json'}
    if token: h['Authorization'] = 'Bearer ' + token
    req = urllib.request.Request(BASE + path, data=json.dumps(body).encode() if body is not None else None, headers=h)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r: return r.status, json.load(r)
    except urllib.error.HTTPError as e: return e.code, None
tok = json.load(open(CRED))
check('health', call('/health')[0] == 200)
check('no-token rejected', call('/api/me')[0] in (401, 403))
st, me = call('/api/me', tok['engineer'])
check('engineer login', st == 200 and me['projects'], str(me and me['user']))
pid = me['projects'][0]['id']
check('outsider has no project access', call(f'/api/projects/{pid}/overview', tok['outsider'])[0] in (401, 403))
st, r = call(f'/api/projects/{pid}/chat', tok['engineer'], {
    'message': '電源24V，名目額定10A，實際可用8A，馬達電流11A，輔助負載3A，持續電流夠嗎？',
    'session_id': 'portable-smoke-%d' % time.time(), 'use_local_llm': True})
check('chat 200', st == 200)
tot = [c.get('numbers', {}).get('total_current_a') for c in (r or {}).get('checks', []) if c.get('rule') == 'continuous_power']
check('deterministic engine: total current 14A (11A motor + 3A aux)', tot == ['14'], 'got %s' % tot)
diag = (r or {}).get('llm_diagnostic', {})
llm_ok = (r or {}).get('reply_source') == 'llm_phrased' and diag.get('reply', {}).get('status') == 'success'
if llm_ok: check('REAL LLM reply (not fallback)', True, str(diag))
elif os.getenv('SMOKE_ALLOW_FALLBACK') == '1': print('NO-LLM: deterministic fallback only, model NOT verified', diag)
else: check('REAL LLM reply (not fallback)', False, str(diag))
print('RESULT:', 'PASS' if not fails else 'FAIL', fails)
sys.exit(1 if fails else 0)
