"""Run only requested safety regressions; refuse all access to live runtime."""
from pathlib import Path
import os,sys,tempfile,json,hashlib
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
box=tempfile.TemporaryDirectory(prefix='riskscope-two-fix-review-')
base=Path(box.name).resolve()
os.environ['AGENT_DB_PATH']=str(base/'default.sqlite3')
os.environ['AGENT_CREDENTIALS_PATH']=str(base/'credentials.json')
os.environ['OLLAMA_URL']=''
sqlite_paths=set();blocked=[]
def audit(event,args):
    if event=='sqlite3.connect':
        p=Path(str(args[0])).resolve()
        if not p.is_relative_to(base):
            blocked.append('sqlite_outside_isolation');raise RuntimeError('Database outside isolated review directory')
        sqlite_paths.add(str(p.relative_to(base)))
    if event=='open' and isinstance(args[0],(str,bytes,os.PathLike)):
        p=Path(os.fsdecode(args[0])).resolve()
        if p.is_relative_to(ROOT/'runtime'):
            blocked.append('runtime_access');raise RuntimeError('Live runtime access prohibited')
sys.addaudithook(audit)
import pytest
code=pytest.main(['-q','--tb=short','-p','no:cacheprovider','--basetemp',str(base/'pytest'),*sys.argv[1:]])
out={'exit_code':int(code),'sqlite_connections_confined_to_temporary_directory':not blocked,
     'runtime_access_attempts':len(blocked),'distinct_temporary_database_paths':len(sqlite_paths),
     'source_hashes':{p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in ['app/api.py','app/db.py','app/static/app.js','tests/test_session_continuity.py','tests/test_db_credentials_isolation.py']}}
Path(__file__).with_name('isolation-'+('extra' if any('test_independent' in s for s in sys.argv) else 'existing')+'.json').write_text(json.dumps(out,indent=2)+'\n')
print(json.dumps({k:v for k,v in out.items() if k!='source_hashes'}))
sys.exit(code)
