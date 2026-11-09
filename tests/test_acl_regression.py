"""
RiskScope v0.1 - Comprehensive P0 ACL Security Regression Tests
==============================================================
Prepared by Antigravity (副手 AI) for independent validation of Claude's fixes.
Core code in app/ remains strictly untouched by Antigravity.

Covers:
1. Stored Analysis Detail (GET /analyses/{id}) checking fact evidence sources.
2. Stored Analysis List (GET /analyses) exclusion of unauthorized analyses.
3. Stored Analysis Detail checking impact path evidence sources (impacts.paths.evidence).
4. Prevention of derived sensitive values (e.g., currents, wattages, formulas) leakage.
5. Alert Provenance ACL: Revocation AFTER event creation (historical cache invalidation).
6. Alert Provenance ACL: Revocation BEFORE event creation.
7. Unimpaired Manager Permissions: Manager retains full legitimate visibility.
8. Unimpaired Legitimate Engineer Access: Authorized engineer workflows operate normally.
"""

import pytest
from app import db
from tests.conftest import ROOT


def _add_distractor_documents(count=8, keyword="search_keyword"):
    """Helper to populate extra documents pushing seed files out of top-8 retrieval."""
    conn = db.connect()
    for i in range(count):
        db.add_doc(
            conn,
            f"DOC-DISTRACTOR-{i:02d}",
            "demo-chamber",
            f"{keyword} specification note",
            "test",
            f"Synthetic distractor note containing {keyword} for retrieval boundary testing.",
        )
    conn.close()


@pytest.mark.acl_regression
def test_stored_analysis_detail_and_list_blocked_on_fact_evidence_revocation(c, manager, engineer):
    """
    Scenario 1 & 2:
    - Fact evidence (DOC-PS) used by check_constraints but pushed out of top-8 retrieval.
    - Revoking DOC-PS must cause GET /analyses/{id} to return 403 Forbidden.
    - The response must NOT leak DOC-PS or derived numbers (10 A, 240 W).
    - GET /analyses (list) must NOT include this analysis ID.
    """
    _add_distractor_documents(8, "search_keyword")

    analysis_resp = c.post(
        f"{ROOT}/analyze",
        headers=engineer,
        json={"question": "search_keyword", "focus": "motor_upgrade"},
    )
    assert analysis_resp.status_code == 200
    analysis = analysis_resp.json()
    analysis_id = analysis["analysis_id"]

    retrieved = [doc["id"] for doc in analysis.get("documents", [])]
    tool_sources = {
        evidence["source_id"]
        for check in analysis.get("checks", [])
        for evidence in check.get("evidence", [])
        if "source_id" in evidence
    }

    assert "DOC-PS" in tool_sources, "DOC-PS must be utilized as tool fact evidence"
    assert "DOC-PS" not in retrieved, "DOC-PS must be excluded from top-8 retrieved documents"

    # Revoke engineer access to DOC-PS
    revoke_resp = c.patch(
        f"{ROOT}/documents/DOC-PS/access",
        headers=manager,
        json={"user_id": "engineer", "enabled": False},
    )
    assert revoke_resp.status_code == 200

    # 1. Detail endpoint verification
    detail_resp = c.get(f"{ROOT}/analyses/{analysis_id}", headers=engineer)
    assert detail_resp.status_code == 403, (
        f"Expected 403 Forbidden on revoked fact evidence, got {detail_resp.status_code}. "
        f"Response body: {detail_resp.text[:300]}"
    )
    assert "DOC-PS" not in detail_resp.text
    assert "240" not in detail_resp.text  # Power limit derived from DOC-PS

    # 2. List endpoint verification: must not appear in allowed list
    list_resp = c.get(f"{ROOT}/analyses", headers=engineer)
    assert list_resp.status_code == 200
    listed_ids = [item["id"] for item in list_resp.json().get("analyses", [])]
    assert analysis_id not in listed_ids, (
        f"Analysis {analysis_id} with revoked evidence DOC-PS leaked in GET /analyses list"
    )


