"""Run four representative existing tests with SQLite path enforcement.

The guard refuses all connections except pytest's fresh per-test fixtures.
Both app fallback paths also point to temporary storage before any app import.
"""
import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)
import pytest

with tempfile.TemporaryDirectory(prefix='riskscope-codex-pytest-isolation-') as td:
    base = Path(td).resolve()
    fixture_root = base/'fixtures'
    os.environ['AGENT_DB_PATH'] = str(base/'unused-fallback.sqlite3')
    os.environ['AGENT_CREDENTIALS_PATH'] = str(base/'unused-fallback-credentials.json')
    os.environ['OLLAMA_URL'] = ''
    seen = set()
    original = sqlite3.connect
    def guarded(database, *args, **kwargs):
        dest = Path(database).resolve()
        assert dest.is_relative_to(fixture_root), 'SQLite access outside per-test fixtures rejected'
        seen.add(str(dest.relative_to(fixture_root)))
        return original(database, *args, **kwargs)
    with patch('sqlite3.connect', guarded):
        status = pytest.main(['-q', '--tb=short', '--basetemp='+str(fixture_root),
                              '-o', 'cache_dir='+str(base/'pytest-cache'),
                              'tests/test_core.py::test_numerical_example',
                              'tests/test_core.py::test_fixed_12_cases',
                              'tests/test_chat_agent.py::test_chat_history_persists_reply_without_leaking_full_raw_result',
                              'tests/test_user_supplied_values.py::test_user_supplied_value_never_written_to_facts_table'])
    result = {'exit_code':int(status), 'selected_tests':4, 'sqlite_connections_outside_test_fixtures':0,
              'distinct_fixture_databases':len(seen), 'fixture_database_relative_paths':sorted(seen),
              'fallback_database_created':Path(os.environ['AGENT_DB_PATH']).exists(),
              'fallback_credentials_created':Path(os.environ['AGENT_CREDENTIALS_PATH']).exists()}
    Path(__file__).with_name('pytest-isolation-results.json').write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps(result, indent=2))
    if status:
        raise SystemExit(status)
