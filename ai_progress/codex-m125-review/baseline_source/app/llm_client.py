"""Thin, fully-diagnosed wrapper around the one local-only Ollama endpoint this
project is allowed to call (app.config.local_ollama_url -- loopback-only, no
cloud/paid address accepted). Every call returns (text_or_None, diagnostic);
callers never have to guess why a reply fell back to the deterministic path --
`diagnostic['status']` is always one of: not_configured, connection_error,
model_not_found, http_error, timeout, invalid_json, empty_response,
unexpected_error, success.

Root cause of the ReadTimeout Codex reproduced (ai_progress/codex-ollama/
diagnostic-configured.json): qwen3:8b has a "thinking" capability that by
default spends many hidden reasoning tokens before the visible answer -- a
10-20s tax on EVERY call, observed directly in the diagnostic's
`thinking_chars` field. Ollama's /api/generate accepts `"think": false` to skip
that phase entirely; verified locally (2026-10-19) to cut a warm call from
~17-20s to well under 2s for both the extraction and reply prompts this project
uses, with no loss of correctness. `keep_alive` is also set generously so the
model doesn't get evicted between a chat turn's two sequential calls, or
between a user's turns a few minutes apart.

Never logs prompt or response text (project data) -- only status/timing
metadata that is safe to persist.
"""
from __future__ import annotations
import time
from . import config

DEFAULT_TIMEOUT = 30.0
DEFAULT_KEEP_ALIVE = '10m'


def call_ollama(prompt, timeout=DEFAULT_TIMEOUT, keep_alive=DEFAULT_KEEP_ALIVE):
    """Returns (text, diagnostic). `text` is a non-empty str on success, else
    None -- callers must treat None as "no LLM output available", never guess
    a value out of a partial/malformed response.

    Reads config.local_ollama_url()/config.OLLAMA_MODEL live on every call
    (via the `config` module object, not a value imported at module-load time)
    so a test's monkeypatch.setattr(config, 'OLLAMA_URL'/'OLLAMA_MODEL', ...)
    always takes effect, regardless of import order."""
    url = config.local_ollama_url()
    if not url:
        return None, {'status': 'not_configured', 'detail': 'OLLAMA_URL 未設定，或不是合法的本機 (loopback) 端點'}

    import httpx
    t0 = time.monotonic()
    try:
        r = httpx.post(
            url + '/api/generate',
            json={'model': config.OLLAMA_MODEL, 'prompt': prompt, 'stream': False, 'think': False,
                  'keep_alive': keep_alive},
            timeout=timeout,
        )
    except httpx.ConnectError as exc:
        return None, {'status': 'connection_error', 'detail': f'無法連線到 {url}：{type(exc).__name__}'}
    except httpx.TimeoutException:
        return None, {'status': 'timeout',
                       'detail': f'逾時（{timeout}s）：模型可能仍在載入或正在生成',
                       'elapsed_seconds': round(time.monotonic() - t0, 3)}
    except Exception as exc:
        return None, {'status': 'unexpected_error', 'detail': f'{type(exc).__name__}'}
    elapsed = round(time.monotonic() - t0, 3)

    if r.status_code == 404:
        return None, {'status': 'model_not_found', 'detail': f'模型 {config.OLLAMA_MODEL} 不存在於 {url}'}
    if r.status_code != 200:
        return None, {'status': 'http_error', 'detail': f'HTTP {r.status_code}'}

    try:
        payload = r.json()
    except Exception:
        return None, {'status': 'invalid_json', 'detail': '回應內容不是合法 JSON'}

    response_text = payload.get('response') if isinstance(payload, dict) else None
    if not isinstance(response_text, str):
        # A missing/None/list/dict `response` field must never be stringified
        # and treated as a real answer -- that was a real bug (str(None) ==
        # 'None', a truthy, "successful"-looking string).
        return None, {'status': 'empty_response', 'detail': 'response 欄位缺失或型別不是字串'}
    response_text = response_text.strip()
    if not response_text:
        return None, {'status': 'empty_response', 'detail': '模型回傳空白內容'}

    return response_text, {'status': 'success', 'elapsed_seconds': elapsed}