@pytest.mark.acl_regression
def test_stored_analysis_detail_blocked_on_impact_path_evidence_revocation(c, manager, engineer):
    """
    Scenario 3:
    - Impact path evidence (DOC-PLAN) used in dependency traversal when engineering checks are empty.
    - Revoking DOC-PLAN must cause GET /analyses/{id} to return 403 Forbidden.
    - Must not leak path evidence or DOC-PLAN identifier.
    """
    _add_distractor_documents(8, "targettopic")

    analysis_resp = c.post(
        f"{ROOT}/analyze",
        headers=engineer,
        json={"question": "targettopic", "focus": "supplier"},
    )
    assert analysis_resp.status_code == 200
    analysis = analysis_resp.json()
    analysis_id = analysis["analysis_id"]

    retrieved = [doc["id"] for doc in analysis.get("documents", [])]
    impact_sources = {
        evidence["source_id"]
        for impact in analysis.get("impacts", [])
        for path in impact.get("paths", [])
        for evidence in path.get("evidence", [])
        if "source_id" in evidence
    }

    assert "DOC-PLAN" in impact_sources, "DOC-PLAN must be in impact path evidence"
    assert "DOC-PLAN" not in retrieved, "DOC-PLAN must be excluded from top-8 retrieved documents"

    # Revoke engineer access to DOC-PLAN
    assert c.patch(
        f"{ROOT}/documents/DOC-PLAN/access",
        headers=manager,
        json={"user_id": "engineer", "enabled": False},
    ).status_code == 200

    # Detail endpoint must reject
    detail_resp = c.get(f"{ROOT}/analyses/{analysis_id}", headers=engineer)
    assert detail_resp.status_code == 403, (
        f"Expected 403 Forbidden on revoked impact evidence, got {detail_resp.status_code}"
    )
    assert "DOC-PLAN" not in detail_resp.text


@pytest.mark.acl_regression
def test_alerts_endpoint_respects_acl_when_revoked_after_event_creation(c, manager, engineer):
    """
    Scenario 4:
    - Event is created FIRST while engineer technically had membership.
    - Alert is persisted.
    - Manager then revokes DOC-SUPPLIER and DOC-PLAN from engineer.
    - Engineer queries GET /alerts.
    - Engineer MUST NOT see downstream nodes derived from DOC-SUPPLIER/DOC-PLAN (e.g. PROCURE-01, ASSEMBLY-01).
    """
    # 1. Trigger manager event before revocation
    event_resp = c.post(
        f"{ROOT}/events",
        headers=manager,
        json={
            "external_event_id": "event-before-revocation",
            "signal_key": "supplier_lead_days",
            "value": "18",
        },
    )
    assert event_resp.status_code == 200
    assert event_resp.json().get("analysis_status") == "completed"

    # 2. Revoke supplier and plan document access
    for doc_id in ("DOC-SUPPLIER", "DOC-PLAN"):
        assert c.patch(
            f"{ROOT}/documents/{doc_id}/access",
            headers=manager,
            json={"user_id": "engineer", "enabled": False},
        ).status_code == 200

    # 3. Direct impact query returns empty
    impact_resp = c.get(f"{ROOT}/impact/SUPPLIER-01", headers=engineer)
    assert impact_resp.status_code == 200
    assert impact_resp.json()["affected_nodes"] == []

    # 4. Alerts query must NOT disclose protected dependency nodes
    alerts_resp = c.get(f"{ROOT}/alerts", headers=engineer)
    assert alerts_resp.status_code == 200
    protected_nodes = ["PROCURE-01", "ASSEMBLY-01", "RELEASE-01", "TEST-01"]
    for alert in alerts_resp.json().get("alerts", []):
        body = alert.get("body", "")
        for node in protected_nodes:
            assert node not in body, (
                f"Historical alert leaked node '{node}' after document revocation. Body: {body}"
            )


