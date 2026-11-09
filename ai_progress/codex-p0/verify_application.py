"""P0 read-only application verification; mutates only disposable synthetic SQLite fixtures."""
from pathlib import Path
import json, sys, tempfile, importlib.metadata as metadata, subprocess, os
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from fastapi.testclient import TestClient
from app import db
from app.api import app
from scripts.evaluate import evaluate
OUT = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path(__file__).resolve().parent
OUT.mkdir(parents=True, exist_ok=True)
API = '/api/projects/demo-chamber'
results = {'langgraph_version':metadata.version('langgraph'), 'scenarios':{}}

def headers(tokens, name):
    return {'Authorization':'Bearer '+tokens[name]}

with tempfile.TemporaryDirectory(prefix='riskscope-codex-p0-') as td:
    db.DB_PATH=Path(td)/'db.sqlite3'
    db.CREDENTIALS_PATH=Path(td)/'tokens.json'
    with TestClient(app) as c:
        tokens=json.loads(db.CREDENTIALS_PATH.read_text())
        manager=headers(tokens,'manager'); engineer=headers(tokens,'engineer')
        response=c.post(API+'/analyze',headers=manager,json={'question':'負載提升能只換馬達嗎？'})
        assert response.status_code==200
        a=response.json()
        assert a['orchestration']=='langgraph'
        assert a['checks'][0]['numbers']['total_current_a']=='11'
        assert a['checks'][0]['numbers']['total_power_w']=='264'
        assert a['options'][0]['hard_constraint']=='blocked'
        assert a['decision_status']=='requires_human_review'
        conn=db.connect()
        calls=[r['tool_name'] for r in conn.execute('SELECT tool_name FROM tool_calls WHERE analysis_id=? ORDER BY id',(a['analysis_id'],))]
        assert calls==['get_context','check_constraints','trace_impact','trace_impact']
        result=evaluate(conn); conn.close()
        assert len(result['cases'])==12
        assert result['aggregate']['multi_hop']['true_positive']==45
        assert result['aggregate']['multi_hop']['path_precision']==1.0
        (OUT/'evaluation.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
        results['scenarios']['graph_smoke']={'http_status':response.status_code,'orchestration':a['orchestration'],'numbers':a['checks'][0]['numbers'],'option_a':a['options'][0]['hard_constraint'],'decision_status':a['decision_status'],'local_llm':a['local_llm']['status'],'tool_calls':calls,'credentials_mode':oct(db.CREDENTIALS_PATH.stat().st_mode & 0o777)}
        # Seed additional authorized synthetic documents to exercise retrieval's top-8 limit.
        conn=db.connect()
        for i in range(8):
            db.add_doc(conn,f'DOC-P0-{i:02}','demo-chamber','targettopic supporting note','test','Synthetic P0 distractor document targettopic')
        conn.close()
        before=c.post(API+'/analyze',headers=engineer,json={'question':'targettopic','focus':'motor_upgrade'}).json()
        retrieved=[d['id'] for d in before['documents']]
        tool_sources=sorted({e['source_id'] for check in before['checks'] for e in check.get('evidence',[])})
        assert 'DOC-PS' not in retrieved and 'DOC-PS' in tool_sources
        revoke=c.patch(API+'/documents/DOC-PS/access',headers=manager,json={'user_id':'engineer','enabled':False})
        assert revoke.status_code==200
        fresh=c.get(API+'/check',headers=engineer)
        old=c.get(API+'/analyses/'+before['analysis_id'],headers=engineer)
        results['scenarios']['stored_analysis_acl_gap']={'fixture':'8 extra authorized synthetic documents; original product code unchanged','retrieved_documents':retrieved,'tool_evidence_documents':tool_sources,'revoked_document':'DOC-PS','fresh_check_status':fresh.json()['status'],'stored_analysis_http_status':old.status_code,'revoked_source_still_in_response':old.status_code==200 and 'DOC-PS' in old.text,'expected':'403 or sanitized response without revoked evidence','finding_reproduced':old.status_code==200 and 'DOC-PS' in old.text}
        # API-only reproduction against standard project data: manager event alert after editor revocation.
        for doc in ('DOC-SUPPLIER','DOC-PLAN'):
            assert c.patch(API+'/documents/'+doc+'/access',headers=manager,json={'user_id':'engineer','enabled':False}).status_code==200
        impact=c.get(API+'/impact/SUPPLIER-01',headers=engineer).json()
        event=c.post(API+'/events',headers=manager,json={'external_event_id':'codex-acl-probe','signal_key':'supplier_lead_days','value':'18'}).json()
        alerts=c.get(API+'/alerts',headers=engineer)
        results['scenarios']['alert_acl_gap']={'revoked_documents':['DOC-SUPPLIER','DOC-PLAN'],'engineer_direct_affected_nodes':impact['affected_nodes'],'manager_event_analysis_status':event['analysis_status'],'engineer_alerts_http_status':alerts.status_code,'engineer_alert_bodies':[x['body'] for x in alerts.json()['alerts']],'expected':'No dependency-derived nodes from sources engineer cannot read','finding_reproduced':not impact['affected_nodes'] and any('PROCURE-01' in x['body'] for x in alerts.json()['alerts'])}
results['status']='verification completed; security findings require independent review'
(OUT/'application-probes.json').write_text(json.dumps(results,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(results,ensure_ascii=False,indent=2))
