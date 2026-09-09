import os
import tempfile
from pathlib import Path

_work = tempfile.TemporaryDirectory(prefix='ntro_tests_')
os.environ['DATA_DIR'] = str(Path(_work.name) / 'data')
os.environ['QDRANT_PATH'] = str(Path(_work.name) / 'qdrant')
os.environ['SECRET_KEY'] = 'test-only-secret-' * 4
os.environ['MODELS_LOCAL_ONLY'] = 'true'

import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.db import init_db, db
from app.security import hash_password, make_token

@pytest.fixture
def client():
    init_db()
    with db() as con:
        for table in ['publications', 'connections', 'assets', 'evidence', 'sources', 'audit_events', 'users']:
            con.execute(f'DELETE FROM {table}')
        for name in ['alice', 'bob']:
            con.execute('INSERT INTO users(username,password_hash) VALUES(?,?)', (name, hash_password('test-pass')))
        rows = con.execute('SELECT id,username FROM users').fetchall()
    with TestClient(app) as api:
        api.users = {r['username']: r['id'] for r in rows}
        api.headers_for = lambda name: {'Authorization': 'Bearer ' + make_token(api.users[name], name)}
        yield api

@pytest.fixture
def source(client):
    response = client.post('/api/sources/text', headers=client.headers_for('alice'), json={'text': 'The research team reports a new Transformer architecture. The system uses attention to process sequences. Evaluation found improved translation quality.', 'name': 'Research note'})
    assert response.status_code == 200
    return response.json()['source_id']
