"""Narrow independent regressions for session ACL and credentials isolation only."""
import hashlib
import json
from pathlib import Path

import httpx
import pytest
from app import db,config
from tests.conftest import env,c,manager,engineer,outsider,ROOT
from tests.test_acl_regression import _add_distractor_documents


@pytest.mark.parametrize('reply_kind',['deterministic','llm'])
@pytest.mark.parametrize('source,focus',[('DOC-PS','motor_upgrade'),('DOC-MOTOR','motor_upgrade'),('DOC-AUX','motor_upgrade'),('DOC-PLAN','supplier')])
def test_history_masks_every_evidence_source_and_recovers_access(c,manager,engineer,outsider,monkeypatch,reply_kind,source,focus):
    # Reuse the existing top-eight boundary fixture: source must be found through
    # engineering or dependency evidence, not merely retrieved documents.
    _add_distractor_documents(8,'search_keyword')
    sentinel='受保護的模型摘要：合成來源推得 11A／264W。'
    if reply_kind=='llm':
        monkeypatch.setattr(config,'OLLAMA_URL','http://127.0.0.1:11434')
        answers=iter(['{}',sentinel])
        def post(url,**kwargs):
            return httpx.Response(200,json={'response':next(answers)},request=httpx.Request('POST',url))
        monkeypatch.setattr(httpx,'post',post)
    else:
        def forbidden(*args,**kwargs):raise AssertionError('No model call expected')
        monkeypatch.setattr(httpx,'post',forbidden)
    response=c.post(ROOT+'/chat',headers=engineer,json={'message':'search_keyword','session_id':'acl-extra','focus':focus,'use_local_llm':reply_kind=='llm'})
    assert response.status_code==200
    created=response.json()
    assert source not in {d['id'] for d in created['documents']}
    assert created['reply_source']==('llm_phrased' if reply_kind=='llm' else 'deterministic_template')
    original=created['reply']
    assert original
    before=c.get(ROOT+'/sessions/acl-extra',headers=engineer).json()
    assert before['turns'][0]['reply']==original and not before['turns'][0]['redacted']
    assert c.patch(ROOT+'/documents/'+source+'/access',headers=manager,json={'user_id':'engineer','enabled':False}).status_code==200
    assert c.get(ROOT+'/analyses/'+created['analysis_id'],headers=engineer).status_code==403
    history=c.get(ROOT+'/sessions/acl-extra',headers=engineer)
    assert history.status_code==200
    record=history.json()['turns'][0]
    assert record['redacted'] is True
    assert record['reply'] is None and record['reply_source'] is None
    assert original not in history.text
    assert sentinel not in history.text
    assert '264' not in history.text  # No secondary summary field discloses power.
    visible=c.get(ROOT+'/sessions/acl-extra',headers=manager).json()['turns'][0]
    assert visible['reply']==original and not visible['redacted']
    assert c.get(ROOT+'/sessions/acl-extra',headers=outsider).status_code==403
    assert c.patch(ROOT+'/documents/'+source+'/access',headers=manager,json={'user_id':'engineer','enabled':True}).status_code==200
    restored=c.get(ROOT+'/sessions/acl-extra',headers=engineer).json()['turns'][0]
    assert restored['reply']==original and not restored['redacted']


def configure_defaults(tmp_path,monkeypatch):
    default_db=tmp_path/'default.sqlite3'
    default_creds=tmp_path/'demo_credentials.json'
    monkeypatch.setattr(db,'DB_PATH',default_db)
    monkeypatch.setattr(db,'CREDENTIALS_PATH',default_creds)
    return default_db,default_creds


def account_hashes(conn):
    return dict(conn.execute('SELECT id,token_hash FROM users'))


def test_second_database_in_same_directory_cannot_replace_default_credentials(tmp_path,monkeypatch):
    default_db,default_creds=configure_defaults(tmp_path,monkeypatch)
    conn=db.init_db();before_hashes=account_hashes(conn);conn.close()
    before=default_creds.read_bytes()
    # Same directory is a valid separate database, and is the original Codex
    # probe's topology. The prior fix only tested an alternative subdirectory.
    conn=db.init_db(tmp_path/'other.sqlite3');conn.close()
    conn=db.connect(default_db);after_hashes=account_hashes(conn);conn.close()
    assert after_hashes==before_hashes
    unchanged = default_creds.read_bytes() == before
    tokens = json.loads(default_creds.read_text())
    matches_default = all(hashlib.sha256(v.encode()).hexdigest() == before_hashes[k] for k,v in tokens.items())
    Path(__file__).with_name('credential-collision.json').write_text(json.dumps({
        'topology':'temporary/default.sqlite3 and temporary/other.sqlite3; default credential basename demo_credentials.json',
        'default_database_user_hashes_unchanged':after_hashes==before_hashes,
        'default_credentials_unchanged':unchanged,
        'credential_file_matches_default_accounts':matches_default,
        'only_temporary_data':True},indent=2)+'\n')
    assert unchanged, 'Separate DB in same directory overwrites default credentials'


def test_explicit_paths_and_existing_init_preserve_accounts_and_credentials(tmp_path,monkeypatch):
    default_db,default_creds=configure_defaults(tmp_path,monkeypatch)
    conn=db.init_db();before_hashes=account_hashes(conn);conn.close()
    before=default_creds.read_bytes()
    separate=tmp_path/'other.sqlite3';target=tmp_path/'other-credentials.json'
    conn=db.init_db(separate,target);other_hashes=account_hashes(conn);conn.close()
    tokens=json.loads(target.read_text())
    assert {k:hashlib.sha256(v.encode()).hexdigest() for k,v in tokens.items()}==other_hashes
    assert default_creds.read_bytes()==before
    conn=db.init_db();assert account_hashes(conn)==before_hashes;conn.close()
    assert default_creds.read_bytes()==before
    other_before=target.read_bytes()
    conn=db.init_db(separate,target);assert account_hashes(conn)==other_hashes;conn.close()
    assert target.read_bytes()==other_before
