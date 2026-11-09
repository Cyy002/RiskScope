"""Eight independent contracts; host, static, mock and Podman evidence stay separate.

Run with the project's existing Python. Snapshot is source-only, frozen before review.
No production files, tokens, ports or volumes are used. No model inference occurs.
"""
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import uuid

import pytest

HERE = Path(__file__).resolve().parent
SNAPSHOT = Path(os.getenv("P0_REVIEW_SOURCE", str(HERE / "snapshot"))).resolve()
PREAMBLE = r'''
import os, json, hashlib, socket
from pathlib import Path
assert Path(os.environ['AGENT_DB_PATH']).is_relative_to(Path(os.environ['REVIEW_TMP']))
assert Path(os.environ['AGENT_CREDENTIALS_PATH']).is_relative_to(Path(os.environ['REVIEW_TMP']))
def deny_network(*args, **kwargs):
    raise AssertionError('This review forbids external network/model calls')
socket.socket.connect = deny_network
socket.create_connection = deny_network
'''


def run_host(tmp_path, body, **overrides):
    env = os.environ.copy()
    env.update(PYTHONPATH=str(SNAPSHOT), PYTHONDONTWRITEBYTECODE="1",
               REVIEW_TMP=str(tmp_path), AGENT_DB_PATH=str(tmp_path / "fresh.sqlite3"),
               AGENT_CREDENTIALS_PATH=str(tmp_path / "new_credentials.json"),
               OLLAMA_URL="", OLLAMA_MODEL="review-only", OLLAMA_REPLY_TIMEOUT_SECONDS="")
    env.update(overrides)
    result = subprocess.run([sys.executable, "-c", PREAMBLE + body], cwd=tmp_path,
                            env=env, text=True, capture_output=True, timeout=45)
    assert result.returncode == 0, result.stderr
    return result.stdout


def test_01_clean_data_directory_initializes_accounts_and_schema(tmp_path):
    """HOST initialization, not a real named-volume claim."""
    run_host(tmp_path, r'''
from app.db import init_db
c = init_db()
assert c.execute('SELECT count(*) FROM users').fetchone()[0] == 3
assert c.execute('SELECT count(*) FROM facts').fetchone()[0] >= 5
p = Path(os.environ['AGENT_CREDENTIALS_PATH'])
assert p.stat().st_mode & 0o777 == 0o600
assert set(json.loads(p.read_text())) == {'manager','engineer','outsider'}
c.close()
''')


def test_02_credentials_are_fresh_independent_and_authenticate(tmp_path):
    """HOST fresh synthetic credentials; neither production nor snapshot tokens."""
    run_host(tmp_path, r'''
from app.db import init_db
from app.security import authenticate
from fastapi import HTTPException
p = Path(os.environ['REVIEW_TMP'])
a = init_db(p/'a.sqlite3', p/'a.json'); b = init_db(p/'b.sqlite3', p/'b.json')
ta=json.loads((p/'a.json').read_text()); tb=json.loads((p/'b.json').read_text())
assert not (set(ta.values()) & set(tb.values()))
assert authenticate(a,'Bearer '+ta['engineer']) == 'engineer'
try:
    authenticate(b,'Bearer '+ta['engineer'])
except HTTPException as e:
    assert e.status_code == 401
else:
    raise AssertionError('Cross-instance token accepted')
a.close(); b.close()
''')


def test_03_model_url_name_and_timeout_are_configurable(tmp_path):
    """MOCK transport only: proves request wiring, NOT actual model connectivity."""
    run_host(tmp_path, r'''
from app import config
from app.llm_client import call_ollama
import httpx
seen = {}
def fake_post(url, **kw):
    seen.update(url=url, **kw)
    return httpx.Response(200,json={'response':'transport fixture only'})
httpx.post = fake_post
assert config.reply_timeout_seconds() == 73
_, diag = call_ollama('synthetic', timeout=config.reply_timeout_seconds())
assert diag['status'] == 'success'
assert seen['url'] == 'http://host.containers.internal:11555/api/generate'
assert seen['json']['model'] == 'review-configurable-model'
assert seen['json']['think'] is False and seen['timeout'] == 73
''', OLLAMA_URL="http://host.containers.internal:11555",
       OLLAMA_MODEL="review-configurable-model", OLLAMA_REPLY_TIMEOUT_SECONDS="73")


def test_04_build_inputs_have_no_mac_absolute_paths_or_forced_arm64():
    """STATIC only; no wheel availability or AMD64 execution inferred."""
    inputs = [SNAPSHOT/x for x in ("Containerfile", "compose.yml", "app/config.py",
                                   "requirements.txt", "requirements-langgraph.txt")]
    for p in inputs:
        text = p.read_text()
        assert not re.search(r"/(?:Users|opt/homebrew|Applications)/", text), p.name
        assert not re.search(r"--platform[= ](?:linux/)?(?:arm64|aarch64)", text), p.name


def test_05_copied_env_must_preserve_container_to_host_model_address():
    """STATIC deploy contract: documented copy-to-.env must not select self-loopback."""
    active = dict(line.strip().split("=", 1) for line in (SNAPSHOT/".env.example").read_text().splitlines()
                  if line.strip() and not line.lstrip().startswith("#") and "=" in line)
    compose = (SNAPSHOT/"compose.yml").read_text()
    default = re.search(r"OLLAMA_URL=\$\{OLLAMA_URL:-([^}]+)\}", compose).group(1)
    effective = active.get("OLLAMA_URL") or default
    assert effective == "http://host.containers.internal:11434", (
        "Copying .env.example overrides Compose's host gateway with container loopback: " + effective)


