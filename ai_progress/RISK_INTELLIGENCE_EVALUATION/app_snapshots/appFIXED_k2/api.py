"""FastAPI API. Local-only PoC auth, no enterprise identity claims."""
from __future__ import annotations
import hashlib
import json
import re
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal
from fastapi import FastAPI, Depends, HTTPException, Header, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from .config import DB_PATH
from .db import connect, init_db, now, audit, transaction, dumps
from .security import authenticate, require_role, document_permitted
from .retrieval import get_context, visible_documents
from .engineering import power_continuous
from .impact import direct_links, trace_impact
from .analyzer import analyze
from .actions import request_action, review_action, execute_action, list_actions
from .events import simulate_event
from .chat import chat_turn

@asynccontextmanager
async def lifespan(app: FastAPI):
    conn = init_db()
    conn.close()
    yield

app = FastAPI(title='CrossDomain Risk Agent PoC', version='0.1.0', lifespan=lifespan,
              description='合成研發案例；只做可追溯分析與模擬寫入')


def session(authorization: str | None = Header(None)):
    conn = connect()
    try:
        actor = authenticate(conn,authorization)
        yield conn, actor
    finally:
        conn.close()

class AnalysisInput(BaseModel):
    question: str = Field(min_length=3,max_length=1000)
    focus: str = Field(default='motor_upgrade',max_length=60)
    priorities: list[str] = Field(default_factory=lambda:['品質','交期','成本'],max_length=5)
    use_local_llm: bool = False
    session_id: str | None = Field(default=None,max_length=80)

class ActionInput(BaseModel):
    analysis_id: str
    task_id: str
    new_state: Literal['planned','in_progress','blocked','done']
    idempotency_key: str

class ReviewInput(BaseModel):
    approve: bool

class EventInput(BaseModel):
    event_source: str = Field(default='manual-simulation')
    external_event_id: str
    signal_key: Literal['supplier_lead_days','test_pass']
    value: str

class DocUpdate(BaseModel):
    expected_version: int = Field(ge=1)
    body: str = Field(min_length=3,max_length=20000)

class FactUpdate(BaseModel):
    value: str = Field(max_length=100)
    unit: str
    evidence_version: int = Field(ge=1)

class PermissionUpdate(BaseModel):
    user_id: str
    enabled: bool

class EdgeInput(BaseModel):
    upstream: str = Field(min_length=1,max_length=80)
    downstream: str = Field(min_length=1,max_length=80)
    evidence_doc_id: str
    description: str = Field(min_length=1,max_length=400)

@app.get('/')
def home():
    return FileResponse(Path(__file__).resolve().parent/'static'/'index.html')

@app.get('/static/{name}')
def static_asset(name: Literal['app.css','app.js']):
    return FileResponse(Path(__file__).resolve().parent/'static'/name)

@app.get('/health')
def health():
    import importlib.util
    return {'status':'ok','poc':True,'langgraph_installed':bool(importlib.util.find_spec('langgraph')),
            'cloud_model_enabled':False}

@app.get('/api/me')
def me(s=Depends(session)):
    c, actor=s
    user=c.execute('SELECT id,display_name FROM users WHERE id=?',(actor,)).fetchone()
    projects=[dict(r) for r in c.execute('''SELECT p.id,p.title,p.data_revision,m.role FROM projects p
                   JOIN project_members m ON m.project_id=p.id
                   WHERE m.user_id=? AND m.active=1''',(actor,)).fetchall()]
    return {'user':dict(user),'projects':projects}

@app.get('/api/projects/{project}/overview')
def overview(project:str,s=Depends(session)):
    c,actor=s
    role=require_role(c,actor,project)
    pr=c.execute('SELECT * FROM projects WHERE id=?',(project,)).fetchone()
    tasks=[dict(r) for r in c.execute('SELECT * FROM simulated_tasks WHERE project_id=? ORDER BY task_id',(project,))]
    alert_count=c.execute('SELECT count(*) FROM alerts WHERE project_id=? AND status=?',(project,'open')).fetchone()[0]
    return {'project':dict(pr),'role':role,'visible_documents':len(visible_documents(c,actor,project)),
            'open_alerts':alert_count,'tasks':tasks,'policy':{'data_location':'local_sqlite',
            'outbound_cloud':'disabled','enterprise_auth':'not_implemented'}}

