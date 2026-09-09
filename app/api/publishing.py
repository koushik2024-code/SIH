from fastapi import APIRouter, Depends
from app.security import current_user
from app.db import db
from app.utils import audit
from app.publishing import Channel, ConnectionRequest, PublishPreview, PublishSubmit, store_connection, preview, submit

router = APIRouter()

@router.get('/connections')
def list_connections(user=Depends(current_user)):
    with db() as con:
        return [dict(r) for r in con.execute('SELECT channel,label,updated_at FROM connections WHERE user_id=?', (user['id'],)).fetchall()]

@router.put('/connections/{channel}')
def save_connection(channel: Channel, req: ConnectionRequest, user=Depends(current_user)):
    return store_connection(user['id'], channel, req)

@router.delete('/connections/{channel}')
def disconnect(channel: Channel, user=Depends(current_user)):
    with db() as con:
        con.execute('DELETE FROM connections WHERE user_id=? AND channel=?', (user['id'], channel))
    audit(user['id'], 'connection.delete', 'connection', channel)
    return {'disconnected': channel}

@router.post('/{asset_id}/preview')
def publication_preview(asset_id: int, req: PublishPreview, user=Depends(current_user)):
    return preview(asset_id, user['id'], req.recipients)

@router.post('/{asset_id}/submit')
def publication_submit(asset_id: int, req: PublishSubmit, user=Depends(current_user)):
    return submit(asset_id, user['id'], req)

@router.get('/history')
def publication_history(user=Depends(current_user)):
    import json
    with db() as con:
        rows = con.execute('SELECT id,asset_id,channel,status,result_json,created_at FROM publications WHERE user_id=? ORDER BY id DESC LIMIT 200', (user['id'],)).fetchall()
    return [{k: v for k, v in dict(r).items() if k != 'result_json'} | {'result': json.loads(r['result_json'])} for r in rows]
