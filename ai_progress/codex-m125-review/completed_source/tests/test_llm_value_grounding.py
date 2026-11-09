"""Regression tests for the fabricated-engineering-value gap Codex found via
fault injection (ai_progress/codex-review-ollama/review_probes.py, finding
`ungrounded_numeric_extraction`): a mocked LLM could report a value+unit for a
fact key that never appeared anywhere in the user's message, and
engineering.convert() alone -- which only checks dimensional sanity, not
provenance -- let it through to the deterministic calculation.

Fix under test: app.chat._grounded_in_message(), wired into
_extract_user_supplied() so a candidate is only accepted when its exact
value+unit literally appears in the user's own text. All tests mock
app.chat.call_ollama directly (no network, no real Ollama) and use the
isolated tmp_path database from tests/conftest.py -- the real runtime/
credentials are never touched.
"""
import json
from app import chat
from tests.conftest import ROOT


def _fake_call_ollama(extraction_json):
    """Returns a stand-in for app.llm_client.call_ollama: answers the
    extraction prompt with `extraction_json`, and the reply-phrasing prompt
    with a fixed harmless sentence (its content is irrelevant to these
    tests, only the extraction path is under test)."""
    def fake(prompt, timeout=30, keep_alive='10m'):
        if '只負責從使用者訊息' in prompt:
            return json.dumps(extraction_json), {'status': 'success', 'elapsed_seconds': 0.01}
        return '試算完成，仍需人工審核。', {'status': 'success', 'elapsed_seconds': 0.01}
    return fake


