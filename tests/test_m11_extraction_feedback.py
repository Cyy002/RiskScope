"""Regression tests for M11.4: a real-GUI run (M11.3, ai_progress/00_STATUS.md)
found that qwen3.6:27b's extraction step can inconsistently fail to produce a
candidate for a value the user clearly meant to change -- "電源實際持續可用容量降
為8A" never mapped to `supply_continuous_current`, and "如果改用9A馬達" sometimes
never mapped to `motor_continuous_current` at all. A direct, isolated
reproduction (not through the GUI) confirmed this is LLM extraction
non-determinism, not a bug in grounding, session merging, the engineering
override, or M7 -- re-running the exact same messages standalone sometimes
succeeded, sometimes didn't, and the downstream pipeline applied the value
correctly every time extraction DID produce it.

Two complementary fixes, neither hardcoding any test value:
1. app.engineering.USER_SUPPLIABLE_KEY_DESCRIPTIONS -- a short Chinese
   description per field (not an example value), given to the LLM extraction
   prompt alongside the bare variable name, to reduce (not guarantee away)
   mapping failures for any phrasing of these five known fields.
2. app.chat._unclaimed_change_intents() -- a purely deterministic (no second
   LLM call) cross-check: scan the message for a number with explicit
   change-intent language (the same _change_intent_mode() M8 already uses)
   that never ended up in `accepted` for any field. When found, the reply
   (both deterministic and LLM-phrased paths) must say so explicitly instead
   of silently reusing the old numbers.

All tests mock app.chat.call_ollama directly (no network, no real Ollama) and
use the isolated tmp_path database from tests/conftest.py -- the real
runtime/credentials are never touched.
"""
import json
from app import chat
from tests.conftest import ROOT


def _fake_call_ollama(extraction_json, captured_prompts=None):
    def fake(prompt, timeout=30, keep_alive='10m'):
        if captured_prompts is not None:
            captured_prompts.append(prompt)
        if '只負責從使用者訊息' in prompt:
            return json.dumps(extraction_json), {'status': 'success', 'elapsed_seconds': 0.01}
        return None, {'status': 'connection_error', 'detail': 'simulated: no reply-phrasing in this test'}
    return fake


def test_extraction_prompt_includes_field_descriptions_not_just_names(monkeypatch):
    """The prompt sent to the model must give it more than the bare variable
    name -- otherwise "電源實際持續可用容量" has no lexical bridge to
    `supply_continuous_current` at all."""
    captured = []
    monkeypatch.setattr(chat, 'call_ollama', _fake_call_ollama({}, captured))
    chat._extract_user_supplied('隨便一句話', True)
    assert captured, 'extraction prompt was never sent'
    prompt = captured[0]
    assert '實際持續可用容量' in prompt
    assert '新馬達' in prompt or '替換馬達' in prompt


def test_unclaimed_change_intent_detected_when_extraction_returns_nothing(c, manager, engineer, monkeypatch):
    """Case A's real failure mode: the model's extraction call returns {}
    (or omits the field) even though the message clearly marks a value for
    change -- the reply must say the change wasn't applied, not stay silent."""
    assert c.patch(f"{ROOT}/documents/DOC-PS/access", headers=manager,
                    json={"user_id": "engineer", "enabled": False}).status_code == 200
    monkeypatch.setattr(chat, 'call_ollama', _fake_call_ollama({}))
    resp = c.post(f"{ROOT}/chat", headers=engineer, json={
        "message": "電源實際持續可用容量降為8A（原本名目額定10A）。",
        "session_id": "m114-a", "use_local_llm": True,
    })
    data = resp.json()
    assert data["unclaimed_change_intents"] == ["8A"]
    assert "尚未成功套用" in data["reply"]
    assert "8A" in data["reply"]


def test_unclaimed_change_intent_absent_when_extraction_succeeds(c, engineer, monkeypatch):
    """When extraction DOES produce the candidate, there is nothing unclaimed
    -- this must not fire false positives on every change-intent phrase."""
    monkeypatch.setattr(chat, 'call_ollama', _fake_call_ollama({
        'motor_continuous_current': {'value': '9', 'unit': 'A'},
    }))
    resp = c.post(f"{ROOT}/chat", headers=engineer, json={
        "message": "如果改用9A馬達，其他條件不變，重新分析。",
        "session_id": "m114-b", "use_local_llm": True,
    })
    data = resp.json()
    assert data["unclaimed_change_intents"] == []
    assert "尚未成功套用" not in data["reply"]
    motor_evidence = next(e for e in data["checks"][0]["evidence"] if e["fact_key"] == "motor_continuous_current")
    assert motor_evidence["value"] == "9"


def test_multi_turn_correction_failure_is_reported_not_silently_ignored(c, engineer, monkeypatch):
    """Case C's exact real failure mode: turn 1 successfully sets the motor to
    11A; turn 2 asks to change it to 9A but extraction returns nothing for
    this turn -- the reply must say the 9A request wasn't applied, and the
    numbers must stay at the last successfully-applied value (11A), not
    silently look like nothing happened."""
    monkeypatch.setattr(chat, 'call_ollama', _fake_call_ollama({
        'motor_continuous_current': {'value': '11', 'unit': 'A'},
    }))
    turn1 = c.post(f"{ROOT}/chat", headers=engineer, json={
        "message": "馬達換成11A的新馬達。", "session_id": "m114-c", "use_local_llm": True,
    }).json()
    assert turn1["checks"][0]["numbers"]["total_current_a"] == "14"

    monkeypatch.setattr(chat, 'call_ollama', _fake_call_ollama({}))
    turn2 = c.post(f"{ROOT}/chat", headers=engineer, json={
        "message": "如果改用9A馬達，其他條件不變，重新分析。", "session_id": "m114-c", "use_local_llm": True,
    }).json()
    assert turn2["unclaimed_change_intents"] == ["9A"]
    assert "尚未成功套用" in turn2["reply"]
    # still 14A (11A motor), not silently recalculated and not fabricated as 9A/12A either
    assert turn2["checks"][0]["numbers"]["total_current_a"] == "14"


def test_plain_number_with_no_change_intent_is_not_flagged_as_unclaimed(c, engineer, monkeypatch):
    """A number with no replace/add language nearby is just an ordinary
    (M6-protected) restatement, not a missed change request -- must not be
    reported as "unclaimed" either."""
    monkeypatch.setattr(chat, 'call_ollama', _fake_call_ollama({}))
    resp = c.post(f"{ROOT}/chat", headers=engineer, json={
        "message": "馬達電流大概是11A左右。", "session_id": "m114-d", "use_local_llm": True,
    })
    data = resp.json()
    assert data["unclaimed_change_intents"] == []
    assert "尚未成功套用" not in data["reply"]


def test_m6_m7_m8_protections_still_intact(c, engineer, monkeypatch):
    """Regression guard: a plain restatement with no change-intent language
    still cannot override an already-'ok' document fact (M6), and the new
    USER_SUPPLIABLE_KEY_DESCRIPTIONS change does not alter any validation
    logic -- only the extraction prompt's wording."""
    monkeypatch.setattr(chat, 'call_ollama', _fake_call_ollama({
        'motor_continuous_current': {'value': '30', 'unit': 'A'},
    }))
    resp = c.post(f"{ROOT}/chat", headers=engineer, json={
        "message": "馬達電流是30A，請評估。", "session_id": "m114-e", "use_local_llm": True,
    })
    data = resp.json()
    motor_evidence = next(e for e in data["checks"][0]["evidence"] if e["fact_key"] == "motor_continuous_current")
    assert motor_evidence["origin"] == "document" and motor_evidence["value"] == "8"
