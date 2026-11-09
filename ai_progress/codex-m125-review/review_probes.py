"""M12.5 acceptance contracts: arithmetic AND meaning, using synthetic DBs only.

Mock extraction is deliberately successful, isolating downstream semantics from
model variability. Run via run_isolated.py; never start a real server/model.
"""
from decimal import Decimal
import json
import os
from pathlib import Path
import re

import pytest
from app import chat, db, engineering
from tests.conftest import ROOT, env, c, engineer, manager, outsider

OBSERVATIONS = {}
A = '電源24V，名目額定10A，實際持續可用容量8A。舊馬達8A，輔助負載3A；馬達替換成11A，交期不能延後。'
CORRECTION = '請更正：電源名目額定10A始終不變，實際持續可用容量8A也不變。只把馬達從11A改用9A，輔助負載3A不變。'


@pytest.fixture(autouse=True)
def save_observations():
    yield
    path = Path(os.environ['M125_OUTPUT']) / 'observations.json'
    path.write_text(json.dumps(OBSERVATIONS, ensure_ascii=False, indent=2) + '\n')


def candidate(value, unit='A'):
    return {'value': str(value), 'unit': unit}


def actual_key():
    # Only the extraction schema adapter may need extension after a schema fix.
    # Acceptance criteria below must not be weakened to accommodate a repair.
    for key in ('supply_available_current', 'supply_actual_current',
                'supply_effective_current', 'supply_available_continuous_current'):
        if key in engineering.USER_SUPPLIABLE_KEYS:
            return key
    return 'supply_continuous_current'


def model(monkeypatch, extracted, reply=None):
    def fake(prompt, **kwargs):
        if '只負責從使用者訊息' in prompt:
            return json.dumps(extracted), {'status': 'success'}
        return reply, {'status': 'success' if reply else 'connection_error'}
    monkeypatch.setattr(chat, 'call_ollama', fake)


def turn(client, headers, text, label, session='m125-independent'):
    response = client.post(f'{ROOT}/chat', headers=headers, json={
        'message': text, 'session_id': session, 'use_local_llm': True,
    })
    assert response.status_code == 200, response.text
    result = response.json()
    conn = db.connect()
    state = json.loads(conn.execute('SELECT user_supplied_json FROM sessions WHERE id=?', (session,)).fetchone()[0])
    conn.close()
    OBSERVATIONS[label] = {'message': text, 'checks': result.get('checks'),
        'facts': result.get('facts'), 'reply': result['reply'], 'reply_source': result['reply_source'],
        'accepted': result.get('user_supplied_accepted_this_turn'),
        'rejected': result.get('user_supplied_rejected_this_turn'),
        'unclaimed': result.get('unclaimed_change_intents'), 'session_inputs': state,
        'diagnostic': result.get('llm_diagnostic')}
    return result


def setup_a(c, engineer, monkeypatch, label='A'):
    model(monkeypatch, {'supply_voltage': candidate(24, 'V'), actual_key(): candidate(8),
          'motor_continuous_current': candidate(11), 'aux_continuous_current': candidate(3)})
    return turn(c, engineer, A, label)


def setup_b(c, engineer, monkeypatch, label='B'):
    setup_a(c, engineer, monkeypatch, label + '-initial')
    model(monkeypatch, {'motor_continuous_current': candidate(9)})
    return turn(c, engineer, '如果改用9A馬達，其他條件不變，重新分析。', label)


def numbers(result, total, power, nominal_pct, actual_pct):
    n = result['checks'][0]['numbers']
    assert Decimal(n['total_current_a']) == Decimal(total)
    assert Decimal(n['total_power_w']) == Decimal(power)
    assert f'{nominal_pct}%' in result['reply']
    assert f'{actual_pct}%' in result['reply']


def semantic_errors(result, nominal='10', actual='8'):
    check = result['checks'][0]
    errors = []
    changes = [e for e in check['evidence'] if e.get('origin') == 'proposed_change'
               and e.get('fact_key', '').startswith('supply')
               and e.get('change_mode') in ('replace', 'add')]
    if changes:
        errors.append('actual capacity mislabelled as supply specification change')
    prose = result['reply'] + '\n' + '\n'.join(f['claim'] for f in result.get('facts', []))
    if re.search(r'(?:電源額定|本身的額定)\s*' + re.escape(actual) + r'\s*A', prose):
        errors.append('actual capacity labelled as rated/nameplate in reply/facts')
    if not re.search(r'(?:實際|可用|有效)[^\n；。]{0,30}' + re.escape(actual) + r'\s*A', result['reply']):
        errors.append('reply does not identify actual available capacity')
    if not re.search(r'(?:名目|額定)[^\n；。]{0,20}' + re.escape(nominal) + r'\s*A', result['reply']):
        errors.append('reply loses nominal rating')
    return errors


