import json
from fastapi import HTTPException
from app.db import db

def owned_sources(user_id, source_ids):
    ids = list(dict.fromkeys(source_ids))
    if not ids:
        raise HTTPException(400, 'Select at least one source')
    with db() as con:
        marks = ','.join('?' for _ in ids)
        rows = con.execute(f'SELECT * FROM sources WHERE user_id=? AND id IN ({marks})', (user_id, *ids)).fetchall()
    if len(rows) != len(ids):
        raise HTTPException(404, 'One or more sources not found')
    by_id = {r['id']: dict(r) for r in rows}
    return [by_id[i] for i in ids]

def source_evidence(user_id, source_ids):
    owned_sources(user_id, source_ids)
    with db() as con:
        marks = ','.join('?' for _ in source_ids)
        rows = con.execute(f'SELECT e.*,s.name AS source_name FROM evidence e JOIN sources s ON s.id=e.source_id AND s.user_id=e.user_id WHERE e.user_id=? AND e.source_id IN ({marks}) ORDER BY e.source_id,e.chunk_index', (user_id, *source_ids)).fetchall()
    return [{**json.loads(r['metadata_json']), 'evidence_id': r['evidence_id'], 'source_id': r['source_id'],
             'user_id': r['user_id'], 'source_name': r['source_name'], 'chunk_index': r['chunk_index'], 'content': r['content']} for r in rows]

def evidence_context(evidence):
    return '\n\n'.join(json.dumps(e, ensure_ascii=False) for e in evidence)
