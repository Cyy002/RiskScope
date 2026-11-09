"""Independent acceptance probes. Failures intentionally preserve unmet requirements.

All data is synthetic tmp_path data. Model replies are fault injection, not
claims that a real model produced these sentences. Existing tests are untouched.
"""
import json
from pathlib import Path
import pytest
from app import chat, db
from tests.conftest import ROOT, env, c, manager, engineer, outsider

OBSERVATIONS = {}

@pytest.fixture(scope='session', autouse=True)
def save_observations():
    yield
    Path(__file__).with_name('observations.json').write_text(
        json.dumps(OBSERVATIONS, ensure_ascii=False, indent=2) + '\n')

def model(monkeypatch, reply):
    prompts = []
    def fake(prompt, **kwargs):
        if '只負責從使用者訊息' in prompt:
            return '{}', {'status': 'success'}
        prompts.append(prompt)
        return reply, {'status': 'success'}
    monkeypatch.setattr(chat, 'call_ollama', fake)
    return prompts

def turn(c, headers, message='供應商交貨延遲，品質驗證尚未完成，交期不能延後。',
         session='m12-independent', focus='supplier', llm=True):
    r = c.post(ROOT + '/chat', headers=headers, json={
        'message': message, 'session_id': session, 'focus': focus,
        'use_local_llm': llm,
    })
    assert r.status_code == 200
    return r.json()

def snapshot():
    conn = db.connect()
    try:
        return {table: [tuple(r) for r in conn.execute('SELECT * FROM ' + table)]
                for table in ('facts', 'project_signals', 'actions', 'simulated_tasks')}
    finally:
        conn.close()

def record_reply(key, result):
    OBSERVATIONS[key] = {
        'reply': result['reply'], 'reply_source': result['reply_source'],
        'diagnostic': result['llm_diagnostic']['reply'],
        'facts': result['facts'],
    }

def test_authorized_seven_days_can_be_phrased(c, engineer, monkeypatch):
    model(monkeypatch, '目前專案訊號記錄供應商交期為7天；不代表已算出延期天數。')
    result = turn(c, engineer)
    record_reply('authorized_seven_days', result)
    assert any('supplier_lead_days = 7' in f['claim'] for f in result['facts'])
    assert result['reply_source'] == 'llm_phrased', 'Evidence-backed 7 days was rejected'

def test_missing_signal_does_not_license_seven_days(c, engineer, monkeypatch):
    conn = db.connect()
    conn.execute("DELETE FROM project_signals WHERE key='supplier_lead_days'")
    conn.close()
    model(monkeypatch, '供應商交期為7天。')
    result = turn(c, engineer)
    record_reply('missing_seven_days', result)
    assert result['reply_source'] == 'deterministic_template'
    assert 'supplier_lead_days = 7' not in result['reply']

@pytest.mark.parametrize('name,text', [
    ('chinese_digits', '供應商交期為十二天，追加成本五萬元。'),
    ('english_units', 'Lead time is 12 days and the extra cost is $5000.'),
    ('unlisted_units', '交期為2月，增加成本€500。'),
    ('chinese_percentage', '延誤機率為百分之三十。'),
    ('fullwidth_percent', '延誤機率為30％。'),
])
def test_fabricated_numeric_formats_are_rejected(c, engineer, monkeypatch, name, text):
    model(monkeypatch, text)
    result = turn(c, engineer)
    record_reply(name, result)
    assert result['reply_source'] == 'deterministic_template', 'Unsupported numeric claim reached reply'

def percentage_result(total='14', limit='8', baseline='10'):
    return {'checks': [{'status': 'fail',
                        'numbers': {'total_current_a': total, 'limit_current_a': limit},
                        'baseline': {'numbers': {'limit_current_a': baseline}}}]}

