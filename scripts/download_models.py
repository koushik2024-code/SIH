"""Explicit operator-invoked model downloads; no private source content is used."""
import argparse
from app.config import settings

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--whisper', action='store_true')
    parser.add_argument('--reranker', action='store_true')
    args = parser.parse_args()
    from sentence_transformers import SentenceTransformer
    SentenceTransformer(settings.embedding_model, trust_remote_code=False)
    print('Embedding model cached.')
    if args.whisper:
        from faster_whisper import WhisperModel
        WhisperModel(settings.whisper_model, device=settings.whisper_device, compute_type=settings.whisper_compute_type)
        print('Whisper model cached.')
    if args.reranker:
        from sentence_transformers import CrossEncoder
        CrossEncoder(settings.reranker_model, trust_remote_code=False)
        print('Reranker cached.')

if __name__ == '__main__':
    main()
