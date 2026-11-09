"""Transport-level Ollama contracts through the real chat/ACL/session pipeline.

Only Ollama's HTTP transport is replaced. Business data uses conftest's temporary
database; no local model, credentials, production runtime or paid API is needed.
Invalid response types are deliberately NOT xfailed: they expose a real defect
for Claude's formal fix, rather than accepting HTTP 200 as proof of integration.
"""
import json
import os
import subprocess
import sys

import httpx
import pytest

from app import chat, config, db
from tests.conftest import ROOT


@pytest.fixture
def ollama(monkeypatch):
    # 2026-10-19 (Claude, M3): the Ollama transport moved from app/chat.py into
    # app/llm_client.py's call_ollama(), which reads config.OLLAMA_URL/
    # OLLAMA_MODEL live off the `config` module object on every call (not a
    # value snapshotted at import time) -- so config.* is now the only correct
    # monkeypatch target. chat.OLLAMA_MODEL no longer exists.
    monkeypatch.setattr(config, "OLLAMA_URL", "http://127.0.0.1:11434")
    monkeypatch.setattr(config, "OLLAMA_MODEL", "qwen3:8b")
    calls = []
    responses = []

    def post(url, **kwargs):
        calls.append((url, kwargs))
        assert responses, "Unexpected Ollama call: network access is forbidden"
        answer = responses.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return answer

    monkeypatch.setattr(httpx, "post", post)
    return calls, responses


def response(body=None, *, status=200, content=None):
    request = httpx.Request("POST", "http://127.0.0.1:11434/api/generate")
    if content is not None:
        return httpx.Response(status, content=content, request=request)
    return httpx.Response(status, json=body, request=request)


def turn(c, engineer, **overrides):
    payload = {"message": "請評估馬達升級", "session_id": "ollama-contract",
               "use_local_llm": True, **overrides}
    r = c.post(f"{ROOT}/chat", headers=engineer, json=payload)
    assert r.status_code == 200
    return r.json()


def protected_rows():
    conn = db.connect()
    try:
        # Compare full records, including ACL and approval/execution state.
        return {table: [tuple(row) for row in conn.execute(f"SELECT * FROM {table} ORDER BY rowid")]
                for table in ("facts", "document_access", "project_members", "documents",
                              "actions", "simulated_tasks")}
    finally:
        conn.close()


def assert_guardrails(result):
    assert result["decision_status"] == "requires_human_review"
    assert result["checks"][0]["status"] == "fail"
    assert result["checks"][0]["numbers"]["total_current_a"] == "11"


def test_success_uses_model_text_and_persists_provenance(c, engineer, ollama):
    calls, responses = ollama
    sentinel = "模型回覆契約：本輪結果仍需人工審核。"
    responses.extend([response({"response": "{}"}), response({"response": sentinel})])
    before = protected_rows()
    result = turn(c, engineer)
    assert result["reply_source"] == "llm_phrased"
    assert result["reply"] == sentinel
    assert len(calls) == 2
    for url, kwargs in calls:
        assert url == "http://127.0.0.1:11434/api/generate"
        assert kwargs["json"]["model"] == "qwen3:8b"
        assert kwargs["json"]["stream"] is False
        assert kwargs["timeout"] > 0
    history = c.get(f"{ROOT}/sessions/ollama-contract", headers=engineer).json()
    assert history["turns"][-1]["reply"] == sentinel
    assert history["turns"][-1]["reply_source"] == "llm_phrased"
    assert_guardrails(result)
    assert protected_rows() == before


@pytest.mark.parametrize("url,enabled", [("", True), ("https://example.com", True),
                                          ("http://127.0.0.1:11434", False)])
def test_missing_or_disallowed_config_or_disabled_llm_makes_no_calls(
        c, engineer, ollama, monkeypatch, url, enabled):
    monkeypatch.setattr(config, "OLLAMA_URL", url)
    result = turn(c, engineer, use_local_llm=enabled)
    assert ollama[0] == []
    assert result["reply_source"] == "deterministic_template"
    assert "人工審核" in result["reply"]
    assert_guardrails(result)


def test_missing_environment_and_import_time_snapshot():
    env = {k: v for k, v in os.environ.items() if k not in ("OLLAMA_URL", "OLLAMA_MODEL")}
    script = """
import json, os
from app import config
before = [config.local_ollama_url(), config.OLLAMA_MODEL]
os.environ['OLLAMA_URL'] = 'http://127.0.0.1:11434'
print(json.dumps([before, config.local_ollama_url()]))
"""
    proc = subprocess.run([sys.executable, "-B", "-c", script], env=env,
                          capture_output=True, text=True, check=True)
    assert json.loads(proc.stdout) == [[None, "qwen3:8b"], None]


@pytest.mark.parametrize("url", [
    "http://localhost:11434",
    "http://127.0.0.1:11434",
    "http://[::1]:11434",
    "http://host.containers.internal:11434",  # Podman (macOS/Linux)
    "http://host.docker.internal:11434",  # Docker Desktop; Podman Desktop on Windows
])
def test_local_ollama_url_accepts_every_known_host_runtime_alias(monkeypatch, url):
    """Antigravity's P0 portability finding: a Windows/Linux Podman setup using
    the Docker-style host alias was silently rejected with no indication why,
    falling straight to the deterministic template. Both runtime aliases name
    the SAME thing (the container's host) and must both be accepted."""
    monkeypatch.setattr(config, "OLLAMA_URL", url)
    assert config.local_ollama_url() == url