@pytest.mark.acl_regression
def test_alerts_endpoint_respects_acl_when_revoked_before_event_creation(c, manager, engineer):
    """
    Scenario 5:
    - Manager revokes DOC-SUPPLIER and DOC-PLAN from engineer FIRST.
    - Event is triggered by manager.
    - Engineer queries GET /alerts.
    - Engineer MUST NOT receive alert details or nodes derived from unauthorized documents.
    """
    for doc_id in ("DOC-SUPPLIER", "DOC-PLAN"):
        assert c.patch(
            f"{ROOT}/documents/{doc_id}/access",
            headers=manager,
            json={"user_id": "engineer", "enabled": False},
        ).status_code == 200

    event_resp = c.post(
        f"{ROOT}/events",
        headers=manager,
        json={
            "external_event_id": "event-after-revocation",
            "signal_key": "supplier_lead_days",
            "value": "18",
        },
    )
    assert event_resp.status_code == 200

    alerts_resp = c.get(f"{ROOT}/alerts", headers=engineer)
    assert alerts_resp.status_code == 200
    protected_nodes = ["PROCURE-01", "ASSEMBLY-01", "RELEASE-01", "TEST-01"]
    for alert in alerts_resp.json().get("alerts", []):
        body = alert.get("body", "")
        for node in protected_nodes:
            assert node not in body, (
                f"Alert leaked node '{node}' when generated after revocation. Body: {body}"
            )


@pytest.mark.acl_regression
def test_manager_retains_full_legitimate_access_to_all_features(c, manager, engineer):
    """
    Scenario 6:
    - Ensure fix does NOT over-restrict manager privileges.
    - Manager can access analyses, view alerts with all affected nodes, and read list.
    """
    _add_distractor_documents(8, "search_keyword")

    analysis_resp = c.post(
        f"{ROOT}/analyze",
        headers=manager,
        json={"question": "search_keyword", "focus": "motor_upgrade"},
    )
    assert analysis_resp.status_code == 200
    analysis_id = analysis_resp.json()["analysis_id"]

    # Manager must have 200 on detail
    detail_resp = c.get(f"{ROOT}/analyses/{analysis_id}", headers=manager)
    assert detail_resp.status_code == 200
    assert detail_resp.json()["analysis_id"] == analysis_id

    # Manager must see analysis in list
    list_resp = c.get(f"{ROOT}/analyses", headers=manager)
    assert list_resp.status_code == 200
    listed_ids = [item["id"] for item in list_resp.json().get("analyses", [])]
    assert analysis_id in listed_ids

    # Manager creates event and sees full nodes in alert
    event_resp = c.post(
        f"{ROOT}/events",
        headers=manager,
        json={
            "external_event_id": "manager-event-check",
            "signal_key": "supplier_lead_days",
            "value": "18",
        },
    )
    assert event_resp.status_code == 200
    manager_alerts = c.get(f"{ROOT}/alerts", headers=manager)
    assert manager_alerts.status_code == 200
    alert_bodies = [a["body"] for a in manager_alerts.json().get("alerts", [])]
    assert any("PROCURE-01" in b for b in alert_bodies), "Manager must see affected nodes in alerts"


@pytest.mark.acl_regression
def test_legitimate_authorized_engineer_features_unimpaired(c, manager, engineer):
    """
    Scenario 7:
    - Ensure fix does NOT break normal engineer functionality for authorized documents.
    - Engineer with valid permissions performs analysis, can re-read it, and sees it in list.
    """
    analysis_resp = c.post(
        f"{ROOT}/analyze",
        headers=engineer,
        json={"question": "電源負載", "focus": "motor_upgrade"},
    )
    assert analysis_resp.status_code == 200
    analysis_id = analysis_resp.json()["analysis_id"]

    # Legitimate engineer re-reads own analysis -> 200 OK
    detail_resp = c.get(f"{ROOT}/analyses/{analysis_id}", headers=engineer)
    assert detail_resp.status_code == 200
    assert detail_resp.json()["analysis_id"] == analysis_id

    # Appears in engineer's analysis list
    list_resp = c.get(f"{ROOT}/analyses", headers=engineer)
    assert list_resp.status_code == 200
    listed_ids = [item["id"] for item in list_resp.json().get("analyses", [])]
    assert analysis_id in listed_ids
