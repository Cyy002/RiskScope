"""
RiskScope v0.1 - P1 Milestone 1 targeted tests: persisted multi-turn session continuity.

Written by Claude alongside the app/ implementation (session_id on /analyze,
sessions table, app/analyzer.py's _open_session). Does not touch
tests/test_p1_multi_turn.py (Antigravity's file) or tests/test_acl_regression.py.

Covers:
1. A session genuinely missing a fact (revoked document, not a contrived string
   match) asks a follow-up and stays open.
2. After the manager restores access, continuing the SAME session_id resolves the
   previously-unknown topic without the caller re-stating anything, and the
   session closes.
3. A session cannot be hijacked by another user, and a closed session rejects
   further turns under the same id (must start a new one).
4. The existing human-approval pipeline (POST /actions -> POST /actions/{id}/review
   -> POST /actions/{id}/execute) is completely unaffected by session_id: no new
   code path lets an analysis or session auto-execute a simulated_tasks change.
5. A document revision bump between two turns of the SAME session makes the next
   turn re-detect staleness instead of silently reusing the first turn's pass/fail --
   each turn re-reads current data, it never replays a cached result.
"""
import pytest
from tests.conftest import ROOT


def test_session_open_on_genuinely_missing_fact_then_resolves_after_access_restored(c, manager, engineer):
    assert c.patch(
        f"{ROOT}/documents/DOC-PS/access", headers=manager,
        json={"user_id": "engineer", "enabled": False},
    ).status_code == 200

    turn1 = c.post(f"{ROOT}/analyze", headers=engineer,
                    json={"question": "電源負載評估", "focus": "motor_upgrade", "session_id": "sess-1"})
    assert turn1.status_code == 200
    d1 = turn1.json()
    assert d1["checks"][0]["status"] == "unknown"
    assert any(u["topic"] == "連續功率檢核" for u in d1["unknowns"])
    assert d1["session"]["id"] == "sess-1"
    assert d1["session"]["turn"] == 1
    assert d1["session"]["status"] == "open"
    assert "連續功率檢核" in d1["session"]["still_unknown"]

    row = c.get(f"{ROOT}/sessions/sess-1", headers=engineer)
    assert row.status_code == 200
    assert row.json()["session"]["status"] == "open"
    assert len(row.json()["turns"]) == 1

    assert c.patch(
        f"{ROOT}/documents/DOC-PS/access", headers=manager,
        json={"user_id": "engineer", "enabled": True},
    ).status_code == 200

    turn2 = c.post(f"{ROOT}/analyze", headers=engineer,
                    json={"question": "電源負載評估", "focus": "motor_upgrade", "session_id": "sess-1"})
    assert turn2.status_code == 200
    d2 = turn2.json()
    assert d2["checks"][0]["status"] in ("pass", "fail")
    assert d2["session"]["turn"] == 2
    assert "連續功率檢核" in d2["session"]["previously_unresolved"]
    assert "連續功率檢核" in d2["session"]["now_resolved"]
    assert d2["session"]["still_unknown"] == []
    assert d2["session"]["status"] == "closed"

    row2 = c.get(f"{ROOT}/sessions/sess-1", headers=engineer)
    assert row2.json()["session"]["status"] == "closed"
    assert len(row2.json()["turns"]) == 2


def test_session_closed_without_any_unknowns_from_the_start(c, engineer):
    turn = c.post(f"{ROOT}/analyze", headers=engineer,
                  json={"question": "電源負載評估", "focus": "motor_upgrade", "session_id": "sess-fresh"})
    assert turn.status_code == 200
    assert turn.json()["session"]["status"] == "closed"
    assert turn.json()["session"]["still_unknown"] == []


def test_session_cannot_be_hijacked_or_continued_after_close(c, manager, engineer):
    c.post(f"{ROOT}/analyze", headers=engineer,
           json={"question": "電源負載評估", "focus": "motor_upgrade", "session_id": "sess-owned"})

    hijack = c.post(f"{ROOT}/analyze", headers=manager,
                     json={"question": "電源負載評估", "focus": "motor_upgrade", "session_id": "sess-owned"})
    assert hijack.status_code == 403

    reopen = c.post(f"{ROOT}/analyze", headers=engineer,
                     json={"question": "電源負載評估", "focus": "motor_upgrade", "session_id": "sess-owned"})
    assert reopen.status_code == 409


