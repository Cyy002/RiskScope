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
#: Separate timeout for app/chat.py's _generic_free_form_reply() (architecture
#: revision 2026-11-04) -- a single free-form call drafts the WHOLE analysis
#: (known facts/unknowns/constraints/risks/options/calculations), far more
#: output than _llm_reply()'s short paraphrase, so the 45s/120s defaults above
#: are too tight and were observed timing out 8B out in real Batch G runs
#: (ai_progress/RISK_INTELLIGENCE_EVALUATION/, claude-b). Falls back to
#: OLLAMA_REPLY_TIMEOUT_SECONDS if set (existing batch scripts already pass
#: that for this call) before these per-model defaults.
OLLAMA_FREE_FORM_TIMEOUT_SECONDS = os.getenv('OLLAMA_FREE_FORM_TIMEOUT_SECONDS', '').strip()
FREE_FORM_TIMEOUT_DEFAULTS_BY_MODEL = {
    'qwen3:8b': 180.0,
    'qwen3.6:27b': 300.0,
}
MAX_DOC_CHARS = 2400
MAX_CONTEXT_CHARS = 8000
MAX_IMPACT_DEPTH = 9
MAX_IMPACT_PATHS = 120

# The proof of concept accepts a loopback Ollama endpoint only. No remote
# address. 'host.containers.internal' (Podman) and 'host.docker.internal'
# (Docker Desktop, and Podman Desktop on Windows/macOS) are both still just
# the container runtime's own fixed, well-known alias for "the host that's
# running this container" -- not an arbitrary remote address -- so allowing
# both keeps the same loopback-only guarantee while fixing a real cross-
# platform gap (Antigravity's P0 portability finding): a Windows or Linux
# Podman setup using the Docker-style alias was silently rejected here with
# no error, falling back to the deterministic template with no indication
# why. A rootless-Linux gateway IP is deliberately NOT added here -- unlike
# these two fixed hostnames, it is a real routable address that varies by
# host and would weaken the "no remote address" guarantee; that gap is
# tracked as a known, documented limitation instead.
def local_ollama_url() -> str | None:
    if not OLLAMA_URL:
        return None
    from urllib.parse import urlparse
    url = urlparse(OLLAMA_URL)
    if url.scheme != 'http' or url.hostname not in {
            'localhost', '127.0.0.1', '::1', 'host.containers.internal', 'host.docker.internal'}:
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


def free_form_reply_timeout_seconds() -> float:
    """Timeout for app/chat.py's _generic_free_form_reply() call specifically
    (architecture revision 2026-11-04) -- a single call drafting a full
    analysis needs far more time than _llm_reply()'s short paraphrase, so this
    is intentionally separate from reply_timeout_seconds() above, not a
    reuse. OLLAMA_FREE_FORM_TIMEOUT_SECONDS wins if set; else
    OLLAMA_REPLY_TIMEOUT_SECONDS (existing batch scripts already pass this for
    this call); else FREE_FORM_TIMEOUT_DEFAULTS_BY_MODEL, defaulting to 180s
    for any model not listed there (never 45s -- that default caused a real
    8B timeout in Batch G, claude-b)."""
    if OLLAMA_FREE_FORM_TIMEOUT_SECONDS:
        try:
            return float(OLLAMA_FREE_FORM_TIMEOUT_SECONDS)
        except ValueError:
            pass
    if OLLAMA_REPLY_TIMEOUT_SECONDS:
        try:
            return float(OLLAMA_REPLY_TIMEOUT_SECONDS)
        except ValueError:
            pass
    return FREE_FORM_TIMEOUT_DEFAULTS_BY_MODEL.get(OLLAMA_MODEL, 180.0)
