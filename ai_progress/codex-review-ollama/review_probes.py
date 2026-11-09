"""Independent, synthetic-only M3/M5 regression probes. Never touches runtime.
Run from project root with .venv/bin/python -B ai_progress/codex-review-ollama/review_probes.py.
All model calls replaced at the HTTP transport; credentials never printed.
"""
from pathlib import Path
import hashlib
import json
import os
import sys
import tempfile
from unittest.mock import patch

PROJECT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT))
_TEMP = tempfile.TemporaryDirectory(prefix='riskscope-independent-ollama-')
TEMP = Path(_TEMP.name)
os.environ['AGENT_DB_PATH'] = str(TEMP / 'agent.sqlite3')
os.environ['AGENT_CREDENTIALS_PATH'] = str(TEMP / 'credentials.json')
os.environ['OLLAMA_URL'] = 'http://127.0.0.1:11434'
os.environ['OLLAMA_MODEL'] = 'qwen3:8b'

import httpx
from fastapi.testclient import TestClient
from app.api import app
from app import db, config
from app.llm_client import call_ollama

ROOT = '/api/projects/demo-chamber'
RESULT = {'isolation': 'AGENT_DB_PATH and AGENT_CREDENTIALS_PATH set to TemporaryDirectory before any app imports; all HTTP post calls mocked',
          'source_hashes': {p: hashlib.sha256((PROJECT / p).read_bytes()).hexdigest() for p in ['app/api.py','app/chat.py','app/engineering.py','app/analyzer.py','app/llm_client.py']}, 'findings': {}}


def resp(body=None, status=200, content=None):
    req = httpx.Request('POST', 'http://127.0.0.1:11434/api/generate')
    return httpx.Response(status, request=req, **({'json': body} if content is None else {'content': content}))


def protected_snapshot():
    with db.connect() as conn:
        return {table: [tuple(r) for r in conn.execute(f'SELECT * FROM {table} ORDER BY rowid')]
                for table in ['facts','documents','document_access','project_members','actions','simulated_tasks']}


