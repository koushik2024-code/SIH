from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit
import ipaddress
from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE = Path(__file__).resolve().parent.parent

class Settings(BaseSettings):
    oauth_base_url: str = 'http://127.0.0.1:8000'
    google_client_id: str = ''
    google_client_secret: str = ''
    github_client_id: str = ''
    github_client_secret: str = ''
    app_name: str = 'NTRO Content Transformation Platform'
    secret_key: str = 'CHANGE_ME'
    access_token_minutes: int = Field(60, ge=1)
    citation_token_minutes: int = Field(10, ge=1, le=60)
    ollama_base_url: str = 'http://127.0.0.1:11434'
    ollama_model: str = 'llama3.2:3b'
    revision_model: str = 'qwen2.5:1.5b'
    enable_web_images: bool = True
    media_user_agent: str = 'NTRO-Content-Studio/3.0 (local research prototype)'
    piper_voices: dict[str, str] = Field(default_factory=dict)
    video_fonts: dict[str, str] = Field(default_factory=dict)
    linkedin_api_version: str = '202608'
    smtp_allowed_hosts: list[str] = ['smtp.gmail.com', 'smtp.office365.com', 'smtp.mail.yahoo.com']
    allow_external_publish: bool = True
    ollama_timeout_seconds: int = Field(180, ge=1)
    ollama_num_ctx: int = Field(16384, ge=4096)
    ollama_num_predict: int = Field(3000, ge=256)
    direct_max_tokens: int = Field(6000, ge=100)
    direct_max_documents: int = Field(5, ge=1)
    embedding_model: str = 'BAAI/bge-small-en-v1.5'
    models_local_only: bool = True
    qdrant_mode: Literal['local', 'server'] = 'local'
    qdrant_path: str = './data/qdrant'
    qdrant_url: str = 'http://127.0.0.1:6333'
    qdrant_collection: str = 'ntro_evidence'
    rag_top_k: int = Field(6, ge=1, le=50)
    rag_candidates: int = Field(15, ge=1, le=100)
    enable_reranker: bool = False
    reranker_model: str = 'cross-encoder/ms-marco-MiniLM-L-6-v2'
    chunk_size: int = Field(1200, ge=100, le=5000)
    chunk_overlap: int = Field(150, ge=0)
    max_upload_mb: int = Field(200, ge=1)
    max_url_mb: int = Field(20, ge=1)
    max_source_chars: int = Field(5000000, ge=1000)
    max_archive_mb: int = Field(500, ge=1)
    max_pdf_pages: int = Field(1000, ge=1)
    max_media_seconds: int = Field(7200, ge=1)
    request_timeout_seconds: int = Field(20, ge=1)
    media_timeout_seconds: int = Field(900, ge=1)
    ffmpeg_exe: str = 'ffmpeg'
    whisper_model: str = 'small'
    whisper_device: str = 'cpu'
    whisper_compute_type: str = 'int8'
    tesseract_cmd: str = ''
    ocr_languages: str = 'eng'
    piper_exe: str = ''
    piper_model: str = ''
    video_font: str = ''
    media_library: str = './data/media_library'
    data_dir: str = './data'
    debug: bool = False
    model_config = SettingsConfigDict(env_file=BASE / '.env', extra='ignore')

    @model_validator(mode='after')
    def budgets(self):
        if self.chunk_overlap >= self.chunk_size:
            raise ValueError('CHUNK_OVERLAP must be smaller than CHUNK_SIZE')
        if self.rag_candidates < self.rag_top_k:
            raise ValueError('RAG_CANDIDATES must be at least RAG_TOP_K')
        if self.direct_max_tokens + self.ollama_num_predict + 2000 > self.ollama_num_ctx:
            raise ValueError('OLLAMA_NUM_CTX must fit DIRECT_MAX_TOKENS + OLLAMA_NUM_PREDICT + 2000')
        # Only an operator-configured local service may receive private source content.
        host = urlsplit(self.ollama_base_url)
        if host.scheme not in {'http', 'https'} or host.username or host.password:
            raise ValueError('Invalid OLLAMA_BASE_URL')
        if host.hostname != 'localhost':
            try:
                if not ipaddress.ip_address(host.hostname).is_loopback:
                    raise ValueError()
            except ValueError:
                raise ValueError('OLLAMA_BASE_URL must be a loopback address') from None
        return self

settings = Settings()
def resolve_path(value):
    p = Path(value)
    return (BASE / p).resolve() if not p.is_absolute() else p.resolve()

DATA = resolve_path(settings.data_dir)
UPLOADS, ASSETS, TEMP = DATA / 'uploads', DATA / 'assets', DATA / 'temp'
DB_PATH = DATA / 'app.db'
MEDIA_LIBRARY = resolve_path(settings.media_library)
for directory in (DATA, UPLOADS, ASSETS, TEMP, MEDIA_LIBRARY):
    directory.mkdir(parents=True, exist_ok=True)

def validate_secret():
    if settings.secret_key == 'CHANGE_ME' or len(settings.secret_key) < 32:
        raise RuntimeError('Set SECRET_KEY to a random value of at least 32 characters. Run python -m scripts.setup_env.')
