"""Evidence-only probes against disposable seeded DBs; no product source modifications."""
import sys,json,tempfile,contextlib,importlib.metadata
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from app import db
from app.api import app
from fastapi.testclient import TestClient
P='/api/projects/demo-chamber'

@contextlib.contextmanager
def fresh():
    with tempfile.TemporaryDirectory(prefix='riskscope-acl-design-') as td:
        db.DB_PATH=Path(td)/'db.sqlite3';db.CREDENTIALS_PATH=Path(td)/'tokens.json'
        with TestClient(app) as c:
            tokens=json.loads(db.CREDENTIALS_PATH.read_text())
            yield c,{n:{'Authorization':'Bearer '+v} for n,v in tokens.items()}

output={'langgraph':importlib.metadata.version('langgraph'),'source_mutations':False,'scenarios':{}}
with fresh() as (c,h):
    for name,units in [('DOC-AUX','24 V 3 A'),('DOC-MOTOR','24 V 8 A'),('DOC-PLAN',''),('DOC-SUPPLIER','')]:
        body=('targettopic '+units+' '+('合成敘述。'*600))[:2500]
        r=c.patch(P+'/documents/'+name,headers=h['manager'],json={'expected_version':1,'body':body})
        assert r.status_code==200,(name,r.text)
    for key,val,unit in [('aux_continuous_current','3','A'),('motor_voltage','24','V'),('motor_continuous_current','8','A')]:
        r=c.patch(P+'/facts/'+key,headers=h['manager'],json={'value':val,'unit':unit,'evidence_version':2})
        assert r.status_code==200,(key,r.text)
    analysis=c.post(P+'/analyze',headers=h['engineer'],json={'question':'targettopic','focus':'motor_upgrade'}).json()
    retrieved=[x['id'] for x in analysis['documents']]
    assert 'DOC-PS' not in retrieved
    assert analysis['checks'][0]['status']=='fail'
    assert c.patch(P+'/documents/DOC-PS/access',headers=h['manager'],json={'user_id':'engineer','enabled':False}).status_code==200
    freshcheck=c.get(P+'/check',headers=h['engineer']).json()
    detail=c.get(P+'/analyses/'+analysis['analysis_id'],headers=h['engineer'])
    listed=c.get(P+'/analyses',headers=h['engineer']).json()['analyses']
    output['scenarios']['existing_seed_api_only_analysis']={
        'extra_documents_added':0,'all_business_updates_via_api':True,
        'retrieved_documents':retrieved,'fresh_check_status':freshcheck['status'],
        'old_analysis_http_status':detail.status_code,
        'revoked_evidence_present':any(x.get('source_id')=='DOC-PS' for x in detail.json().get('checks',[{}])[0].get('evidence',[])),
        'old_analysis_in_list':any(x['id']==analysis['analysis_id'] for x in listed),
        'finding_reproduced':detail.status_code==200 and freshcheck['status']=='unknown'
    }
with fresh() as (c,h):
    event=c.post(P+'/events',headers=h['manager'],json={'external_event_id':'before-revocation','signal_key':'supplier_lead_days','value':'18'}).json()
    before=c.get(P+'/alerts',headers=h['engineer']).json()['alerts']
    assert len(before)==1 and event['analysis_status']=='completed'
    for doc in ['DOC-SUPPLIER','DOC-PLAN']:
        assert c.patch(P+'/documents/'+doc+'/access',headers=h['manager'],json={'user_id':'engineer','enabled':False}).status_code==200
    after=c.get(P+'/alerts',headers=h['engineer']).json()['alerts']
    impact=c.get(P+'/impact/SUPPLIER-01',headers=h['engineer']).json()
    overview=c.get(P+'/overview',headers=h['engineer']).json()
    output['scenarios']['existing_alert_then_revocation']={
        'alerts_before':len(before),'alerts_after':len(after),
        'direct_affected_nodes_after':impact['affected_nodes'],
        'open_alert_count_after':overview['open_alerts'],
        'protected_node_in_old_alert':any('PROCURE-01' in x['body'] for x in after),
        'finding_reproduced':not impact['affected_nodes'] and any('PROCURE-01' in x['body'] for x in after)
    }
with fresh() as (c,h):
    for doc in ['DOC-SUPPLIER','DOC-PLAN']:
        assert c.patch(P+'/documents/'+doc+'/access',headers=h['manager'],json={'user_id':'engineer','enabled':False}).status_code==200
    event=c.post(P+'/events',headers=h['manager'],json={'external_event_id':'after-revocation','signal_key':'supplier_lead_days','value':'18'}).json()
    alerts=c.get(P+'/alerts',headers=h['engineer']).json()['alerts']
    direct=c.get(P+'/impact/SUPPLIER-01',headers=h['engineer']).json()
    output['scenarios']['standard_seed_only_alert_gap']={
        'extra_documents_added':0,'manager_event_analysis_status':event['analysis_status'],
        'engineer_direct_nodes':direct['affected_nodes'],
        'protected_node_in_alert':any('PROCURE-01' in x['body'] for x in alerts),
        'finding_reproduced':not direct['affected_nodes'] and any('PROCURE-01' in x['body'] for x in alerts)
    }
with fresh() as (c,h):
    conn=db.connect()
    for i in range(8):
        db.add_doc(conn,f'DOC-BOUNDARY-{i:02}','demo-chamber','targettopic note','test','targettopic synthetic note')
    conn.close()
    analysis=c.post(P+'/analyze',headers=h['engineer'],json={'question':'targettopic','focus':'supplier'}).json()
    assert analysis['checks']==[]
    assert 'DOC-PLAN' not in [d['id'] for d in analysis['documents']]
    sources={e['source_id'] for impact in analysis['impacts'] for path in impact['paths'] for e in path['evidence']}
    assert 'DOC-PLAN' in sources
    assert c.patch(P+'/documents/DOC-PLAN/access',headers=h['manager'],json={'user_id':'engineer','enabled':False}).status_code==200
    detail=c.get(P+'/analyses/'+analysis['analysis_id'],headers=h['engineer'])
    fresh_impact=c.get(P+'/impact/SUPPLIER-01',headers=h['engineer']).json()
    output['scenarios']['impact_evidence_without_engineering_checks']={
        'checks':analysis['checks'],'original_path_sources':sorted(sources),
        'fresh_affected_nodes':fresh_impact['affected_nodes'],
        'old_analysis_http_status':detail.status_code,
        'old_analysis_contains_revoked_source':'DOC-PLAN' in detail.text,
        'finding_reproduced':detail.status_code==200 and 'DOC-PLAN' in detail.text
    }
Path(__file__).with_name('api-boundaries.json').write_text(json.dumps(output,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(output,ensure_ascii=False,indent=2))
