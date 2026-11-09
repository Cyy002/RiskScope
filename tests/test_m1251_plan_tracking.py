"""M12.5.1: previous-plan tracking, bare multi-field scenario, old-value wording,
generalization beyond 10A/8A (no hard-coded numbers)."""
import json
import pytest
from app import chat
from tests.conftest import ROOT


def model(monkeypatch, cands):
    def fake(prompt, **kw):
        if '只負責從使用者訊息' in prompt:
            return json.dumps(cands), {'status': 'success'}
        return None, {'status': 'connection_error'}
    monkeypatch.setattr(chat, 'call_ollama', fake)


def turn(c, h, msg, sid):
    r = c.post(f'{ROOT}/chat', headers=h, json={'message': msg, 'session_id': sid, 'use_local_llm': True})
    assert r.status_code == 200
    return r.json()


def v(x, u='A'):
    return {'value': str(x), 'unit': u}


@pytest.mark.parametrize('nom,act,m1,m2,aux,volt', [(10, 8, 11, 9, 3, 24), (20, 15, 17, 12, 4, 24), (6, 5, 7, 4, 1, 24)])
def test_bare_scenario_then_motor_only_change_tracks_previous_plan(c, engineer, monkeypatch, nom, act, m1, m2, aux, volt):
    model(monkeypatch, {'supply_voltage': v(volt, 'V'), 'supply_actual_current': v(act),
                         'motor_continuous_current': v(m1), 'aux_continuous_current': v(aux)})
    a = turn(c, engineer, f'電源{volt}V，名目額定{nom}A，實際可用{act}A，馬達{m1}A，輔助{aux}A。', f'pt-{nom}')
    na = a['checks'][0]['numbers']
    assert na['total_current_a'] == str(m1 + aux)
    assert na['nameplate_limit_current_a'] == '10'  # nameplate stays the DOCUMENT value; only the user's actual capacity is supplied
    assert na['actual_limit_current_a'] == str(act)
    model(monkeypatch, {'motor_continuous_current': v(m2)})
    b = turn(c, engineer, f'只將馬達改成{m2}A，其餘完全不變。', f'pt-{nom}')
    nb = b['checks'][0]['numbers']
    assert nb['total_current_a'] == str(m2 + aux)
    assert nb['actual_limit_current_a'] == str(act)
    assert f'上一輪方案的 {m1}A 改為 {m2}A' in b['reply']
    d_i = m1 - m2
    assert f'電流需求下降 {d_i}A' in b['reply']
    assert f'功率需求下降 {d_i * volt}W' in b['reply']
    assert '電源名目額定電流 由' not in b['reply'] and '電源實際可用容量 由' not in b['reply']


def test_old_value_wording_is_not_a_second_request(c, engineer, monkeypatch):
    model(monkeypatch, {'motor_continuous_current': v(9)})
    d = turn(c, engineer, '馬達改用9A取代原本11A，電源不要修改。', 'old-val')
    assert d['checks'][0]['numbers']['motor_current_a'] == '9'
    assert d['unclaimed_change_intents'] == []


def test_lone_bare_number_still_cannot_override_document(c, engineer, monkeypatch):
    model(monkeypatch, {'motor_continuous_current': v(11)})
    d = turn(c, engineer, '馬達是11A', 'lone')
    assert d['checks'][0]['numbers']['motor_current_a'] == '8'
    assert d['unclaimed_change_intents'] == ['11A']


def test_equivalent_unit_restatement_is_not_a_fresh_change(c, engineer, monkeypatch):
    model(monkeypatch, {'supply_actual_current': v(8)})
    turn(c, engineer, '電源實際可用8A', 'eq')
    model(monkeypatch, {'supply_actual_current': v(8000, 'mA')})
    d = turn(c, engineer, '電源實際可用8000mA，沒有變', 'eq')
    assert d['unclaimed_change_intents'] == []
    assert '電源實際可用容量 由' not in d['reply']


def test_previous_numbers_sentinel_never_reaches_the_session_detail_api(c, engineer, monkeypatch):
    """Claude A's review: the `__previous_numbers__` plan-tracking sentinel is
    piggybacked onto sessions.user_supplied_json purely as internal bookkeeping
    (see chat_turn()'s docstring) -- GET /sessions/{id} must never hand it to a
    caller raw inside that column, since only the real USER_SUPPLIABLE_KEYS
    fields are part of this endpoint's actual contract."""
    model(monkeypatch, {'supply_actual_current': v(8), 'motor_continuous_current': v(11)})
    turn(c, engineer, '電源實際可用8A，馬達換成11A。', 'sentinel-leak')
    detail = c.get(f'{ROOT}/sessions/sentinel-leak', headers=engineer).json()
    assert '__previous_numbers__' not in detail['session']['user_supplied_json']


_R = {'checks': [{'status': 'fail', 'numbers': {
    'total_current_a': '14', 'limit_current_a': '8', 'nameplate_limit_current_a': '10', 'actual_limit_current_a': '8',
    'total_power_w': '336', 'limit_power_w': '192', 'nameplate_limit_power_w': '240', 'actual_limit_power_w': '192'}}]}


@pytest.mark.parametrize('nom,act', [(12, 9), (30, 22), (5, 4)])
def test_genuine_nameplate_replacement_is_not_hardcoded_to_10(c, engineer, monkeypatch, nom, act):
    """Claude A's review of claude-b's M12.5.1 handoff: the existing generalization
    test above (test_bare_scenario_then_motor_only_change_tracks_previous_plan)
    only varies the ACTUAL-capacity/motor/aux numbers; its mocked extraction never
    returns a new `supply_continuous_current`, so `nameplate_limit_current_a` stays
    hardcoded at the document's 10A in every row regardless of the `nom` parameter
    in the message text -- nameplate generalization was never actually exercised.
    This closes that gap via the genuine replace path (distinct from the earlier
    unit test, which only used the single fixed pair 12A/document baseline)."""
    model(monkeypatch, {'supply_continuous_current': v(nom), 'supply_actual_current': v(act)})
    d = turn(c, engineer, f'現在把電源連續額定改成{nom}A，實際可用也改成{act}A，馬達及輔助負載不變。', f'nameplate-gen-{nom}')
    numbers = d['checks'][0]['numbers']
    assert numbers['nameplate_limit_current_a'] == str(nom)
    assert numbers['actual_limit_current_a'] == str(act)
    nameplate_evidence = next(e for e in d['checks'][0]['evidence'] if e['fact_key'] == 'supply_continuous_current')
    assert nameplate_evidence['origin'] == 'proposed_change' and nameplate_evidence['baseline_value'] == '10'
    assert f'電源名目額定電流 由 10A' in d['reply']
    assert d['unclaimed_change_intents'] == []


@pytest.mark.parametrize('text,ok', [
    ('總電流14A、336W，超出名目額定約 40%，超過實際可用容量 75%。', True),
    ('相對額定超出約40%，相對實際容量超出75%。', True),
    ('超出名目額定約 33%。', False),                 # fabricated value
    ('延誤機率為40%。', False),                      # borrowed, not anchored to an overage
    ('超出預期的延誤機率為40%。', False),            # bridge words outside the whitelist cannot anchor
])
def test_m7_percentage_anchor_accepts_natural_phrasing_but_not_borrowed_or_fabricated(text, ok):
    trustworthy, reason = chat._reply_is_trustworthy(text, _R, None, None, None, '')
    assert trustworthy is ok, reason
