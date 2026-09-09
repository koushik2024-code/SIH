import html
import json
from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse
from app.security import decode_citation_token
from app.db import db
from app.utils import audit

router = APIRouter()

@router.get('/{evidence_id}', response_class=HTMLResponse)
def open_citation(evidence_id: str, token: str):
    payload = decode_citation_token(token)
    if payload.get('evidence_id') != evidence_id:
        raise HTTPException(403, 'Citation mismatch')
    with db() as con:
        row = con.execute('SELECT e.*,s.name FROM evidence e JOIN sources s ON s.id=e.source_id AND s.user_id=e.user_id WHERE e.evidence_id=? AND e.user_id=?',
                          (evidence_id, int(payload['sub']))).fetchone()
    if not row:
        raise HTTPException(404, 'Evidence not found')
    metadata = json.loads(row['metadata_json'])
    details = {k: v for k, v in metadata.items() if v is not None}
    audit(int(payload['sub']), 'citation.open', 'evidence', evidence_id)
    body = f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Source evidence</title><link rel="stylesheet" href="/style.css"></head>
<body><main class="citation"><p class="eyebrow">SOURCE EVIDENCE</p><h1>{html.escape(evidence_id)}</h1>
<h2>{html.escape(row['name'])}</h2><p>{html.escape(json.dumps(details, ensure_ascii=False))}</p>
<pre>{html.escape(row['content'])}</pre><p>Provenance identifies the source passage; it does not certify the source as true.</p></main></body></html>'''
    return HTMLResponse(body)
