"""M12.5 / M12.5.1: real-production user-reported bug -- the supply's
nameplate rating (10A, from DOC-PS) and its actual-usable capacity (8A, a
user-supplied scenario constraint) are two co-existing facts about the SAME,
unchanging hardware. Once established in turn 1, the Agent kept re-
announcing this pair as "電源額定由10A改成8A" on every later turn -- including
turns that were only about correcting the motor, and even after the user
explicitly said the supply had not changed. The underlying engineering
numbers were always correct; only the narrative was wrong, and a second,
compounding bug made things worse: the user's own clarifying restatement
("電源沒有變，額定一直是10A、實際可用一直是8A") was misread as two NEW,
conflicting change requests for the supply, which then got flagged as
"尚未成功套用" (failed to apply) simply because this turn's extraction didn't
re-submit them.

M12.5's first attempt patched only the NARRATIVE layer (fresh-vs-standing
display) while `supply_continuous_current` still held BOTH meanings as a
single field. Codex's independent review of that attempt (ai_progress/
codex-m125-review/) found the structural confusion was still there one layer
down: Evidence/Facts still recorded the actual-capacity value as a
"proposed_change" REPLACING the nameplate, and M7 still accepted a reply that
literally claimed "電源額定由10A改為8A" because 10 and 8 both happened to be
real, trusted numbers (just the wrong claimed ROLE for them). M12.5.1 fixes
this at the data-model level:

1. `supply_actual_current` (engineering.py) is now a genuinely separate,
   always-optional fact_key from `supply_continuous_current` (the nameplate)
   -- never a replace/override of it. `_explicit_change_requests()`
   (app/chat.py) routes an actual-capacity number to this new key
   unconditionally, using a directional nearest-descriptor match
   (`_descriptor_gaps`) so two differently-described numbers sitting close
   together in one clause ("額定一直是10A、實際可用一直是8A") each find their
   own correct descriptor.
2. `engineering.power_continuous()` reports both `nameplate_limit_current_a`
   and `actual_limit_current_a` independently in `numbers` on every call --
   no recursive baseline-vs-override comparison needed for this purpose.
3. `_unclaimed_change_intents()` checks the session's current merged state,
   not just this turn's fresh extraction, so a plain restatement of an
   already-applied value is never flagged as a failed new request.
4. `fresh_change_keys` (physical-value-aware via `_entries_equivalent`)
   distinguishes "this field genuinely changed this turn" from "carried
   forward unchanged" -- only the former gets "由X改成Y" framing.
5. M7 (`_reply_is_trustworthy`) rejects a claimed NAMEPLATE RATING change
   ("電源額定由X改為Y") unless `supply_continuous_current` is ACTUALLY a
   'proposed_change' this turn -- a claim citing individually-real numbers
   for the wrong field role is no longer accepted just because the numbers
   exist somewhere in the trusted set.

All tests use the isolated tmp_path database from tests/conftest.py; no
production data is touched.
"""
import json
from app import chat, engineering
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
        'supply_actual_current': {'value': '8', 'unit': 'A'},
        'motor_continuous_current': {'value': '11', 'unit': 'A'},
    })
    a = turn(c, engineer, '電源實際可用電流是8A，馬達原本8A，現在要換成11A的新馬達。')
    assert a['checks'][0]['numbers']['total_current_a'] == '14'
    assert a['checks'][0]['numbers']['total_power_w'] == '336'
    assert a['checks'][0]['numbers']['nameplate_limit_current_a'] == '10'
    assert a['checks'][0]['numbers']['actual_limit_current_a'] == '8'
    assert '40%' in a['reply'] and '75%' in a['reply']
    assert a['unclaimed_change_intents'] == []
    # The nameplate is never touched -- it stays a plain document fact, not
    # a proposed_change, even though the actual-capacity field is.
    nameplate_evidence = next(e for e in a['checks'][0]['evidence']
                               if e['fact_key'] == 'supply_continuous_current')
    assert nameplate_evidence['origin'] == 'document'

    model(monkeypatch, {'motor_continuous_current': {'value': '9', 'unit': 'A'}})
    b = turn(c, engineer, '電源沒有變，額定一直是10A、實際可用一直是8A，請把馬達改成9A。')
    assert b['checks'][0]['numbers']['total_current_a'] == '12'
    assert b['checks'][0]['numbers']['total_power_w'] == '288'
    assert b['checks'][0]['numbers']['nameplate_limit_current_a'] == '10'
    assert b['checks'][0]['numbers']['actual_limit_current_a'] == '8'
    assert '20%' in b['reply'] and '50%' in b['reply']
    # Root cause 3: a plain restatement of an already-established value must
    # never be reported as a failed new request.
    assert b['unclaimed_change_intents'] == []
    assert '尚未成功套用' not in b['reply']
    # Root cause 1/2/4: the supply must be framed as a standing, unchanged
    # condition -- never "由10A改成8A" on a turn that didn't change it.
    assert '電源額定由10A改成8A' not in b['reply']
    assert 'supply_continuous_current 由' not in b['reply']
    assert '本輪未變更' in b['reply']
    # The genuinely-new change this turn (the motor) still gets the fresh
    # "proposed new scenario" framing, in its proper Chinese label.
    # M12.5.1: compared against the PREVIOUS PLAN (11A), not the document's 8A (Codex P1-03).
    assert '馬達連續電流 由上一輪方案的 11A 改為 9A' in b['reply']
    assert '馬達連續電流 由 8A' not in b['reply']


