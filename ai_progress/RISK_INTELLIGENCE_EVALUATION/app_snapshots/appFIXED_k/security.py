from __future__ import annotations
import hashlib
import hmac
from fastapi import Header, HTTPException


def authenticate(conn, authorization: str | None):
    if not authorization or not authorization.startswith('Bearer '):
        raise HTTPException(401, '請提供 Bearer API token（首次執行見 runtime/demo_credentials.json）')
    token = authorization[7:]
    if not token or len(token) > 200:
        raise HTTPException(401, '無效憑證')
    hashed = hashlib.sha256(token.encode()).hexdigest()
    row = conn.execute('SELECT id,display_name,token_hash FROM users WHERE active=1').fetchall()
    for user in row:
        if hmac.compare_digest(user['token_hash'], hashed):
            return user['id']
    raise HTTPException(401, '無效憑證')


def role_for(conn, actor, project):
    row = conn.execute('''SELECT p.role FROM project_members p JOIN users u ON p.user_id=u.id
                          WHERE p.user_id=? AND p.project_id=? AND p.active=1 AND u.active=1''',
                       (actor, project)).fetchone()
    if not row:
        raise HTTPException(403, '沒有專案權限或授權已撤銷')
    return row['role']


def require_role(conn, actor, project, allowed=('manager','editor','reader')):
    role = role_for(conn, actor, project)
    if role not in allowed:
        raise HTTPException(403, '角色沒有執行此操作的權限')
    return role


def document_permitted(conn, actor, project, doc_id):
    role_for(conn, actor, project)
    row = conn.execute('''SELECT 1 FROM documents d JOIN document_access a ON d.id=a.document_id
                          WHERE d.id=? AND d.project_id=? AND a.user_id=? AND a.enabled=1''',
                       (doc_id, project, actor)).fetchone()
    return bool(row)