@app.get('/api/projects/{project}/documents')
def documents(project:str,s=Depends(session)):
    c,actor=s
    return {'documents':visible_documents(c,actor,project)}

@app.get('/api/projects/{project}/context')
def context(project:str,q:str='',s=Depends(session)):
    c,actor=s
    return {'documents':get_context(c,actor,project,q)}

@app.get('/api/projects/{project}/check')
def check(project:str,s=Depends(session)):
    c,actor=s
    return power_continuous(c,actor,project)

@app.post('/api/projects/{project}/analyze')
def analyze_route(project:str,inp:AnalysisInput,s=Depends(session)):
    c,actor=s
    return analyze(c,actor,project,inp.question,inp.focus,inp.priorities,
                   use_local_llm=inp.use_local_llm,session_id=inp.session_id)

@app.get('/api/projects/{project}/sessions/{session_id}')
def session_detail(project:str,session_id:str,s=Depends(session)):
    c,actor=s
    role=require_role(c,actor,project)
    row=c.execute('SELECT * FROM sessions WHERE id=? AND project_id=?',(session_id,project)).fetchone()
    if not row:
        raise HTTPException(404,'找不到此對話')
    if row['user_id']!=actor and role!='manager':
        raise HTTPException(403,'不能讀取他人的分析對話')
    turns=[]
    for r in c.execute('SELECT id,question,created_at,result_json FROM analyses WHERE session_id=? ORDER BY created_at',(session_id,)):
        parsed=json.loads(r['result_json'])
        # M5 started putting real computed numbers (checks.numbers, facts) into
        # `reply` so it could be specific instead of a generic one-liner -- this
        # broke the original assumption here that `reply` never carries raw
        # derived values, so it must now go through the same source-by-source ACL
        # re-check as _analysis_access before being handed back (Codex found this:
        # GET /analyses/{id} correctly 403s after revocation, but this endpoint
        # kept serving the old numbers verbatim via `reply`).
        revoked=any(not document_permitted(c,actor,project,sid) for sid in _result_source_ids(parsed))
        turns.append({'id':r['id'],'question':r['question'],'created_at':r['created_at'],
                      'reply':None if revoked else parsed.get('reply'),
                      'reply_source':None if revoked else parsed.get('reply_source'),
                      'redacted':revoked})
    session_out=dict(row)
    # M12.5.1: app/chat.py piggybacks an internal, non-fact_key sentinel
    # ('__previous_numbers__', the previous turn's computed numbers used only
    # to narrate a plan-to-plan delta) onto this same user_supplied_json
    # column to avoid a schema migration -- `dict(row)` above would otherwise
    # hand that internal bookkeeping key straight to the client raw inside
    # the JSON string, even though a caller of this endpoint only has any
    # reason to expect the real USER_SUPPLIABLE_KEYS fields here.
    try:
        supplied=json.loads(session_out.get('user_supplied_json') or '{}')
        supplied.pop('__previous_numbers__',None)
        session_out['user_supplied_json']=dumps(supplied)
    except (TypeError, ValueError):
        pass
    return {'session':session_out,'turns':turns}

class ChatInput(BaseModel):
    message: str = Field(min_length=1,max_length=1000)
    session_id: str = Field(min_length=1,max_length=80)
    focus: str = Field(default='motor_upgrade',max_length=60)
    use_local_llm: bool = True

@app.post('/api/projects/{project}/chat')
def chat_route(project:str,inp:ChatInput,s=Depends(session)):
    c,actor=s
    return chat_turn(c,actor,project,inp.message,inp.session_id,inp.focus,inp.use_local_llm)


def _result_source_ids(result):
    """Every document ID a stored analysis result's facts/risks/paths trace back to,
    not just the top-N retrieval context -- tool evidence and impact paths carry their
    own source_id that may reference a document outside the retrieved context list."""
    ids=set()
    for doc in result.get('documents',[]) or []:
        if doc.get('id'):
            ids.add(doc['id'])
    for src in result.get('sources',[]) or []:
        if src.get('id'):
            ids.add(src['id'])
    for check in result.get('checks',[]) or []:
        for ev in check.get('evidence',[]) or []:
            if ev.get('source_id'):
                ids.add(ev['source_id'])
    for impact in result.get('impacts',[]) or []:
        for path in impact.get('paths',[]) or []:
            for ev in path.get('evidence',[]) or []:
                if ev.get('source_id'):
                    ids.add(ev['source_id'])
    return ids


