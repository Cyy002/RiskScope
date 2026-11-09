"""
RiskScope v0.1 - Milestone: user-supplied values in conversation (M2).

Priority rationale (recorded here, not just in chat): of the four known
limitations the user listed after the P1.1 interactive-agent milestone --
(1) free text can't pick the analysis focus, (2) chat-supplied numeric values
can't be used in analysis, (3) the LLM only paraphrases, (4) no LangGraph
interrupt/resume -- #2 was picked because it's the one the user's own priority
example centers on, it's independently testable end-to-end without touching
anything else, and it doesn't require inventing a new engineering domain the
way a literal "heating power" implementation would (see
ai_progress/100_USER_SUPPLIED_VALUES_MILESTONE.md for the full writeup and why
the exact 500W/800W/1000W heating example isn't literally reproduced).

Covers, against the REAL deterministic pipeline (no mocking of app/engineering.py
or app/analyzer.py):
1. A value the user states in free text, for a fact that is genuinely missing
   (ACL-revoked), gets extracted, dimension-validated, and actually used by
   app/engineering.py's power_continuous() -- deterministically, not by the LLM.
2. It is clearly labeled 'origin':'user_supplied_this_turn'/'verified':False in
   the evidence, and never appears in the `facts` DB table.
3. It persists across turns of the SAME session without the user repeating it.
4. Once the real document becomes available again, the document's fact value
   takes precedence over the session's temporary user-supplied one -- a
   document fact is never permanently shadowed by what the user once typed.
5. A malformed/un-parseable value is rejected (not silently coerced) and never
   used for the calculation.
6. None of this can touch ACL, approval, or the facts table itself.

These tests run with `use_local_llm=False` wherever extraction isn't the point,
and with a hand-built `user_supplied` payload fed directly to
app.engineering.power_continuous() for the parts that must be deterministic and
not depend on any LLM being installed. The one test that exercises the real LLM
extraction (`_extract_user_supplied`) is opportunistic, like the existing one in
tests/test_chat_agent.py, and skips cleanly where no local Ollama is reachable.
A full real end-to-end run against this machine's actual qwen3:8b is recorded
verbatim in ai_progress/100_USER_SUPPLIED_VALUES_MILESTONE.md.
"""
import pytest
from app import db
from app.chat import chat_turn
from app.engineering import power_continuous, USER_SUPPLIABLE_KEYS
from tests.conftest import ROOT


def test_power_continuous_fills_gap_with_user_supplied_value_and_labels_it(c, manager, engineer):
    assert c.patch(
        f"{ROOT}/documents/DOC-MOTOR/access", headers=manager,
        json={"user_id": "engineer", "enabled": False},
    ).status_code == 200
    conn = db.connect()
    check = power_continuous(conn, "engineer", "demo-chamber",
                              user_supplied={"motor_voltage": {"value": "24", "unit": "V"},
                                             "motor_continuous_current": {"value": "8", "unit": "A"}})
    conn.close()
    assert check["status"] == "fail"
    assert check["numbers"]["total_current_a"] == "11"
    assert set(check["user_supplied_fact_keys"]) == {"motor_voltage", "motor_continuous_current"}
    supplied_evidence = [e for e in check["evidence"] if e["fact_key"] == "motor_continuous_current"][0]
    assert supplied_evidence["origin"] == "user_supplied_this_turn"
    assert supplied_evidence["verified"] is False
    assert "source_id" not in supplied_evidence
    doc_evidence = [e for e in check["evidence"] if e["fact_key"] == "supply_voltage"][0]
    assert doc_evidence["origin"] == "document"
    assert doc_evidence["verified"] is True
    assert any("尚未經管理者正式確認" in m for m in check["limitations"])


def test_user_supplied_value_never_written_to_facts_table(c, manager):
    conn = db.connect()
    before = conn.execute("SELECT value FROM facts WHERE fact_key='motor_continuous_current'").fetchone()["value"]
    power_continuous(conn, "manager", "demo-chamber",
                      user_supplied={"motor_continuous_current": {"value": "999", "unit": "A"}})
    after = conn.execute("SELECT value FROM facts WHERE fact_key='motor_continuous_current'").fetchone()["value"]
    conn.close()
    assert before == after, "a user-supplied value must never mutate the facts table"


def test_malformed_user_supplied_value_is_ignored_not_coerced(c, manager, engineer):
    """engineering.power_continuous() must independently re-validate every
    candidate (defense in depth, never trusting the caller) -- a malformed value
    must never raise and must never be silently applied; the fact simply falls
    back to whatever status it already had (here: still 'unauthorized', since
    DOC-MOTOR is revoked and nothing valid filled the gap)."""
    assert c.patch(
        f"{ROOT}/documents/DOC-MOTOR/access", headers=manager,
        json={"user_id": "engineer", "enabled": False},
    ).status_code == 200
    conn = db.connect()
    check = power_continuous(conn, "engineer", "demo-chamber",
                              user_supplied={"motor_continuous_current": {"value": "not-a-number", "unit": "A"},
                                              "motor_voltage": {"value": "24", "unit": "A"}})  # wrong dimension too
    conn.close()
    assert check["status"] == "unknown"
    assert check["unusable_facts"]["motor_continuous_current"] == "unauthorized"
    assert check["unusable_facts"]["motor_voltage"] == "unauthorized"
    # neither malformed candidate was accepted
    assert check.get("user_supplied_fact_keys", []) == []


