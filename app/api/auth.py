from collections import defaultdict, deque
from threading import Lock
from time import monotonic
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from app.db import db
from app.security import verify_password, make_token, hash_password
from app.utils import audit

router = APIRouter()
_attempts = defaultdict(deque)
_lock = Lock()
_dummy_hash = hash_password('not-an-account-password')

class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=1, max_length=1024)

@router.post('/login')
def login(req: LoginRequest, request: Request):
    ip = request.client.host if request.client else 'local'
    now = monotonic()
    with _lock:
        # Prototype per-process throttle; production uses a shared reverse-proxy limit.
        for key in list(_attempts):
            while _attempts[key] and _attempts[key][0] < now - 60:
                _attempts[key].popleft()
            if not _attempts[key]:
                del _attempts[key]
        if len(_attempts[ip]) >= 10:
            raise HTTPException(429, 'Too many sign-in attempts; retry in a minute')
        _attempts[ip].append(now)
    with db() as con:
        row = con.execute('SELECT * FROM users WHERE username=?', (req.username,)).fetchone()
    valid = verify_password(req.password, row['password_hash'] if row else _dummy_hash)
    if not row or not valid:
        audit(None, 'login.failure')
        raise HTTPException(401, 'Invalid credentials')
    audit(row['id'], 'login.success')
    return {'access_token': make_token(row['id'], row['username']), 'token_type': 'bearer'}

from app.api.oauth import router as oauth_router
router.include_router(oauth_router, prefix='/oauth')