def _analysis_access(c,actor,project,row):
    role=require_role(c,actor,project)
    if row['user_id']!=actor and role!='manager':
        raise HTTPException(403,'不能讀取他人的分析紀錄')
    result=json.loads(row['result_json'])
    # A stored result may include previously authorized confidential evidence from
    # any source (retrieval context, engineering evidence, or impact-path evidence),
    # not only the documents list -- revoking any one of them must block the whole record.
    for source_id in _result_source_ids(result):
        if not document_permitted(c,actor,project,source_id):
            raise HTTPException(403,'該分析包含現已撤銷授權的來源；禁止重讀')
    return result

@app.get('/api/projects/{project}/analyses')
def analyses(project:str,s=Depends(session)):
    c,actor=s
    role=require_role(c,actor,project)
    if role=='manager':
        rows=c.execute('SELECT * FROM analyses WHERE project_id=? ORDER BY created_at DESC LIMIT 50',(project,)).fetchall()
    else:
        rows=c.execute('SELECT * FROM analyses WHERE project_id=? AND user_id=? ORDER BY created_at DESC LIMIT 50',(project,actor)).fetchall()
    allowed=[]
    for row in rows:
        try:
            res=_analysis_access(c,actor,project,row)
        except HTTPException:
            continue
        allowed.append({'id':row['id'],'question':row['question'],'focus':row['focus'],
                        'created_at':row['created_at'],'project_revision':row['project_revision'],
                        'risk_count':len(res['risks'])})
    return {'analyses':allowed}

@app.get('/api/projects/{project}/analyses/{analysis_id}')
def analysis_detail(project:str,analysis_id:str,s=Depends(session)):
    c,actor=s
    row=c.execute('SELECT * FROM analyses WHERE id=? AND project_id=?',(analysis_id,project)).fetchone()
    if not row:
        raise HTTPException(404,'找不到分析')
    result=_analysis_access(c,actor,project,row)
    return {'analysis_id':analysis_id,**result}

@app.get('/api/projects/{project}/impact/{root}')
def impact(project:str,root:str,s=Depends(session)):
    c,actor=s
    return trace_impact(c,actor,project,root)

@app.get('/api/projects/{project}/links/{root}')
def links(project:str,root:str,s=Depends(session)):
    c,actor=s
    return direct_links(c,actor,project,root)

@app.post('/api/projects/{project}/actions')
def action_new(project:str,inp:ActionInput,s=Depends(session)):
    c,actor=s
    return request_action(c,actor,project,inp.analysis_id,inp.task_id,inp.new_state,inp.idempotency_key)

@app.get('/api/projects/{project}/actions')
def action_list(project:str,s=Depends(session)):
    c,actor=s
    return {'actions':list_actions(c,actor,project)}

@app.post('/api/projects/{project}/actions/{action_id}/review')
def action_review(project:str,action_id:str,inp:ReviewInput,s=Depends(session)):
    c,actor=s
    return review_action(c,actor,project,action_id,inp.approve)

@app.post('/api/projects/{project}/actions/{action_id}/execute')
def action_execute(project:str,action_id:str,s=Depends(session)):
    c,actor=s
    return execute_action(c,actor,project,action_id)

@app.post('/api/projects/{project}/events')
def event_create(project:str,inp:EventInput,s=Depends(session)):
    c,actor=s
    return simulate_event(c,actor,project,inp.event_source,inp.external_event_id,inp.signal_key,inp.value)

_LEGACY_NODE_CLAUSE = re.compile('可能受影響節點：[^。]*。?')

