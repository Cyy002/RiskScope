"""
RiskScope v0.1 - regression test for the ACL-fix tail risk explicitly flagged in
ai_progress/claude-acl-fix/12_CLAUDE_ACL_FIX_REPORT.md section 6: an alert row written
by the pre-fix app/events.py code has the affected-node names baked directly into the
`body` text, with no node_sources_json snapshot to re-verify against. Simulates that
exact row via a direct DB insert (the current write path can no longer produce one --
app/events.py never persists the node-name clause into body any more), then asserts the
new GET /alerts endpoint does not echo it back, for any reader including the manager,
without deleting or resetting the runtime database.

Written by Claude. Does not touch app/, tests/test_acl_regression.py, or
tests/test_p1_multi_turn.py (Antigravity's files).
"""
import uuid
from app import db
from tests.conftest import ROOT


def _insert_legacy_alert(body):
    conn = db.connect()
    event_id = str(uuid.uuid4())
    alert_id = str(uuid.uuid4())
    conn.execute(
        'INSERT INTO events VALUES (?,?,?,?,?,?,?,?,?)',
        (event_id, 'demo-chamber', 'legacy-sim', f'legacy-{event_id}',
         'supplier_lead_days', '7', '18', 'SUPPLIER-01', db.now()),
    )
    # No node_sources_json column value given on purpose -> defaults to '{}',
    # exactly like a row written before this fix existed.
    conn.execute(
        'INSERT INTO alerts(id,project_id,event_id,title,body,status,created_at) VALUES (?,?,?,?,?,?,?)',
        (alert_id, 'demo-chamber', event_id, '合成資料變更需確認', body, 'open', db.now()),
    )
    conn.close()
    return alert_id


def test_legacy_prefix_alert_node_names_are_redacted_for_every_reader(c, manager, engineer):
    legacy_body = (
        'supplier_lead_days: 7 → 18。已重新分析 11111111-1111-1111-1111-111111111111；'
        '可能受影響節點：ASSEMBLY-01, PROCURE-01, RELEASE-01, TEST-01。影響不是已證明延期。'
    )
    _insert_legacy_alert(legacy_body)

    for creds in (manager, engineer):
        resp = c.get(f"{ROOT}/alerts", headers=creds)
        assert resp.status_code == 200
        bodies = [a['body'] for a in resp.json()['alerts']]
        assert any('已遮蔽' in b for b in bodies), 'legacy row must be redacted, not dropped silently'
        for node in ('ASSEMBLY-01', 'PROCURE-01', 'RELEASE-01', 'TEST-01'):
            for b in bodies:
                assert node not in b, f"legacy alert leaked node '{node}' to reader"
        # The non-sensitive part of the original event description must survive.
        assert any('supplier_lead_days: 7' in b for b in bodies)


def test_legacy_alert_without_node_clause_is_untouched(c, manager):
    """A legacy row that never mentioned nodes at all (e.g. the failure branch, which
    never contained node names even pre-fix) must pass through unmodified -- the fix
    must only redact rows that actually match the risky legacy pattern."""
    safe_body = 'test_pass: unknown → fail。自動分析失敗（ValueError），請手動重試；不可視為已評估。'
    _insert_legacy_alert(safe_body)
    resp = c.get(f"{ROOT}/alerts", headers=manager)
    assert resp.status_code == 200
    assert any(a['body'] == safe_body for a in resp.json()['alerts'])
