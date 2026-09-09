from fastapi import APIRouter, Depends
from app.security import current_user
from app.schemas import RouteRequest
from app.repository import owned_sources, source_evidence, evidence_context
from app.router import choose_route

router = APIRouter()

def analyze(req, user_id):
    owned_sources(user_id, req.source_ids)
    evidence = source_evidence(user_id, req.source_ids)
    decision = choose_route(evidence_context(evidence), len(req.source_ids), req.persistent_knowledge, req.retrieval_requested)
    return decision, evidence

@router.post('')
def preview(req: RouteRequest, user=Depends(current_user)):
    decision, _ = analyze(req, user['id'])
    return decision.as_dict()
