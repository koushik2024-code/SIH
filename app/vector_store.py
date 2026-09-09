"""SQLite owns evidence; Qdrant is a rebuildable, tenant-filtered semantic index."""
import hashlib
from threading import RLock
from uuid import uuid5, NAMESPACE_URL
from qdrant_client import QdrantClient, models
from app.config import settings, resolve_path
from app.embeddings import embed_documents, embed_query
from app.repository import source_evidence, owned_sources

_lock = RLock()
_client = None

def collection_name():
    fingerprint = hashlib.sha256(settings.embedding_model.encode()).hexdigest()[:10]
    return f'{settings.qdrant_collection}_{fingerprint}'

def client():
    global _client
    with _lock:
        if _client is None:
            _client = (QdrantClient(path=str(resolve_path(settings.qdrant_path))) if settings.qdrant_mode == 'local'
                       else QdrantClient(url=settings.qdrant_url, timeout=settings.request_timeout_seconds))
        return _client

def close_client():
    global _client
    with _lock:
        if _client is not None:
            _client.close()
            _client = None

def tenant_filter(user_id, source_ids):
    if not isinstance(user_id, int) or user_id <= 0 or not source_ids:
        raise ValueError('User and selected sources are required for vector access')
    return models.Filter(must=[models.FieldCondition(key='user_id', match=models.MatchValue(value=user_id)),
                               models.FieldCondition(key='source_id', match=models.MatchAny(any=list(source_ids)))])

def index_source(user_id, source_id):
    evidence = source_evidence(user_id, [source_id])
    if not evidence:
        raise ValueError('Source has no evidence')
    name = collection_name()
    with _lock:
        q = client()
        if q.collection_exists(name):
            count = q.count(name, count_filter=tenant_filter(user_id, [source_id]), exact=True).count
            if count == len(evidence):
                return
        for offset in range(0, len(evidence), 64):
            batch = evidence[offset:offset + 64]
            vectors = embed_documents([e['content'] for e in batch])
            if not q.collection_exists(name):
                q.create_collection(name, vectors_config=models.VectorParams(size=len(vectors[0]), distance=models.Distance.COSINE))
                if settings.qdrant_mode == 'server':
                    for key in ('user_id', 'source_id'):
                        q.create_payload_index(name, key, field_schema=models.PayloadSchemaType.INTEGER)
            points = [models.PointStruct(id=str(uuid5(NAMESPACE_URL, f'ntro:{user_id}:{e["evidence_id"]}')), vector=v, payload=e)
                      for e, v in zip(batch, vectors)]
            q.upsert(name, points=points, wait=True)

def search_evidence(user_id, query, source_ids, limit):
    owned_sources(user_id, source_ids)
    vector = embed_query(query)
    with _lock:
        hits = client().query_points(collection_name(), query=vector, query_filter=tenant_filter(user_id, source_ids),
                                     limit=limit, with_payload=True).points
    # Bind back to canonical SQLite content; never trust vector payload text as authoritative.
    canonical = {e['evidence_id']: e for e in source_evidence(user_id, source_ids)}
    return [{**canonical[h.payload['evidence_id']], 'score': h.score} for h in hits
            if h.payload and h.payload.get('user_id') == user_id and h.payload.get('evidence_id') in canonical]

def delete_source_vectors(user_id, source_id):
    owned_sources(user_id, [source_id])
    with _lock:
        q = client()
        if q.collection_exists(collection_name()):
            q.delete(collection_name(), points_selector=models.FilterSelector(filter=tenant_filter(user_id, [source_id])), wait=True)
