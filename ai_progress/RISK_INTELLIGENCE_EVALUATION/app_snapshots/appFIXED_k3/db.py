from __future__ import annotations
import contextlib
import hashlib
import json
import secrets
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator
from .config import DB_PATH, CREDENTIALS_PATH


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def dumps(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True)


def connect(path: Path | str | None = None) -> sqlite3.Connection:
    dest = Path(path or DB_PATH)
    dest.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(dest), timeout=20, check_same_thread=False, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA foreign_keys=ON')
    conn.execute('PRAGMA busy_timeout=20000')
    conn.execute('PRAGMA journal_mode=WAL')
    return conn


@contextlib.contextmanager
def transaction(conn: sqlite3.Connection) -> Iterator[sqlite3.Connection]:
    conn.execute('BEGIN IMMEDIATE')
    try:
        yield conn
        conn.execute('COMMIT')
    except BaseException:
        conn.execute('ROLLBACK')
        raise


SCHEMA = '''
CREATE TABLE IF NOT EXISTS users(
 id TEXT PRIMARY KEY, display_name TEXT NOT NULL, token_hash TEXT UNIQUE NOT NULL,
 active INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS projects(
 id TEXT PRIMARY KEY, title TEXT NOT NULL, data_revision INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS project_members(
 user_id TEXT NOT NULL REFERENCES users(id), project_id TEXT NOT NULL REFERENCES projects(id),
 role TEXT NOT NULL CHECK(role IN ('manager','editor','reader')), active INTEGER NOT NULL DEFAULT 1,
 PRIMARY KEY(user_id,project_id)
);
CREATE TABLE IF NOT EXISTS documents(
 id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id),
 title TEXT NOT NULL, category TEXT NOT NULL,
 classification TEXT NOT NULL CHECK(classification IN ('synthetic','internal','confidential','unclassified')),
 version INTEGER NOT NULL DEFAULT 1, body TEXT NOT NULL, created_at TEXT NOT NULL,
 updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS document_revisions(
 document_id TEXT NOT NULL REFERENCES documents(id), version INTEGER NOT NULL,
 body TEXT NOT NULL, sha256 TEXT NOT NULL, changed_at TEXT NOT NULL,
 PRIMARY KEY(document_id,version)
);
CREATE TABLE IF NOT EXISTS document_access(
 document_id TEXT NOT NULL REFERENCES documents(id), user_id TEXT NOT NULL REFERENCES users(id),
 enabled INTEGER NOT NULL, PRIMARY KEY(document_id,user_id)
);
CREATE TABLE IF NOT EXISTS facts(
 id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id),
 fact_key TEXT NOT NULL, value TEXT NOT NULL, unit TEXT NOT NULL,
 document_id TEXT NOT NULL REFERENCES documents(id), document_version INTEGER NOT NULL,
 UNIQUE(project_id,fact_key)
);
CREATE TABLE IF NOT EXISTS dependencies(
 id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id),
 upstream TEXT NOT NULL, downstream TEXT NOT NULL,
 evidence_doc_id TEXT NOT NULL REFERENCES documents(id), evidence_version INTEGER NOT NULL,
 description TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS sessions(
 id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id),
 user_id TEXT NOT NULL REFERENCES users(id), focus TEXT NOT NULL,
 status TEXT NOT NULL DEFAULT 'open' CHECK(status IN ('open','closed')),
 user_supplied_json TEXT NOT NULL DEFAULT '{}',
 created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS analyses(
 id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id), user_id TEXT NOT NULL REFERENCES users(id),
 question TEXT NOT NULL, focus TEXT NOT NULL, mode TEXT NOT NULL,
 project_revision INTEGER NOT NULL, created_at TEXT NOT NULL, result_json TEXT NOT NULL,
 session_id TEXT REFERENCES sessions(id)
);
CREATE TABLE IF NOT EXISTS tool_calls(
 id INTEGER PRIMARY KEY AUTOINCREMENT, analysis_id TEXT NOT NULL REFERENCES analyses(id),
 tool_name TEXT NOT NULL, arguments_json TEXT NOT NULL, result_json TEXT NOT NULL,
 created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS actions(
 id TEXT PRIMARY KEY, analysis_id TEXT NOT NULL REFERENCES analyses(id), project_id TEXT NOT NULL REFERENCES projects(id),
 requested_by TEXT NOT NULL REFERENCES users(id), type TEXT NOT NULL,
 payload_json TEXT NOT NULL, idempotency_key TEXT NOT NULL,
 project_revision INTEGER NOT NULL, state TEXT NOT NULL, approver_id TEXT,
 created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
 UNIQUE(project_id,idempotency_key)
);
CREATE TABLE IF NOT EXISTS simulated_tasks(
 project_id TEXT NOT NULL REFERENCES projects(id), task_id TEXT NOT NULL,
 state TEXT NOT NULL, updated_at TEXT NOT NULL,
 PRIMARY KEY(project_id,task_id)
);
CREATE TABLE IF NOT EXISTS events(
 id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id),
 event_source TEXT NOT NULL, external_event_id TEXT NOT NULL,
 signal_key TEXT NOT NULL, old_value TEXT, new_value TEXT NOT NULL,
 root_node TEXT NOT NULL, created_at TEXT NOT NULL,
 UNIQUE(project_id,event_source,external_event_id)
);
CREATE TABLE IF NOT EXISTS project_signals(
 project_id TEXT NOT NULL REFERENCES projects(id), key TEXT NOT NULL,
 value TEXT NOT NULL, event_id TEXT, PRIMARY KEY(project_id,key)
);
CREATE TABLE IF NOT EXISTS alerts(
 id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id),
 event_id TEXT NOT NULL UNIQUE REFERENCES events(id),
 title TEXT NOT NULL, body TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'open',
 node_sources_json TEXT NOT NULL DEFAULT '{}',
 created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS audit(
 id INTEGER PRIMARY KEY AUTOINCREMENT, actor_id TEXT, project_id TEXT,
 operation TEXT NOT NULL, target TEXT NOT NULL, details_json TEXT NOT NULL,
 created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_documents_project ON documents(project_id);
CREATE INDEX IF NOT EXISTS idx_facts_project ON facts(project_id);
CREATE INDEX IF NOT EXISTS idx_analyses_project ON analyses(project_id,created_at);
CREATE INDEX IF NOT EXISTS idx_dep_source ON dependencies(project_id,upstream);
'''


