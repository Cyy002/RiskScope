"""Non-destructive review probes: all databases/credentials are fresh temporary files.

This records current behavior, including defects; passing assertions mean the
observed behavior was reproduced, not that every behavior is safe.
"""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
OUT = Path(__file__).with_name('runtime-probe-results.json')


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def snapshot(conn):
    names = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
    # Hash records internally; no tokens, hashes, documents, or private data emitted.
    return {name: hashlib.sha256(repr([tuple(r) for r in conn.execute('SELECT * FROM "'+name+'" ORDER BY rowid')]).encode()).hexdigest() for name in names}


def run():
    results = {'scope': 'fresh temporary synthetic fixtures only', 'probes': {},
               'source_sha256': {p: sha(ROOT/p) for p in ['app/db.py','app/config.py','scripts/evaluate.py','tests/conftest.py','app/security.py']}}
    with tempfile.TemporaryDirectory(prefix='riskscope-codex-runtime-review-') as td:
        base = Path(td).resolve()
        os.environ['AGENT_DB_PATH'] = str(base/'default.sqlite3')
        os.environ['AGENT_CREDENTIALS_PATH'] = str(base/'default-credentials.json')
        os.environ.pop('OLLAMA_URL', None)
        from app import db
        from scripts.evaluate import evaluate
        assert db.DB_PATH.is_relative_to(base)
        assert db.CREDENTIALS_PATH.is_relative_to(base)

        # Block accidental access to any database outside this disposable tree.
        original_connect = sqlite3.connect
        def guarded_connect(database, *args, **kwargs):
            if str(database) != ':memory:':
                assert Path(database).resolve().is_relative_to(base), 'non-isolated SQLite path rejected'
            return original_connect(database, *args, **kwargs)

        with patch('sqlite3.connect', guarded_connect):
            # R1: running the CLI evaluator initializes its selected DB and writes credentials.
            cli_db = base/'evaluate.sqlite3'
            cli_creds = base/'evaluate-credentials.json'
            cli_env = {**os.environ, 'AGENT_DB_PATH': str(cli_db), 'AGENT_CREDENTIALS_PATH': str(cli_creds)}
            completed = subprocess.run([sys.executable, '-B', '-m', 'scripts.evaluate'], cwd=ROOT,
                                       env=cli_env, capture_output=True, text=True, check=True)
            metrics = json.loads(completed.stdout)
            c = db.connect(cli_db)
            counts = {t: c.execute('SELECT COUNT(*) FROM '+t).fetchone()[0] for t in ['users','documents','audit']}
            assert counts == {'users':3, 'documents':6, 'audit':1}
            assert cli_creds.exists()
            results['probes']['evaluate_cli_creates_data'] = {
                'database_created':cli_db.exists(), 'credential_file_created':cli_creds.exists(),
                'counts':counts, 'evaluation_true_positive':metrics['aggregate']['multi_hop']['true_positive']}

            # Current schemas and data are preserved by repeated init and evaluate(conn).
            c.execute("UPDATE facts SET value='9' WHERE fact_key='motor_continuous_current'")
            c.execute("INSERT INTO sessions(id,project_id,user_id,focus,status,created_at,updated_at) VALUES ('isolation-proof','demo-chamber','engineer','motor_upgrade','open','fixture','fixture')")
            before = snapshot(c)
            cred_before = sha(cli_creds)
            c.close()
            c = db.init_db(cli_db, cli_creds)
            assert snapshot(c) == before
            assert sha(cli_creds) == cred_before
            evaluate(c)
            assert snapshot(c) == before
            results['probes']['existing_current_database_preserved'] = {
                'all_table_digests_unchanged':True, 'credentials_unchanged':True,
                'custom_fact_preserved':c.execute("SELECT value FROM facts WHERE fact_key='motor_continuous_current'").fetchone()[0] == '9',
                'session_preserved':c.execute("SELECT count(*) FROM sessions WHERE id='isolation-proof'").fetchone()[0] == 1}

            # R1: evaluator also migrates an existing older schema, despite existing users.
            for table, column in [('alerts','node_sources_json'),('analyses','session_id'),('sessions','user_supplied_json')]:
                c.execute('ALTER TABLE '+table+' DROP COLUMN '+column)
            c.close()
            completed = subprocess.run([sys.executable, '-B', '-m', 'scripts.evaluate'], cwd=ROOT,
                                       env=cli_env, capture_output=True, text=True, check=True)
            c = db.connect(cli_db)
            added = {table: column in [r[1] for r in c.execute('PRAGMA table_info('+table+')')]
                     for table, column in [('alerts','node_sources_json'),('analyses','session_id'),('sessions','user_supplied_json')]}
            assert all(added.values())
            assert c.execute("SELECT count(*) FROM sessions WHERE id='isolation-proof'").fetchone()[0] == 1
            results['probes']['evaluate_cli_migrates_existing_data'] = {'columns_restored_by_evaluator':added,
                'existing_session_preserved':True, 'credential_file_unchanged':sha(cli_creds)==cred_before}
            c.close()

            # R2: explicit DB-only override still targets the shared default credentials path.
            c = db.init_db()
            before_hash = c.execute("SELECT token_hash FROM users WHERE id='manager'").fetchone()[0]
            before_credentials = sha(db.CREDENTIALS_PATH)
            c.close()
            other = db.init_db(base/'other.sqlite3')
            other.close()
            c = db.connect()
            after_hash = c.execute("SELECT token_hash FROM users WHERE id='manager'").fetchone()[0]
            new_credentials = json.loads(db.CREDENTIALS_PATH.read_text())
            mismatch = hashlib.sha256(new_credentials['manager'].encode()).hexdigest() != after_hash
            del new_credentials
            assert before_hash == after_hash and sha(db.CREDENTIALS_PATH) != before_credentials and mismatch
            results['probes']['db_only_override_replaces_default_credentials'] = {
                'existing_database_user_hash_unchanged':True,
                'default_credentials_file_overwritten':True,
                'credentials_no_longer_match_existing_database':True}
            c.close()

            # R3: DB commits before credentials write; a write failure makes retries skip recovery.
            fail_db, fail_credentials = base/'credential-failure.sqlite3', base/'credential-failure.json'
            original_write = Path.write_text
            def denied(path, *args, **kwargs):
                if path == fail_credentials:
                    raise PermissionError('synthetic credential write failure')
                return original_write(path, *args, **kwargs)
            try:
                with patch.object(Path, 'write_text', denied):
                    db.init_db(fail_db, fail_credentials)
            except PermissionError:
                pass
            else:
                raise AssertionError('expected injected write failure')
            c = db.init_db(fail_db, fail_credentials)
            count = c.execute('SELECT count(*) FROM users').fetchone()[0]
            assert count == 3 and not fail_credentials.exists()
            results['probes']['credential_write_failure_not_recovered'] = {
                'users_committed_before_failed_credential_write':count,
                'retry_credential_file_exists':fail_credentials.exists(),
                'retry_returns_success_without_usable_credentials_file':True}
            c.close()

            # Existing users with no demo seeds are not reset/repopulated.
            partial = base/'partial.sqlite3'
            c = db.connect(partial)
            c.execute('CREATE TABLE users(id TEXT PRIMARY KEY, display_name TEXT NOT NULL, token_hash TEXT UNIQUE NOT NULL, active INTEGER NOT NULL DEFAULT 1)')
            c.execute("INSERT INTO users VALUES ('fixture-user','fixture',?,1)", (hashlib.sha256(b'not-a-real-secret').hexdigest(),))
            c.close()
            c = db.init_db(partial, base/'partial-credentials.json')
            assert c.execute('SELECT count(*) FROM users').fetchone()[0] == 1
            assert c.execute('SELECT count(*) FROM projects').fetchone()[0] == 0
            results['probes']['partial_existing_users_do_not_trigger_reseed'] = {
                'existing_user_preserved':True, 'missing_demo_project_not_reseeded':True,
                'missing_credentials_not_recreated':not (base/'partial-credentials.json').exists()}
            c.close()

    OUT.write_text(json.dumps(results, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    run()
