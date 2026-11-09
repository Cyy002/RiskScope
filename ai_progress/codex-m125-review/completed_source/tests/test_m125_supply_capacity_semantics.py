"""M12.5: real-production user-reported bug -- the supply's nameplate rating
(10A, from DOC-PS) and its actual-usable capacity (8A, a user-supplied
scenario constraint) are two co-existing facts about the SAME, unchanging
hardware. Once established in turn 1, the Agent kept re-announcing this pair
as "電源額定由10A改成8A" on every later turn -- including turns that were
only about correcting the motor, and even after the user explicitly said the
supply had not changed. The underlying engineering numbers were always
correct; only the narrative was wrong, and a second, compounding bug made
things worse: the user's own clarifying restatement ("電源沒有變，額定一直是
10A、實際可用一直是8A") was misread as two NEW, conflicting change requests
for the supply, which then got flagged as "尚未成功套用" (failed to apply)
simply because this turn's extraction didn't re-submit them.

Two root causes, both in app/chat.py:
1. `_explicit_change_requests()`'s actual-capacity detection searched the
   whole clause for the "實際可用" phrase, not the specific number near it --
   so a clause stating BOTH the nameplate value and the actual-capacity
   value ("額定一直是10A、實際可用一直是8A") attributed both numbers to
   "actual capacity", producing two conflicting requests. Fixed by making
   the match directional (nearest PRECEDING descriptor per number) via
   `_nearest_preceding_gap`.
2. `_unclaimed_change_intents()` only checked THIS TURN's freshly-accepted
   values -- a request whose value exactly matches what the session already
   has in effect (a plain restatement, not a new proposal) was wrongly
   treated as a failed new request. Fixed by also matching against the
   session's current merged state.
3. `_deterministic_reply()`/`_llm_reply()` rendered engineering.
   power_continuous()'s recomputed-every-turn "proposed_change" evidence as
   "由X改成Y" unconditionally -- correct for a turn that actually introduces
   or changes the override, misleading for a turn carrying forward an
   unchanged one. Fixed via `fresh_change_keys`.

All tests use the isolated tmp_path database from tests/conftest.py; no
production data is touched.
"""
import json
from app import chat
from tests.conftest import ROOT


def model(monkeypatch, candidates, reply=None):
    def fake(prompt, **kwargs):
        if '只負責從使用者訊息' in prompt:
            return json.dumps(candidates), {'status': 'success'}
        return reply, {'status': 'success' if reply else 'connection_error'}
    monkeypatch.setattr(chat, 'call_ollama', fake)


def turn(c, engineer, message, session='m125', llm=True):
    r = c.post(f'{ROOT}/chat', headers=engineer, json={
        'message': message, 'session_id': session, 'use_local_llm': llm,
    })
    assert r.status_code == 200
    return r.json()


def test_a_then_corrected_motor_keeps_supply_as_a_standing_condition(c, engineer, monkeypatch):
    """The exact user-reported scenario: establish actual-capacity 8A + 11A
    motor, then correct only the motor to 9A while the user explicitly
    reaffirms the supply hasn't changed. Numbers must match the user's
    stated correct results; the supply must never be re-reported as
    "changing" on turn 2, and nothing about the correction may be flagged as
    unclaimed."""
    model(monkeypatch, {
        'supply_continuous_current': {'value': '8', 'unit': 'A'},
        'motor_continuous_current': {'value': '11', 'unit': 'A'},
    })
    a = turn(c, engineer, '電源實際可用電流是8A，馬達原本8A，現在要換成11A的新馬達。')
    assert a['checks'][0]['numbers']['total_current_a'] == '14'
    assert a['checks'][0]['numbers']['total_power_w'] == '336'
    assert '40%' in a['reply'] and '75%' in a['reply']
    assert a['unclaimed_change_intents'] == []

    model(monkeypatch, {'motor_continuous_current': {'value': '9', 'unit': 'A'}})
    b = turn(c, engineer, '電源沒有變，額定一直是10A、實際可用一直是8A，請把馬達改成9A。')
    assert b['checks'][0]['numbers']['total_current_a'] == '12'
    assert b['checks'][0]['numbers']['total_power_w'] == '288'
    assert '20%' in b['reply'] and '50%' in b['reply']
    # Root cause 2: a plain restatement of an already-established value must
    # never be reported as a failed new request.
    assert b['unclaimed_change_intents'] == []
    assert '尚未成功套用' not in b['reply']
    # Root cause 1 & 3: the supply must be framed as a standing, unchanged
    # condition -- never "由10A改成8A" on a turn that didn't change it.
    assert '電源額定由10A改成8A' not in b['reply']
    assert 'supply_continuous_current 由' not in b['reply']
    assert '本輪未變更' in b['reply']
    # The genuinely-new change this turn (the motor) still gets the fresh
    # "proposed new scenario" framing.
    assert 'motor_continuous_current 由 8A' in b['reply']