def audit(conn, actor, project, operation, target, details=None):
    conn.execute('INSERT INTO audit(actor_id,project_id,operation,target,details_json,created_at) VALUES (?,?,?,?,?,?)',
                 (actor, project, operation, target, dumps(details or {}), now()))


def add_doc(conn, doc_id, project_id, title, category, body, allowed=('manager', 'engineer'), classification='synthetic'):
    t = now()
    conn.execute('INSERT INTO documents VALUES (?,?,?,?,?,?,?,?,?)',
                 (doc_id, project_id, title, category, classification, 1, body, t, t))
    conn.execute('INSERT INTO document_revisions VALUES (?,?,?,?,?)',
                 (doc_id, 1, body, hashlib.sha256(body.encode()).hexdigest(), t))
    for user in allowed:
        conn.execute('INSERT INTO document_access VALUES (?,?,1)', (doc_id, user))


def init_db(path=None, credentials_path=None):
    """Idempotent bootstrapping. Secrets are generated locally, never committed.

    If `path` is given without `credentials_path`, the credentials file is
    derived from `path`'s own directory instead of falling back to the global
    default CREDENTIALS_PATH -- otherwise initializing some other database
    would silently overwrite the default app's login credentials with tokens
    that don't match that default database's stored hashes (found during
    independent review; see ai_progress/codex-review-runtime/). The derived
    name is also keyed on `path`'s own stem, not just its directory -- two
    different databases that happen to sit in the *same* directory (Codex's
    follow-up reproduction, ai_progress/codex-review-reverify/) must still get
    distinct credentials files instead of colliding on one shared basename."""
    if credentials_path is None and path is not None:
        db_path = Path(path).resolve()
        credentials_path = db_path.parent / f'{db_path.stem}.{CREDENTIALS_PATH.name}'
    conn = connect(path)
    conn.executescript(SCHEMA)
    try:
        # CREATE TABLE IF NOT EXISTS does not retrofit columns onto a pre-existing
        # alerts table from before this snapshot column existed.
        conn.execute("ALTER TABLE alerts ADD COLUMN node_sources_json TEXT NOT NULL DEFAULT '{}'")
    except sqlite3.OperationalError:
        pass
    try:
        # Same retrofit for analyses.session_id on a pre-existing database from
        # before multi-turn sessions existed; the new `sessions` table itself is
        # created fresh by the CREATE TABLE IF NOT EXISTS above.
        conn.execute('ALTER TABLE analyses ADD COLUMN session_id TEXT REFERENCES sessions(id)')
    except sqlite3.OperationalError:
        pass
    try:
        # Retrofit for a pre-existing sessions table from before user-supplied
        # values existed.
        conn.execute("ALTER TABLE sessions ADD COLUMN user_supplied_json TEXT NOT NULL DEFAULT '{}'")
    except sqlite3.OperationalError:
        pass
    if conn.execute('SELECT 1 FROM users LIMIT 1').fetchone():
        return conn
    tokens = {n: secrets.token_urlsafe(36) for n in ('manager', 'engineer', 'outsider')}
    with transaction(conn):
        for user, display in [('manager', '專案管理者'), ('engineer', '研發工程師'), ('outsider', '無權限帳號')]:
            conn.execute('INSERT INTO users VALUES (?,?,?,1)',
                         (user, display, hashlib.sha256(tokens[user].encode()).hexdigest()))
        conn.execute('INSERT INTO projects VALUES (?,?,1)', ('demo-chamber', '軟硬體整合設備｜合成研發案例'))
        conn.executemany('INSERT INTO project_members VALUES (?,?,?,1)', [
            ('manager', 'demo-chamber', 'manager'), ('engineer', 'demo-chamber', 'editor')
        ])
        project = 'demo-chamber'
        add_doc(conn, 'DOC-PS', project, 'PS-01 電源規格', '電氣',
                '合成規格：PS-01，24 V DC，連續額定電流 10 A（額定連續輸出 240 W）；不含啟動峰值、降額曲線與實測溫度。')
        add_doc(conn, 'DOC-MOTOR', project, 'M-02 馬達候選規格', '機電',
                '合成規格：M-02，24 V，指定工況連續輸入電流 8 A；尚無啟動電流、驅動器相容性與尺寸完整資料。')
        add_doc(conn, 'DOC-AUX', project, '其他系統負載', '電氣',
                '合成估計：同一個 24 V 電源另有持續 3 A 負載，假設與 M-02 同時連續運作。')
        add_doc(conn, 'DOC-PLAN', project, '整合研發依賴與驗證任務', '專案',
                '合成依賴：馬達影響驅動器／機構；驅動器影響韌體；機構影響熱評估；電源影響配線；整合與回歸測試需依賴各設計。未提供工期，不可推算延期天數。')
        add_doc(conn, 'DOC-CONF', project, '機密：內部成本假設（權限測試）', '成本',
                '合成敏感資料：此文件僅為 ACL 測試，非真實報價。', allowed=('manager',), classification='confidential')
        add_doc(conn, 'DOC-SUPPLIER', project, '合成供應商與需求修訂', '採購',
                '合成事件：採購交期變更可能影響採購、整合與驗證里程碑；工期與緩衝尚未確認。')
        facts = [
            ('F-PS-V','supply_voltage','24','V','DOC-PS'),
            ('F-PS-A','supply_continuous_current','10','A','DOC-PS'),
            ('F-M-V','motor_voltage','24','V','DOC-MOTOR'),
            ('F-M-A','motor_continuous_current','8','A','DOC-MOTOR'),
            ('F-A-A','aux_continuous_current','3','A','DOC-AUX'),
        ]
        for fid, key, val, unit, doc_id in facts:
            conn.execute('INSERT INTO facts VALUES (?,?,?,?,?,?,1)', (fid, project, key, val, unit, doc_id))
        edges = [
            ('M-02','DRIVER-01','DOC-PLAN','馬達變更需核對驅動器'),
            ('DRIVER-01','FIRMWARE-01','DOC-PLAN','驅動器影響韌體保護'),
            ('FIRMWARE-01','TEST-01','DOC-PLAN','韌體變更需回歸測試'),
            ('M-02','MECH-01','DOC-PLAN','馬達尺寸影響機構'),
            ('MECH-01','THERMAL-01','DOC-PLAN','機構更動需熱評估'),
            ('THERMAL-01','TEST-01','DOC-PLAN','熱評估納入驗證'),
            ('PS-01','WIRING-01','DOC-PLAN','電源調整可能影響配線'),
            ('WIRING-01','ASSEMBLY-01','DOC-PLAN','配線變更影響組裝'),
            ('ASSEMBLY-01','TEST-01','DOC-PLAN','組裝後須回歸測試'),
            ('TEST-01','RELEASE-01','DOC-PLAN','測試影響交付里程碑'),
            ('SUPPLIER-01','PROCURE-01','DOC-SUPPLIER','供應商交期影響採購'),
            ('PROCURE-01','ASSEMBLY-01','DOC-SUPPLIER','採購到貨影響組裝'),
            ('REQ-01','M-02','DOC-PLAN','需求修改造成選型重審'),
            ('TEST-FAIL-01','TEST-01','DOC-PLAN','測試失敗須重驗'),
            ('EXTERNAL-01','PROCURE-01','DOC-SUPPLIER','外部資源影響採購'),
            ('DRIVER-02','DRIVER-01','DOC-PLAN','驅動器選型變更'),
            ('FW-REQ-01','FIRMWARE-01','DOC-PLAN','韌體需求變更'),
            ('MECH-CLEARANCE-01','MECH-01','DOC-PLAN','機構干涉風險'),
            ('THERMAL-LIMIT-01','THERMAL-01','DOC-PLAN','熱限制影響驗證'),
        ]
        for i, (up, down, doc, descr) in enumerate(edges, 1):
            conn.execute('INSERT INTO dependencies VALUES (?,?,?,?,?,?,?)',
                         (f'DEP-{i:02}', project, up, down, doc, 1, descr))
        for task in ('PROCURE-01','ASSEMBLY-01','TEST-01','RELEASE-01'):
            conn.execute('INSERT INTO simulated_tasks VALUES (?,?,?,?)', (project, task, 'planned', now()))
        for k,v in (('supplier_lead_days','7'), ('test_pass','unknown')):
            conn.execute('INSERT INTO project_signals VALUES (?,?,?,NULL)', (project,k,v))
        audit(conn, 'system', project, 'initialize', project, {'synthetic': True})
    credential_file = Path(credentials_path or CREDENTIALS_PATH)
    credential_file.parent.mkdir(parents=True, exist_ok=True)
    credential_file.write_text(json.dumps(tokens, ensure_ascii=False, indent=2), encoding='utf-8')
    credential_file.chmod(0o600)
    return conn
