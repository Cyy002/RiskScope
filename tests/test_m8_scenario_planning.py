"""Regression tests for M8: the user-reported bug that RiskScope kept
re-evaluating the OLD engineering spec even after the user explicitly
proposed a new one (e.g. "replace the motor with an 11A unit, keep the aux
load, the schedule can't slip") -- app/engineering.py's power_continuous()
only ever let a user-supplied value fill a genuine gap (missing/stale/
unauthorized); it never let one supersede an already-authorized ('ok')
document fact, no matter how explicitly the user asked for that change.

Fix under test:
- app.chat._change_intent_mode() -- deterministic, keyword-based detection of
  explicit change-intent language ("換成"/"更換"/... for a component swap,
  "新增"/"額外"/... for an added load) right next to a grounded number. A
  plain restatement with no such language nearby still cannot override an
  'ok' fact (M6/M7 protection unchanged).
- app.engineering.power_continuous()'s new `mode` handling: 'replace' swaps
  in the user's value for a hypothetical new-plan calculation; 'add' sums it
  onto the existing authorized value. Either way the result is labelled
  'proposed_change' in evidence (never written to `facts`), and the pure
  document baseline is attached alongside it (`check['baseline']`) so the
  reply can compare before/after instead of just silently replacing one
  number with another.
- app.analyzer._open_session()'s continuation fix: a fully-specified
  analysis (all facts already 'ok', nothing missing) resolves and closes the
  session on turn 1 -- previously ANY further turn under that session_id,
  including one proposing a brand new scenario, got a hard 409 and could
  never be evaluated at all. Now a turn carrying a non-empty `user_supplied`
  (only ever true via app/chat.py's extraction -- the plain /analyze route
  never supplies one) is let back in regardless of 'closed'; a bare repeat
  with nothing new still 409s exactly as before (see
  tests/test_session_continuity.py's existing hijack/closed-session test,
  untouched by this fix).

M8 final round (3 more issues, all found via Codex's independent review):
- app.analyzer._is_repeat_question() -- a closed session must also accept a
  genuine follow-up with NO new number at all (explaining a risk, comparing
  options, asking what's missing) -- gating only on "did this turn supply a
  new value" would block all of that. The deterministic, non-gameable
  signal used instead: is this turn's question text a byte-for-byte repeat
  of one already asked in this session? If not, it's accepted as meaningful
  even with zero new numbers; an exact repeat with nothing new still 409s.
- app.chat._change_intent_mode()'s proximity fix -- a single sentence
  combining BOTH kinds of intent for two different numbers ("馬達替換成11A，
  另外新增一個2A裝置") used to let "新增" anywhere in a wide fixed window win
  for EVERY number in the sentence, including the one next to "替換成". Fixed
  to pick whichever keyword occurrence is textually closest to each specific
  number, so replace and add are never confused with each other.
- app.engineering.power_continuous()'s pending_additions -- 'add' mode with
  NO authorized baseline to add onto (the document fact is itself missing/
  stale/unauthorized) used to substitute the bare delta in as if it WERE the
  whole load (e.g. "新增 2A" on an unknown aux load became a 2A total aux
  load). Now the fact stays exactly as unusable as before and the known
  increment is reported separately in `result['pending_additions']`,
  surfaced in the reply as "記錄了新增量, 但基準未知, 請補充" instead of a
  fabricated total.

Demo project facts (unchanged by any test here): 24V supply, nameplate
10A continuous limit, 8A motor, 3A aux load -- the same baseline numbers
used throughout this project's history (11A/264W fail scenario).

All tests mock app.chat.call_ollama directly (no network, no real Ollama) and
use the isolated tmp_path database from tests/conftest.py -- the real
runtime/credentials are never touched.
"""
import json
from decimal import Decimal
from app import chat
from tests.conftest import ROOT


