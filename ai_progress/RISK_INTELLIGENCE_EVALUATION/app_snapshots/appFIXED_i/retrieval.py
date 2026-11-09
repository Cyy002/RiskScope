from __future__ import annotations
import re
from .config import MAX_DOC_CHARS, MAX_CONTEXT_CHARS
from .security import role_for, document_permitted


def visible_documents(conn, actor, project):
    role_for(conn, actor, project)
    return [dict(r) for r in conn.execute('''
      SELECT d.id,d.title,d.category,d.classification,d.version,d.body,d.updated_at
      FROM documents d JOIN document_access a ON a.document_id=d.id
      WHERE d.project_id=? AND a.user_id=? AND a.enabled=1 ORDER BY d.id
    ''', (project, actor)).fetchall()]


def get_context(conn, actor, project, query='', limit=6):
    """Allowlist retrieval BEFORE scoring; inaccessible text cannot enter a model prompt."""
    docs = visible_documents(conn, actor, project)
    tokens = set(re.findall(r'[a-zA-Z]+[-\d]*|\d+|[\u4e00-\u9fff]{1,3}', query.lower()))
    def score(doc):
        text = (doc['title'] + ' ' + doc['body']).lower()
        return sum(3 if token in doc['title'].lower() else 1 for token in tokens if token in text)
    docs.sort(key=lambda doc: (-score(doc), doc['id']))
    out = []
    remaining = MAX_CONTEXT_CHARS
    for doc in docs[:max(0,min(limit,12))]:
        text = doc['body'][:min(MAX_DOC_CHARS,remaining)]
        remaining -= len(text)
        if remaining <= 0:
            break
        out.append({k:v for k,v in doc.items() if k != 'body'} | {'excerpt':text, 'truncated': len(text)!=len(doc['body'])})
    return out


def read_facts(conn, actor, project, keys):
    """Return missing/stale/unauthorized distinctly; never use fact values if evidence is invalid."""
    role_for(conn, actor, project)
    result = {}
    for key in keys:
        row = conn.execute('''SELECT f.*,d.version AS latest_version FROM facts f
                              JOIN documents d ON d.id=f.document_id
                              WHERE f.project_id=? AND f.fact_key=?''', (project,key)).fetchone()
        if row is None:
            result[key] = {'status':'missing'}
        elif not document_permitted(conn,actor,project,row['document_id']):
            result[key] = {'status':'unauthorized'}
        elif row['document_version'] != row['latest_version']:
            result[key] = {'status':'stale','document_id':row['document_id'], 'stored_version':row['document_version'], 'latest_version':row['latest_version']}
        else:
            result[key] = {'status':'ok','value':row['value'],'unit':row['unit'],
                           'source_id':row['document_id'],'source_version':row['document_version']}
    return result
