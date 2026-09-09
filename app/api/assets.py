from pathlib import Path
import json
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse, Response
from app.security import current_user, make_citation_token
from app.db import db
from app.config import ASSETS
from app.utils import audit
from app.verify import collect_citations
from app.render import render_text

router = APIRouter()

def owned_asset(asset_id, user_id):
    with db() as con:
        row = con.execute('SELECT * FROM assets WHERE id=? AND user_id=?', (asset_id, user_id)).fetchone()
    if not row:
        raise HTTPException(404, 'Asset not found')
    return dict(row)

def citation_links(result, user_id):
    return {c: f'/api/citations/{c}?token={make_citation_token(user_id, c)}' for c in collect_citations(result)}

def present_asset(asset_id, user_id):
    row = owned_asset(asset_id, user_id)
    meta = json.loads(row['metadata_json'])
    result = meta.get('result', {})
    return {'asset_id': row['id'], 'output_type': row['output_type'], 'source_ids': json.loads(row['source_ids']),
            'created_at': row['created_at'], **meta, 'citation_links': citation_links(result, user_id),
            'download_url': f'/api/assets/{asset_id}/download'}

@router.get('')
def history(user=Depends(current_user)):
    with db() as con:
        rows = con.execute('SELECT id,source_ids,output_type,created_at,metadata_json FROM assets WHERE user_id=? ORDER BY id DESC', (user['id'],)).fetchall()
    output = []
    for row in rows:
        meta = json.loads(row['metadata_json'])
        output.append({'id': row['id'], 'source_ids': json.loads(row['source_ids']), 'output_type': row['output_type'],
                       'created_at': row['created_at'], 'source_names': meta.get('source_names', []),
                       'title': meta.get('result', {}).get('title') or meta.get('result', {}).get('subject') or meta.get('result', {}).get('hook') or row['output_type'],
                       'language': meta.get('controls', {}).get('language', 'English'), 'version': meta.get('version', 1),
                       'parent_asset_id': meta.get('parent_asset_id'), 'edit_mode': meta.get('edit_mode', 'generated'),
                       'route': meta.get('route'), 'route_reason': meta.get('route_reason'), 'verification': meta.get('verification')})
    return output

@router.get('/{asset_id}')
def detail(asset_id: int, user=Depends(current_user)):
    return present_asset(asset_id, user['id'])

@router.get('/{asset_id}/download')
def download(asset_id: int, request: Request, user=Depends(current_user)):
    row = owned_asset(asset_id, user['id'])
    path = Path(row['path']).resolve()
    if not path.is_relative_to(ASSETS.resolve()) or not path.is_file():
        raise HTTPException(404, 'Asset file not found')
    audit(user['id'], 'asset.download', 'asset', asset_id)
    if row['output_type'] == 'video':
        return FileResponse(path, filename=f'asset_{asset_id}.mp4', media_type='video/mp4')
    result = json.loads(row['metadata_json']).get('result', {})
    text = render_text(result, row['output_type'])
    links = citation_links(result, user['id'])
    if links:
        origin = str(request.base_url).rstrip('/')
        text += '\n\nSources (signed links expire in 10 minutes; reopen History to refresh)\n'
        text += '\n'.join(f'- [{c}]({origin}{url})' for c, url in links.items())
    return Response(text + '\n', media_type='text/markdown', headers={'Content-Disposition': f'attachment; filename="asset_{asset_id}.md"'})

from app.schemas import ManualEditRequest, RevisionRequest, DeleteSelection
from app.limits import processing_slot

@router.post('/{asset_id}/edit', dependencies=[Depends(processing_slot)])
def manual_edit(asset_id: int, req: ManualEditRequest, user=Depends(current_user)):
    from app.revisions import context, save_version
    from app.render import RenderFailure
    row, meta, evidence = context(asset_id, user['id'])
    try:
        return save_version(row, meta, evidence, req.result, user['id'], 'manual')
    except RenderFailure as exc:
        raise HTTPException(422, str(exc)) from None

@router.post('/{asset_id}/revise', dependencies=[Depends(processing_slot)])
def ai_revision(asset_id: int, req: RevisionRequest, user=Depends(current_user)):
    from app.revisions import revise
    from app.llm import ModelUnavailable
    from app.render import RenderFailure
    try:
        return revise(asset_id, user['id'], req.instruction, req.language)
    except ModelUnavailable:
        raise HTTPException(502, 'Revision model unavailable. Download the model shown under Connections / Local model setup with ollama pull, then retry.') from None
    except RenderFailure as exc:
        raise HTTPException(422, str(exc)) from None


def delete_assets(ids, user_id):
    ids = list(dict.fromkeys(ids))
    marks = ','.join('?' for _ in ids)
    with db() as con:
        con.execute('BEGIN IMMEDIATE')
        rows = con.execute(f'SELECT id,path FROM assets WHERE user_id=? AND id IN ({marks})', (user_id, *ids)).fetchall()
        if len(rows) != len(ids):
            raise HTTPException(404, 'One or more outputs not found')
        if con.execute(f"SELECT id FROM publications WHERE user_id=? AND asset_id IN ({marks}) AND status='sending'", (user_id, *ids)).fetchone():
            raise HTTPException(409, 'An output is being submitted. Wait for publishing to finish.')
        con.execute(f'DELETE FROM assets WHERE user_id=? AND id IN ({marks})', (user_id, *ids))
    cleanup_warning = False
    for row in rows:
        path = Path(row['path']).resolve()
        if path.is_relative_to(ASSETS.resolve()):
            for target in (path, path.with_suffix('.timeline.json'), path.with_suffix('.frames.zip')):
                try:
                    target.unlink(missing_ok=True)
                except OSError:
                    cleanup_warning = True
    audit(user_id, 'asset.delete', details={'ids': ids, 'file_cleanup_pending': cleanup_warning})
    return {'deleted_ids': ids, 'file_cleanup_pending': cleanup_warning,
            'message': 'Removed from this workspace. Previously published posts or sent emails are unaffected.'}

@router.post('/delete-selection')
def delete_selection(req: DeleteSelection, user=Depends(current_user)):
    return delete_assets(req.ids, user['id'])

@router.delete('/{asset_id}')
def remove_asset(asset_id: int, user=Depends(current_user)):
    return delete_assets([asset_id], user['id'])

@router.get('/{asset_id}/frames')
def download_frames(asset_id: int, user=Depends(current_user)):
    row = owned_asset(asset_id, user['id'])
    path = Path(row['path']).resolve().with_suffix('.frames.zip')
    if row['output_type'] != 'video' or not path.is_relative_to(ASSETS.resolve()) or not path.is_file():
        raise HTTPException(404, 'Frames unavailable. Regenerate this video with the update.')
    return FileResponse(path, filename=f'asset_{asset_id}_frames.zip', media_type='application/zip')
