"""M11.4 bounded extraction, application feedback and session updates."""
import json
import pytest
from app import chat, db
from tests.conftest import ROOT


def model(monkeypatch, candidates, reply=None):
    def fake(prompt, **kwargs):
        if '只負責從使用者訊息' in prompt:
            return json.dumps(candidates), {'status': 'success'}
        return reply, {'status': 'success' if reply else 'connection_error'}
    monkeypatch.setattr(chat, 'call_ollama', fake)


def turn(c, engineer, message, session='m114-independent', llm=True):
    r = c.post(f'{ROOT}/chat', headers=engineer, json={
        'message': message, 'session_id': session, 'use_local_llm': llm,
    })
    assert r.status_code == 200
    return r.json()


@pytest.mark.parametrize('actual_phrase', [
    '實際持續可用8A', '實際持續可用容量為8A', '降額後可用8A',
])
def test_a_then_c_changes_only_session_scenario(c, engineer, monkeypatch, actual_phrase):
    conn = db.connect()
    before = [tuple(r) for r in conn.execute('SELECT * FROM facts ORDER BY id')]
    conn.close()
    model(monkeypatch, {
        'supply_voltage': {'value': '24', 'unit': 'V'},
        'supply_continuous_current': {'value': '8', 'unit': 'A'},
        'motor_continuous_current': {'value': '11', 'unit': 'A'},
        'aux_continuous_current': {'value': '3', 'unit': 'A'},
    })
    a = turn(c, engineer, f'電源24V，額定10A，{actual_phrase}。舊馬達8A，輔助負載3A；馬達替換成11A，交期不能延後。')
    assert a['checks'][0]['numbers']['total_current_a'] == '14'
    assert a['checks'][0]['numbers']['total_power_w'] == '336'
    assert a['checks'][0]['numbers']['limit_current_a'] == '8'
    assert '40%' in a['reply'] and '75%' in a['reply']
    model(monkeypatch, {'motor_continuous_current': {'value': '9', 'unit': 'A'}})
    result = turn(c, engineer, '如果改用9A馬達，其他條件不變，重新分析。')
    assert result['checks'][0]['numbers']['total_current_a'] == '12'
    assert result['checks'][0]['numbers']['total_power_w'] == '288'
    assert result['checks'][0]['numbers']['limit_current_a'] == '8'
    assert '20%' in result['reply'] and '50%' in result['reply']
    assert result['unclaimed_change_intents'] == []
    conn = db.connect()
    assert [tuple(r) for r in conn.execute('SELECT * FROM facts ORDER BY id')] == before
    conn.close()


def test_nameplate_candidate_cannot_mask_actual_capacity_request(c, engineer, monkeypatch):
    model(monkeypatch, {'supply_continuous_current': {'value': '10', 'unit': 'A'}})
    data = turn(c, engineer, '電源額定10A，實際持續可用7.5A。')
    assert data['unclaimed_change_intents'] == ['7.5A']
    # M12.5.1: the plain nameplate restatement is harmless (no mode => cannot touch the
    # authorized document fact) but must never be read as the actual-capacity value.
    assert data['user_supplied_accepted_this_turn'].get('supply_continuous_current', {}).get('mode') is None
    assert 'supply_actual_current' not in data['user_supplied_accepted_this_turn']
    assert 'actual_limit_current_a' not in data['checks'][0]['numbers']
    assert '尚未成功套用' in data['reply']


def test_same_number_in_wrong_field_does_not_hide_missing_change(c, engineer, monkeypatch):
    model(monkeypatch, {'aux_continuous_current': {'value': '6.5', 'unit': 'A'}})
    data = turn(c, engineer, '馬達改用6.5A，其他條件不變。')
    assert data['unclaimed_change_intents'] == ['6.5A']
    assert data['checks'][0]['numbers']['motor_current_a'] == '8'
    assert '尚未成功套用' in data['reply']


def test_llm_cannot_omit_the_failed_change_warning(c, engineer, monkeypatch):
    model(monkeypatch, {}, reply='目前仍需要人工審核，請補充規格。')
    data = turn(c, engineer, '馬達改用6.5A。')
    assert data['reply_source'] == 'llm_phrased'
    assert data['reply'].startswith('本次提出的條件尚未成功套用')
    history = c.get(f"{ROOT}/sessions/m114-independent", headers=engineer).json()
    assert '尚未成功套用' in history['turns'][-1]['reply']


@pytest.mark.parametrize('message', [
    '修改報告標題，馬達電流9A。',
    '報告改用9A作為章節名稱。',
    '馬達不要改用9A。',
    '原本名目額定10A。',
    '電源10A，馬達8A，實際持續可用9A。',
])
def test_only_explicit_engineering_changes_are_flagged(message):
    assert chat._explicit_change_requests(message) == []


def test_disabled_extraction_and_invalid_dimension_still_report_change(c, engineer, monkeypatch):
    disabled = turn(c, engineer, '如果改用9A馬達。', session='m114-disabled', llm=False)
    assert disabled['unclaimed_change_intents'] == ['9A']
    model(monkeypatch, {'motor_continuous_current': {'value': '9', 'unit': 'W'}})
    invalid = turn(c, engineer, '馬達電流改成9W。', session='m114-invalid')
    assert invalid['unclaimed_change_intents'] == ['9W']
    assert '尚未成功套用' in invalid['reply']
    assert invalid['user_supplied_accepted_this_turn'] == {}


def test_plain_restatement_does_not_erase_previous_explicit_plan(c, engineer, monkeypatch):
    model(monkeypatch, {'motor_continuous_current': {'value': '11', 'unit': 'A'}})
    turn(c, engineer, '馬達換成11A。')
    model(monkeypatch, {'motor_continuous_current': {'value': '8', 'unit': 'A'}})
    data = turn(c, engineer, '原本馬達電流是8A。')
    assert data['checks'][0]['numbers']['total_current_a'] == '14'


def test_accepted_delta_without_baseline_is_reported_as_not_applied(c, manager, engineer, monkeypatch):
    c.patch(f'{ROOT}/documents/DOC-AUX/access', headers=manager,
            json={'user_id': 'engineer', 'enabled': False})
    model(monkeypatch, {'aux_continuous_current': {'value': '2', 'unit': 'A'}})
    data = turn(c, engineer, '輔助負載新增2A。')
    assert data['checks'][0]['status'] == 'unknown'
    assert data['unclaimed_change_intents'] == ['2A']
    assert '尚未成功套用' in data['reply']