@pytest.mark.parametrize('name,text,result,expected', [
    ('borrowed_percentage', '供應商延誤機率為40%。', percentage_result(), False),
    ('rounded_fabrication', '相對現有額定超出40.4%。', percentage_result(), False),
    ('valid_fractional_percentage', '相對現有額定超出40.6%。',
     percentage_result('14.06', '10', '10'), True),
])
def test_percentages_match_quantity_and_precision(name, text, result, expected):
    accepted, reason = chat._reply_is_trustworthy(text, result, None, None, None, '')
    OBSERVATIONS[name] = {'text': text, 'accepted': accepted, 'reason': reason,
                          'expected_accepted': expected}
    assert accepted == expected

def test_unverified_qualitative_claim_cannot_become_confirmed(c, engineer, monkeypatch):
    before = snapshot()
    model(monkeypatch, '品質驗證已完成，替代供應商已確認可用，方案G-C的成本最低。')
    result = turn(c, engineer)
    after = snapshot()
    record_reply('qualitative_fabrication', result)
    OBSERVATIONS['qualitative_fabrication']['formal_tables_unchanged'] = before == after
    assert before == after
    assert result['decision_status'] == 'requires_human_review'
    assert all(o['hard_constraint'] == 'unverified' for o in result['options'])
    assert result['reply_source'] == 'deterministic_template', 'Unknown test result was phrased as confirmed'

def test_decision_constraints_and_documents_reach_reply_model(c, engineer, monkeypatch):
    prompts = model(monkeypatch, '尚待驗證，請補充資訊。')
    message = '關鍵供應商交貨延遲；品質優先，客戶交期絕不能延後，禁止未驗證替代件。'
    result = turn(c, engineer, message)
    prompt = prompts[-1]
    OBSERVATIONS['reply_context'] = {
        'current_question_present': message in prompt,
        'deadline_constraint_present': '客戶交期絕不能延後' in prompt,
        'substitution_constraint_present': '禁止未驗證替代件' in prompt,
        'documents_in_result': len(result['documents']),
        'document_excerpts_in_prompt': any(d['excerpt'] in prompt for d in result['documents'] if d.get('excerpt')),
        'decision_context': result['decision_structure']['decision_context'],
    }
    assert message in prompt, 'Reply model receives scaffold but not current decision question'

def test_options_change_when_constraints_and_priorities_change(c, engineer):
    results = []
    for question, priorities in [
        ('供應商交貨延遲，交期不能延後，禁止替代供應商。', ['交期', '品質', '成本']),
        ('供應商交貨延遲，可以延後交期，優先更換供應商。', ['成本', '品質', '交期']),
    ]:
        r = c.post(ROOT + '/analyze', headers=engineer, json={
            'question': question, 'focus': 'supplier', 'priorities': priorities,
        })
        assert r.status_code == 200
        results.append(r.json())
    OBSERVATIONS['fixed_options'] = {
        'options_identical': results[0]['options'] == results[1]['options'],
        'consequences_identical': results[0]['decision_structure']['consequences'] == results[1]['decision_structure']['consequences'],
        'options': results[0]['options'],
    }
    assert results[0]['options'] != results[1]['options'], 'Conflicting constraints produce identical options'

def test_signal_followup_is_applied_or_explicitly_rejected(c, engineer, monkeypatch):
    prompts = model(monkeypatch, '尚待驗證，請補充資訊。')
    first = turn(c, engineer, '供應商延遲，品質優先且交期絕不能延後。')
    second = turn(c, engineer, '供應商交期請改為12天，品質驗證已完成，其他條件不變。')
    OBSERVATIONS['signal_followup'] = {
        'turn': second['session']['turn'], 'facts_unchanged': first['facts'] == second['facts'],
        'unknowns_unchanged': first['unknowns'] == second['unknowns'],
        'options_unchanged': first['options'] == second['options'],
        'unclaimed_change_intents': second['unclaimed_change_intents'],
        'previous_constraint_in_reply_prompt': '交期絕不能延後' in prompts[-1],
        'reply': second['reply'],
    }
    assert second['session']['turn'] == 2
    applied = any('supplier_lead_days = 12' in f['claim'] for f in second['facts'])
    warning = bool(second['unclaimed_change_intents']) or '未套用' in second['reply'] or '尚未成功套用' in second['reply']
    assert applied or warning, 'Unsupported signal update silently leaves old values'