def _fake_call_ollama(extraction_json):
    """Mocks extraction (so a controlled candidate reaches _extract_user_supplied)
    but reports the reply-phrasing call as unavailable, so chat_turn() falls
    back to its deterministic template -- the one guaranteed-present path
    whose content these tests can assert on directly."""
    def fake(prompt, timeout=30, keep_alive='10m'):
        if '只負責從使用者訊息' in prompt:
            return json.dumps(extraction_json), {'status': 'success', 'elapsed_seconds': 0.01}
        return None, {'status': 'connection_error', 'detail': 'simulated: no reply-phrasing in this test'}
    return fake


def test_a_replacing_motor_and_supply_uses_the_new_plan_not_the_old_spec(c, engineer, monkeypatch):
    """The acceptance case: replace the motor (8A -> 11A) and correct the
    supply's real sustained capacity (nameplate 10A -> actual 8A), aux load
    unchanged. Must evaluate 11+3=14A / 24x14=336W against the NEW plan, not
    silently keep using the old 8A motor or the 10A nameplate."""
    monkeypatch.setattr(chat, 'call_ollama', _fake_call_ollama({
        'motor_continuous_current': {'value': '11', 'unit': 'A'},
        'supply_continuous_current': {'value': '8', 'unit': 'A'},
    }))
    resp = c.post(f"{ROOT}/chat", headers=engineer, json={
        "message": "我們打算把馬達換成11A的新馬達；電源實際持續可用容量降為8A（原本名目額定10A）；"
                    "輔助負載維持不變；交期不能延後。",
        "session_id": "m8-a", "use_local_llm": True,
    })
    data = resp.json()
    check = data["checks"][0]
    assert data["user_supplied_accepted_this_turn"] == {
        'motor_continuous_current': {'value': '11', 'unit': 'A', 'mode': 'replace'},
        # M12.5.1: the model mis-files "實際持續可用容量" under the nameplate key (as this
        # mock does); the wording-based request analysis re-keys it to the actual-capacity field.
        'supply_actual_current': {'value': '8', 'unit': 'A', 'mode': 'replace'},
    }
    n = check["numbers"]
    assert n["nameplate_limit_current_a"] == "10" and n["actual_limit_current_a"] == "8"
    assert n["total_current_a"] == "14"
    assert n["total_power_w"] == "336"
    assert n["limit_current_a"] == "8"
    assert check["status"] == "fail"
    # the untouched aux load still comes straight from the document, unaffected
    aux_evidence = next(e for e in check["evidence"] if e["fact_key"] == "aux_continuous_current")
    assert aux_evidence["origin"] == "document" and aux_evidence["value"] == "3"
    # both overrides are clearly labelled as a proposed scenario, never a document fact
    motor_evidence = next(e for e in check["evidence"] if e["fact_key"] == "motor_continuous_current")
    assert motor_evidence["origin"] == "proposed_change" and motor_evidence["verified"] is False
    assert motor_evidence["baseline_value"] == "8"
    # the pure document baseline (no overrides) is attached for comparison
    baseline = check["baseline"]
    assert baseline["numbers"]["total_current_a"] == "11"  # 8 (old motor) + 3 (aux)
    assert baseline["numbers"]["limit_current_a"] == "10"  # nameplate, untouched
    assert baseline["status"] == "fail"
    # the deterministic reply must name the comparison, not just one number
    assert "336" in data["reply"] and "40" in data["reply"] and "75" in data["reply"]
    assert "新方案" in data["reply"]


def test_b_plain_restatement_without_change_intent_still_cannot_override_ok_fact(c, engineer, monkeypatch):
    """M6/M7 regression guard: restating a number with NO change-intent
    language nearby must still be rejected from touching an already-'ok'
    document fact -- M8 only ever expands the override path when the user's
    own text explicitly asks for a change."""
    monkeypatch.setattr(chat, 'call_ollama', _fake_call_ollama({
        'motor_continuous_current': {'value': '11', 'unit': 'A'},
    }))
    resp = c.post(f"{ROOT}/chat", headers=engineer, json={
        "message": "馬達電流是11A，請評估。", "session_id": "m8-b", "use_local_llm": True,
    })
    data = resp.json()
    check = data["checks"][0]
    assert check["user_supplied_fact_keys"] == []
    assert "baseline" not in check
    motor_evidence = next(e for e in check["evidence"] if e["fact_key"] == "motor_continuous_current")
    assert motor_evidence["origin"] == "document" and motor_evidence["value"] == "8"


