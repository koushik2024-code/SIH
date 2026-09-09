from pathlib import Path
from uuid import uuid4
import hashlib
import json
from bs4 import BeautifulSoup
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool
from app.security import current_user
from app.config import settings, UPLOADS
from app.utils import sha256_bytes, audit, fetch_public_url
from app.ingest import parse_file, SUPPORTED_EXTS, ParseFailure
from app.chunking import chunk_sections
from app.db import db
from app.repository import owned_sources

router = APIRouter()

def _store(user, name, media_type, content, content_hash, metadata, sections=None):
    if not content.strip():
        raise HTTPException(422, 'No extractable text found')
    if len(content) > settings.max_source_chars:
        raise HTTPException(413, 'Source text exceeds MAX_SOURCE_CHARS')
    name = name[:255]
    with db() as con:
        cur = con.execute('INSERT INTO sources(user_id,name,media_type,content,content_hash,metadata_json) VALUES(?,?,?,?,?,?)',
                          (user['id'], name, media_type, content, content_hash, json.dumps(metadata, ensure_ascii=False)))
        sid = cur.lastrowid
        evidence = chunk_sections(sections or [{'text': content}], sid, user['id'], name)
        for e in evidence:
            meta = {k: v for k, v in e.items() if k not in {'content', 'evidence_id', 'source_id', 'user_id', 'chunk_index'}}
            con.execute('INSERT INTO evidence(user_id,source_id,evidence_id,chunk_index,content,metadata_json) VALUES(?,?,?,?,?,?)',
                        (user['id'], sid, e['evidence_id'], e['chunk_index'], e['content'], json.dumps(meta, ensure_ascii=False)))
    audit(user['id'], 'source.create', 'source', sid, {'parser': metadata.get('parser'), 'chunks': len(evidence)})
    return {'source_id': sid, 'name': name, 'media_type': media_type, 'content_hash': content_hash,
            'metadata': metadata, 'evidence_count': len(evidence), 'status': 'ready', 'vector_status': 'indexed_on_first_rag'}

@router.post('/upload')
async def upload(file: UploadFile = File(...), user=Depends(current_user)):
    suffix = Path(file.filename or '').suffix.lower()
    if suffix not in SUPPORTED_EXTS:
        raise HTTPException(400, 'Unsupported file extension')
    directory = UPLOADS / str(user['id'])
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f'{uuid4().hex}{suffix}'
    count, digest = 0, hashlib.sha256()
    try:
        with path.open('wb') as target:
            while block := await file.read(1024 * 1024):
                count += len(block)
                if count > settings.max_upload_mb * 1024 * 1024:
                    raise HTTPException(413, 'Upload too large')
                digest.update(block)
                target.write(block)
        content, metadata, sections = await run_in_threadpool(parse_file, path)
        return await run_in_threadpool(_store, user, file.filename or path.name, file.content_type or 'application/octet-stream',
                                      content, digest.hexdigest(), metadata, sections)
    except HTTPException:
        raise
    except ParseFailure as exc:
        raise HTTPException(422, str(exc)) from None
    except Exception:
        raise HTTPException(422, 'Parsing failed. Check file validity and the required local parser/model installation.') from None
    finally:
        # Canonical text + hashes are retained; raw uploads are removed by default.
        path.unlink(missing_ok=True)
        await file.close()

class TextSource(BaseModel):
    text: str = Field(min_length=1, max_length=5000000)
    name: str = Field('Pasted text', min_length=1, max_length=255)

@router.post('/text')
def text_source(req: TextSource, user=Depends(current_user)):
    return _store(user, req.name, 'text/plain', req.text, sha256_bytes(req.text.encode()), {'parser': 'direct_text'})

class UrlSource(BaseModel):
    url: str = Field(min_length=1, max_length=2048)

@router.post('/url')
def url_source(req: UrlSource, user=Depends(current_user)):
    try:
        data, content_type = fetch_public_url(req.url)
    except OverflowError:
        raise HTTPException(413, 'URL content too large') from None
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from None
    except Exception:
        raise HTTPException(422, 'Cannot fetch public webpage') from None
    soup = BeautifulSoup(data, 'html.parser')
    for tag in soup(['script', 'style', 'noscript']):
        tag.decompose()
    content = '\n\n'.join(soup.stripped_strings)
    result = _store(user, soup.title.get_text() if soup.title else 'Webpage', content_type, content, sha256_bytes(data), {'parser': 'url_html', 'url': req.url})
    audit(user['id'], 'source.url', 'source', result['source_id'])
    return result

@router.get('')
def list_sources(user=Depends(current_user)):
    with db() as con:
        rows = con.execute('SELECT id,name,media_type,content_hash,metadata_json,created_at FROM sources WHERE user_id=? ORDER BY id DESC', (user['id'],)).fetchall()
    result = []
    for row in rows:
        item = dict(row)
        item['metadata'] = json.loads(item.pop('metadata_json'))
        result.append(item)
    return result

@router.get('/{source_id}')
def source_detail(source_id: int, user=Depends(current_user)):
    item = owned_sources(user['id'], [source_id])[0]
    item['metadata'] = json.loads(item.pop('metadata_json'))
    item.pop('user_id')
    return item

from app.limits import processing_slot

@router.delete('/{source_id}', dependencies=[Depends(processing_slot)])
def remove_source(source_id: int, user=Depends(current_user)):
    from app.vector_store import delete_source_vectors
    owned_sources(user['id'], [source_id])
    with db() as con:
        con.execute('BEGIN IMMEDIATE')
        assets = con.execute('SELECT source_ids FROM assets WHERE user_id=?', (user['id'],)).fetchall()
        if any(source_id in json.loads(r['source_ids']) for r in assets):
            raise HTTPException(409, 'Delete outputs using this source first so their citations remain valid.')
        try:
            delete_source_vectors(user['id'], source_id)
        except Exception:
            raise HTTPException(503, 'Could not remove source vectors. Check Qdrant and retry; source retained.') from None
        con.execute('DELETE FROM evidence WHERE user_id=? AND source_id=?', (user['id'], source_id))
        con.execute('DELETE FROM sources WHERE user_id=? AND id=?', (user['id'], source_id))
    audit(user['id'], 'source.delete', 'source', source_id)
    return {'deleted_id': source_id}
