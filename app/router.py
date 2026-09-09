import math
from dataclasses import dataclass, asdict
from app.config import settings

@dataclass
class RouteDecision:
    route: str
    route_reason: str
    estimated_tokens: int
    query_recommended: bool

    def as_dict(self):
        return asdict(self)

def estimate_tokens(text):
    # Conservative heuristic, including non-Latin text; not a model tokenizer.
    return max(1, math.ceil(sum(0.34 if ord(c) < 128 else 1.5 for c in text)))

def choose_route(text, document_count=1, persistent_knowledge=False, retrieval_requested=False, direct_limit=None):
    tokens = estimate_tokens(text)
    limit = direct_limit or settings.direct_max_tokens
    reason = None
    if persistent_knowledge:
        reason = 'Persistent/reusable knowledge requested'
    elif retrieval_requested:
        reason = 'Operator requested topic retrieval'
    elif document_count > settings.direct_max_documents:
        reason = f'More than {settings.direct_max_documents} documents selected'
    elif tokens > limit:
        reason = f'Input exceeds direct budget ({limit} estimated tokens)'
    return RouteDecision('RAG' if reason else 'DIRECT', reason or 'Current input fits the direct context budget', tokens, bool(reason))