def test_c_adding_a_new_load_sums_onto_the_existing_one_instead_of_replacing_it(c, engineer, monkeypatch):
    """支援「新增負載」：the aux load gets an explicit addition (not a swap) --
    the existing 3A document value must still be visible as the baseline
    that got added to, not discarded."""
    monkeypatch.setattr(chat, 'call_ollama', _fake_call_ollama({
        'aux_continuous_current': {'value': '2', 'unit': 'A'},
    }))
    resp = c.post(f"{ROOT}/chat", headers=engineer, json={
        "message": "我們想再新增一個2A的輔助負載。", "session_id": "m8-c", "use_local_llm": True,
    })
    data = resp.json()
    check = data["checks"][0]
    assert data["user_supplied_accepted_this_turn"] == {
        'aux_continuous_current': {'value': '2', 'unit': 'A', 'mode': 'add'},
    }
    aux_evidence = next(e for e in check["evidence"] if e["fact_key"] == "aux_continuous_current")
    assert aux_evidence["origin"] == "proposed_change"
    assert aux_evidence["value"] == "5"  # 3 (existing) + 2 (newly added)
    assert aux_evidence["change_mode"] == "add"
    assert aux_evidence["baseline_value"] == "3"
    # motor (8A) unchanged + new combined aux (5A) = 13A, still against the untouched 10A limit
    assert check["numbers"]["total_current_a"] == "13"
    assert check["baseline"]["numbers"]["total_current_a"] == "11"


def test_d_unrelated_missing_information_is_still_never_fabricated(c, manager, engineer, monkeypatch):
    """Proposing a change to one component must not loosen the existing
    protection for a genuinely-missing OTHER fact -- aux access is revoked
    (unauthorized), and the motor replacement proposal must not cause the
    engine to invent a number for it."""
    assert c.patch(f"{ROOT}/documents/DOC-AUX/access", headers=manager,
                    json={"user_id": "engineer", "enabled": False}).status_code == 200
    monkeypatch.setattr(chat, 'call_ollama', _fake_call_ollama({
        'motor_continuous_current': {'value': '11', 'unit': 'A'},
    }))
    resp = c.post(f"{ROOT}/chat", headers=engineer, json={
        "message": "馬達換成11A的新馬達，輔助負載維持不變。", "session_id": "m8-d", "use_local_llm": True,
    })
    data = resp.json()
    check = data["checks"][0]
    assert check["status"] == "unknown"
    assert check["unusable_facts"] == {"aux_continuous_current": "unauthorized"}
    motor_evidence = next(e for e in check["evidence"] if e["fact_key"] == "motor_continuous_current")
    assert motor_evidence["origin"] == "proposed_change" and motor_evidence["value"] == "11"


def test_e_multi_turn_correction_updates_the_proposed_plan(c, engineer, monkeypatch):
    """多輪追問能延續、修正：turn 1 proposes an 11A motor; turn 2, in the SAME
    session, corrects it to a 9A motor instead -- the second turn's figure
    must win, not silently keep using the first turn's proposal."""
    monkeypatch.setattr(chat, 'call_ollama', _fake_call_ollama({
        'motor_continuous_current': {'value': '11', 'unit': 'A'},
    }))
    turn1 = c.post(f"{ROOT}/chat", headers=engineer, json={
        "message": "馬達先換成11A的新馬達試算看看。", "session_id": "m8-e", "use_local_llm": True,
    }).json()
    assert turn1["checks"][0]["numbers"]["total_current_a"] == "14"  # 11+3

    monkeypatch.setattr(chat, 'call_ollama', _fake_call_ollama({
        'motor_continuous_current': {'value': '9', 'unit': 'A'},
    }))
    turn2 = c.post(f"{ROOT}/chat", headers=engineer, json={
        "message": "改一下，馬達改成9A的規格重新試算。", "session_id": "m8-e", "use_local_llm": True,
    }).json()
    check2 = turn2["checks"][0]
    assert check2["numbers"]["total_current_a"] == "12"  # 9+3, not 14
    assert check2["status"] == "fail"  # 12 > nameplate 10A
    motor_evidence = next(e for e in check2["evidence"] if e["fact_key"] == "motor_continuous_current")
    assert motor_evidence["value"] == "9"


