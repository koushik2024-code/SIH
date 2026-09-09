from datetime import datetime, timedelta, timezone
import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerificationError, InvalidHashError
from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from app.config import settings, validate_secret
from app.db import db

ph = PasswordHasher()
bearer = HTTPBearer(auto_error=False)

def hash_password(password):
    return ph.hash(password)

def verify_password(password, hashed):
    try:
        return ph.verify(hashed, password)
    except (VerificationError, InvalidHashError):
        return False

def _token(payload, minutes):
    validate_secret()
    now = datetime.now(timezone.utc)
    return jwt.encode({**payload, 'iat': now, 'exp': now + timedelta(minutes=minutes)}, settings.secret_key, algorithm='HS256')

def make_token(user_id, username):
    return _token({'sub': str(user_id), 'username': username, 'type': 'access'}, settings.access_token_minutes)

def _decode(token, kind):
    try:
        p = jwt.decode(token, settings.secret_key, algorithms=['HS256'], options={'require': ['exp', 'iat', 'sub', 'type']})
        if p['type'] != kind or int(p['sub']) <= 0:
            raise ValueError()
        return p
    except (jwt.PyJWTError, ValueError, TypeError):
        raise HTTPException(401, 'Invalid or expired token') from None

def current_user(creds: HTTPAuthorizationCredentials = Depends(bearer)):
    if not creds or creds.scheme.lower() != 'bearer':
        raise HTTPException(401, 'Missing bearer token')
    p = _decode(creds.credentials, 'access')
    with db() as con:
        row = con.execute('SELECT id,username FROM users WHERE id=?', (int(p['sub']),)).fetchone()
    if not row:
        raise HTTPException(401, 'User not found')
    return dict(row)

def make_citation_token(user_id, evidence_id, minutes=None):
    return _token({'sub': str(user_id), 'user_id': user_id, 'evidence_id': evidence_id, 'type': 'citation'},
                  settings.citation_token_minutes if minutes is None else minutes)

def decode_citation_token(token):
    p = _decode(token, 'citation')
    if p.get('user_id') != int(p['sub']):
        raise HTTPException(401, 'Invalid citation token')
    return p
