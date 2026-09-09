import re
from app.config import settings

def chunk_text(text):
    """Prefer paragraphs/sentences, split an oversized span only as a fallback."""
    size, overlap = settings.chunk_size, settings.chunk_overlap
    text = text.strip()
    start = 0
    while start < len(text):
        end = min(start + size, len(text))
        if end < len(text):
            candidates = [m.end() for m in re.finditer(r'\n\s*\n|(?<=[.!?])\s+|\n', text[start:end])]
            viable = [p for p in candidates if p >= size // 2]
            if viable:
                end = start + viable[-1]
            else:
                space = text.rfind(' ', start + size // 2, end)
                if space > start:
                    end = space
        piece = text[start:end].strip()
        if piece:
            yield piece
        if end == len(text):
            break
        start = max(start + 1, end - overlap)

def chunk_sections(sections, source_id, user_id, source_name):
    chunks = []
    for section in sections:
        for content in chunk_text(section['text']):
            index = len(chunks)
            meta = {k: v for k, v in section.items() if k != 'text'}
            chunks.append({'user_id': user_id, 'source_id': source_id, 'source_name': source_name,
                           'evidence_id': f'EVID-{source_id}-{index:04d}', 'chunk_index': index,
                           'page': None, 'sheet': None, 'timestamp_start': None, 'timestamp_end': None,
                           **meta, 'content': content})
    return chunks