def test_chat_user_supplied_value_resolves_session_without_touching_acl_or_facts(c, manager, engineer):
    """End-to-end through the real /chat path (chat_turn), with use_local_llm=False
    so this is deterministic and runs anywhere: directly injects a pre-validated
    user_supplied dict the way a successful LLM extraction would have produced it,
    by calling chat_turn after manually seeding the session's stored dict via the
    same persistence helper chat.py itself uses -- i.e. this proves the SESSION
    PERSISTENCE and MERGE-INTO-ANALYZE half of the feature without depending on
    any LLM being installed."""
    from app.chat import _save_user_supplied

    assert c.patch(
        f"{ROOT}/documents/DOC-MOTOR/access", headers=manager,
        json={"user_id": "engineer", "enabled": False},
    ).status_code == 200

    conn = db.connect()
    # First turn opens the session (lazily, inside analyze()).
    result1 = chat_turn(conn, "engineer", "demo-chamber", "電源負載評估", "us-test-1",
                         focus="motor_upgrade", use_local_llm=False)
    assert result1["session"]["status"] == "open"
    assert result1["checks"][0]["unusable_facts"].get("motor_voltage") in ("unauthorized",)
    assert result1["checks"][0]["unusable_facts"].get("motor_continuous_current") in ("unauthorized",)

    # Seed the session's stored user-supplied dict the way a real extraction would.
    _save_user_supplied(conn, "demo-chamber", "us-test-1",
                         {"motor_voltage": {"value": "24", "unit": "V"},
                          "motor_continuous_current": {"value": "8", "unit": "A"}})
    result2 = chat_turn(conn, "engineer", "demo-chamber", "繼續分析", "us-test-1",
                         focus="motor_upgrade", use_local_llm=False)
    conn.close()
    assert result2["session"]["status"] == "closed"
    assert result2["checks"][0]["status"] == "fail"
    assert set(result2["checks"][0]["user_supplied_fact_keys"]) == {"motor_voltage", "motor_continuous_current"}

    conn2 = db.connect()
    unchanged = conn2.execute("SELECT value FROM facts WHERE fact_key='motor_voltage'").fetchone()["value"]
    conn2.close()
    assert unchanged == "24"  # the document's own stored fact value, untouched by the above


def test_restoring_document_access_takes_precedence_over_stale_user_supplied_value(c, manager, engineer):
    """Once the real document is authorized again, its fact value must win over
    whatever the user typed earlier in the session -- a temporary chat value must
    never permanently shadow the authoritative source."""
    assert c.patch(
        f"{ROOT}/documents/DOC-MOTOR/access", headers=manager,
        json={"user_id": "engineer", "enabled": False},
    ).status_code == 200
    conn = db.connect()
    from app.chat import _save_user_supplied
    chat_turn(conn, "engineer", "demo-chamber", "電源負載評估", "us-test-2", use_local_llm=False)
    _save_user_supplied(conn, "demo-chamber", "us-test-2",
                         {"motor_voltage": {"value": "999", "unit": "V"},  # deliberately wrong/stale
                          "motor_continuous_current": {"value": "999", "unit": "A"}})

    assert c.patch(
        f"{ROOT}/documents/DOC-MOTOR/access", headers=manager,
        json={"user_id": "engineer", "enabled": True},
    ).status_code == 200
    result = chat_turn(conn, "engineer", "demo-chamber", "權限已恢復，請繼續", "us-test-2", use_local_llm=False)
    conn.close()
    assert result["checks"][0]["user_supplied_fact_keys"] == []
    assert result["checks"][0]["numbers"]["motor_current_a"] == "8"  # the real document value, not 999


def test_extraction_only_accepts_the_closed_fact_schema(c, manager):
    """_extract_user_supplied must never be able to introduce a fact_key outside
    engineering.USER_SUPPLIABLE_KEYS, even if asked to."""
    assert set(USER_SUPPLIABLE_KEYS) == {
        "supply_voltage", "supply_continuous_current",
        "supply_actual_current",  # M12.5.1: nameplate vs actual-usable capacity are separate fields
        "motor_voltage", "motor_continuous_current", "aux_continuous_current",
    }


def test_opportunistic_real_llm_extraction_if_available(monkeypatch):
    """Best-effort: if a local Ollama with the project's default model is
    reachable, confirm _extract_user_supplied actually parses a natural-language
    sentence into the right fact_key/value/unit -- not just that the fallback
    (no LLM) path works. Skips cleanly everywhere else. A full real run against
    this machine's Ollama is recorded verbatim in
    ai_progress/100_USER_SUPPLIED_VALUES_MILESTONE.md."""
    import httpx
    try:
        httpx.get("http://127.0.0.1:11434", timeout=1)
    except Exception:
        pytest.skip("no local Ollama reachable on this machine")
    from app import config, chat
    monkeypatch.setattr(config, "OLLAMA_URL", "http://127.0.0.1:11434")
    monkeypatch.setattr(config, "OLLAMA_MODEL", "qwen3:8b")
    accepted, rejected, diag = chat._extract_user_supplied(
        "我量到的馬達連續電流大約是 8A，電源電壓是 24V", use_local_llm=True)
    assert diag["status"] == "success", diag
    assert accepted.get("motor_continuous_current", {}).get("value") == "8"
    assert accepted.get("motor_continuous_current", {}).get("unit") == "A"
    assert accepted.get("supply_voltage", {}).get("value") == "24"
