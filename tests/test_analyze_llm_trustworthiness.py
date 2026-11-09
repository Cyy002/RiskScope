"""M12.2: regression tests for the /analyze(use_local_llm=true) trust gap
Codex's independent review found (ai_progress/codex-review-m121-analyze/):
app/analyzer.py's own optional LLM explanation (`result['local_llm']`) never
called app/chat.py's `_reply_is_trustworthy()` -- the ONE gate that normally
stands between model text and the user/stored record. A fabricated
approval/schedule/cost/percentage/qualitative-completion claim here was
returned as `status: 'generated_unverified'` and written straight into
`analyses.result_json`, even though the identical text is rejected outright
by `/chat`.

Fix under test: `app.analyzer._safe_local_explanation()` now calls the exact
same `app.chat._reply_is_trustworthy()` (deferred import to avoid a circular
module dependency) against the full `result` before returning anything --
a rejected claim's raw text is never put in the response or persisted; only
a non-sensitive `status`/`reason` is.

All tests mock app.chat.call_ollama directly (no network, no real Ollama) and
use the isolated tmp_path database from tests/conftest.py.
"""
import json
from app import config, llm_client
from tests.conftest import ROOT


def _fake_call_ollama(reply_text):
    """app.analyzer._safe_local_explanation() does `from .llm_client import
    call_ollama` freshly INSIDE the function on every call, so the only
    monkeypatch target that actually takes effect for /analyze's path is
    app.llm_client.call_ollama itself -- patching app.chat.call_ollama (a
    separate name bound in chat.py's own namespace) has no effect here."""
    def fake(prompt, timeout=30, keep_alive='10m'):
        if '只負責從使用者訊息' in prompt:
            return '{}', {'status': 'success', 'elapsed_seconds': 0.01}
        return reply_text, {'status': 'success', 'elapsed_seconds': 0.01}
    return fake


def _enable_local_llm(monkeypatch):
    """Only the local-endpoint GATE (config.local_ollama_url()) needs a
    truthy OLLAMA_URL for _safe_local_explanation() to proceed past its
    'disabled' early return -- no actual socket is ever used since
    call_ollama itself is mocked."""
    monkeypatch.setattr(config, 'OLLAMA_URL', 'http://127.0.0.1:11434')


def test_fabricated_approval_is_rejected_and_not_stored(c, engineer, monkeypatch):
    _enable_local_llm(monkeypatch)
    monkeypatch.setattr(llm_client, 'call_ollama',
                         _fake_call_ollama('TEST-01 已核准，可以立即執行。'))
    resp = c.post(ROOT + '/analyze', headers=engineer, json={
        'question': '請分析供應商交期與品質驗證風險。', 'focus': 'supplier',
        'session_id': 'analyze-trust-a', 'use_local_llm': True,
    })
    data = resp.json()
    assert data['local_llm']['status'] == 'rejected_inconsistent'
    # The non-sensitive rejection `reason` may legitimately name the claim
    # type being rejected (same established pattern as /chat's own M7
    # rejection reasons) -- what must never survive is the raw model `text`
    # itself, i.e. the full fabricated sentence, anywhere in the response or
    # the persisted record.
    assert 'text' not in data['local_llm']
    assert 'TEST-01 已核准，可以立即執行。' not in json.dumps(data, ensure_ascii=False)
    detail = c.get(ROOT + '/analyses/' + data['analysis_id'], headers=engineer)
    assert 'TEST-01 已核准，可以立即執行。' not in json.dumps(detail.json(), ensure_ascii=False)


def test_fabricated_schedule_and_cost_are_rejected(c, engineer, monkeypatch):
    _enable_local_llm(monkeypatch)
    monkeypatch.setattr(llm_client, 'call_ollama',
                         _fake_call_ollama('供應商將延誤12天，新增成本為5000元。'))
    resp = c.post(ROOT + '/analyze', headers=engineer, json={
        'question': '請分析供應商交期與品質驗證風險。', 'focus': 'supplier',
        'session_id': 'analyze-trust-b', 'use_local_llm': True,
    })
    data = resp.json()
    assert data['local_llm']['status'] == 'rejected_inconsistent'
    assert 'text' not in data['local_llm']
    assert '供應商將延誤12天，新增成本為5000元。' not in json.dumps(data, ensure_ascii=False)


def test_fabricated_qualitative_completion_is_rejected(c, engineer, monkeypatch):
    _enable_local_llm(monkeypatch)
    monkeypatch.setattr(llm_client, 'call_ollama', _fake_call_ollama('品質驗證已完成。'))
    resp = c.post(ROOT + '/analyze', headers=engineer, json={
        'question': '請分析供應商交期與品質驗證風險。', 'focus': 'supplier',
        'session_id': 'analyze-trust-c', 'use_local_llm': True,
    })
    data = resp.json()
    assert data['local_llm']['status'] == 'rejected_inconsistent'
    assert data['decision_status'] == 'requires_human_review'


def test_fabricated_engineering_number_is_rejected(c, engineer, monkeypatch):
    _enable_local_llm(monkeypatch)
    # Real computed numbers for the default motor scenario are 11A/264W.
    monkeypatch.setattr(llm_client, 'call_ollama', _fake_call_ollama('新方案總電流99A、總功率24W。'))
    resp = c.post(ROOT + '/analyze', headers=engineer, json={
        'question': '請分析馬達升級風險。', 'focus': 'motor_upgrade',
        'session_id': 'analyze-trust-d', 'use_local_llm': True,
    })
    data = resp.json()
    assert data['checks'][0]['numbers']['total_current_a'] == '11'
    assert data['local_llm']['status'] == 'rejected_inconsistent'


def test_authorized_sourced_content_still_passes_through(c, engineer, monkeypatch):
    """A faithful, grounded explanation (matching the real known project
    signal) must still come through as 'generated_unverified', not be
    collaterally rejected by reusing /chat's check."""
    _enable_local_llm(monkeypatch)
    monkeypatch.setattr(llm_client, 'call_ollama',
                         _fake_call_ollama('供應商交期為7天，仍需人工審核。'))
    resp = c.post(ROOT + '/analyze', headers=engineer, json={
        'question': '請分析供應商交期與品質驗證風險。', 'focus': 'supplier',
        'session_id': 'analyze-trust-e', 'use_local_llm': True,
    })
    data = resp.json()
    assert data['local_llm']['status'] == 'generated_unverified'
    assert data['local_llm']['text'] == '供應商交期為7天，仍需人工審核。'


def test_disabled_and_unavailable_statuses_are_untouched(c, engineer):
    """No Ollama endpoint configured -- the pre-existing 'disabled' path
    must never even reach the new trustworthiness check."""
    resp = c.post(ROOT + '/analyze', headers=engineer, json={
        'question': '請分析供應商交期與品質驗證風險。', 'focus': 'supplier',
        'session_id': 'analyze-trust-f', 'use_local_llm': True,
    })
    assert resp.json()['local_llm']['status'] == 'disabled'


def test_acl_denial_happens_before_any_model_call(c, outsider, monkeypatch):
    calls = []
    def fake(prompt, **kwargs):
        calls.append(prompt)
        return 'irrelevant', {'status': 'success'}
    monkeypatch.setattr(llm_client, 'call_ollama', fake)
    resp = c.post(ROOT + '/analyze', headers=outsider, json={
        'question': '請分析供應商交期。', 'focus': 'supplier',
        'session_id': 'analyze-trust-g', 'use_local_llm': True,
    })
    assert resp.status_code == 403
    assert not calls