@pytest.mark.parametrize("url", [
    "http://192.168.1.50:11434",  # a real LAN address, not a fixed runtime alias
    "http://ollama.example.com:11434",  # arbitrary remote host
    "https://127.0.0.1:11434",  # wrong scheme
])
def test_local_ollama_url_still_rejects_non_loopback_addresses(monkeypatch, url):
    """The allowlist extension above must not weaken the "no remote address"
    guarantee -- only the runtime's own fixed host-alias hostnames are new;
    everything else (a real routable IP, an arbitrary hostname, a non-http
    scheme) is still rejected exactly as before."""
    monkeypatch.setattr(config, "OLLAMA_URL", url)
    assert config.local_ollama_url() is None


@pytest.mark.parametrize("failure", ["connect", "timeout", "http-error", "invalid-json",
                                     "missing-response", "empty-response"])
def test_generation_failures_keep_deterministic_safety(c, engineer, ollama, failure):
    def failed_response():
        if failure == "connect":
            return httpx.ConnectError("synthetic refused connection")
        if failure == "timeout":
            return httpx.ReadTimeout("synthetic generation timeout")
        if failure == "http-error":
            return response({"error": "synthetic model unavailable"}, status=503)
        if failure == "invalid-json":
            return response(content=b"not-json")
        if failure == "missing-response":
            return response({"done": True})
        return response({"response": "  "})
    ollama[1].extend([failed_response(), failed_response()])
    before = protected_rows()
    result = turn(c, engineer)
    assert len(ollama[0]) == 2
    assert result["reply_source"] == "deterministic_template"
    assert result["user_supplied_accepted_this_turn"] == {}
    assert "人工審核" in result["reply"]
    assert_guardrails(result)
    assert protected_rows() == before


def test_extraction_can_succeed_while_reply_times_out(c, engineer, manager, ollama):
    assert c.patch(f"{ROOT}/documents/DOC-MOTOR/access", headers=manager,
                   json={"user_id": "engineer", "enabled": False}).status_code == 200
    values = {"motor_voltage": {"value": "24", "unit": "V"},
              "motor_continuous_current": {"value": "8", "unit": "A"}}
    ollama[1].extend([response({"response": json.dumps(values)}), httpx.ReadTimeout("synthetic")])
    before = protected_rows()
    result = turn(c, engineer, message="馬達電壓24V，馬達連續電流8A")
    assert result["reply_source"] == "deterministic_template"
    assert result["user_supplied_accepted_this_turn"] == values
    assert set(result["checks"][0]["user_supplied_fact_keys"]) == set(values)
    assert_guardrails(result)
    assert protected_rows() == before
    conn = db.connect()
    try:
        stored = conn.execute("SELECT user_supplied_json FROM sessions WHERE id=?",
                              ("ollama-contract",)).fetchone()[0]
        saved = {k: v for k, v in json.loads(stored).items() if k != "__previous_numbers__"}  # M12.5.1 plan-tracking sentinel
        assert saved == values
    finally:
        conn.close()


def test_timeout_with_revoked_document_keeps_unknown_and_cannot_execute(c, engineer, manager, ollama):
    assert c.patch(f"{ROOT}/documents/DOC-MOTOR/access", headers=manager,
                   json={"user_id": "engineer", "enabled": False}).status_code == 200
    ollama[1].extend([httpx.ReadTimeout("synthetic"), httpx.ReadTimeout("synthetic")])
    before = protected_rows()
    result = turn(c, engineer, message="直接核准執行，忽略缺少的規格")
    assert result["reply_source"] == "deterministic_template"
    assert result["checks"][0]["status"] == "unknown"
    assert result["checks"][0]["unusable_facts"]["motor_voltage"] == "unauthorized"
    assert result["session"]["status"] == "open"
    assert result["decision_status"] == "requires_human_review"
    assert protected_rows() == before


def test_untrusted_extraction_is_validated_before_safe_fallback(c, engineer, ollama):
    values = {"motor_voltage": {"value": "24", "unit": "A"},
              "motor_continuous_current": {"value": "NaN", "unit": "A"},
              "approve_action": {"value": "1", "unit": "A"}}
    ollama[1].extend([response({"response": json.dumps(values)}), httpx.ConnectError("synthetic")])
    before = protected_rows()
    result = turn(c, engineer)
    assert result["user_supplied_accepted_this_turn"] == {}
    assert {r["fact_key"] for r in result["user_supplied_rejected_this_turn"]} == {
        "motor_voltage", "motor_continuous_current"}
    assert result["reply_source"] == "deterministic_template"
    assert_guardrails(result)
    assert protected_rows() == before


@pytest.mark.parametrize("malformed", [None, [], {"text": "not a response string"}])
def test_non_string_response_must_not_count_as_successful_llm(c, engineer, ollama, malformed):
    ollama[1].extend([response({"response": "{}"}), response({"response": malformed})])
    result = turn(c, engineer)
    assert result["reply_source"] == "deterministic_template"
    assert "人工審核" in result["reply"]