def _alert_view(c,actor,project,row):
    """Alerts are project-wide (require_role only, no analysis-ownership restriction --
    a manager's alert must stay visible to any project member). But the affected-node
    clause was derived from whatever ACL the event's creator held at creation time, so
    it must be re-checked against the CURRENT reader's access to the snapshotted
    node_source_requirements before being shown, independently of who created it."""
    d=dict(row)
    node_sources=json.loads(d.pop('node_sources_json') or '{}')
    if not node_sources:
        # No snapshot to re-verify against. The post-fix code never persists the
        # node-name clause into `body` (it's appended dynamically below, only after
        # passing the current reader's ACL) -- so a stored body that already contains
        # this literal phrase can only have been written by the pre-fix code, with
        # unverifiable node names baked in. We cannot retroactively confirm whoever
        # reads it now still holds the source access that justified writing it, so the
        # safe default is to redact that clause for every reader rather than echo it
        # back verbatim -- without touching the stored row or resetting the database.
        if _LEGACY_NODE_CLAUSE.search(d['body']):
            d['body']=_LEGACY_NODE_CLAUSE.sub(
                '可能受影響節點：（此提醒建立於 ACL 安全修正前，內容已無法重新驗證來源授權，已遮蔽；如需最新結果請管理者重新觸發對應事件）。',
                d['body'])
        return d
    visible=sorted(node for node,groups in node_sources.items()
                    if any(all(document_permitted(c,actor,project,sid) for sid in group) for group in groups))
    hidden=len(node_sources)-len(visible)
    if visible:
        clause=f'可能受影響節點：{", ".join(visible)}。'
        if hidden:
            clause+=f'（另有 {hidden} 個節點因來源權限不足已隱藏）'
    else:
        clause='可能受影響節點：因目前來源權限不足無法顯示。'
    d['body']=d['body']+clause
    return d

@app.get('/api/projects/{project}/alerts')
def alerts(project:str,s=Depends(session)):
    c,actor=s
    require_role(c,actor,project)
    rows=c.execute('SELECT * FROM alerts WHERE project_id=? ORDER BY created_at DESC LIMIT 60',(project,)).fetchall()
    return {'alerts':[_alert_view(c,actor,project,r) for r in rows]}

@app.get('/api/projects/{project}/events')
def events(project:str,s=Depends(session)):
    c,actor=s
    require_role(c,actor,project)
    return {'events':[dict(r) for r in c.execute('SELECT * FROM events WHERE project_id=? ORDER BY created_at DESC LIMIT 60',(project,))]}

@app.patch('/api/projects/{project}/documents/{doc_id}')
def edit_document(project:str,doc_id:str,inp:DocUpdate,s=Depends(session)):
    c,actor=s
    require_role(c,actor,project,('manager',))
    if not document_permitted(c,actor,project,doc_id):
        raise HTTPException(403,'缺少文件授權')
    with transaction(c):
        row=c.execute('SELECT * FROM documents WHERE id=? AND project_id=?',(doc_id,project)).fetchone()
        if not row:
            raise HTTPException(404,'文件不存在')
        if inp.expected_version!=row['version']:
            raise HTTPException(409,'文件版本衝突')
        v=row['version']+1
        c.execute('UPDATE documents SET body=?,version=?,updated_at=? WHERE id=?',
                  (inp.body,v,now(),doc_id))
        c.execute('INSERT INTO document_revisions VALUES (?,?,?,?,?)',
                  (doc_id,v,inp.body,hashlib.sha256(inp.body.encode()).hexdigest(),now()))
        c.execute('UPDATE projects SET data_revision=data_revision+1 WHERE id=?',(project,))
        audit(c,actor,project,'update_document',doc_id,{'from_version':v-1,'to_version':v})
    return {'id':doc_id,'version':v,'dependent_facts':'stale_until_revalidated'}

@app.patch('/api/projects/{project}/facts/{key}')
def update_fact(project:str,key:str,inp:FactUpdate,s=Depends(session)):
    from .engineering import UNIT_TABLE,convert
    import re
    c,actor=s
    require_role(c,actor,project,('manager',))
    if inp.unit not in UNIT_TABLE:
        raise HTTPException(422,'不支援的單位')
    expected_dimension = 'voltage' if key.endswith('_voltage') else 'current' if key.endswith('_current') else None
    if expected_dimension is None:
        raise HTTPException(422,'此規格尚未有對應的維度驗證規則')
    try:
        convert(inp.value,inp.unit,expected_dimension)
    except ValueError as exc:
        raise HTTPException(422,str(exc))
    with transaction(c):
        row=c.execute('SELECT f.*, d.version, d.body FROM facts f JOIN documents d ON f.document_id=d.id WHERE f.project_id=? AND f.fact_key=?',(project,key)).fetchone()
        if not row:
            raise HTTPException(404,'規格不存在')
        if not document_permitted(c,actor,project,row['document_id']):
            raise HTTPException(403,'缺少來源權限')
        if inp.evidence_version!=row['version']:
            raise HTTPException(409,'必須先核對最新來源文件版本')
        # Require the updated value + unit to appear in the current authorized source.
        # This is basic traceability, NOT a substitute for professional document interpretation.
        pattern = r'(?<![\d.])' + re.escape(inp.value) + r'\s*' + re.escape(inp.unit) + r'\b'
        if not re.search(pattern,row['body'],flags=re.IGNORECASE):
            raise HTTPException(422,'來源文件最新版本不包含此數值與單位，禁止宣稱已重新驗證')
        c.execute('UPDATE facts SET value=?,unit=?,document_version=? WHERE project_id=? AND fact_key=?',
                  (inp.value,inp.unit,inp.evidence_version,project,key))
        c.execute('UPDATE projects SET data_revision=data_revision+1 WHERE id=?',(project,))
        audit(c,actor,project,'validate_fact',key,{'source_doc_id':row['document_id'],'source_version':inp.evidence_version})
    return {'fact':key,'source_version':inp.evidence_version,'status':'revalidated'}