def test_session_turn_detects_document_revision_change_not_cached_result(c, manager, engineer):
    """Within one still-open session (kept open by a genuinely missing fact), a
    document that changes mid-dialogue must show up as freshly-stale on the very
    next turn -- proving each turn re-reads current data instead of replaying
    whatever it computed on turn 1."""
    assert c.patch(
        f"{ROOT}/documents/DOC-AUX/access", headers=manager,
        json={"user_id": "engineer", "enabled": False},
    ).status_code == 200

    turn1 = c.post(f"{ROOT}/analyze", headers=engineer,
                    json={"question": "電源負載評估", "focus": "motor_upgrade", "session_id": "sess-stale"})
    assert turn1.status_code == 200
    d1 = turn1.json()
    assert d1["checks"][0]["status"] == "unknown"
    assert d1["checks"][0]["unusable_facts"].get("aux_continuous_current") == "unauthorized"
    assert "motor_continuous_current" not in d1["checks"][0]["unusable_facts"]
    assert d1["session"]["status"] == "open"

    doc = c.get(f"{ROOT}/documents", headers=manager).json()["documents"]
    motor_version = next(d["version"] for d in doc if d["id"] == "DOC-MOTOR")
    bump = c.patch(f"{ROOT}/documents/DOC-MOTOR", headers=manager,
                    json={"expected_version": motor_version, "body": "新版馬達規格：待重新確認電流額定值"})
    assert bump.status_code == 200

    turn2 = c.post(f"{ROOT}/analyze", headers=engineer,
                    json={"question": "電源負載評估", "focus": "motor_upgrade", "session_id": "sess-stale"})
    assert turn2.status_code == 200
    d2 = turn2.json()
    assert d2["checks"][0]["status"] == "unknown"
    # Turn 2 must reflect BOTH the still-unauthorized source and the newly-stale one --
    # a cached replay of turn 1 would only show the former.
    assert d2["checks"][0]["unusable_facts"].get("aux_continuous_current") == "unauthorized"
    assert d2["checks"][0]["unusable_facts"].get("motor_continuous_current") == "stale"
    assert d2["session"]["status"] == "open"


def test_analyze_without_session_id_is_fully_backward_compatible(c, engineer):
    resp = c.post(f"{ROOT}/analyze", headers=engineer,
                  json={"question": "電源負載評估", "focus": "motor_upgrade"})
    assert resp.status_code == 200
    assert "session" not in resp.json()


def test_approval_pipeline_unreachable_from_analyze_or_session(c, manager, engineer):
    """Session continuity must not create any path that bypasses manager review:
    an analysis (with or without session_id) never itself changes simulated_tasks,
    and the real actions pipeline still requires an explicit manager approval step."""
    analysis = c.post(f"{ROOT}/analyze", headers=engineer,
                       json={"question": "電源負載評估", "focus": "motor_upgrade",
                             "session_id": "sess-approval"}).json()

    action = c.post(f"{ROOT}/actions", headers=engineer, json={
        "analysis_id": analysis["analysis_id"], "task_id": "TEST-01",
        "new_state": "blocked", "idempotency_key": "session-continuity-check",
    })
    assert action.status_code == 200
    action_id = action.json()["action_id"]
    assert action.json()["state"] == "pending"

    exec_before_approval = c.post(f"{ROOT}/actions/{action_id}/execute", headers=manager)
    assert exec_before_approval.status_code == 409

    engineer_self_approve = c.post(f"{ROOT}/actions/{action_id}/review", headers=engineer, json={"approve": True})
    assert engineer_self_approve.status_code == 403

    approved = c.post(f"{ROOT}/actions/{action_id}/review", headers=manager, json={"approve": True})
    assert approved.status_code == 200
    assert approved.json()["state"] == "approved"

    executed = c.post(f"{ROOT}/actions/{action_id}/execute", headers=manager)
    assert executed.status_code == 200
    assert executed.json()["state"] == "executed"


def test_session_transcript_redacts_reply_after_source_revocation(c, manager, engineer):
    """Codex independently found this during his M3/M4 review round (2026-10-19,
    ai_progress/codex-review-ollama/review-probes.json 'history_acl'): M5 enriched
    `reply` to include real computed numbers (checks.numbers), which broke the
    original assumption in GET /sessions/{id} that `reply` never carries raw
    derived values -- GET /analyses/{id} correctly 403s after a source is
    revoked, but the session transcript endpoint kept serving the old numbers
    verbatim via `reply`. Fixed by re-running the same per-source ACL check
    _analysis_access uses, per turn, before returning reply/reply_source."""
    turn = c.post(f"{ROOT}/chat", headers=engineer,
                  json={"message": "電源負載評估", "session_id": "sess-redact", "use_local_llm": False})
    assert turn.status_code == 200
    assert "11" in turn.json()["reply"]  # sanity: the reply really does contain the number

    assert c.patch(
        f"{ROOT}/documents/DOC-PS/access", headers=manager,
        json={"user_id": "engineer", "enabled": False},
    ).status_code == 200

    analysis_id = turn.json()["analysis_id"]
    detail = c.get(f"{ROOT}/analyses/{analysis_id}", headers=engineer)
    assert detail.status_code == 403

    history = c.get(f"{ROOT}/sessions/sess-redact", headers=engineer)
    assert history.status_code == 200
    t = history.json()["turns"][0]
    assert t["redacted"] is True
    assert t["reply"] is None
    assert t["reply_source"] is None

    # manager still has access to DOC-PS -> must see it unredacted
    manager_view = c.get(f"{ROOT}/sessions/sess-redact", headers=manager)
    mt = manager_view.json()["turns"][0]
    assert mt["redacted"] is False
    assert "11" in mt["reply"]
