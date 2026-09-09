from functools import lru_cache
from threading import RLock
from app.config import settings

model_lock = RLock()

@lru_cache(maxsize=1)
def embedding_model():
    from sentence_transformers import SentenceTransformer
    return SentenceTransformer(settings.embedding_model, device='cpu', local_files_only=settings.models_local_only, trust_remote_code=False)

def embed_documents(texts):
    with model_lock:
        return embedding_model().encode(texts, normalize_embeddings=True, show_progress_bar=False).tolist()

def embed_query(query):
    prefix = 'Represent this sentence for searching relevant passages: ' if 'bge-' in settings.embedding_model.lower() else ''
    return embed_documents([prefix + query])[0]

@lru_cache(maxsize=1)
def reranker():
    from sentence_transformers import CrossEncoder
    return CrossEncoder(settings.reranker_model, device='cpu', local_files_only=settings.models_local_only, trust_remote_code=False)

def rerank(query, evidence):
    with model_lock:
        scores = reranker().predict([(query, e['content']) for e in evidence])
    return [e for _, e in sorted(zip(scores, evidence), key=lambda p: float(p[0]), reverse=True)]
