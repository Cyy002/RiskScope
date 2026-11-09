"""Read-only integration diagnosis; business writes are confined to disposable DBs."""
from pathlib import Path
import sys,os,json,tempfile,time,hashlib,platform,importlib.metadata as metadata
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from app import config,chat,db
from app.api import app
from fastapi.testclient import TestClient
import httpx
mode=sys.argv[1]
out={'mode':mode,'python':sys.version,'platform':platform.platform(),'configured_url':config.local_ollama_url(),'configured_model':chat.OLLAMA_MODEL,'calls':[], 'versions':{p:metadata.version(p) for p in ['httpx','fastapi','langgraph']},'source_hashes':{p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in ['app/config.py','app/chat.py','compose.yml','Containerfile']}}
original=httpx.post

def record_post(url,**kwargs):
    started=time.monotonic();payload=kwargs.get('json',{})
    if mode == 'reply-timeout60' and '欄位清單' not in payload.get('prompt',''):
        kwargs['timeout']=60  # Diagnostic-only override; no product source changes.
    item={'url':url,'model':payload.get('model'),'timeout':kwargs.get('timeout'),'stage':'extract' if '欄位清單' in payload.get('prompt','') else 'reply'}
    try:
        r=original(url,**kwargs);item['http_status']=r.status_code
        try:
            body=r.json();item.update({'json_keys':list(body),'response_type':type(body.get('response')).__name__,'response_chars':len(str(body.get('response',''))),'thinking_chars':len(str(body.get('thinking',''))),'done':body.get('done'),'total_duration':body.get('total_duration'),'load_duration':body.get('load_duration'),'eval_count':body.get('eval_count')})
        except Exception as exc:item['json_error']=type(exc).__name__
        return r
    except Exception as exc:
        item['error_type']=type(exc).__name__;raise
    finally:
        item['elapsed_seconds']=round(time.monotonic()-started,3);out['calls'].append(item)
httpx.post=record_post
with tempfile.TemporaryDirectory(prefix='riskscope-ollama-diagnostic-') as td:
    db.DB_PATH=Path(td)/'db.sqlite3';db.CREDENTIALS_PATH=Path(td)/'tokens.json'
    with TestClient(app) as c:
        token=json.loads(db.CREDENTIALS_PATH.read_text())['engineer']
        started=time.monotonic()
        r=c.post('/api/projects/demo-chamber/chat',headers={'Authorization':'Bearer '+token},json={'message':'請評估馬達升級，目前需要補充哪些資訊？','session_id':'ollama-diagnostic','use_local_llm':True})
        data=r.json();out.update({'chat_http_status':r.status_code,'reply_source':data.get('reply_source'),'reply_chars':len(data.get('reply','')),'accepted_values':data.get('user_supplied_accepted_this_turn'),'constraint_status':data.get('checks',[{}])[0].get('status'),'decision_status':data.get('decision_status'),'elapsed_seconds':round(time.monotonic()-started,3)})
        history=c.get('/api/projects/demo-chamber/sessions/ollama-diagnostic',headers={'Authorization':'Bearer '+token}).json()
        out['persisted_reply_source']=history.get('turns',[{}])[0].get('reply_source')
path=Path(__file__).with_name('diagnostic-'+mode+'.json');path.write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n');print(json.dumps(out,ensure_ascii=False,indent=2))
