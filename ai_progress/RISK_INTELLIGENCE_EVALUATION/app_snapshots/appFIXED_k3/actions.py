"""Simulated write actions with human approval, optimistic revision and idempotency."""
from __future__ import annotations
import json
import uuid
from fastapi import HTTPException
from .db import audit, dumps, now, transaction
from .security import require_role

VALID_STATES = {'planned','in_progress','blocked','done'}


def request_action(conn, actor, project, analysis_id, task_id, new_state, idempotency_key):
    role = require_role(conn,actor,project,('manager','editor'))
    if new_state not in VALID_STATES:
        raise HTTPException(422, '非法任務狀態')
    if not (3 <= len(idempotency_key) <= 100):
        raise HTTPException(422, 'idempotency_key 長度須介於 3–100')
    a = conn.execute('SELECT * FROM analyses WHERE id=? AND project_id=?',(analysis_id,project)).fetchone()
    if not a:
        raise HTTPException(404, '找不到分析紀錄')
    if a['user_id'] != actor and role != 'manager':
        raise HTTPException(403,'不可使用他人的分析紀錄')
    task = conn.execute('SELECT 1 FROM simulated_tasks WHERE project_id=? AND task_id=?',
                        (project,task_id)).fetchone()
    if not task:
        raise HTTPException(422,'僅能修改允許清單中的模擬任務')
    payload = {'task_id':task_id,'new_state':new_state}
    with transaction(conn):
        prior = conn.execute('SELECT * FROM actions WHERE project_id=? AND idempotency_key=?',
                             (project,idempotency_key)).fetchone()
        if prior:
            if prior['type']!='set_task_status' or prior['payload_json']!=dumps(payload) or prior['analysis_id']!=analysis_id:
                raise HTTPException(409,'相同冪等鍵對應不同內容')
            return {'action_id':prior['id'],'state':prior['state'],'reused':True}
        current = conn.execute('SELECT data_revision FROM projects WHERE id=?',(project,)).fetchone()['data_revision']
        if a['project_revision'] != current:
            raise HTTPException(409,'分析使用舊資料版本，請重新分析')
        aid = str(uuid.uuid4())
        conn.execute('INSERT INTO actions VALUES (?,?,?,?,?,?,?,?,?,?,?,?)',
           (aid,analysis_id,project,actor,'set_task_status',dumps(payload),idempotency_key,current,
            'pending',None,now(),now()))
        audit(conn,actor,project,'request_action',aid,{'task_id':task_id,'state':new_state})
    return {'action_id':aid,'state':'pending','reused':False}


def review_action(conn, actor, project, action_id, approve):
    require_role(conn,actor,project,('manager',))
    with transaction(conn):
        row = conn.execute('SELECT * FROM actions WHERE project_id=? AND id=?',(project,action_id)).fetchone()
        if not row:
            raise HTTPException(404,'找不到動作')
        if row['state']!='pending':
            raise HTTPException(409,'已審核的動作不可再次審核')
        rev = conn.execute('SELECT data_revision FROM projects WHERE id=?',(project,)).fetchone()['data_revision']
        if rev!=row['project_revision']:
            conn.execute('UPDATE actions SET state=?,updated_at=? WHERE id=?',('stale',now(),action_id))
            audit(conn,actor,project,'reject_stale_action',action_id,{'was_revision':row['project_revision'],'now_revision':rev})
            return {'action_id':action_id,'state':'stale','reason':'資料版本改變，必須重新分析和申請'}
        state = 'approved' if approve else 'rejected'
        conn.execute('UPDATE actions SET state=?,approver_id=?,updated_at=? WHERE id=?',(state,actor,now(),action_id))
        audit(conn,actor,project,'review_action',action_id,{'approved':approve})
        return {'action_id':action_id,'state':state}


def execute_action(conn, actor, project, action_id):
    require_role(conn,actor,project,('manager',))
    with transaction(conn):
        row = conn.execute('SELECT * FROM actions WHERE project_id=? AND id=?',(project,action_id)).fetchone()
        if not row:
            raise HTTPException(404,'找不到動作')
        if row['state']=='executed':
            return {'action_id':action_id,'state':'executed','reused':True}
        if row['state']!='approved':
            raise HTTPException(409,'動作尚未核准或已失效')
        rev = conn.execute('SELECT data_revision FROM projects WHERE id=?',(project,)).fetchone()['data_revision']
        if rev != row['project_revision']:
            conn.execute('UPDATE actions SET state=?,updated_at=? WHERE id=?',('stale',now(),action_id))
            audit(conn,actor,project,'reject_stale_execute',action_id,{'actual_revision':rev})
            return {'action_id':action_id,'state':'stale','reason':'核准後資料版本改變，禁止執行'}
        payload = json.loads(row['payload_json'])
        task_id = payload['task_id']
        exists = conn.execute('SELECT 1 FROM simulated_tasks WHERE project_id=? AND task_id=?',(project,task_id)).fetchone()
        if not exists or payload['new_state'] not in VALID_STATES:
            raise HTTPException(422,'模擬動作資料不合法')
        conn.execute('UPDATE simulated_tasks SET state=?,updated_at=? WHERE project_id=? AND task_id=?',
                    (payload['new_state'],now(),project,task_id))
        conn.execute('UPDATE actions SET state=?,updated_at=? WHERE id=?',('executed',now(),action_id))
        conn.execute('UPDATE projects SET data_revision=data_revision+1 WHERE id=?',(project,))
        audit(conn,actor,project,'execute_simulated_action',action_id,{'task_id':task_id,'value':payload['new_state']})
        return {'action_id':action_id,'state':'executed','reused':False,'simulated_only':True}


def list_actions(conn, actor, project):
    role = require_role(conn,actor,project)
    rows = conn.execute('SELECT * FROM actions WHERE project_id=? ORDER BY created_at DESC LIMIT 80',(project,)).fetchall()
    return [{**dict(r),'payload':json.loads(r['payload_json'])} for r in rows
            if role=='manager' or r['requested_by']==actor]
