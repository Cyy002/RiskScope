"""
RiskScope v0.1 - P1 Multi-Turn Agent Pre-Implementation Specification & Test Suite
==================================================================================
Prepared by Antigravity (副手工程師) for P1 First Milestone.
Core code in app/ remains untouched.

2026-10-18 22:55 update (Claude, with explicit user authorization -- Antigravity hit
her usage quota and Copilot cannot write files in this session, so the user asked
Claude to take over the remaining work rather than leave it blocked):

Scenario 1, 2 and 3 below were failing against the real implementation. Per the
user's explicit instruction, the fix is to correct the test's premise/API usage to
match the actual product requirement, NOT to weaken the assertions or invent a new
app/ surface to satisfy them:

- Scenario 1 asserted `unknowns` must mention specific words, but the original
  payload used the seed project's fully-provisioned default data, so the
  deterministic engine correctly returns a definite pass/fail, not "unknown" --
  there was no missing data to detect. Fixed by actually revoking the engineer's
  access to DOC-PS first (the same real-ACL-gap technique already used in
  tests/test_acl_regression.py and tests/test_session_continuity.py), so the test
  now exercises a genuine information gap instead of asserting a string the engine
  never produces for well-provisioned input. The original assertions are otherwise
  unchanged.
- Scenario 2 and 3 assumed an Actions API that was never implemented:
  `PATCH /actions/{id}` with `{"status": "approved"}`, and `POST /actions` with
  `title`/`task_key`/`delta` fields. The actual, already-existing, already-tested
  (tests/test_core.py) contract is `POST /actions` with
  `analysis_id`/`task_id`/`new_state`/`idempotency_key`, followed by
  `POST /actions/{id}/review` with `{"approve": bool}`, then
  `POST /actions/{id}/execute`. There is no missing product feature here --
  "unauthorized operations must not execute" and "stale data must block execution"
  are both already enforced by the existing pipeline (see test_core.py's
  test_stale_approval_after_event / test_stale_execute_after_approval /
  test_reject_action). Fixed both scenarios to exercise the real endpoints, now
  explicitly through a session_id so they double as the P1 "session dialogue must
  not bypass human approval" check the file's docstring describes. No parallel
  Actions API was added to app/.

Covers:
1. Session Initialization & Needs-Info Detection:
   When input problem is underspecified or quantitative data is missing,
   the Agent responds with `status='needs_info'` (or `clarification_needed`),
   preserving session context and asking targeted follow-up questions.
2. Context Continuation & State Resume:
   User supplies the requested clarification / supplementary parameter;
   the Agent resumes from prior session state without starting from scratch.
3. Provenance & Deterministic Tool Trace Retention:
   Multi-turn interactions retain full auditability of tool_calls, quantitative
   constraints, and document ACLs.
4. Stale Session Invalidation on Data Revision Change:
   If project data_revision updates between turns, the session must re-validate
   and reject blind execution against outdated baselines.
5. Strict Approval Enforcement:
   Actions proposed during multi-turn dialogue remain 'pending' and strictly require
   human manager approval before simulated execution.
"""

import pytest
from app import db
from tests.conftest import ROOT


@pytest.mark.p1_agent
def test_p1_session_identifies_missing_data_and_asks_followup(c, manager, engineer):
    """
    P1 Scenario 1:
    When an analysis request lacks critical operational parameters (e.g., duty cycle,
    peak startup current), the system detects missing information and initiates a
    persisted session with active questions rather than an unguided final report.
    """
    # Genuinely create a missing/unauthorized fact first -- the default seed project
    # has all five continuous-power facts fully authorized, so a plain question
    # against it correctly yields a definite pass/fail, never "unknown". Revoking a
    # source document is the same real-data technique used throughout
    # tests/test_acl_regression.py and tests/test_session_continuity.py.
    assert c.patch(
        f"{ROOT}/documents/DOC-PS/access", headers=manager,
        json={"user_id": "engineer", "enabled": False},
    ).status_code == 200

    payload = {
        "question": "評估更換高轉速主軸馬達之可行性",
        "focus": "motor_upgrade",
        "session_id": "p1-scenario-1",
    }

    resp = c.post(f"{ROOT}/analyze", headers=engineer, json=payload)
    assert resp.status_code == 200
    data = resp.json()

    # Verify core P1 multi-turn state requirements:
    # 1. Distinguishes unknowns and targeted questions
    assert "questions_to_manager" in data or "questions_to_user" in data
    questions = data.get("questions_to_user") or data.get("questions_to_manager")
    assert len(questions) > 0, "Agent must identify missing information and generate questions"

    # 2. Unknowns explicitly enumerated
    assert "unknowns" in data
    assert any("連續功率" in str(u) or "啟動" in str(u) or "規格" in str(u) for u in data["unknowns"]), (
        "Agent must explicitly identify unknown parameters"
    )

    # 3. Decision status remains guarded
    assert data["decision_status"] == "requires_human_review"

    # 4. P1 session bookkeeping: the dialogue must stay open while something is unknown.
    assert data["session"]["id"] == "p1-scenario-1"
    assert data["session"]["status"] == "open"


