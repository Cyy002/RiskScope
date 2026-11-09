"""Regression tests for M7.1: M7's `_reply_is_trustworthy()` originally allowed
an approval claim whenever ANY action in the project had been approved
(app.chat._approved_action_exists), regardless of whether that approval had
anything to do with the current conversation. The user flagged this as a
real gap: Action A approved, Action B still pending, and an LLM reply about B
could still say "already approved" by pointing at A's approved row.

Fix under test: app.chat._approved_action_for_this_conversation() -- an
approval claim is only trusted when there is an approved `actions` row whose
`analysis_id` belongs to an analysis in THIS exact session, AND whose
task_id is literally named in the current message (never inferred from the
model's own claim, never just "same project"). All tests mock
app.chat.call_ollama directly and use the isolated tmp_path database from
tests/conftest.py -- the real runtime/credentials are never touched, and no
action is approved except through the existing /actions + /actions/{id}/review
endpoints under the normal manager-only review gate.
"""
from app import chat
from tests.conftest import ROOT


def _fake_call_ollama(reply_text):
    def fake(prompt, timeout=30, keep_alive='10m'):
        if '只負責從使用者訊息' in prompt:
            return '{}', {'status': 'success', 'elapsed_seconds': 0.01}
        return reply_text, {'status': 'success', 'elapsed_seconds': 0.01}
    return fake


def _open_session_turn(c, manager, engineer, session_id):
    """DOC-MOTOR revoked so the check stays 'unknown' and the session stays
    'open' for a follow-up turn -- these tests are only about approval
    linkage, not engineering check status."""
    assert c.patch(f"{ROOT}/documents/DOC-MOTOR/access", headers=manager,
                    json={"user_id": "engineer", "enabled": False}).status_code == 200
    return c.post(f"{ROOT}/chat", headers=engineer, json={
        "message": "請評估馬達升級", "session_id": session_id, "use_local_llm": False,
    }).json()


def _approve_task(c, manager, engineer, analysis_id, task_id, idempotency_key):
    action = c.post(f"{ROOT}/actions", headers=engineer, json={
        "analysis_id": analysis_id, "task_id": task_id,
        "new_state": "blocked", "idempotency_key": idempotency_key,
    }).json()
    assert c.post(f"{ROOT}/actions/{action['action_id']}/review", headers=manager,
                   json={"approve": True}).json()["state"] == "approved"
    return action


def test_approved_action_a_does_not_leak_into_discussion_of_unapproved_action_b(c, manager, engineer, monkeypatch):
    turn1 = _open_session_turn(c, manager, engineer, "link-ab")
    _approve_task(c, manager, engineer, turn1["analysis_id"], "TEST-01", "link-ab-001")

    # Same session, but this turn is explicitly about RELEASE-01 (never approved).
    monkeypatch.setattr(chat, 'call_ollama',
                         _fake_call_ollama('RELEASE-01 已核准，可以立即執行。'))
    resp = c.post(f"{ROOT}/chat", headers=engineer, json={
        "message": "RELEASE-01 現在可以執行了嗎？", "session_id": "link-ab", "use_local_llm": True,
    })
    data = resp.json()
    assert data["reply_source"] == "deterministic_template"
    assert data["llm_diagnostic"]["reply"]["status"] == "rejected_inconsistent"


def test_approved_action_linked_to_this_conversation_is_shown_correctly(c, manager, engineer, monkeypatch):
    turn1 = _open_session_turn(c, manager, engineer, "link-a-real")
    _approve_task(c, manager, engineer, turn1["analysis_id"], "TEST-01", "link-a-real-001")

    monkeypatch.setattr(chat, 'call_ollama',
                         _fake_call_ollama('TEST-01 已核准，後續可以依核准結果安排作業。'))
    resp = c.post(f"{ROOT}/chat", headers=engineer, json={
        "message": "TEST-01 現在狀況如何？", "session_id": "link-a-real", "use_local_llm": True,
    })
    data = resp.json()
    assert data["reply_source"] == "llm_phrased"
    assert data["llm_diagnostic"]["reply"]["status"] == "success"
    assert "核准" in data["reply"]