def test_A_arithmetic(c, engineer, monkeypatch):
    numbers(setup_a(c, engineer, monkeypatch, 'A-arithmetic'), '14', '336', '40', '75')


def test_A_distinct_capacity_meanings(c, engineer, monkeypatch):
    result = setup_a(c, engineer, monkeypatch, 'A-semantics')
    assert semantic_errors(result) == []


def test_B_motor_only_arithmetic(c, engineer, monkeypatch):
    numbers(setup_b(c, engineer, monkeypatch, 'B-arithmetic'), '12', '288', '20', '50')


def test_B_no_power_specification_change(c, engineer, monkeypatch):
    result = setup_b(c, engineer, monkeypatch, 'B-semantics')
    assert semantic_errors(result) == []


def test_C_restatement_is_not_an_unapplied_change(c, engineer, monkeypatch):
    setup_b(c, engineer, monkeypatch, 'C-before')
    # An extractor may reasonably omit unchanged values. Session already has 8A.
    model(monkeypatch, {})
    result = turn(c, engineer, '請更正：電源名目額定10A始終不變，實際持續可用容量8A也不變。馬達仍為9A。', 'C-restatement')
    numbers(result, '12', '288', '20', '50')
    assert result['unclaimed_change_intents'] == [], 'Unchanged, already applied capacity is not a failed edit'
    assert semantic_errors(result) == []


def test_C_M7_rejects_numerically_valid_but_semantically_false_change(c, engineer, monkeypatch):
    setup_a(c, engineer, monkeypatch, 'C-M7-initial')
    false_reply = '電源額定由10A改為8A，馬達改用9A。'
    model(monkeypatch, {actual_key(): candidate(8), 'motor_continuous_current': candidate(9)}, false_reply)
    result = turn(c, engineer, CORRECTION, 'C-M7-false-change')
    assert result['reply_source'] == 'deterministic_template', 'M7 must reject false field/transition meaning, even when all numbers exist'
    assert false_reply not in result['reply']
    assert semantic_errors(result) == [], 'fallback must also preserve meanings'


def seed_generalized_case():
    # Only fixture-created synthetic database; adjust documents AND their facts.
    conn = db.connect()
    mapping = {'supply_voltage': '48', 'supply_continuous_current': '15',
               'motor_voltage': '48', 'motor_continuous_current': '10', 'aux_continuous_current': '2'}
    bodies = {'DOC-PS': '隔離合成電源規格：48V，連續名目額定15A。',
              'DOC-MOTOR': '隔離合成馬達規格：48V，連續電流10A。',
              'DOC-AUX': '隔離合成輔助負載：48V，連續電流2A。'}
    import hashlib
    with db.transaction(conn):
        for key, value in mapping.items():
            conn.execute('UPDATE facts SET value=? WHERE fact_key=?', (value, key))
        for doc, body in bodies.items():
            conn.execute('UPDATE documents SET body=? WHERE id=?', (body, doc))
            conn.execute('UPDATE document_revisions SET body=?,sha256=? WHERE document_id=? AND version=1',
                         (body, hashlib.sha256(body.encode()).hexdigest(), doc))
    conn.close()


@pytest.mark.parametrize('semantic', [False, True], ids=['arithmetic', 'semantics'])
def test_D_generalized_capacities(c, engineer, monkeypatch, semantic):
    seed_generalized_case()
    model(monkeypatch, {'supply_voltage': candidate(48, 'V'), actual_key(): candidate(12),
                       'motor_continuous_current': candidate(16), 'aux_continuous_current': candidate(2)})
    result = turn(c, engineer, '電源48V，名目額定15A，實際持續可用12A。舊馬達10A，輔助負載2A；馬達替換成16A。', f'D-{semantic}')
    numbers(result, '18', '864', '20', '50')
    if semantic:
        assert semantic_errors(result, '15', '12') == []