@pytest.mark.p1_agent
def test_p1_stale_data_revision_blocks_stale_session_execution(c, manager, engineer):
    """
    P1 Scenario 2:
    Verify that if a project's data revision changes while a decision session is active,
    the session detects staleness and refuses blind execution without re-check.

    Exercises the real Actions contract (POST /actions -> POST /actions/{id}/review),
    not the PATCH /actions/{id} shape this test originally assumed -- see module
    docstring. A stale review returns HTTP 200 with state="stale" in the body (the
    existing, already-tested behavior in tests/test_core.py), and execute is what
    returns 409; this test asserts both halves instead of guessing a status code.
    """
    # 1. Engineer runs initial analysis under a session, as P1 intends.
    analysis_resp = c.post(
        f"{ROOT}/analyze",
        headers=engineer,
        json={"question": "電源負載", "focus": "motor_upgrade", "session_id": "p1-scenario-2"},
    )
    assert analysis_resp.status_code == 200
    initial_analysis = analysis_resp.json()

    # 2. Engineer requests a simulated change based on that analysis (real contract).
    action_resp = c.post(
        f"{ROOT}/actions",
        headers=engineer,
        json={
            "analysis_id": initial_analysis["analysis_id"],
            "task_id": "TEST-01",
            "new_state": "blocked",
            "idempotency_key": "p1-scenario-2-stale",
        },
    )
    assert action_resp.status_code == 200
    action_id = action_resp.json()["action_id"]
    assert action_resp.json()["state"] == "pending"

    # 3. Project data revision updates (e.g. document modification) while the action
    #    is still pending -- this must invalidate blind approval/execution.
    patch_resp = c.patch(
        f"{ROOT}/documents/DOC-PS",
        headers=manager,
        json={"expected_version": 1, "body": "新版電源規格：更新溫度降額參數"},
    )
    assert patch_resp.status_code == 200

    # 4. Reviewing a stale action does not silently approve it: the pipeline marks it
    #    'stale' (200 OK, not a false 'approved'), and execute is hard-blocked (409).
    review_resp = c.post(f"{ROOT}/actions/{action_id}/review", headers=manager, json={"approve": True})
    assert review_resp.status_code == 200
    assert review_resp.json()["state"] == "stale", (
        f"Expected the stale action to be marked 'stale' on review, got {review_resp.json()}"
    )
    exec_resp = c.post(f"{ROOT}/actions/{action_id}/execute", headers=manager)
    assert exec_resp.status_code == 409, (
        f"Expected 409 Conflict executing a stale action, got {exec_resp.status_code}"
    )


@pytest.mark.p1_agent
def test_p1_strict_human_approval_enforced_no_auto_execution(c, manager, engineer):
    """
    P1 Scenario 3:
    Verify that no Agent response, multi-turn reply, or LLM synthesis can directly
    execute state changes to simulated_tasks without human manager approval.

    Exercises the real Actions contract -- see module docstring for why the original
    PATCH /actions/{id} + title/task_key/delta shape was replaced.
    """
    # 1. Run analysis under a session (P1 dialogue context).
    analysis = c.post(
        f"{ROOT}/analyze",
        headers=engineer,
        json={"question": "電源負載", "focus": "motor_upgrade", "session_id": "p1-scenario-3"},
    ).json()

    # 2. Create pending action via the real contract.
    action = c.post(
        f"{ROOT}/actions",
        headers=engineer,
        json={
            "analysis_id": analysis["analysis_id"],
            "task_id": "TEST-01",
            "new_state": "blocked",
            "idempotency_key": "p1-scenario-3-approval",
        },
    ).json()
    action_id = action["action_id"]
    assert action["state"] == "pending"

    # 3. Non-manager (engineer) cannot approve their own request.
    unauthorized_approve = c.post(
        f"{ROOT}/actions/{action_id}/review", headers=engineer, json={"approve": True}
    )
    assert unauthorized_approve.status_code == 403, "Engineer must not be able to self-approve actions"

    # 4. Cannot execute an unapproved (pending) action directly.
    unapproved_exec = c.post(f"{ROOT}/actions/{action_id}/execute", headers=manager)
    assert unapproved_exec.status_code == 409, (
        f"Unapproved action execution must be blocked, got {unapproved_exec.status_code}"
    )

    # 5. Only after explicit manager approval does execution succeed -- the session/
    #    analysis layer never gets to skip this human gate.
    approved = c.post(f"{ROOT}/actions/{action_id}/review", headers=manager, json={"approve": True})
    assert approved.status_code == 200
    assert approved.json()["state"] == "approved"
    executed = c.post(f"{ROOT}/actions/{action_id}/execute", headers=manager)
    assert executed.status_code == 200
    assert executed.json()["state"] == "executed"


@pytest.mark.p1_agent
def test_p1_facts_inferences_assumptions_unknowns_quad_separation(c, engineer):
    """
    P1 Scenario 4:
    Verify the architectural invariant:
    Outputs must maintain strict quadruple separation:
    - facts (traceable to tool/document)
    - inferences (logical deductions based on facts)
    - assumptions (explicit operating premises)
    - unknowns (missing/unverifiable information)
    """
    res = c.post(
        f"{ROOT}/analyze",
        headers=engineer,
        json={"question": "馬達升級至 8 A", "focus": "motor_upgrade"}
    ).json()
    
    assert isinstance(res.get("facts"), list)
    assert isinstance(res.get("inferences"), list)
    assert isinstance(res.get("assumptions"), list)
    assert isinstance(res.get("unknowns"), list)
    
    # Verify fact provenance
    for fact in res["facts"]:
        assert "basis" in fact, "Every fact must possess an explicit verifiable basis"
        assert "sources" in fact, "Every fact must trace back to concrete sources"