def test_approval_claim_with_no_discussed_task_id_is_rejected(c, manager, engineer, monkeypatch):
    turn1 = _open_session_turn(c, manager, engineer, "link-no-task")
    _approve_task(c, manager, engineer, turn1["analysis_id"], "TEST-01", "link-no-task-001")

    # The message never names any task_id at all -- cannot reliably tell what
    # "already approved" would even refer to.
    monkeypatch.setattr(chat, 'call_ollama', _fake_call_ollama('已經核准了，可以繼續。'))
    resp = c.post(f"{ROOT}/chat", headers=engineer, json={
        "message": "可以繼續嗎？", "session_id": "link-no-task", "use_local_llm": True,
    })
    data = resp.json()
    assert data["reply_source"] == "deterministic_template"
    assert data["llm_diagnostic"]["reply"]["status"] == "rejected_inconsistent"


def test_approval_from_a_different_session_does_not_apply(c, manager, engineer, monkeypatch):
    turn1 = _open_session_turn(c, manager, engineer, "link-session-1")
    _approve_task(c, manager, engineer, turn1["analysis_id"], "TEST-01", "link-session-1-001")

    # A brand new, unrelated session -- same project, same task_id mentioned,
    # but this conversation never touched that approval.
    monkeypatch.setattr(chat, 'call_ollama', _fake_call_ollama('TEST-01 已核准，可以執行。'))
    resp = c.post(f"{ROOT}/chat", headers=engineer, json={
        "message": "TEST-01 的狀態如何？", "session_id": "link-session-2", "use_local_llm": True,
    })
    data = resp.json()
    assert data["reply_source"] == "deterministic_template"
    assert data["llm_diagnostic"]["reply"]["status"] == "rejected_inconsistent"


def test_unapproved_action_still_correctly_reports_pending(c, manager, engineer, monkeypatch):
    turn1 = _open_session_turn(c, manager, engineer, "link-pending")
    # Requested but never reviewed -- stays 'pending', never 'approved'.
    c.post(f"{ROOT}/actions", headers=engineer, json={
        "analysis_id": turn1["analysis_id"], "task_id": "TEST-01",
        "new_state": "blocked", "idempotency_key": "link-pending-001",
    })

    monkeypatch.setattr(chat, 'call_ollama', _fake_call_ollama('TEST-01 尚未核准，仍待管理者審核。'))
    resp = c.post(f"{ROOT}/chat", headers=engineer, json={
        "message": "TEST-01 現在核准了嗎？", "session_id": "link-pending", "use_local_llm": True,
    })
    data = resp.json()
    # a denial ("尚未核准") is not an approval claim -- M7's negation lookback
    # already covers this, M7.1 must not regress it.
    assert data["reply_source"] == "llm_phrased"
    assert data["llm_diagnostic"]["reply"]["status"] == "success"


def test_m7_safety_and_numeric_fallback_still_work_unchanged(c, engineer, monkeypatch):
    """M7.1 must not weaken the existing M7 safety-claim / numeric-contradiction
    checks -- this is the same scenario as test_b in
    test_llm_reply_trustworthiness.py, re-asserted here as a direct regression
    guard for this round's change."""
    monkeypatch.setattr(chat, 'call_ollama',
                         _fake_call_ollama('已確認安全通過，沒有風險，可以直接執行升級。'))
    resp = c.post(f"{ROOT}/chat", headers=engineer, json={
        "message": "請評估馬達升級", "session_id": "link-m7-safety", "use_local_llm": True,
    })
    data = resp.json()
    assert data["checks"][0]["status"] == "fail"
    assert data["reply_source"] == "deterministic_template"
    assert data["llm_diagnostic"]["reply"]["status"] == "rejected_inconsistent"
