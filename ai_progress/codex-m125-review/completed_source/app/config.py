from __future__ import annotations
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
DB_PATH = Path(os.getenv('AGENT_DB_PATH', BASE_DIR / 'runtime' / 'agent.sqlite3'))
CREDENTIALS_PATH = Path(os.getenv('AGENT_CREDENTIALS_PATH', BASE_DIR / 'runtime' / 'demo_credentials.json'))
OLLAMA_URL = os.getenv('OLLAMA_URL', '').strip()  # Never send to a cloud endpoint.
OLLAMA_MODEL = os.getenv('OLLAMA_MODEL', 'qwen3:8b')
#: Explicit override for the reply-phrasing call's timeout (app/chat.py's
#: _llm_reply) -- always wins over the per-model default below. Leave unset
#: to use REPLY_TIMEOUT_DEFAULTS_BY_MODEL.
OLLAMA_REPLY_TIMEOUT_SECONDS = os.getenv('OLLAMA_REPLY_TIMEOUT_SECONDS', '').strip()
#: Per-model default for that same timeout -- a reply generates far more
#: tokens than the short extraction call, so one size does not fit every
#: model. Values are measured, not guessed (M9 isolated probe,
#: ai_progress/00_STATUS.md): qwen3:8b's typical reply with think:false
#: completes well under 45s; qwen3.6:27b's (~650 output tokens at
#: ~14.8 tokens/s) took ~61s, so 120s leaves real headroom without being
#: unbounded. Any model not listed here keeps the original 45s default --
#: this never changes 8B's existing behavior.
REPLY_TIMEOUT_DEFAULTS_BY_MODEL = {
    'qwen3:8b': 45.0,
    'qwen3.6:27b': 120.0,
}
MAX_DOC_CHARS = 2400
MAX_CONTEXT_CHARS = 8000
MAX_IMPACT_DEPTH = 9
MAX_IMPACT_PATHS = 120

# The proof of concept accepts a loopback Ollama endpoint only. No remote address.
def local_ollama_url() -> str | None:
    if not OLLAMA_URL:
        return None
    from urllib.parse import urlparse
    url = urlparse(OLLAMA_URL)
    if url.scheme != 'http' or url.hostname not in {'localhost', '127.0.0.1', '::1', 'host.containers.internal'}:
        return None
    return OLLAMA_URL.rstrip('/')


def reply_timeout_seconds() -> float:
    """Timeout for app/chat.py's _llm_reply() call specifically (never the
    extraction call, which stays on its own short fixed timeout -- a reply
    generates far more tokens). Reads OLLAMA_REPLY_TIMEOUT_SECONDS/OLLAMA_MODEL
    live off this module's own globals (not a value captured at import time),
    same as local_ollama_url() above, so a test's
    monkeypatch.setattr(config, 'OLLAMA_MODEL', ...) always takes effect.
    Explicit OLLAMA_REPLY_TIMEOUT_SECONDS always wins; otherwise falls back to
    REPLY_TIMEOUT_DEFAULTS_BY_MODEL, defaulting to the original 45s for any
    model not listed there."""
    if OLLAMA_REPLY_TIMEOUT_SECONDS:
        try:
            return float(OLLAMA_REPLY_TIMEOUT_SECONDS)
        except ValueError:
            pass
    return REPLY_TIMEOUT_DEFAULTS_BY_MODEL.get(OLLAMA_MODEL, 45.0)