def test_explicit_restatement_of_both_values_routes_to_separate_fields(c, engineer, monkeypatch):
    """Direct unit check on the parser root cause: a clause stating the
    nameplate and actual-capacity numbers together must route each to its
    OWN field -- the nameplate number must never be misattributed as an
    actual-capacity request, and vice versa."""
    requests = chat._explicit_change_requests('額定一直是10A、實際可用一直是8A。')
    actual_requests = [r for r in requests if r['fact_key'] == 'supply_actual_current']
    nameplate_requests = [r for r in requests if r['fact_key'] == 'supply_continuous_current']
    assert len(actual_requests) <= 1
    if actual_requests:
        assert actual_requests[0]['value'] == '8'
    assert nameplate_requests == []


def test_cross_clause_actual_capacity_still_recognized_on_first_mention(c, engineer, monkeypatch):
    """Regression guard: fixing the above must not break the legitimate,
    existing cross-clause case where the component word and the actual-
    capacity phrase are in different clauses of the SAME sentence -- and the
    nameplate (10A, matching the document already) must not be touched."""
    model(monkeypatch, {'supply_actual_current': {'value': '7.5', 'unit': 'A'}})
    data = turn(c, engineer, '電源額定10A，實際持續可用7.5A。', session='m125-crossclause')
    assert data['user_supplied_accepted_this_turn'] == {
        'supply_actual_current': {'value': '7.5', 'unit': 'A'}}
    assert data['checks'][0]['numbers']['nameplate_limit_current_a'] == '10'
    assert data['checks'][0]['numbers']['actual_limit_current_a'] == '7.5'


def test_generic_values_not_hardcoded_to_10_and_8(c, engineer, monkeypatch):
    """M12.5 Phase D (per Codex's suggested generalization check): the fix
    must not be specific to the literal numbers 10/8 -- a different nameplate
    and actual-capacity pair restated on a later turn must behave the same
    way. Document nameplate stays 10A throughout (never touched); only the
    actual-capacity field and the motor are supplied by the user here."""
    model(monkeypatch, {
        'supply_actual_current': {'value': '15', 'unit': 'A'},
        'motor_continuous_current': {'value': '20', 'unit': 'A'},
    })
    a = turn(c, engineer, '電源實際可用電流是15A，馬達要換成20A的新馬達。', session='m125-generic')
    assert a['checks'][0]['numbers']['actual_limit_current_a'] == '15'
    assert a['checks'][0]['numbers']['nameplate_limit_current_a'] == '10'
    assert a['checks'][0]['numbers']['limit_current_a'] == '10'  # binding = min(nameplate 10, actual 15)

    model(monkeypatch, {'motor_continuous_current': {'value': '18', 'unit': 'A'}})
    b = turn(c, engineer, '電源沒有變，實際可用一直是15A，請把馬達改成18A。',
             session='m125-generic')
    assert b['unclaimed_change_intents'] == []
    assert 'supply_actual_current 由' not in b['reply']
    assert '本輪未變更' in b['reply']


def test_negated_supply_change_produces_no_request(c, engineer, monkeypatch):
    """案例E (negation): explicitly saying not to change the supply must
    never produce a phantom request for either supply field."""
    requests = chat._explicit_change_requests('不要修改電源，只換馬達成9A。')
    assert all(r['fact_key'] not in ('supply_continuous_current', 'supply_actual_current')
               for r in requests)


def test_formal_facts_table_never_touched_by_the_scenario_dialogue(c, engineer, monkeypatch):
    from app import db
    conn = db.connect()
    before = [tuple(r) for r in conn.execute('SELECT * FROM facts ORDER BY id')]
    conn.close()
    model(monkeypatch, {
        'supply_actual_current': {'value': '8', 'unit': 'A'},
        'motor_continuous_current': {'value': '11', 'unit': 'A'},
    })
    turn(c, engineer, '電源實際可用電流是8A，馬達換成11A。', session='m125-facts')
    model(monkeypatch, {'motor_continuous_current': {'value': '9', 'unit': 'A'}})
    turn(c, engineer, '電源沒有變，額定一直是10A、實際可用一直是8A，請把馬達改成9A。', session='m125-facts')
    conn = db.connect()
    after = [tuple(r) for r in conn.execute('SELECT * FROM facts ORDER BY id')]
    conn.close()
    assert before == after


def test_supply_actual_current_is_optional_not_required(c, engineer, monkeypatch):
    """A session that never mentions actual-usable capacity at all must
    still work exactly as before M12.5 -- it is optional, not a sixth
    required engineering field."""
    model(monkeypatch, {})
    result = turn(c, engineer, '請評估目前的馬達升級方案。', session='m125-no-actual')
    assert result['checks'][0]['status'] in ('pass', 'fail')
    assert 'actual_limit_current_a' not in result['checks'][0]['numbers']
    assert result['checks'][0]['numbers']['limit_current_a'] == \
        result['checks'][0]['numbers']['nameplate_limit_current_a']


def test_real_nameplate_replacement_still_applies_and_is_framed_as_a_change(c, engineer, monkeypatch):
    """Per the user's explicit instruction: a GENUINE nameplate change must
    still work, and must still be visibly framed as a change -- the fix must
    not blanket-protect the nameplate field into never being replaceable."""
    model(monkeypatch, {'supply_continuous_current': {'value': '12', 'unit': 'A'}})
    result = turn(c, engineer, '現在把電源連續額定改成12A，馬達及輔助負載不變。', session='m125-real-change')
    assert result['checks'][0]['numbers']['nameplate_limit_current_a'] == '12'
    nameplate_evidence = next(e for e in result['checks'][0]['evidence']
                               if e['fact_key'] == 'supply_continuous_current')
    assert nameplate_evidence['origin'] == 'proposed_change'
    assert '電源名目額定電流 由 10A' in result['reply']
