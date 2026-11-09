"""Deployment fault injection; all Podman/curl/sleep commands are synthetic.

Tests the frozen first deployment kit. Never invokes a real container engine,
network endpoint, production token or production volume.
"""
import contextlib
import io
import json
import os
from pathlib import Path
import runpy
import subprocess
import sys

import pytest

HERE = Path(__file__).resolve().parent
SNAPSHOT = Path(os.getenv("P0_REVIEW_DEPLOY_SOURCE", str(HERE / "snapshot"))).resolve()


def invoke(tmp_path, action, **settings):
    binpath = tmp_path / "bin"
    binpath.mkdir()
    recorder = binpath / "podman"
    recorder.write_text("#!" + sys.executable + "\n" + r'''
import os,sys,json
with open(os.environ['REVIEW_COMMAND_LOG'],'a') as f:
    f.write(json.dumps(sys.argv[1:])+'\n')
if sys.argv[1:2]==['restart'] and os.getenv('REVIEW_FAIL_RESTART')=='1':
    sys.exit(42)
if sys.argv[1:2]==['exec']:
    print('SYNTHETIC_REVIEW_CREDENTIAL')
''')
    recorder.chmod(0o700)
    for name, body in [('curl', 'echo health-fixture'), ('sleep', ':'), ('cmp', 'exit 0')]:
        p = binpath / name
        p.write_text('#!/bin/sh\n'+body+'\n')
        p.chmod(0o700)
    # Redirect ONLY the fixed temporary file into this test's private directory.
    # Otherwise testing the vulnerable original could overwrite another process's file.
    script = tmp_path / 'driver.sh'
    script.write_text((SNAPSHOT/'deploy/riskscope.sh').read_text().replace(
        '/tmp/rs_tok_before', str(tmp_path/'captured-credential')))
    env = {k:v for k,v in os.environ.items() if not k.startswith(('RS_', 'OLLAMA_', 'REVIEW_'))}
    env.update(PATH=str(binpath)+os.pathsep+os.environ['PATH'],
               REVIEW_COMMAND_LOG=str(tmp_path/'commands.jsonl'))
    env.update(settings)
    p = subprocess.run(['/bin/bash', '-c', 'umask 022; exec /bin/bash "$1" "$2"',
                        'review',str(script),action], env=env,capture_output=True,text=True,timeout=8)
    log = tmp_path/'commands.jsonl'
    commands = [json.loads(x) for x in log.read_text().splitlines()] if log.exists() else []
    return p, commands


def test_host_network_must_not_escape_reserved_port_guard(tmp_path):
    p, commands = invoke(tmp_path, 'up', RS_HOST_NETWORK='1', RS_PORT='8100')
    # This kit's image CMD still binds 0.0.0.0:8000. Current host mode must refuse
    # until an explicitly safe app bind address/port is implemented and validated.
    unsafe = [c for c in commands if c and c[0]=='run' and '--network=host' in c]
    assert not unsafe, 'Guard accepted RS_PORT=8100 but emitted host network with default app :8000'
    assert p.returncode != 0


def test_build_must_not_overwrite_protected_production_image_tag(tmp_path):
    p, commands = invoke(tmp_path, 'build', RS_IMAGE='localhost/riskscope-poc:0.4')
    assert not any(c and c[0]=='build' for c in commands), 'Reserved production image tag reached podman build'
    assert p.returncode != 0


def test_failed_restart_must_not_leave_plaintext_credentials(tmp_path):
    p, commands = invoke(tmp_path, 'restart-test', REVIEW_FAIL_RESTART='1')
    assert p.returncode != 0
    artifact = tmp_path/'captured-credential'
    exposed = artifact.exists() and 'SYNTHETIC_REVIEW_CREDENTIAL' in artifact.read_text()
    mode = oct(artifact.stat().st_mode & 0o777) if artifact.exists() else 'absent'
    assert not exposed, 'Restart failure leaves plaintext credential file; permissions='+mode


def test_purge_must_not_remove_an_unowned_arbitrary_workload(tmp_path):
    p, commands = invoke(tmp_path, 'purge', RS_NAME='unrelated-workload', RS_VOLUME='unrelated-data')
    destructive = [c for c in commands if c and (c[0]=='rm' or c[:2]==['volume','rm'])]
    assert not destructive, 'Purge blindly trusts RS_NAME/RS_VOLUME without ownership verification'
    assert p.returncode != 0


def test_smoke_fallback_must_not_report_overall_real_agent_pass(tmp_path, monkeypatch):
    """Mock only: demonstrates the smoke tool's false-green classification."""
    import urllib.request
    credentials = tmp_path/'synthetic.json'
    credentials.write_text(json.dumps({'engineer':'synthetic-engineer','outsider':'synthetic-outsider'}))
    monkeypatch.setenv('AGENT_CREDENTIALS_PATH',str(credentials))
    monkeypatch.setenv('SMOKE_ALLOW_FALLBACK','1')
    class Response:
        def __init__(self, status, body): self.status=status; self.body=body
        def __enter__(self): return self
        def __exit__(self,*args): pass
        def read(self): return json.dumps(self.body).encode()
    def fake_urlopen(req,**kwargs):
        auth=req.headers.get('Authorization','')
        if req.full_url.endswith('/health'): return Response(200,{'status':'ok'})
        if not auth: return Response(401,{})
        if 'outsider' in auth: return Response(403,{})
        if req.full_url.endswith('/api/me'):
            return Response(200,{'user':{'id':'engineer'},'projects':[{'id':'demo-chamber'}]})
        assert req.full_url.endswith('/chat')
        return Response(200,{'checks':[{'rule':'continuous_power','numbers':{'total_current_a':'14'}}],
             'reply_source':'deterministic','llm_diagnostic':{'reply':{'status':'not_configured'}}})
    monkeypatch.setattr(urllib.request,'urlopen',fake_urlopen)
    output=io.StringIO()
    with contextlib.redirect_stdout(output), pytest.raises(SystemExit):
        runpy.run_path(str(SNAPSHOT/'scripts/portable_smoke.py'),run_name='__main__')
    assert 'RESULT: PASS' not in output.getvalue(), 'No real LLM succeeded, but smoke final result is PASS'
