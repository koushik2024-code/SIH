import json
from uuid import uuid4
from fastapi import APIRouter, Depends, HTTPException
from app.db import db
from app.security import current_user
from app.schemas import TransformRequest
from app.repository import owned_sources
from app.api.route import analyze
from app.rag import retrieve, build_query
from app.llm import generate, ModelUnavailable, OutputInvalid
from app.render import save_markdown, make_video, render_text, RenderFailure
from app.config import ASSETS
from app.utils import audit
from app.api.assets import present_asset

from app.limits import processing_slot

router = APIRouter()

@router.post('', dependencies=[Depends(processing_slot)])
def transform(req: TransformRequest, user=Depends(current_user)):
    from app.languages import language_code
    try:
        language_code(req.language)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None
    sources = owned_sources(user['id'], req.source_ids)
    decision, direct_evidence = analyze(req, user['id'])
    controls = req.model_dump(exclude={'source_ids', 'output_types'})
    if decision.route == 'DIRECT':
        controls['retrieval_query'] = None
    audit(user['id'], 'transform.route', details=decision.as_dict())
    outputs, errors = [], []
    directory = ASSETS / str(user['id'])
    directory.mkdir(parents=True, exist_ok=True)
    for output_type in req.output_types:
        query, path = None, None
        try:
            if decision.route == 'RAG':
                query = build_query(output_type, controls, sources)
                try:
                    evidence = retrieve(user['id'], query, req.source_ids)
                except HTTPException:
                    raise
                except Exception:
                    raise HTTPException(502, 'Local semantic retrieval failed. Check installed embedding model and Qdrant configuration.') from None
                if not evidence:
                    raise HTTPException(422, 'No evidence fits the retrieval context budget')
            else:
                evidence = direct_evidence
            result, verification = generate(output_type, controls, evidence)
            path = directory / (uuid4().hex + ('.mp4' if output_type == 'video' else '.md'))
            media = make_video(result, path, controls) if output_type == 'video' else None
            if output_type != 'video':
                save_markdown(result, output_type, path)
            metadata = {**decision.as_dict(), 'verification': verification, 'result': result,
                        'evidence_ids': [e['evidence_id'] for e in evidence], 'retrieval_query_used': query,
                        'source_names': [s['name'] for s in sources], 'controls': controls, 'media': media,
                        'rendered_text': render_text(result, output_type)}
            with db() as con:
                con.execute('BEGIN IMMEDIATE')
                for sid in req.source_ids:
                    if not con.execute('SELECT id FROM sources WHERE id=? AND user_id=?', (sid, user['id'])).fetchone():
                        path.unlink(missing_ok=True)
                        path.with_suffix('.timeline.json').unlink(missing_ok=True)
                        raise HTTPException(409, 'A selected source was deleted during generation; output was not saved.')
                cur = con.execute('INSERT INTO assets(user_id,source_ids,output_type,path,metadata_json) VALUES(?,?,?,?,?)',
                                  (user['id'], json.dumps(req.source_ids), output_type, str(path), json.dumps(metadata, ensure_ascii=False)))
                asset_id = cur.lastrowid
            audit(user['id'], 'asset.create', 'asset', asset_id, {'output_type': output_type, 'route': decision.route})
            outputs.append(present_asset(asset_id, user['id']))
        except OutputInvalid as exc:
            detail = {'message': str(exc), 'verification': exc.verification}
            if exc.preview:
                detail['sanitized_model_output'] = exc.preview
            errors.append({'output_type': output_type, 'status': 422, 'detail': detail})
        except ModelUnavailable as exc:
            errors.append({'output_type': output_type, 'status': 502, 'detail': str(exc)})
        except RenderFailure as exc:
            errors.append({'output_type': output_type, 'status': 422, 'detail': str(exc)})
        except HTTPException as exc:
            errors.append({'output_type': output_type, 'status': exc.status_code, 'detail': exc.detail})
    if errors:
        audit(user['id'], 'transform.failure', details={'output_types': [e['output_type'] for e in errors]})
    if not outputs:
        raise HTTPException(errors[0]['status'], {'message': 'No requested outputs succeeded', 'errors': errors})
    return {'source_ids': req.source_ids, **decision.as_dict(), 'outputs': outputs, 'errors': errors}
