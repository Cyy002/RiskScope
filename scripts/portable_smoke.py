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
ATTEMPTS = int(os.getenv('SMOKE_ATTEMPTS', '3'))   # small models are non-deterministic; M7 may legitimately reject one reply
outcomes, r, st = [], None, None
for i in range(ATTEMPTS):
    st, r = call(f'/api/projects/{pid}/chat', tok['engineer'], {
        'message': '電源24V，名目額定10A，實際可用8A，馬達電流11A，輔助負載3A，持續電流夠嗎？',
        'session_id': 'portable-smoke-%d-%d' % (time.time(), i), 'use_local_llm': True})
    tot = [c.get('numbers', {}).get('total_current_a') for c in (r or {}).get('checks', []) if c.get('rule') == 'continuous_power']
    d = (r or {}).get('llm_diagnostic', {})
    acc = (r or {}).get('reply_source') == 'llm_phrased' and d.get('reply', {}).get('status') == 'success'
    outcomes.append({'attempt': i + 1, 'total_current': tot, 'llm_accepted_by_M7': acc, 'reply_status': d.get('reply', {}).get('status')})
    if tot != ['14']: break           # structured wrongness is never retried away
    if acc: break
check('chat 200', st == 200)
check('deterministic engine: total current 14A (11A motor + 3A aux) on every attempt', all(o['total_current'] == ['14'] for o in outcomes), str(outcomes))
diag = (r or {}).get('llm_diagnostic', {})
llm_ok = any(o['llm_accepted_by_M7'] for o in outcomes)
print('LLM attempts (accepted/total): %d/%d' % (sum(o['llm_accepted_by_M7'] for o in outcomes), len(outcomes)))
real_llm_pass = False
if llm_ok:
    check('REAL LLM reply (not fallback)', True, str(diag)); real_llm_pass = True
elif os.getenv('SMOKE_ALLOW_FALLBACK') == '1':
    print('NO-LLM: deterministic fallback only, model NOT verified', diag)
else:
    check('REAL LLM reply (not fallback)', False, str(diag))
deterministic_pass = not [f for f in fails if not f.startswith('REAL LLM')]
print('deterministic_pass=%s real_llm_pass=%s' % (deterministic_pass, real_llm_pass))
if fails:
    print('RESULT: FAIL', fails); sys.exit(1)
if not real_llm_pass:
    print('RESULT: DETERMINISTIC-ONLY (NOT a real-Agent PASS; no LLM verified)'); sys.exit(2)
print('RESULT: PASS (deterministic + real LLM)')
