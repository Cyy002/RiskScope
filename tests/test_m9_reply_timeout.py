"""Regression tests for M9.1: app/chat.py's _llm_reply() used to call
call_ollama(prompt, timeout=45) unconditionally -- a constant tuned for
qwen3:8b. M9's isolated real-model probe (ai_progress/00_STATUS.md) measured
qwen3.6:27b needing ~61s for a typical reply with think:false, so every real
27B call timed out at 45s and fell back to the deterministic template.

Fix under test: app.config.reply_timeout_seconds() -- an explicit
OLLAMA_REPLY_TIMEOUT_SECONDS env override always wins; otherwise a per-model
default table (qwen3:8b stays 45s unchanged, qwen3.6:27b gets 120s); any
other model keeps the original 45s default. app.chat._llm_reply() now calls
call_ollama(prompt, timeout=config.reply_timeout_seconds()) instead of the
hardcoded constant.

These tests mock app.chat.call_ollama to capture the `timeout` kwarg it was
actually called with -- no real Ollama call, no network. The one real-model
timing measurement for this round is recorded separately in ai_progress/
(per the user's instruction to avoid repeating long-running 27B tests here).
"""
from app import chat, config
from tests.conftest import ROOT


def test_reply_timeout_defaults_to_45s_for_8b(monkeypatch):
    monkeypatch.setattr(config, 'OLLAMA_MODEL', 'qwen3:8b')
    monkeypatch.setattr(config, 'OLLAMA_REPLY_TIMEOUT_SECONDS', '')
    assert config.reply_timeout_seconds() == 45.0


def test_reply_timeout_defaults_to_120s_for_27b(monkeypatch):
    monkeypatch.setattr(config, 'OLLAMA_MODEL', 'qwen3.6:27b')
    monkeypatch.setattr(config, 'OLLAMA_REPLY_TIMEOUT_SECONDS', '')
    assert config.reply_timeout_seconds() == 120.0


def test_reply_timeout_defaults_to_45s_for_an_unlisted_model(monkeypatch):
    """An unrecognized model (e.g. qwen3-coder:30b, never measured) must keep
    the original, safe default -- never guess a longer timeout for a model
    this project has no real timing data for."""
    monkeypatch.setattr(config, 'OLLAMA_MODEL', 'qwen3-coder:30b')
    monkeypatch.setattr(config, 'OLLAMA_REPLY_TIMEOUT_SECONDS', '')
    assert config.reply_timeout_seconds() == 45.0


def test_explicit_env_override_always_wins(monkeypatch):
    monkeypatch.setattr(config, 'OLLAMA_MODEL', 'qwen3.6:27b')
    monkeypatch.setattr(config, 'OLLAMA_REPLY_TIMEOUT_SECONDS', '90')
    assert config.reply_timeout_seconds() == 90.0


def test_malformed_env_override_falls_back_to_model_default(monkeypatch):
    monkeypatch.setattr(config, 'OLLAMA_MODEL', 'qwen3:8b')
    monkeypatch.setattr(config, 'OLLAMA_REPLY_TIMEOUT_SECONDS', 'not-a-number')
    assert config.reply_timeout_seconds() == 45.0


def test_llm_reply_actually_uses_the_model_aware_timeout(c, engineer, monkeypatch):
    """End-to-end through chat_turn(): with OLLAMA_MODEL set to the 27B tag,
    _llm_reply must call call_ollama with timeout=120, not the old hardcoded
    45 -- verified by capturing the kwarg a mocked call_ollama actually
    received, so this stays fast (no real model call)."""
    monkeypatch.setattr(config, 'OLLAMA_MODEL', 'qwen3.6:27b')
    monkeypatch.setattr(config, 'OLLAMA_REPLY_TIMEOUT_SECONDS', '')
    captured = {}

    def fake(prompt, timeout=30, keep_alive='10m'):
        if '只負責從使用者訊息' in prompt:
            return '{}', {'status': 'success', 'elapsed_seconds': 0.01}
        captured['timeout'] = timeout
        return '已完成本輪分析，結果與確定性模板一致。', {'status': 'success', 'elapsed_seconds': 0.01}

    monkeypatch.setattr(chat, 'call_ollama', fake)
    resp = c.post(f"{ROOT}/chat", headers=engineer, json={
        "message": "請評估目前的馬達升級方案。", "session_id": "m9-timeout-check", "use_local_llm": True,
    })
    assert resp.status_code == 200
    assert captured['timeout'] == 120.0


def test_timeout_still_falls_back_to_deterministic_template_safely(c, engineer, monkeypatch):
    """M6/M7/M7.1 safety net unchanged: if the (now longer) timeout is still
    exceeded, or Ollama fails for any reason, the reply must still fall back
    to the deterministic template -- never hang, never surface a half-formed
    or untrusted reply."""
    monkeypatch.setattr(config, 'OLLAMA_MODEL', 'qwen3.6:27b')
    monkeypatch.setattr(config, 'OLLAMA_REPLY_TIMEOUT_SECONDS', '')

    def fake(prompt, timeout=30, keep_alive='10m'):
        if '只負責從使用者訊息' in prompt:
            return '{}', {'status': 'success', 'elapsed_seconds': 0.01}
        return None, {'status': 'timeout', 'detail': f'逾時（{timeout}s）', 'elapsed_seconds': timeout}

    monkeypatch.setattr(chat, 'call_ollama', fake)
    resp = c.post(f"{ROOT}/chat", headers=engineer, json={
        "message": "請評估目前的馬達升級方案。", "session_id": "m9-timeout-fallback", "use_local_llm": True,
    })
    data = resp.json()
    assert data["reply_source"] == "deterministic_template"
    assert data["llm_diagnostic"]["reply"]["status"] == "timeout"