def test_mismatch_requires_confirmation_before_motor_calculation(c, engineer):
    result = turn(c, engineer, '拿鐵和美式咖啡哪個比較好？', focus='motor_upgrade', llm=False)
    OBSERVATIONS['mismatch'] = {'warning': result['focus_mismatch_warning'],
                               'numbers': result['checks'][0].get('numbers') if result['checks'] else None,
                               'reply': result['reply']}
    assert result['focus_mismatch_warning']
    assert result['checks'] == [], 'Unrelated input still executes and displays motor analysis'

def test_signal_access_follows_project_membership_and_document_acl(c, engineer, manager, outsider, monkeypatch):
    prompts = model(monkeypatch, '專案訊號仍須人工確認。')
    # Reader is deliberately permitted project-wide signals but cannot edit them.
    conn = db.connect()
    conn.execute("UPDATE project_members SET role='reader' WHERE user_id='engineer'")
    conn.execute("INSERT INTO projects VALUES ('other-project','isolated other project',1)")
    conn.execute("INSERT INTO project_signals VALUES ('other-project','private_marker','OTHER_PROJECT_SENTINEL',NULL)")
    conn.close()
    first = turn(c, engineer)
    assert any('supplier_lead_days = 7' in f['claim'] for f in first['facts'])
    assert '合成敏感資料' not in json.dumps(first, ensure_ascii=False)
    assert 'OTHER_PROJECT_SENTINEL' not in json.dumps(first) + prompts[-1]
    event = c.post(ROOT + '/events', headers=engineer, json={
        'external_event_id': 'reader-test', 'signal_key': 'supplier_lead_days', 'value': '12',
    })
    assert event.status_code == 403
    revoked = c.patch(ROOT + '/documents/DOC-SUPPLIER/access', headers=manager,
                      json={'user_id': 'engineer', 'enabled': False})
    assert revoked.status_code == 200
    history = c.get(ROOT + '/sessions/m12-independent', headers=engineer)
    assert history.json()['turns'][0]['redacted'] is True
    second = turn(c, engineer, '供應商有哪些後續限制？')
    assert any('supplier_lead_days = 7' in f['claim'] for f in second['facts'])
    assert not any(d['id'] == 'DOC-SUPPLIER' for d in second['documents'])
    assert not second['impacts'][0]['affected_nodes']
    assert 'PROCURE-01' not in prompts[-1]
    assert c.post(ROOT + '/chat', headers=outsider, json={
        'message': '供應商', 'session_id': 'outside', 'focus': 'supplier', 'use_local_llm': False,
    }).status_code == 403
    assert c.patch(ROOT + '/members/access', headers=manager,
                   json={'user_id': 'engineer', 'enabled': False}).status_code == 200
    assert c.get(ROOT + '/sessions/m12-independent', headers=engineer).status_code == 403
    assert c.get(ROOT + '/analyses/' + second['analysis_id'], headers=engineer).status_code == 403
    assert c.post(ROOT + '/chat', headers=engineer, json={
        'message': '供應商後續', 'session_id': 'm12-independent', 'focus': 'supplier', 'use_local_llm': False,
    }).status_code == 403
    OBSERVATIONS['acl_controls'] = {
        'project_reader_sees_public_signals': True,
        'other_project_and_confidential_document_hidden': True,
        'reader_cannot_write_signals': True,
        'document_revocation_redacts_old_history_and_paths': True,
        'membership_revocation_blocks_new_and_old_reads': True,
        'document_revocation_does_not_revoke_public_signal': True,
    }
