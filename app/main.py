from contextlib import asynccontextmanager
import logging
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from fastapi.staticfiles import StaticFiles
from app.config import BASE, settings, validate_secret
from app.db import init_db
from app.vector_store import close_client
from app.api import auth, sources, route, transform, assets, citations, publishing

class BodyTooLarge(Exception):
    pass

class RequestSizeLimit:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            return await self.app(scope, receive, send)
        limit = (settings.max_upload_mb + 1) * 1024 * 1024 if scope['path'] == '/api/sources/upload' else 24 * 1024 * 1024
        count = 0
        async def bounded_receive():
            nonlocal count
            message = await receive()
            count += len(message.get('body', b''))
            if count > limit:
                raise HTTPException(413, 'Request body too large')
            return message
        await self.app(scope, bounded_receive, send)

@asynccontextmanager
async def lifespan(app):
    validate_secret()
    init_db()
    yield
    close_client()

app = FastAPI(title=settings.app_name, lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
app.add_middleware(RequestSizeLimit)

@app.exception_handler(BodyTooLarge)
async def too_large(request, exc):
    return JSONResponse(status_code=413, content={'detail': 'Request body too large'})

@app.exception_handler(RequestValidationError)
async def request_invalid(request, exc):
    errors = [{'loc': e['loc'], 'msg': e['msg'], 'type': e['type']} for e in exc.errors()]
    return JSONResponse(status_code=422, content={'detail': errors})

@app.exception_handler(Exception)
async def internal_error(request, exc):
    logging.getLogger('ntro').error('Unhandled request error: %s', type(exc).__name__)
    return JSONResponse(status_code=500, content={'detail': 'Internal processing error; inspect local configuration and service status'})

@app.middleware('http')
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['Referrer-Policy'] = 'no-referrer'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['Cache-Control'] = 'no-store'
    response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' blob:; media-src 'self' blob:; object-src 'none'; frame-ancestors 'none'; base-uri 'none'"
    return response

@app.get('/api/health')
def health():
    return {'status': 'ok', 'build': 'manual-social-3', 'social_connections': 'manual_credentials', 'generation': 'local_ollama', 'qdrant_mode': settings.qdrant_mode}

from fastapi import Depends
from app.security import current_user
from app.diagnostics import setup_status

@app.get('/api/setup')
def local_setup(user=Depends(current_user)):
    return setup_status()

for module, prefix in [(auth, 'auth'), (sources, 'sources'), (route, 'route'), (transform, 'transform'), (assets, 'assets'), (citations, 'citations'), (publishing, 'publishing')]:
    app.include_router(module.router, prefix='/api/' + prefix, tags=[prefix])
app.mount('/', StaticFiles(directory=BASE / 'frontend', html=True), name='frontend')