def test_f_proposed_plan_persists_across_a_turn_that_does_not_repeat_it(c, engineer, monkeypatch):
    """延續：once accepted in turn 1 (with explicit change intent), the
    proposed motor replacement must still apply in turn 2 even though turn
    2's message never repeats "換成" or the number."""
    monkeypatch.setattr(chat, 'call_ollama', _fake_call_ollama({
        'motor_continuous_current': {'value': '11', 'unit': 'A'},
    }))
    turn1 = c.post(f"{ROOT}/chat", headers=engineer, json={
        "message": "馬達換成11A的新馬達。", "session_id": "m8-f", "use_local_llm": True,
    }).json()
    assert turn1["checks"][0]["numbers"]["total_current_a"] == "14"

    monkeypatch.setattr(chat, 'call_ollama', _fake_call_ollama({}))
    turn2 = c.post(f"{ROOT}/chat", headers=engineer, json={
        "message": "請再確認一次結論就好。", "session_id": "m8-f", "use_local_llm": True,
    }).json()
    assert turn2["user_supplied_accepted_this_turn"] == {}
    assert turn2["checks"][0]["numbers"]["total_current_a"] == "14"
    assert turn2["checks"][0]["user_supplied_fact_keys"] == ["motor_continuous_current"]


def test_g_a_fully_specified_turn_1_no_longer_409s_a_followup_proposal(c, engineer, monkeypatch):
    """This is the exact reported bug: turn 1 has every fact already 'ok'
    (nothing missing), so the deterministic check resolves immediately and
    the session closes on turn 1 -- before M8's session fix, ANY further
    turn under this session_id, including one proposing a brand new motor,
    got a hard 409 and the user could never follow up at all."""
    monkeypatch.setattr(chat, 'call_ollama', _fake_call_ollama({}))
    turn1 = c.post(f"{ROOT}/chat", headers=engineer, json={
        "message": "請評估目前的馬達升級方案。", "session_id": "m8-g", "use_local_llm": True,
    })
    assert turn1.status_code == 200
    assert turn1.json()["session"]["status"] == "closed"

    monkeypatch.setattr(chat, 'call_ollama', _fake_call_ollama({
        'motor_continuous_current': {'value': '11', 'unit': 'A'},
    }))
    turn2 = c.post(f"{ROOT}/chat", headers=engineer, json={
        "message": "我想把馬達換成11A的新馬達，重新評估。", "session_id": "m8-g", "use_local_llm": True,
    })
    assert turn2.status_code == 200, turn2.text
    assert turn2.json()["checks"][0]["numbers"]["total_current_a"] == "14"


def test_h_a_bare_repeat_with_nothing_new_still_cannot_reopen_a_closed_session(c, engineer, monkeypatch):
    """Regression guard, not a new M8 requirement: a session closed with no
    engineering value ever supplied, and no new value in the follow-up
    either, must still 409 -- matching
    tests/test_session_continuity.py::test_session_cannot_be_hijacked_or_continued_after_close
    exactly, just exercised through /chat instead of the plain /analyze
    route this time."""
    monkeypatch.setattr(chat, 'call_ollama', _fake_call_ollama({}))
    c.post(f"{ROOT}/chat", headers=engineer, json={
        "message": "請評估目前的馬達升級方案。", "session_id": "m8-h", "use_local_llm": True,
    })
    again = c.post(f"{ROOT}/chat", headers=engineer, json={
        "message": "請評估目前的馬達升級方案。", "session_id": "m8-h", "use_local_llm": True,
    })
    assert again.status_code == 409


