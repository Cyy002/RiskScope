"""One bounded audit run; deny production runtime and real network access."""
from pathlib import Path
import hashlib
import json
import os
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.dont_write_bytecode = True
files = sorted(list((ROOT / 'app').rglob('*.py')) +
               list((ROOT / 'tests').glob('test_*.py')))

def hashes():
    return {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in files}

before = hashes()
box = tempfile.TemporaryDirectory(prefix='riskscope-m12-review-')
base = Path(box.name).resolve()
os.environ['AGENT_DB_PATH'] = str(base / 'default.sqlite3')
os.environ['AGENT_CREDENTIALS_PATH'] = str(base / 'credentials.json')
os.environ['OLLAMA_URL'] = ''
db_paths, blocked = set(), []

def guard(event, args):
    if event == 'sqlite3.connect':
        path = Path(str(args[0])).resolve()
        if not path.is_relative_to(base):
            blocked.append('sqlite_outside_isolation')
            raise RuntimeError('Database outside review sandbox')
        db_paths.add(str(path.relative_to(base)))
    if event == 'open' and isinstance(args[0], (str, bytes, os.PathLike)):
        path = Path(os.fsdecode(args[0])).resolve()
        if path.is_relative_to(ROOT / 'runtime'):
            blocked.append('production_runtime_access')
            raise RuntimeError('Production runtime access forbidden')
    if event == 'socket.connect':
        address = args[1]
        if isinstance(address, tuple):
            blocked.append('network_connect')
            raise RuntimeError('Real network calls forbidden during isolated tests')

sys.addaudithook(guard)
import pytest

code = pytest.main(['-q', '--tb=short', '-p', 'no:cacheprovider',
                   '--basetemp', str(base / 'pytest'),
                   '--junitxml', str(Path(__file__).with_name('results.xml')),
                   *sys.argv[1:]])
after = hashes()
result = {
    'exit_code': int(code), 'distinct_temporary_databases': len(db_paths),
    'blocked_access_attempts': blocked,
    'product_and_existing_tests_unchanged': before == after,
    'source_hashes': after,
    'real_llm_calls': 0,
}
Path(__file__).with_name('isolation.json').write_text(json.dumps(result, indent=2) + '\n')
print(json.dumps({k: v for k, v in result.items() if k != 'source_hashes'}))
sys.exit(code)
