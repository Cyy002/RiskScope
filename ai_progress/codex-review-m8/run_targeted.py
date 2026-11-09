"""One M8-only pytest invocation, with live-runtime and network access blocked."""
from pathlib import Path
import hashlib
import json
import os
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
box = tempfile.TemporaryDirectory(prefix="riskscope-m8-review-")
base = Path(box.name).resolve()
os.environ["AGENT_DB_PATH"] = str(base / "default.sqlite3")
os.environ["AGENT_CREDENTIALS_PATH"] = str(base / "credentials.json")
os.environ["OLLAMA_URL"] = ""
paths = [
    "app/chat.py", "app/engineering.py", "app/analyzer.py",
    "app/static/app.js", "tests/conftest.py",
    "tests/test_m8_scenario_planning.py", "tests/test_session_continuity.py",
]
before = {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in paths}
blocked = []
sqlite_paths = set()


def guard(event, args):
    if event == "sqlite3.connect":
        p = Path(str(args[0])).resolve()
        if not p.is_relative_to(base):
            blocked.append("database_outside_temporary_directory")
            raise RuntimeError("Only isolated temporary databases are allowed")
        sqlite_paths.add(str(p.relative_to(base)))
    if event == "open" and isinstance(args[0], (str, bytes, os.PathLike)):
        p = Path(os.fsdecode(args[0])).resolve()
        if p.is_relative_to(ROOT / "runtime"):
            blocked.append("live_runtime_access")
            raise RuntimeError("Live runtime access prohibited")
    if event == "socket.connect" and isinstance(args[1], tuple):
        blocked.append("network_access")
        raise RuntimeError("External network disabled for this review")


sys.addaudithook(guard)
from fastapi.testclient import TestClient
import pytest

responses = []
original_request = TestClient.request


def record_request(self, method, url, *args, **kwargs):
    response = original_request(self, method, url, *args, **kwargs)
    if str(method).upper() == "POST" and str(url).endswith("/chat"):
        data = response.json()
        check = (data.get("checks") or [{}])[0]
        # Only synthetic engineering results; never headers, tokens, or full payloads.
        responses.append({
            "session_id": (kwargs.get("json") or {}).get("session_id"),
            "http_status": response.status_code,
            "detail": data.get("detail"),
            "session": data.get("session"),
            "numbers": check.get("numbers"),
            "proposed_evidence": [
                e for e in check.get("evidence", [])
                if e.get("origin") == "proposed_change"
            ],
        })
    return response


TestClient.request = record_request
code = pytest.main([
    "-q", "--tb=short", "-p", "no:cacheprovider",
    "--basetemp", str(base / "pytest"),
    "tests/test_m8_scenario_planning.py",
])
after = {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in paths}
evidence = {
    "pytest_exit_code": int(code),
    "pytest_invocations": 1,
    "test_file": "tests/test_m8_scenario_planning.py",
    "sqlite_paths_confined_to_temporary_directory": not blocked,
    "distinct_temporary_database_paths": len(sqlite_paths),
    "blocked_access_attempts": blocked,
    "reviewed_source_files_unchanged": before == after,
    "source_hashes": after,
    "chat_responses": responses,
}
(OUT / "test-evidence.json").write_text(
    json.dumps(evidence, ensure_ascii=False, indent=2) + "\n"
)
print(json.dumps({k: v for k, v in evidence.items()
                  if k not in ("source_hashes", "chat_responses")},
                 ensure_ascii=False))
sys.exit(code)