def test_06_build_context_excludes_private_env_and_backups():
    """STATIC existing simple ignore list; does not claim secrets are in final image."""
    rules = [line.strip().strip('/') for line in (SNAPSHOT/".containerignore").read_text().splitlines()
             if line.strip() and not line.lstrip().startswith('#')]
    # Conservative contract for this current manifest: recognized explicit exclusions.
    missing = []
    if not any(x in rules for x in ('.env', '.env*', '*')):
        missing.append('.env')
    if not any(x in rules for x in ('ai_progress', 'ai_progress/backups', 'ai_progress/*', '*')):
        missing.append('ai_progress/backups')
    assert not missing, 'Missing explicit private build-context exclusions: '+', '.join(missing)


def test_07_real_agent_api_and_data_survive_new_python_process(tmp_path):
    """REAL deterministic Agent/API + process restart, no model or container claim."""
    run_host(tmp_path, r'''
from fastapi.testclient import TestClient
from app.api import app
from app.db import connect
with TestClient(app) as client:
    tokens=json.loads(Path(os.environ['AGENT_CREDENTIALS_PATH']).read_text())
    h={'Authorization':'Bearer '+tokens['engineer']}
    url='/api/projects/demo-chamber/analyze'
    assert client.post(url,json={'question':'馬達與電源負載分析'}).status_code == 401
    r=client.post(url,headers=h,json={'question':'馬達與電源負載分析','use_local_llm':False})
    assert r.status_code == 200
    a=r.json()
    assert a['checks'][0]['numbers']['total_current_a'] == '11'
    assert a['checks'][0]['numbers']['total_power_w'] == '264'
    assert a['facts'][0]['sources'] and a['impacts'][0]['affected_nodes']
    assert a['decision_status'] == 'requires_human_review'
    c=connect()
    assert c.execute('SELECT count(*) FROM tool_calls WHERE analysis_id=?',(a['analysis_id'],)).fetchone()[0] > 0
    assert c.execute('SELECT count(*) FROM actions').fetchone()[0] == 0
    c.close()
    p=Path(os.environ['REVIEW_TMP'])
    (p/'record.json').write_text(json.dumps({'id':a['analysis_id'], 'result':a,
       'credential_sha':hashlib.sha256(Path(os.environ['AGENT_CREDENTIALS_PATH']).read_bytes()).hexdigest()}))
''')
    run_host(tmp_path, r'''
from fastapi.testclient import TestClient
from app.api import app
from app.db import connect
saved=json.loads((Path(os.environ['REVIEW_TMP'])/'record.json').read_text())
with TestClient(app) as client:
    p=Path(os.environ['AGENT_CREDENTIALS_PATH'])
    assert hashlib.sha256(p.read_bytes()).hexdigest() == saved['credential_sha']
    h={'Authorization':'Bearer '+json.loads(p.read_text())['engineer']}
    r=client.get('/api/projects/demo-chamber/analyses/'+saved['id'],headers=h)
    assert r.status_code == 200
    assert r.json()['analysis_id'] == saved['id']
    assert r.json()['checks'] == saved['result']['checks']
    c=connect(); assert c.execute('SELECT count(*) FROM analyses').fetchone()[0] == 1; c.close()
''')


def test_08_podman_clean_volume_lifecycle_and_persistence():
    """OPT-IN real Podman. Missing engine/image is SKIP, never PASS.

    P0_REVIEW_IMAGE must be an already-built, non-production image ID. No pull/build,
    host port, host bind mount or network. All resources have fresh UUID names.
    """
    engine = shutil.which('podman')
    image = os.getenv('P0_REVIEW_IMAGE', '')
    if not engine:
        pytest.skip('Podman unavailable in this executor; no container/volume/platform claim')
    if not re.fullmatch(r'sha256:[0-9a-f]{64}', image):
        pytest.skip('Needs explicitly supplied immutable isolated P0_REVIEW_IMAGE (sha256 ID)')
    suffix = uuid.uuid4().hex
    name = 'codex-p0-'+suffix
    volume = name+'-data'
    assert name != 'riskscope' and volume != 'riskscope_runtime'
    def podman(*args):
        return subprocess.run([engine,*args],capture_output=True,text=True,timeout=60)
    assert podman('volume','create','--label','review.owner=codex-p0',volume).returncode == 0
    script = """
import hashlib,json
from pathlib import Path
from app.db import init_db
c=init_db(); p=Path('/app/runtime'); cred=p/'demo_credentials.json'; marker=p/'review-marker.json'
digest=hashlib.sha256(cred.read_bytes()).hexdigest()
if marker.exists():
    assert json.loads(marker.read_text())['credential_sha']==digest
    assert c.execute('SELECT count(*) FROM users').fetchone()[0]==3
    print('REVIEW_RESTART_PERSISTED')
else:
    marker.write_text(json.dumps({'credential_sha':digest})); print('REVIEW_INITIALIZED')
c.close()
"""
    try:
        first = podman('run','--pull=never','--name',name,'--label','review.owner=codex-p0',
                       '--network=none','-v',volume+':/app/runtime',image,'python','-c',script)
        assert first.returncode == 0, first.stderr
        assert 'REVIEW_INITIALIZED' in first.stdout
        second = podman('start','-a',name)
        assert second.returncode == 0, second.stderr
        assert 'REVIEW_RESTART_PERSISTED' in second.stdout
    finally:
        # Only resources whose unique names were generated by this test are eligible.
        assert re.fullmatch(r'codex-p0-[0-9a-f]{32}',name)
        removed=podman('rm','-f',name)
        deleted=podman('volume','rm',volume)
        assert deleted.returncode == 0, deleted.stderr
