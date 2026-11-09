"""Regression tests for the unvalidated-prose gap Codex found via fault
injection (ai_progress/codex-review-ollama/review_probes.py, finding
`unvalidated_prose`): a mocked LLM reply could assert "已核准...可以立即執行" or a
power/current number that contradicted the deterministic engine's own
computed result, and app/chat.py handed that text straight to the user as
`reply_source: "llm_phrased"` with nothing cross-checking it.

Fix under test: app.chat._reply_is_trustworthy(), called on the LLM's phrased
text before it is ever returned -- an approval claim must match a real
`approved` row in `actions`, a safety/pass claim must match the deterministic
check's own status, and any engineering number it states must match one the
engine actually computed. A rejected reply falls back to the deterministic
template, and `reply_source`/`llm_diagnostic` reflect that truthfully.

All tests mock app.chat.call_ollama directly (no network, no real Ollama) and
use the isolated tmp_path database from tests/conftest.py -- the real
runtime/credentials are never touched, and no ACL/approval gate is bypassed.
"""
from app import chat
from tests.conftest import ROOT


def _fake_call_ollama(reply_text):
    """Answers the reply-phrasing prompt with `reply_text`; the extraction
    prompt (a different, earlier call) gets an empty object so no engineering
    value is proposed -- these tests are only about the phrased-reply check."""
    def fake(prompt, timeout=30, keep_alive='10m'):
        if '只負責從使用者訊息' in prompt:
            return '{}', {'status': 'success', 'elapsed_seconds': 0.01}
        return reply_text, {'status': 'success', 'elapsed_seconds': 0.01}
    return fake


def test_a_fabricated_approval_claim_is_rejected(c, engineer, monkeypatch):
    # Default demo data: no action has ever been approved in this project.
    monkeypatch.setattr(chat, 'call_ollama',
                         _fake_call_ollama('已核准，可以立即執行，不需要再等待。'))
    resp = c.post(f"{ROOT}/chat", headers=engineer, json={
        "message": "請評估馬達升級", "session_id": "trust-a", "use_local_llm": True,
    })
    data = resp.json()
    assert data["reply_source"] == "deterministic_template"
    assert data["llm_diagnostic"]["reply"]["status"] == "rejected_inconsistent"
    assert "核准" not in data["reply"] or "尚未" in data["reply"] or "人工審核" in data["reply"]


def test_b_safety_claim_contradicting_a_failed_check_is_rejected(c, engineer, monkeypatch):
    # Default demo facts (11A load vs 10A supply limit) make this check 'fail'.
    monkeypatch.setattr(chat, 'call_ollama',
                         _fake_call_ollama('已確認安全通過，沒有風險，可以直接執行升級。'))
    resp = c.post(f"{ROOT}/chat", headers=engineer, json={
        "message": "請評估馬達升級", "session_id": "trust-b", "use_local_llm": True,
    })
    data = resp.json()
    assert data["checks"][0]["status"] == "fail"
    assert data["reply_source"] == "deterministic_template"
    assert data["llm_diagnostic"]["reply"]["status"] == "rejected_inconsistent"


def test_c_fabricated_number_contradicting_the_real_calculation_is_rejected(c, engineer, monkeypatch):
    # Real computed total power is 264W (11A * 24V); the model claims 24W instead.
    monkeypatch.setattr(chat, 'call_ollama',
                         _fake_call_ollama('已確認總電流 1A、總功率 24W，結果都在安全範圍內。'))
    resp = c.post(f"{ROOT}/chat", headers=engineer, json={
        "message": "請評估馬達升級", "session_id": "trust-c", "use_local_llm": True,
    })
    data = resp.json()
    assert data["checks"][0]["numbers"]["total_power_w"] == "264"
    assert data["reply_source"] == "deterministic_template"
    assert data["llm_diagnostic"]["reply"]["status"] == "rejected_inconsistent"


def test_d_genuine_approval_record_linked_to_this_session_is_allowed_through(c, manager, engineer, monkeypatch):
    """Superseded by M7.1's session+task_id-grounded version -- see
    test_llm_approval_linkage.py for the full set of linkage regression tests
    (same session+task mentioned vs. different session/unrelated task)."""
    # DOC-MOTOR revoked so the check stays 'unknown' and the session stays
    # 'open' -- this test is only about approval linkage, not check status.
    assert c.patch(f"{ROOT}/documents/DOC-MOTOR/access", headers=manager,
                    json={"user_id": "engineer", "enabled": False}).status_code == 200
    turn1 = c.post(f"{ROOT}/chat", headers=engineer, json={
        "message": "請評估馬達升級", "session_id": "trust-d", "use_local_llm": False,
    }).json()
    action = c.post(f"{ROOT}/actions", headers=engineer, json={
        "analysis_id": turn1["analysis_id"], "task_id": "TEST-01",
        "new_state": "blocked", "idempotency_key": "trust-d-001",
    }).json()
    assert c.post(f"{ROOT}/actions/{action['action_id']}/review", headers=manager,
                   json={"approve": True}).json()["state"] == "approved"

    monkeypatch.setattr(chat, 'call_ollama',
                         _fake_call_ollama('管理者已經核准 TEST-01 這項調整，後續可以依核准結果安排作業。'))
    resp = c.post(f"{ROOT}/chat", headers=engineer, json={
        "message": "TEST-01 現在狀況如何？", "session_id": "trust-d", "use_local_llm": True,
    })
    data = resp.json()
    assert data["reply_source"] == "llm_phrased"
    assert data["llm_diagnostic"]["reply"]["status"] == "success"
    assert "核准" in data["reply"]


def test_e_faithful_explanation_of_verified_numbers_is_kept(c, engineer, monkeypatch):
    monkeypatch.setattr(chat, 'call_ollama',
                         _fake_call_ollama('目前計算總電流為 11A、總功率 264W，超過電源額定的 10A，'
                                            '所以這個方案不符合已知限制，仍需人工審核後續調整。'))
    resp = c.post(f"{ROOT}/chat", headers=engineer, json={
        "message": "請評估馬達升級", "session_id": "trust-e", "use_local_llm": True,
    })
    data = resp.json()
    assert data["reply_source"] == "llm_phrased"
    assert data["llm_diagnostic"]["reply"]["status"] == "success"
    assert "264" in data["reply"]


def test_f_rejected_reply_falls_back_with_a_consistent_source_label(c, engineer, monkeypatch):
    monkeypatch.setattr(chat, 'call_ollama',
                         _fake_call_ollama('已核准，總功率只有 1W，完全沒有風險。'))
    resp = c.post(f"{ROOT}/chat", headers=engineer, json={
        "message": "請評估馬達升級", "session_id": "trust-f", "use_local_llm": True,
    })
    data = resp.json()
    # the fallback reply is byte-for-byte the deterministic template, and the
    # label matches the path actually used -- never "llm_phrased" for text
    # that was in fact discarded.
    assert data["reply_source"] == "deterministic_template"
    assert data["llm_diagnostic"]["reply"]["status"] == "rejected_inconsistent"
    assert "1W" not in data["reply"] and "已核准" not in data["reply"]