@pytest.mark.parametrize('message', [
    '馬達改用9A取代原本11A，電源不要修改。',
    '改用9A馬達，原本是11A；電源不要修改。',
    '不要修改電源，只把馬達從11A改用9A。',
], ids=['new-before-old-same-clause', 'new-before-old-separate-clause', 'negated-supply-only-motor'])
def test_E_order_and_negation(c, engineer, monkeypatch, message):
    setup_a(c, engineer, monkeypatch, 'E-initial-' + message)
    model(monkeypatch, {'motor_continuous_current': candidate(9)})
    result = turn(c, engineer, message, 'E-' + message)
    numbers(result, '12', '288', '20', '50')
    assert result['unclaimed_change_intents'] == []


def test_E_restatement_does_not_request_supply_replacement():
    message = '電源名目額定10A，實際持續可用8A，兩者保持不變。馬達11A，輔助負載3A。'
    requests = chat._explicit_change_requests(message)
    OBSERVATIONS['E-restatement-requests'] = requests
    assert not [r for r in requests if r['fact_key'].startswith('supply') and r.get('mode') in ('replace', 'add')]


def test_E_negated_motor_change_preserves_active_plan(c, engineer, monkeypatch):
    setup_a(c, engineer, monkeypatch, 'E-negated-initial')
    model(monkeypatch, {'motor_continuous_current': candidate(9)})
    result = turn(c, engineer, '馬達不要改用9A。電源不要修改。', 'E-negated-result')
    numbers(result, '14', '336', '40', '75')
    assert result['unclaimed_change_intents'] == []


def test_F_scenario_never_writes_formal_facts_or_actions(c, engineer, monkeypatch):
    def protected():
        conn = db.connect()
        data = {table: [tuple(row) for row in conn.execute(f'SELECT * FROM {table} ORDER BY 1')]
                for table in ('facts', 'actions', 'simulated_tasks')}
        conn.close()
        return data
    before = protected()
    setup_b(c, engineer, monkeypatch, 'F-readonly')
    assert protected() == before


def test_three_turn_arithmetic_and_no_false_unclaimed(c, engineer, monkeypatch):
    a = setup_a(c, engineer, monkeypatch, 'three-turn-A')
    model(monkeypatch, {'motor_continuous_current': candidate(9)})
    b = turn(c, engineer, '只將馬達改成9A，其餘完全不變。', 'three-turn-B')
    model(monkeypatch, {})
    third = turn(c, engineer, '電源額定一直是10A，實際可用一直是8A，我只修改馬達。', 'three-turn-C')
    numbers(a, '14', '336', '40', '75')
    for result in (b, third):
        numbers(result, '12', '288', '20', '50')
        assert result['unclaimed_change_intents'] == []
        assert 'supply_continuous_current 由' not in result['reply']
    assert Decimal(a['checks'][0]['numbers']['total_current_a']) - Decimal(b['checks'][0]['numbers']['total_current_a']) == 2
    assert Decimal(a['checks'][0]['numbers']['total_power_w']) - Decimal(b['checks'][0]['numbers']['total_power_w']) == 48


def test_previous_turn_motor_and_delta_must_be_visible(c, engineer, monkeypatch):
    result = setup_b(c, engineer, monkeypatch, 'B-previous-plan-comparison')
    text = result['reply']
    errors = []
    if '由 8A' in text and 'motor_continuous_current' in text:
        errors.append('fresh motor change still uses document 8A instead of previous-plan 11A')
    if not re.search(r'(下降|減少|降低)[^\n。；]{0,15}2\s*A', text):
        errors.append('current decrease 2A absent')
    if not re.search(r'(下降|減少|降低)[^\n。；]{0,15}48\s*W', text):
        errors.append('power decrease 48W absent')
    assert errors == []


def test_M7_accepts_correct_previous_plan_deltas(c, engineer, monkeypatch):
    setup_a(c, engineer, monkeypatch, 'delta-M7-initial')
    reply = '本輪馬達由11A改為9A，總電流下降2A、功率下降48W。'
    model(monkeypatch, {'motor_continuous_current': candidate(9)}, reply)
    result = turn(c, engineer, '只將馬達改成9A，其餘完全不變。', 'delta-M7')
    assert result['reply_source'] == 'llm_phrased', 'True deltas need deterministic provenance, not a blanket M7 relaxation'
    assert reply == result['reply']