@app.patch('/api/projects/{project}/documents/{doc_id}/access')
def set_doc_access(project:str,doc_id:str,inp:PermissionUpdate,s=Depends(session)):
    c,actor=s
    require_role(c,actor,project,('manager',))
    with transaction(c):
        if not c.execute('SELECT 1 FROM documents WHERE id=? AND project_id=?',(doc_id,project)).fetchone():
            raise HTTPException(404,'文件不存在')
        if not c.execute('SELECT 1 FROM users WHERE id=?',(inp.user_id,)).fetchone():
            raise HTTPException(404,'使用者不存在')
        c.execute('''INSERT INTO document_access(document_id,user_id,enabled) VALUES (?,?,?)
                    ON CONFLICT(document_id,user_id) DO UPDATE SET enabled=excluded.enabled''',
                  (doc_id,inp.user_id,int(inp.enabled)))
        c.execute('UPDATE projects SET data_revision=data_revision+1 WHERE id=?',(project,))
        audit(c,actor,project,'update_document_access',doc_id,{'user':inp.user_id,'enabled':inp.enabled})
    return {'doc_id':doc_id,'user_id':inp.user_id,'enabled':inp.enabled}

@app.patch('/api/projects/{project}/members/access')
def set_project_access(project:str,inp:PermissionUpdate,s=Depends(session)):
    c,actor=s
    require_role(c,actor,project,('manager',))
    with transaction(c):
        row=c.execute('SELECT * FROM project_members WHERE user_id=? AND project_id=?',(inp.user_id,project)).fetchone()
        if not row:
            raise HTTPException(404,'使用者不在專案成員中')
        if actor==inp.user_id and not inp.enabled:
            raise HTTPException(422,'不能自行撤銷目前管理帳號')
        c.execute('UPDATE project_members SET active=? WHERE user_id=? AND project_id=?',
                 (int(inp.enabled),inp.user_id,project))
        c.execute('UPDATE projects SET data_revision=data_revision+1 WHERE id=?',(project,))
        audit(c,actor,project,'update_member_access',inp.user_id,{'enabled':inp.enabled})
    return {'user_id':inp.user_id,'enabled':inp.enabled}

@app.post('/api/projects/{project}/dependencies')
def add_dependency(project:str,inp:EdgeInput,s=Depends(session)):
    from .db import now
    import uuid
    c,actor=s
    require_role(c,actor,project,('manager',))
    if not document_permitted(c,actor,project,inp.evidence_doc_id):
        raise HTTPException(403,'依賴來源未授權')
    row=c.execute('SELECT version FROM documents WHERE id=? AND project_id=?',(inp.evidence_doc_id,project)).fetchone()
    with transaction(c):
        did=str(uuid.uuid4())
        c.execute('INSERT INTO dependencies VALUES (?,?,?,?,?,?,?)',
                  (did,project,inp.upstream,inp.downstream,inp.evidence_doc_id,row['version'],inp.description))
        c.execute('UPDATE projects SET data_revision=data_revision+1 WHERE id=?',(project,))
        audit(c,actor,project,'add_dependency',did,{'from':inp.upstream,'to':inp.downstream})
    return {'id':did,'source_version':row['version']}

@app.get('/api/projects/{project}/audit')
def audit_log(project:str,s=Depends(session)):
    c,actor=s
    require_role(c,actor,project,('manager',))
    return {'logs':[dict(r) for r in c.execute('SELECT * FROM audit WHERE project_id=? ORDER BY id DESC LIMIT 100',(project,))]}
