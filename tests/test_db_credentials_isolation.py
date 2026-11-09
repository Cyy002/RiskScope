"""Regression test for a credentials-overwrite footgun Codex independently
reproduced (ai_progress/codex-review-runtime/runtime-probe-results.json,
probe `db_only_override_replaces_default_credentials`): calling
init_db(path=<some other db>) without credentials_path used to fall back to
the global default CREDENTIALS_PATH, overwriting the default app's login
credentials with tokens that didn't match the default database's stored
hashes. Everything here uses temporary files only -- the real default
runtime/credentials are never touched."""
import json
from pathlib import Path

from app import db


def test_db_only_override_does_not_touch_default_credentials(tmp_path, monkeypatch):
    default_db = tmp_path / 'default.sqlite3'
    default_creds = tmp_path / 'default-credentials.json'
    monkeypatch.setattr(db, 'DB_PATH', default_db)
    monkeypatch.setattr(db, 'CREDENTIALS_PATH', default_creds)

    default_conn = db.init_db()
    default_hash_before = default_conn.execute(
        "SELECT token_hash FROM users WHERE id='manager'").fetchone()[0]
    default_creds_before = default_creds.read_text()
    default_conn.close()

    other_db = tmp_path / 'other' / 'other.sqlite3'
    other_conn = db.init_db(other_db)
    other_conn.close()

    # The default database's stored hash and credentials file must be
    # byte-for-byte unchanged.
    default_conn = db.connect(default_db)
    default_hash_after = default_conn.execute(
        "SELECT token_hash FROM users WHERE id='manager'").fetchone()[0]
    default_conn.close()
    assert default_hash_after == default_hash_before
    assert default_creds.read_text() == default_creds_before

    # The other database must get its OWN credentials file, next to it, named
    # after its own stem (not the default's basename) so it can never collide
    # with another database's derived credentials file in the same directory.
    derived_creds = other_db.parent / f'{other_db.stem}.{default_creds.name}'
    assert derived_creds.exists()
    other_conn = db.connect(other_db)
    other_hash = other_conn.execute(
        "SELECT token_hash FROM users WHERE id='manager'").fetchone()[0]
    other_conn.close()
    import hashlib
    other_tokens = json.loads(derived_creds.read_text())
    assert hashlib.sha256(other_tokens['manager'].encode()).hexdigest() == other_hash


def test_second_database_in_same_directory_does_not_collide_with_default(tmp_path, monkeypatch):
    """Codex's follow-up reproduction (ai_progress/codex-review-reverify/):
    two distinct databases sitting in the SAME directory must not derive the
    same credentials basename, or the second init_db() call overwrites the
    first database's credentials file even though neither call used the
    global default path."""
    default_db = tmp_path / 'default.sqlite3'
    default_creds = tmp_path / 'demo_credentials.json'
    monkeypatch.setattr(db, 'DB_PATH', default_db)
    monkeypatch.setattr(db, 'CREDENTIALS_PATH', default_creds)

    default_conn = db.init_db()
    default_hash_before = default_conn.execute(
        "SELECT token_hash FROM users WHERE id='manager'").fetchone()[0]
    default_creds_bytes_before = default_creds.read_bytes()
    default_conn.close()

    other_db = tmp_path / 'other.sqlite3'  # same directory as default_db
    other_conn = db.init_db(other_db)
    other_conn.close()

    default_conn = db.connect(default_db)
    default_hash_after = default_conn.execute(
        "SELECT token_hash FROM users WHERE id='manager'").fetchone()[0]
    default_conn.close()
    assert default_hash_after == default_hash_before
    assert default_creds.read_bytes() == default_creds_bytes_before


def test_default_init_still_works_with_no_args(tmp_path, monkeypatch):
    monkeypatch.setattr(db, 'DB_PATH', tmp_path / 'agent.sqlite3')
    monkeypatch.setattr(db, 'CREDENTIALS_PATH', tmp_path / 'demo_credentials.json')
    conn = db.init_db()
    assert conn.execute('SELECT count(*) FROM users').fetchone()[0] == 3
    assert (tmp_path / 'demo_credentials.json').exists()
    conn.close()


def test_explicit_matching_credentials_path_still_honored(tmp_path, monkeypatch):
    monkeypatch.setattr(db, 'DB_PATH', tmp_path / 'unused.sqlite3')
    monkeypatch.setattr(db, 'CREDENTIALS_PATH', tmp_path / 'unused-credentials.json')
    explicit_db = tmp_path / 'explicit' / 'explicit.sqlite3'
    explicit_creds = tmp_path / 'explicit-creds-elsewhere.json'
    conn = db.init_db(explicit_db, explicit_creds)
    conn.close()
    assert explicit_creds.exists()
    assert not (explicit_db.parent / 'demo_credentials.json').exists()