def test_a_fabricated_values_with_no_numbers_in_message_are_rejected(c, manager, engineer, monkeypatch):
    assert c.patch(f"{ROOT}/documents/DOC-MOTOR/access", headers=manager,
                    json={"user_id": "engineer", "enabled": False}).status_code == 200
    monkeypatch.setattr(chat, 'call_ollama',
                         _fake_call_ollama({'motor_voltage': {'value': '24', 'unit': 'V'},
                                             'motor_continuous_current': {'value': '1', 'unit': 'A'}}))
    resp = c.post(f"{ROOT}/chat", headers=engineer, json={
        "message": "請分析，不要猜測未提供的規格。", "session_id": "ground-a", "use_local_llm": True,
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["user_supplied_accepted_this_turn"] == {}
    reasons = [r['reason'] for r in data["user_supplied_rejected_this_turn"]]
    assert len(reasons) == 2 and all('找不到對應文字' in r for r in reasons)
    assert data["checks"][0]["status"] == "unknown"


def test_b_values_the_user_actually_typed_are_accepted(c, manager, engineer, monkeypatch):
    assert c.patch(f"{ROOT}/documents/DOC-MOTOR/access", headers=manager,
                    json={"user_id": "engineer", "enabled": False}).status_code == 200
    candidates = {'motor_voltage': {'value': '24', 'unit': 'V'},
                   'motor_continuous_current': {'value': '1', 'unit': 'A'}}
    monkeypatch.setattr(chat, 'call_ollama', _fake_call_ollama(candidates))
    resp = c.post(f"{ROOT}/chat", headers=engineer, json={
        "message": "馬達電壓24V，電流1A，請評估。", "session_id": "ground-b", "use_local_llm": True,
    })
    data = resp.json()
    assert data["user_supplied_accepted_this_turn"] == candidates
    assert data["user_supplied_rejected_this_turn"] == []
    assert data["checks"][0]["status"] == "pass"


def test_c_partially_grounded_values_only_accept_the_grounded_part(c, manager, engineer, monkeypatch):
    assert c.patch(f"{ROOT}/documents/DOC-MOTOR/access", headers=manager,
                    json={"user_id": "engineer", "enabled": False}).status_code == 200
    monkeypatch.setattr(chat, 'call_ollama',
                         _fake_call_ollama({'motor_voltage': {'value': '24', 'unit': 'V'},
                                             'motor_continuous_current': {'value': '1', 'unit': 'A'}}))
    resp = c.post(f"{ROOT}/chat", headers=engineer, json={
        "message": "馬達電壓24V，電流還沒量到。", "session_id": "ground-c", "use_local_llm": True,
    })
    data = resp.json()
    assert data["user_supplied_accepted_this_turn"] == {'motor_voltage': {'value': '24', 'unit': 'V'}}
    rejected_keys = [r['fact_key'] for r in data["user_supplied_rejected_this_turn"]]
    assert rejected_keys == ['motor_continuous_current']
    # motor_continuous_current is still missing -> cannot be marked pass
    assert data["checks"][0]["status"] == "unknown"


def test_d_legitimate_unit_conversion_is_still_accepted_and_normalized(c, manager, engineer, monkeypatch):
    assert c.patch(f"{ROOT}/documents/DOC-MOTOR/access", headers=manager,
                    json={"user_id": "engineer", "enabled": False}).status_code == 200
    candidates = {'motor_voltage': {'value': '24000', 'unit': 'mV'},
                   'motor_continuous_current': {'value': '1', 'unit': 'A'}}
    monkeypatch.setattr(chat, 'call_ollama', _fake_call_ollama(candidates))
    resp = c.post(f"{ROOT}/chat", headers=engineer, json={
        "message": "馬達電壓24000mV，電流1A，請評估。", "session_id": "ground-d", "use_local_llm": True,
    })
    data = resp.json()
    assert data["user_supplied_accepted_this_turn"] == candidates
    check = data["checks"][0]
    assert check["status"] == "pass"
    assert check["numbers"]["motor_voltage_v"] == "24"  # mV -> V, verified by engineering.convert()


def test_e_formal_document_value_is_never_overridden_by_user_supplied(c, manager, engineer, monkeypatch):
    # No document revoked this time -- motor_voltage is already 'ok' (24V, the
    # real DOC-MOTOR spec) before the user ever says anything.
    candidates = {'motor_voltage': {'value': '30', 'unit': 'V'}}
    monkeypatch.setattr(chat, 'call_ollama', _fake_call_ollama(candidates))
    resp = c.post(f"{ROOT}/chat", headers=engineer, json={
        "message": "馬達電壓是30V，請用這個數字評估。", "session_id": "ground-e", "use_local_llm": True,
    })
    data = resp.json()
    check = data["checks"][0]
    # the document-backed value (24V) wins; the fabricated-override attempt (30V) never reaches `numbers`
    assert check["numbers"]["motor_voltage_v"] == "24"
    assert 'motor_voltage' not in check["user_supplied_fact_keys"]
    motor_evidence = next(e for e in check["evidence"] if e["fact_key"] == "motor_voltage")
    assert motor_evidence["origin"] == "document" and motor_evidence["value"] == "24"


def test_f_session_persisted_values_survive_a_turn_with_no_new_numbers(c, manager, engineer, monkeypatch):
    assert c.patch(f"{ROOT}/documents/DOC-MOTOR/access", headers=manager,
                    json={"user_id": "engineer", "enabled": False}).status_code == 200
    # Turn 1: only the voltage is grounded in the text -- current stays missing,
    # so the check (and the session) stay open, same as test C.
    monkeypatch.setattr(chat, 'call_ollama',
                         _fake_call_ollama({'motor_voltage': {'value': '24', 'unit': 'V'},
                                             'motor_continuous_current': {'value': '1', 'unit': 'A'}}))
    turn1 = c.post(f"{ROOT}/chat", headers=engineer, json={
        "message": "馬達電壓24V，電流還沒量到。", "session_id": "ground-f", "use_local_llm": True,
    }).json()
    assert turn1["user_supplied_accepted_this_turn"] == {'motor_voltage': {'value': '24', 'unit': 'V'}}
    assert turn1["checks"][0]["status"] == "unknown"
    assert turn1["session"]["status"] == "open"

    # Turn 2: only the current is mentioned. The voltage accepted last turn must
    # still apply even though this turn's message never repeats "24V".
    monkeypatch.setattr(chat, 'call_ollama',
                         _fake_call_ollama({'motor_continuous_current': {'value': '1', 'unit': 'A'}}))
    turn2 = c.post(f"{ROOT}/chat", headers=engineer, json={
        "message": "量到了，電流1A。", "session_id": "ground-f", "use_local_llm": True,
    }).json()
    assert turn2["user_supplied_accepted_this_turn"] == {'motor_continuous_current': {'value': '1', 'unit': 'A'}}
    assert turn2["checks"][0]["status"] == "pass"
    assert set(turn2["checks"][0]["user_supplied_fact_keys"]) == {'motor_voltage', 'motor_continuous_current'}