def test_i_a_genuine_followup_with_no_new_number_still_reopens_a_closed_session(c, engineer, monkeypatch):
    """A fully-specified turn 1 closes the session immediately (same as test
    g), but the user should still be able to ask something genuinely
    different afterwards -- questioning the recommendation, asking what's
    missing -- with zero new engineering numbers. This must NOT be gated on
    "did this turn supply a number"."""
    monkeypatch.setattr(chat, 'call_ollama', _fake_call_ollama({}))
    turn1 = c.post(f"{ROOT}/chat", headers=engineer, json={
        "message": "請評估目前的馬達升級方案。", "session_id": "m8-i", "use_local_llm": True,
    })
    assert turn1.json()["session"]["status"] == "closed"

    followup = c.post(f"{ROOT}/chat", headers=engineer, json={
        "message": "為什麼這個方案不符合限制？還需要補充什麼驗證資料才能核准？",
        "session_id": "m8-i", "use_local_llm": True,
    })
    assert followup.status_code == 200, followup.text
    assert followup.json()["checks"][0]["status"] == "fail"


def test_j_combined_replace_and_add_in_one_sentence_are_not_confused(c, engineer, monkeypatch):
    """支援同句「替換＋新增」：換掉馬達 and 新增一個獨立負載 in one message must
    apply the right mode to each number -- never let "新增" anywhere in the
    sentence make the replace value get summed instead of swapped, and never
    double-count the old 8A motor."""
    monkeypatch.setattr(chat, 'call_ollama', _fake_call_ollama({
        'motor_continuous_current': {'value': '11', 'unit': 'A'},
        'aux_continuous_current': {'value': '2', 'unit': 'A'},
    }))
    resp = c.post(f"{ROOT}/chat", headers=engineer, json={
        "message": "將原本8A馬達替換成11A，另外新增一個2A裝置。",
        "session_id": "m8-j", "use_local_llm": True,
    })
    data = resp.json()
    check = data["checks"][0]
    motor_evidence = next(e for e in check["evidence"] if e["fact_key"] == "motor_continuous_current")
    aux_evidence = next(e for e in check["evidence"] if e["fact_key"] == "aux_continuous_current")
    assert motor_evidence["change_mode"] == "replace" and motor_evidence["value"] == "11"
    assert aux_evidence["change_mode"] == "add" and aux_evidence["value"] == "5"  # 3 (existing) + 2, not 2 alone
    # 11 (new motor, not 8+11) + 5 (3+2, not just 2) = 16 -- nothing double-counted
    assert check["numbers"]["total_current_a"] == "16"


def test_k_adding_to_an_unknown_baseline_never_fabricates_a_total(c, manager, engineer, monkeypatch):
    """原負載未知時的新增操作：aux access is revoked (unauthorized, so there is
    no authorized baseline at all), and the user says "新增2A" -- the 2A must
    never be substituted in as if it were the whole aux load; the check must
    stay 'unknown' and the known increment must be reported separately so a
    reply can ask for the missing baseline instead of inventing one."""
    assert c.patch(f"{ROOT}/documents/DOC-AUX/access", headers=manager,
                    json={"user_id": "engineer", "enabled": False}).status_code == 200
    monkeypatch.setattr(chat, 'call_ollama', _fake_call_ollama({
        'aux_continuous_current': {'value': '2', 'unit': 'A'},
    }))
    resp = c.post(f"{ROOT}/chat", headers=engineer, json={
        "message": "輔助負載原本不清楚，但我們想新增2A的裝置。",
        "session_id": "m8-k", "use_local_llm": True,
    })
    data = resp.json()
    check = data["checks"][0]
    assert check["status"] == "unknown"
    assert "numbers" not in check
    assert check["unusable_facts"] == {"aux_continuous_current": "unauthorized"}
    pending = check["pending_additions"]
    assert len(pending) == 1
    assert pending[0]["fact_key"] == "aux_continuous_current"
    assert pending[0]["added_value"] == "2" and pending[0]["added_unit"] == "A"
    # the deterministic reply must mention the known increment, never claim a total
    assert "2A" in data["reply"] and "基準" in data["reply"]