def test_explicit_restatement_of_both_values_is_not_a_conflicting_request(c, engineer, monkeypatch):
    """Direct unit check on the parser root cause: a clause stating the
    nameplate and actual-capacity numbers together must only ever produce
    ONE request (the actual-capacity one) -- the nameplate number must never
    be misattributed as a second, conflicting supply request."""
    requests = chat._explicit_change_requests('額定一直是10A、實際可用一直是8A。')
    supply_requests = [r for r in requests if r['fact_key'] == 'supply_continuous_current']
    assert len(supply_requests) <= 1
    if supply_requests:
        assert supply_requests[0]['value'] == '8'


def test_cross_clause_actual_capacity_still_recognized_on_first_mention(c, engineer, monkeypatch):
    """Regression guard: fixing the above must not break the legitimate,
    existing cross-clause case where the component word and the actual-
    capacity phrase are in different clauses of the SAME sentence."""
    model(monkeypatch, {'supply_continuous_current': {'value': '7.5', 'unit': 'A'}})
    data = turn(c, engineer, '電源額定10A，實際持續可用7.5A。', session='m125-crossclause')
    assert data['user_supplied_accepted_this_turn'] == {
        'supply_continuous_current': {'value': '7.5', 'unit': 'A', 'mode': 'replace'}}


def test_generic_values_not_hardcoded_to_10_and_8(c, engineer, monkeypatch):
    """M12.5 Phase D (per Codex's suggested generalization check): the fix
    must not be specific to the literal numbers 10/8 -- a different nameplate
    and actual-capacity pair restated on a later turn must behave the same
    way."""
    model(monkeypatch, {
        'supply_continuous_current': {'value': '15', 'unit': 'A'},
        'motor_continuous_current': {'value': '20', 'unit': 'A'},
    })
    a = turn(c, engineer, '電源實際可用電流是15A，馬達要換成20A的新馬達。', session='m125-generic')
    assert a['checks'][0]['numbers']['limit_current_a'] == '15'

    model(monkeypatch, {'motor_continuous_current': {'value': '18', 'unit': 'A'}})
    b = turn(c, engineer, '電源沒有變，額定一直是20A、實際可用一直是15A，請把馬達改成18A。',
             session='m125-generic')
    assert b['unclaimed_change_intents'] == []
    assert 'supply_continuous_current 由' not in b['reply']
    assert '本輪未變更' in b['reply']


def test_negated_supply_change_produces_no_request(c, engineer, monkeypatch):
    """案例E (negation): explicitly saying not to change the supply must
    never produce a phantom request for it."""
    requests = chat._explicit_change_requests('不要修改電源，只換馬達成9A。')
    assert all(r['fact_key'] != 'supply_continuous_current' for r in requests)


def test_formal_facts_table_never_touched_by_the_scenario_dialogue(c, engineer, monkeypatch):
    from app import db
    conn = db.connect()
    before = [tuple(r) for r in conn.execute('SELECT * FROM facts ORDER BY id')]
    conn.close()
    model(monkeypatch, {
        'supply_continuous_current': {'value': '8', 'unit': 'A'},
        'motor_continuous_current': {'value': '11', 'unit': 'A'},
    })
    turn(c, engineer, '電源實際可用電流是8A，馬達換成11A。', session='m125-facts')
    model(monkeypatch, {'motor_continuous_current': {'value': '9', 'unit': 'A'}})
    turn(c, engineer, '電源沒有變，額定一直是10A、實際可用一直是8A，請把馬達改成9A。', session='m125-facts')
    conn = db.connect()
    after = [tuple(r) for r in conn.execute('SELECT * FROM facts ORDER BY id')]
    conn.close()
    assert before == after
