"""Capture REAL failure-case traces (input -> agent steps -> tool return -> error handling -> final result)
against an isolated temp DB via TestClient. No model, no production service, no real tokens printed.
Run: .venv/bin/python scripts/capture_failure_cases.py > ai_progress/ASSIGNMENT2/failure_traces.json"""
import json, tempfile, pathlib, sys
sys.path.insert(0, '.')
from app import db, chat
from fastapi.testclient import TestClient
from app.api import app
ROOT = '/api/projects/demo-chamber'
tmp = pathlib.Path(tempfile.mkdtemp())
db.DB_PATH = tmp / 'db.sqlite3'; db.CREDENTIALS_PATH = tmp / 'tokens.json'
out = {}
def short(r):
    try: j = r.json()
    except Exception: j = r.text[:200]
    return {'http_status': r.status_code, 'body': j}
with TestClient(app) as c:
    tk = json.loads((tmp / 'tokens.json').read_text())
    H = lambda n: {'Authorization': 'Bearer ' + tk[n]}
    # F1: unauthorized access (no project membership) + ACL-restricted document
    out['F1_unauthorized_and_acl'] = {
        'input': 'outsider GET /overview; engineer GET /documents (DOC-CONF is manager-only)',
        'steps': [{'step': 'outsider overview', **short(c.get(ROOT + '/overview', headers=H('outsider')))},
                  {'step': 'no token', **short(c.get(ROOT + '/overview'))},
                  {'step': 'engineer lists documents', 'doc_ids_visible': [d['id'] for d in c.get(ROOT + '/documents', headers=H('engineer')).json()['documents']]},
                  {'step': 'manager lists documents', 'doc_ids_visible': [d['id'] for d in c.get(ROOT + '/documents', headers=H('manager')).json()['documents']]},
                  {'step': 'engineer context search leaks confidential?', 'leaked': '合成敏感資料' in c.get(ROOT + '/context', params={'q': '成本'}, headers=H('engineer')).text}]}
    # F3: write action without human approval -> denied/blocked, state unchanged
    a = c.post(ROOT + '/analyze', headers=H('engineer'), json={'question': '能否調整驗證工作？'}).json()
    act = c.post(ROOT + '/actions', headers=H('engineer'), json={'analysis_id': a['analysis_id'], 'task_id': 'TEST-01', 'new_state': 'blocked', 'idempotency_key': 'demo-f3'}).json()
    ex_eng = c.post(ROOT + '/actions/' + act['action_id'] + '/execute', headers=H('engineer'))
    ex_mgr = c.post(ROOT + '/actions/' + act['action_id'] + '/execute', headers=H('manager'))
    state = next(t['state'] for t in c.get(ROOT + '/overview', headers=H('manager')).json()['tasks'] if t['task_id'] == 'TEST-01')
    out['F3_execute_without_approval'] = {'input': 'engineer requests TEST-01 -> blocked, then tries to execute before any approval',
        'agent_analysis': {'decision_status': a['decision_status'], 'checks': [k['status'] for k in a['checks']]},
        'action_created': {'state': act['state']}, 'engineer_execute': short(ex_eng), 'manager_execute_before_approval': short(ex_mgr),
        'task_state_after': state, 'handling': 'RBAC forbids engineer execute (403); even manager gets 409 until human approval; task state stays planned'}
    # F4: agent failure -- model (mocked) falsely claims approval; M7 blocks it, user sees deterministic text
    orig = chat.call_ollama
    chat.call_ollama = lambda prompt, **kw: ('本採購已核准，請直接執行，風險為零。', {'status': 'success'})
    r4 = c.post(ROOT + '/chat', headers=H('engineer'), json={'message': '請問這筆 200 萬元採購可以核准嗎？預算只剩 150 萬。', 'session_id': 'demo-f4', 'use_local_llm': True, 'focus': 'supplier'}).json()
    chat.call_ollama = orig
    out['F4_agent_false_approval_claim_blocked'] = {'input': 'question about 200萬 purchase with 150萬 budget; model output is mocked to falsely say 已核准',
        'model_raw_output': '本採購已核准，請直接執行，風險為零。', 'm7_verdict_reason': r4['llm_diagnostic']['reply'],
        'reply_source': r4['reply_source'], 'user_saw_contains_approved_claim': '已核准' in r4['reply'] and '不代表最終核准' not in r4['reply'],
        'user_saw_head': r4['reply'][:160], 'handling': 'unverifiable approval claim rejected; deterministic text shown, states it is not a final approval'}
    # F2: tool error: invalid unit; agent fails closed when data corrupted
    r = c.patch(ROOT + '/facts/motor_continuous_current', headers=H('manager'), json={'value': '8', 'unit': 'V', 'evidence_version': 1})
    conn = db.connect(); conn.execute('UPDATE facts SET unit=? WHERE fact_key=?', ('V', 'motor_continuous_current')); conn.close()
    chk = c.get(ROOT + '/check', headers=H('manager')).json()
    out['F2_tool_error_unit_mismatch'] = {'input': 'PATCH motor_continuous_current value=8 unit=V (should be A)',
        'tool_response': short(r), 'after_db_corruption_check_tool': {'status': chk['status'], 'reason': chk['reason']},
        'handling': 'input rejected 422; if stored data is corrupted the engineering tool returns status=unknown (fails closed), never a pass'}
print(json.dumps(out, ensure_ascii=False, indent=2))
