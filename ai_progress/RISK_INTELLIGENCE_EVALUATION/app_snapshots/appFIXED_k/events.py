"""Whitelisted synthetic change events, automatic re-analysis and local alerts."""
from __future__ import annotations
import uuid
from fastapi import HTTPException
from .db import audit, dumps, now, transaction
from .security import require_role
from .analyzer import analyze
from .impact import node_source_requirements

SIGNALS = {
 'supplier_lead_days': {'root':'SUPPLIER-01','focus':'supplier','kind':'nonnegative_int'},
 'test_pass': {'root':'TEST-FAIL-01','focus':'test_failure','kind':'test_status'},
}


def simulate_event(conn, actor, project, event_source, external_event_id, signal_key, value):
    require_role(conn,actor,project,('manager','editor'))
    if signal_key not in SIGNALS:
        raise HTTPException(422,'不允許修改此模擬訊號')
    cfg = SIGNALS[signal_key]
    if cfg['kind']=='nonnegative_int':
        try:
            if str(int(value)) != str(value) or not 0<=int(value)<=3650:
                raise ValueError
        except (ValueError,TypeError):
            raise HTTPException(422,'交期必須為 0–3650 的整數天數')
    elif str(value) not in ('pass','fail','unknown'):
        raise HTTPException(422,'測試狀態限 pass/fail/unknown')
    event_source = event_source.strip()
    external_event_id = external_event_id.strip()
    if not 1<=len(event_source)<=80 or not 1<=len(external_event_id)<=80:
        raise HTTPException(422,'事件來源與事件識別碼不得空白且長度至多 80')
    with transaction(conn):
        previous = conn.execute('SELECT * FROM events WHERE project_id=? AND event_source=? AND external_event_id=?',
                                (project,event_source,external_event_id)).fetchone()
        if previous:
            if previous['signal_key']!=signal_key or previous['new_value']!=str(value):
                raise HTTPException(409,'重複事件 ID 對應不同內容')
            alert = conn.execute('SELECT id FROM alerts WHERE event_id=?',(previous['id'],)).fetchone()
            return {'event_id':previous['id'],'alert_id':alert['id'] if alert else None,'deduplicated':True}
        record = conn.execute('SELECT value FROM project_signals WHERE project_id=? AND key=?',
                              (project,signal_key)).fetchone()
        old = record['value'] if record else None
        changed = old != str(value)
        needs_review = changed and (signal_key != 'test_pass' or str(value) != 'pass')
        event_id = str(uuid.uuid4())
        alert_id = str(uuid.uuid4()) if needs_review else None
        conn.execute('INSERT INTO events VALUES (?,?,?,?,?,?,?,?,?)',
                     (event_id,project,event_source,external_event_id,signal_key,old,str(value),cfg['root'],now()))
        if changed:
            conn.execute('INSERT INTO project_signals VALUES (?,?,?,?) ON CONFLICT(project_id,key) DO UPDATE SET value=excluded.value,event_id=excluded.event_id',
                         (project,signal_key,str(value),event_id))
            conn.execute('UPDATE projects SET data_revision=data_revision+1 WHERE id=?',(project,))
        if needs_review:
            conn.execute('INSERT INTO alerts VALUES (?,?,?,?,?,?,?,?)',
                         (alert_id,project,event_id,'合成資料變更需確認',
                          f'{signal_key}: {old} → {value}。系統將重新分析依賴影響；非真實供應商事件。',
                          'open','{}',now()))
        audit(conn,actor,project,'simulate_event',event_id,{'key':signal_key,'from':old,'to':value,
                        'changed':changed,'needs_review':needs_review})
    if not needs_review:
        return {'event_id':event_id,'alert_id':None,'deduplicated':False,
                'analysis_status':'skipped_no_change' if not changed else 'skipped_no_risk',
                'reason':'無實質資料變動' if not changed else '通過的測試結果不應被誤報為失敗風險'}
    # The alert persists even when analysis fails: fail-closed, never fake successful processing.
    try:
        analysis = analyze(conn,actor,project,f'合成事件：{signal_key} 由 {old} 更改為 {value}',
                           cfg['focus'],mode='event')
        impact0 = analysis['impacts'][0]
        # Snapshot which source_id(s) prove each affected node, instead of baking the
        # creator's ACL-derived node names into the stored text: a later reader may hold
        # different (or since-revoked) access, and must be re-checked against this
        # snapshot at read time rather than the live dependency graph.
        node_sources = node_source_requirements(impact0)
        with transaction(conn):
            conn.execute('UPDATE alerts SET body=?, node_sources_json=? WHERE id=?',
                (f'{signal_key}: {old} → {value}。已重新分析 {analysis["analysis_id"]}；'
                 '影響不是已證明延期。',dumps(node_sources),alert_id))
        return {'event_id':event_id,'alert_id':alert_id,'analysis_id':analysis['analysis_id'],
                'affected_nodes':impact0['affected_nodes'],'deduplicated':False,'analysis_status':'completed'}
    except Exception as exc:
        with transaction(conn):
            conn.execute('UPDATE alerts SET body=? WHERE id=?',
                (f'{signal_key}: {old} → {value}。自動分析失敗（{type(exc).__name__}），請手動重試；不可視為已評估。',alert_id))
            audit(conn,actor,project,'event_analysis_failed',event_id,{'error_type':type(exc).__name__})
        return {'event_id':event_id,'alert_id':alert_id,'deduplicated':False,'analysis_status':'failed'}