@pytest.mark.parametrize('value,unit', [('8.0','A'), ('8000','mA')], ids=['decimal-format','equivalent-unit'])
def test_fresh_change_uses_physical_value_not_raw_dictionary(c, engineer, monkeypatch, value, unit):
    setup_a(c, engineer, monkeypatch, 'same-value-initial-' + unit)
    model(monkeypatch, {actual_key(): candidate(value, unit)})
    result = turn(c, engineer, f'電源實際可用仍是{value}{unit}，只是重述，沒有變更。', 'same-value-' + unit)
    assert result['checks'][0]['numbers']['limit_current_a'] == '8'
    assert 'supply_continuous_current 由' not in result['reply'], 'Equivalent quantities must not create a fresh change'


def test_accepted_restatement_without_mode_does_not_hide_applied_state(c, engineer, monkeypatch):
    setup_a(c, engineer, monkeypatch, 'warning-state-initial')
    # Explicit state-level test: successful extraction of a plain restatement
    # must not shadow the correctly applied merged state merely by being truthy.
    result = OBSERVATIONS['warning-state-initial']
    state = result['session_inputs']
    unclaimed = chat._unclaimed_change_intents('電源實際可用8A。',
        {'supply_continuous_current': candidate(8)}, result['checks'][0], state)
    OBSERVATIONS['warning-shadowing'] = {'unclaimed': unclaimed}
    assert unclaimed == []


def test_negation_scoped_to_power_not_whole_clause(c, engineer, monkeypatch):
    setup_a(c, engineer, monkeypatch, 'negation-clause-initial')
    model(monkeypatch, {'motor_continuous_current': candidate(9)})
    result = turn(c, engineer, '電源不要改成12A但馬達改用9A。', 'negation-clause')
    numbers(result, '12', '288', '20', '50')


def test_descriptor_after_value(c, engineer, monkeypatch):
    model(monkeypatch, {actual_key(): candidate(8), 'motor_continuous_current': candidate(11)})
    result = turn(c, engineer, '電源8A才是實際可用容量，10A是名目額定，馬達改用11A，輔助負載3A。', 'postfix-descriptor')
    numbers(result, '14', '336', '40', '75')


def test_real_supply_change_still_applies(c, engineer, monkeypatch):
    setup_b(c, engineer, monkeypatch, 'real-supply-initial')
    model(monkeypatch, {'supply_continuous_current': candidate(12)})
    result = turn(c, engineer, '現在把電源連續額定改成12A，馬達9A及輔助負載3A不變。', 'real-supply')
    assert result['checks'][0]['numbers']['limit_current_a'] == '12'
    assert result['checks'][0]['numbers']['total_current_a'] == '12'
    assert result['unclaimed_change_intents'] == []
    assert 'supply_continuous_current 由' in result['reply']


def test_real_supply_replacement_keeps_both_new_ratings(c, engineer, monkeypatch):
    setup_b(c, engineer, monkeypatch, 'dual-supply-initial')
    model(monkeypatch, {actual_key(): candidate(16)})
    result = turn(c, engineer, '電源換成名目額定20A的電源，實際可用16A，馬達9A與輔助3A都不變。', 'dual-supply-replacement')
    assert result['checks'][0]['numbers']['limit_current_a'] == '16'
    assert result['unclaimed_change_intents'] == []
    assert re.search(r'(?:名目|額定)[^\n；。]{0,15}20\s*A', result['reply'])


def test_literal_three_turn_initial_conditions(c, engineer, monkeypatch):
    # Exact requested initial-condition form, with no inferred replacement verb.
    # Formal fixture has an 8A motor, so accepting a scenario must remain separate
    # from changing that formal fact. Silently reporting 11A total is not correct.
    model(monkeypatch, {'supply_voltage': candidate(24, 'V'), actual_key(): candidate(8),
                       'motor_continuous_current': candidate(11), 'aux_continuous_current': candidate(3)})
    a = turn(c, engineer, '電源24V，名目額定10A，實際可用8A，馬達11A，輔助3A。', 'literal-A')
    model(monkeypatch, {'motor_continuous_current': candidate(9)})
    b = turn(c, engineer, '只將馬達改成9A，其餘完全不變。', 'literal-B')
    model(monkeypatch, {})
    third = turn(c, engineer, '電源額定一直是10A，實際可用一直是8A，我只修改馬達。', 'literal-C')
    numbers(a, '14', '336', '40', '75')
    for result in (b, third):
        numbers(result, '12', '288', '20', '50')

