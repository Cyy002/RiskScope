"""M12.1 single-path safety review. All model text is mock fault injection."""
import json
from pathlib import Path
import pytest
from app import chat, db, config, llm_client
from tests.conftest import ROOT, env, c, manager, engineer, outsider

observed = {}

@pytest.fixture(scope='session', autouse=True)
def save_evidence():
    yield
    Path(__file__).with_name('observations.json').write_text(
        json.dumps(observed, ensure_ascii=False, indent=2) + '\n')

def install_model(monkeypatch, text):
    calls, validations = [], []
    original = chat._reply_is_trustworthy
    def fake(prompt, **kwargs):
        calls.append(prompt)
        if '只負責從使用者訊息' in prompt:
            return '{}', {'status': 'success'}
        return text, {'status': 'success'}
    def spy(*args, **kwargs):
        result = original(*args, **kwargs)
        validations.append({'accepted': result[0], 'reason': result[1]})
        return result
    # Only enable the local endpoint gate. No actual socket is ever used.
    monkeypatch.setattr(config, 'OLLAMA_URL', 'http://127.0.0.1:11434')
    monkeypatch.setattr(llm_client, 'call_ollama', fake)
    monkeypatch.setattr(chat, 'call_ollama', fake)
    monkeypatch.setattr(chat, '_reply_is_trustworthy', spy)
    return calls, validations

def protected_tables():
    conn = db.connect()
    try:
        return {name: [tuple(r) for r in conn.execute('SELECT * FROM '+name)]
                for name in ('facts', 'project_signals', 'actions', 'simulated_tasks')}
    finally:
        conn.close()

def analyze(c, header, session, focus='supplier', llm=True, question='請分析供應商交期與品質驗證風險。'):
    return c.post(ROOT+'/analyze', headers=header, json={
        'question': question, 'focus': focus, 'session_id': session, 'use_local_llm': llm,
    })

@pytest.mark.parametrize('name,text,focus', [
    ('approval', 'TEST-01 已核准，可以立即執行。', 'supplier'),
    ('schedule', '供應商將延誤12天。', 'supplier'),
    ('cost', '新增成本為5000元。', 'supplier'),
    ('percentage', '延誤機率為30%。', 'supplier'),
    ('test_complete', '品質驗證已完成。', 'supplier'),
    ('engineering', '新方案總電流99A、總功率24W。', 'motor_upgrade'),
])
def test_analyze_rejects_the_same_untrusted_output_as_chat(c, engineer, monkeypatch, name, text, focus):
    calls, validations = install_model(monkeypatch, text)
    before = protected_tables()
    question = '請分析馬達升級風險。' if focus == 'motor_upgrade' else '請分析供應商交期與品質驗證風險。'
    baseline_response = analyze(c, engineer, name+'-baseline', focus, False, question)
    assert baseline_response.status_code == 200
    baseline = baseline_response.json()
    response = analyze(c, engineer, name+'-analyze', focus, True, question)
    assert response.status_code == 200
    a = response.json()
    analyze_validation_count = len(validations)
    detail = c.get(ROOT+'/analyses/'+a['analysis_id'], headers=engineer)
    assert detail.status_code == 200
    ch = c.post(ROOT+'/chat', headers=engineer, json={
        'message': question, 'focus': focus, 'session_id': name+'-chat', 'use_local_llm': True,
    })
    assert ch.status_code == 200
    b = ch.json()
    fields = ('facts', 'checks', 'options', 'unknowns', 'impacts', 'decision_status')
    deterministic_unchanged = all(a[k] == baseline[k] for k in fields)
    tables_unchanged = before == protected_tables()
    observed[name] = {
        'injected_text': text, 'analyze_status': response.status_code,
        'analyze_local_llm': a['local_llm'],
        'analyze_m7_calls': analyze_validation_count,
        'analysis_detail_stores_raw_output': text in json.dumps(detail.json(), ensure_ascii=False),
        'chat_reply_source': b['reply_source'],
        'chat_diagnostic': b['llm_diagnostic']['reply'],
        'chat_m7_calls': len(validations)-analyze_validation_count,
        'deterministic_output_unchanged': deterministic_unchanged,
        'protected_tables_unchanged': tables_unchanged,
    }
    assert deterministic_unchanged and tables_unchanged
    assert b['reply_source'] == 'deterministic_template'
    assert b['llm_diagnostic']['reply']['status'] == 'rejected_inconsistent'
    assert text not in a['local_llm'].get('text', ''), 'Analyze exposes text rejected by chat M7'

def test_authorized_content_and_session_still_work(c, engineer, monkeypatch):
    text = '供應商交期為7天，仍需人工審核。'
    _, validations = install_model(monkeypatch, text)
    first = analyze(c, engineer, 'safe-session').json()
    second = analyze(c, engineer, 'safe-session', question='請繼續分析供應商的驗證需求。')
    assert second.status_code == 200
    assert second.json()['session']['turn'] == 2
    ch = c.post(ROOT+'/chat', headers=engineer, json={
        'message': '請分析供應商交期。', 'focus': 'supplier', 'session_id': 'safe-chat', 'use_local_llm': True,
    }).json()
    assert first['local_llm']['text'] == text
    assert ch['reply_source'] == 'llm_phrased'
    observed['safe_control'] = {'authorized_seven_days_returned': True, 'second_turn': 2,
                              'chat_m7_accepts': validations[-1]['accepted']}

def test_acl_ownership_and_revocation_still_apply(c, manager, engineer, outsider, monkeypatch):
    calls, _ = install_model(monkeypatch, '模型文字僅供參考。')
    denied = analyze(c, outsider, 'outsider')
    assert denied.status_code == 403 and not calls
    first = analyze(c, engineer, 'acl-session').json()
    assert not any(d['id'] == 'DOC-CONF' for d in first['documents'])
    assert '合成敏感資料' not in calls[-1]
    count = len(calls)
    assert analyze(c, manager, 'acl-session').status_code == 403
    assert len(calls) == count
    assert c.patch(ROOT+'/documents/DOC-SUPPLIER/access', headers=manager,
                   json={'user_id':'engineer','enabled':False}).status_code == 200
    assert c.get(ROOT+'/analyses/'+first['analysis_id'], headers=engineer).status_code == 403
    history = c.get(ROOT+'/sessions/acl-session', headers=engineer).json()
    assert history['turns'][0]['redacted'] is True
    second = analyze(c, engineer, 'acl-session', question='供應商後續資訊有哪些？').json()
    assert not any(d['id'] == 'DOC-SUPPLIER' for d in second['documents'])
    assert not second['impacts'][0]['affected_nodes']
    assert c.patch(ROOT+'/members/access', headers=manager,
                   json={'user_id':'engineer','enabled':False}).status_code == 200
    assert analyze(c, engineer, 'acl-session').status_code == 403
    assert c.get(ROOT+'/sessions/acl-session', headers=engineer).status_code == 403
    observed['acl_control'] = {'nonmember_denied_before_llm': True,
                              'private_document_not_in_prompt': True,
                              'session_ownership_enforced': True,
                              'source_revocation_blocks_stored_analysis': True,
                              'revoked_paths_excluded_from_new_analysis': True,
                              'membership_revocation_denies_new_and_history': True}
