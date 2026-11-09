import json
import pytest
from fastapi.testclient import TestClient
from app import db
from app.api import app

@pytest.fixture
def env(tmp_path,monkeypatch):
    monkeypatch.setattr(db,'DB_PATH',tmp_path/'db.sqlite3')
    monkeypatch.setattr(db,'CREDENTIALS_PATH',tmp_path/'tokens.json')
    with TestClient(app) as client:
        tokens=json.loads((tmp_path/'tokens.json').read_text())
        def h(name): return {'Authorization':'Bearer '+tokens[name]}
        yield client,h

@pytest.fixture
def manager(env):return env[1]('manager')

@pytest.fixture
def engineer(env):return env[1]('engineer')

@pytest.fixture
def outsider(env):return env[1]('outsider')

@pytest.fixture
def c(env):return env[0]

ROOT='/api/projects/demo-chamber'
