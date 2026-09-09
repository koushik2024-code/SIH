from app.config import settings
from app.vector_store import index_source, search_evidence
from app.embeddings import rerank
from app.repository import owned_sources
from app.router import estimate_tokens

QUERIES = {
    'linkedin': 'Main contribution, significant findings, methodology, results and implications for a professional LinkedIn post.',
    'executive_summary': 'Main findings, conclusions, risks, important statistics and decision-relevant information.',
    'advisory': 'Risks, affected systems, impact, mitigations, recommendations and operational guidance.',
    'presentation': 'Major sections, findings, supporting facts and logical presentation structure.',
    'video': 'Most important factual points to explain in a short multi-scene video.',
    'email': 'Key message, relevant facts, audience impact and requested actions for an email.',
    'x_post': 'Most significant news, findings and implications for a concise factual thread.',
    'infographic': 'Key facts, statistics, comparisons and relationships for an infographic specification.'
}

def build_query(output_type, controls, sources):
    explicit = (controls.get('retrieval_query') or '').strip()
    if explicit:
        return explicit
    return ' '.join([QUERIES[output_type], f"Objective: {controls.get('objective', 'inform')}.",
                     f"Audience: {controls.get('audience', 'general')}.",
                     'Source titles: ' + '; '.join(s['name'] for s in sources), controls.get('user_instruction', '')])

def retrieve(user_id, query, source_ids, top_k=None):
    owned_sources(user_id, source_ids)
    for sid in source_ids:
        index_source(user_id, sid)
    hits = search_evidence(user_id, query, source_ids, settings.rag_candidates)
    if settings.enable_reranker and hits:
        hits = rerank(query, hits)
    selected, used = [], 0
    budget = min(settings.direct_max_tokens, settings.ollama_num_ctx - settings.ollama_num_predict - 2500)
    for hit in hits[:top_k or settings.rag_top_k]:
        cost = estimate_tokens(hit['content']) + 180
        if used + cost <= budget:
            selected.append(hit)
            used += cost
    return selected