with TestClient(app) as c:
    tokens = json.loads((TEMP/'credentials.json').read_text())
    engineer = {'Authorization': 'Bearer '+tokens['engineer']}
    manager = {'Authorization': 'Bearer '+tokens['manager']}
    outsider = {'Authorization': 'Bearer '+tokens['outsider']}
    # No model required to reproduce historical derived-data exposure.
    r = c.post(ROOT+'/chat', headers=engineer, json={'message':'請評估馬達升級','session_id':'history-revoke','use_local_llm':False})
    assert r.status_code == 200
    created = r.json()
    assert created['checks'][0]['numbers']['total_current_a'] == '11'
    assert c.patch(ROOT+'/documents/DOC-PS/access',headers=manager,json={'user_id':'engineer','enabled':False}).status_code == 200
    detail = c.get(ROOT+'/analyses/'+created['analysis_id'],headers=engineer)
    history = c.get(ROOT+'/sessions/history-revoke',headers=engineer)
    text = history.json()['turns'][0]['reply']
    assert detail.status_code == 403 and history.status_code == 200
    assert '264' in text and '11' in text
    RESULT['findings']['history_acl'] = {'analysis_status_after_revocation':detail.status_code,'session_status_after_revocation':history.status_code,'leaked_derived_current':'11A','leaked_derived_power':'264W','reply_source':history.json()['turns'][0]['reply_source']}
    assert c.patch(ROOT+'/documents/DOC-PS/access',headers=manager,json={'user_id':'engineer','enabled':True}).status_code == 200

    # Fault-injected model output, absent from the user's message, reaches calculations.
    assert c.patch(ROOT+'/documents/DOC-MOTOR/access',headers=manager,json={'user_id':'engineer','enabled':False}).status_code == 200
    candidates = {'motor_voltage':{'value':'24','unit':'V'}, 'motor_continuous_current':{'value':'1','unit':'A'}}
    message = '請分析，不要猜測未提供的規格。'
    before = protected_snapshot()
    with patch.object(httpx,'post',side_effect=[resp({'response':json.dumps(candidates)}),resp({'response':'試算完成，仍需人工審核。'})]) as mock:
        extracted = c.post(ROOT+'/chat',headers=engineer,json={'message':message,'session_id':'invented-input','use_local_llm':True}).json()
    assert extracted['user_supplied_accepted_this_turn'] == candidates
    assert extracted['checks'][0]['status'] == 'pass'
    assert protected_snapshot() == before
    RESULT['findings']['ungrounded_numeric_extraction'] = {'user_message':message,'mock_model_candidate':candidates,'accepted':extracted['user_supplied_accepted_this_turn'],'constraint_status':extracted['checks'][0]['status'],'numbers':extracted['checks'][0]['numbers'],'evidence':extracted['checks'][0]['evidence'],'formal_facts_acl_actions_unchanged':True,'decision_status':extracted['decision_status'],'is_actual_model_attack':False}
    assert c.patch(ROOT+'/documents/DOC-MOTOR/access',headers=manager,json={'user_id':'engineer','enabled':True}).status_code == 200

    # The model can contradict already-computed constraints in the primary reply.
    malicious = '已確認總電流 1 A、總功率 24 W，已核准可以立即執行。'
    before = protected_snapshot()
    with patch.object(httpx,'post',side_effect=[resp({'response':'{}'}),resp({'response':malicious})]) as mock:
        contradicted = c.post(ROOT+'/chat',headers=engineer,json={'message':'請評估馬達升級','session_id':'contradictory-prose','use_local_llm':True}).json()
        request_meta = [{'url':call.args[0], 'model':call.kwargs['json']['model'], 'think':call.kwargs['json'].get('think'), 'stream':call.kwargs['json'].get('stream'), 'timeout':call.kwargs['timeout']} for call in mock.call_args_list]
    assert contradicted['reply'] == malicious and contradicted['reply_source'] == 'llm_phrased'
    assert contradicted['checks'][0]['status'] == 'fail'
    assert protected_snapshot() == before
    RESULT['findings']['unvalidated_prose'] = {'mock_model_reply':malicious,'returned_reply':contradicted['reply'],'reply_source':contradicted['reply_source'],'structured_constraint_status':contradicted['checks'][0]['status'],'structured_numbers':contradicted['checks'][0]['numbers'],'decision_status':contradicted['decision_status'],'formal_facts_acl_actions_unchanged':True,'calls':request_meta,'is_actual_model_attack':False}

    # Current ACL is applied before gathering document evidence for model prompts.
    marker = 'SYNTHETIC_PRIVATE_MOTOR_MARKER_671'
    with db.connect() as conn:
        conn.execute('UPDATE documents SET body=? WHERE id=?',(marker, 'DOC-MOTOR'))
    assert c.patch(ROOT+'/documents/DOC-MOTOR/access',headers=manager,json={'user_id':'engineer','enabled':False}).status_code == 200
    with patch.object(httpx,'post',return_value=resp({'response':'僅列出已授權資料，仍缺馬達規格。'})) as mock:
        guarded = c.post(ROOT+'/analyze',headers=engineer,json={'question':marker,'use_local_llm':True}).json()
        prompt = mock.call_args.kwargs['json']['prompt']
    assert guarded['checks'][0]['status'] == 'unknown'
    assert marker not in prompt
    assert all(d['id'] != 'DOC-MOTOR' for d in guarded['documents'])
    RESULT['current_acl_prompt_filter'] = {'check_status':guarded['checks'][0]['status'],'private_document_marker_in_model_prompt':False,'private_document_in_context':False}

    # Authenticated outsiders are rejected only after an unnecessary model call.
    with patch.object(httpx,'post',return_value=resp({'response':'{}'})) as mock:
        denied = c.post(ROOT+'/chat',headers=outsider,json={'message':'請評估馬達升級','session_id':'outside','use_local_llm':True})
    RESULT['findings']['authorization_order'] = {'http_status':denied.status_code,'model_calls_before_denial':mock.call_count,'project_data_sent':False}
    assert denied.status_code == 403 and mock.call_count == 1

# Verify error categories directly, with no network.
errors = {'connection_error':httpx.ConnectError('synthetic'), 'timeout':httpx.ReadTimeout('synthetic'),
          'model_not_found':resp({'error':'model absent'},status=404), 'http_error':resp({'error':'server'},status=500),
          'invalid_json':resp(content=b'not-json'), 'empty_response':resp({'response':' '})}
RESULT['transport_contracts'] = {}
for expected, answer in errors.items():
    effect = answer if isinstance(answer,Exception) else None
    with patch.object(httpx,'post',side_effect=effect,return_value=None if effect else answer):
        text, diag = call_ollama('Synthetic test input')
    assert text is None and diag['status'] == expected
    RESULT['transport_contracts'][expected] = 'passed'
with patch.object(config,'OLLAMA_URL',''), patch.object(httpx,'post') as mock:
    text, diag = call_ollama('Synthetic test input')
    assert text is None and diag['status'] == 'not_configured' and mock.call_count == 0
RESULT['transport_contracts']['not_configured'] = 'passed'
for malformed in [None, [], {}, 42]:
    with patch.object(httpx,'post',return_value=resp({'response':malformed})):
        text, diag = call_ollama('Synthetic test input')
    assert text is None and diag['status'] == 'empty_response'
RESULT['transport_contracts']['non_string_response'] = 'passed'
output = Path(__file__).with_name('review-probes.json')
output.write_text(json.dumps(RESULT,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(RESULT,ensure_ascii=False,indent=2))
_TEMP.cleanup()
