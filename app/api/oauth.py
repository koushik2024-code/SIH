"""Server-side authorization code login; provider tokens never enter the browser."""
import base64
import hashlib
import secrets
import time
import json
from urllib.parse import urlencode, urlsplit
import requests
from fastapi import APIRouter, Request, HTTPException, Depends
from fastapi.responses import RedirectResponse, JSONResponse
from app.config import settings
from app.db import db
from app.security import hash_password, make_token, current_user

router = APIRouter()
PROVIDERS = {
    'google': ('https://accounts.google.com/o/oauth2/v2/auth', 'https://oauth2.googleapis.com/token', 'https://openidconnect.googleapis.com/v1/userinfo', 'openid profile email https://www.googleapis.com/auth/gmail.send'),
    'github': ('https://github.com/login/oauth/authorize', 'https://github.com/login/oauth/access_token', 'https://api.github.com/user', 'read:user'),
}

def config(provider):
    if provider not in PROVIDERS:
        raise HTTPException(404, 'Unknown sign-in provider')
    client = getattr(settings, provider + '_client_id')
    secret = getattr(settings, provider + '_client_secret')
    if not client or not secret:
        raise HTTPException(503, 'Provider not configured. See docs/OAUTH_VIDEO_SETUP.md')
    base = settings.oauth_base_url.rstrip('/')
    parsed = urlsplit(base)
    if parsed.scheme != 'https' and not (parsed.scheme == 'http' and parsed.hostname in {'localhost', '127.0.0.1'}):
        raise HTTPException(503, 'OAuth requires HTTPS except on localhost')
    if parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path:
        raise HTTPException(503, 'OAUTH_BASE_URL must be an origin without a path')
    return client, secret, base + '/api/auth/oauth/' + provider + '/callback'

def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()

def cookie(response, key, value, age):
    response.set_cookie(key, value, max_age=age, httponly=True, secure=settings.oauth_base_url.startswith('https://'), samesite='lax', path='/api/auth/oauth')

@router.get('/providers')
def providers():
    return [{'provider': p, 'enabled': bool(getattr(settings, p+'_client_id') and getattr(settings, p+'_client_secret'))} for p in PROVIDERS]

@router.get('/{provider}/start')
def start(provider: str):
    return begin(provider)

@router.post('/connect/{provider}')
def connect(provider: str, user=Depends(current_user)):
    if provider in {'linkedin', 'x'}:
        return JSONResponse({'url': '/?connect=' + provider})
    response = begin(provider, user['id'])
    result = JSONResponse({'url':response.headers['location']})
    result.headers['set-cookie'] = response.headers['set-cookie']
    return result

def begin(provider, user_id=None):
    client, _, callback = config(provider)
    state, binding, verifier = (secrets.token_urlsafe(32) for _ in range(3))
    with db() as con:
        con.execute('DELETE FROM oauth_states WHERE expires<?', (time.time(),))
        con.execute('DELETE FROM oauth_handoffs WHERE expires<?', (time.time(),))
        con.execute('INSERT INTO oauth_states VALUES(?,?,?,?,?,?)', (digest(state), provider, digest(binding), verifier, time.time()+600, user_id))
    params = dict(client_id=client, redirect_uri=callback, response_type='code', scope=PROVIDERS[provider][3], state=state)
    if provider == 'google':
        params.update(access_type='offline', prompt='consent')
    if provider in {'google', 'github'}:
        params.update(code_challenge=base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b'=').decode(), code_challenge_method='S256')
    response = RedirectResponse(PROVIDERS[provider][0]+'?'+urlencode(params), 302)
    cookie(response, 'ntro_oauth_binding', binding, 600)
    return response

@router.get('/{provider}/callback')
def callback(provider: str, request: Request, state: str = '', code: str = '', error: str = ''):
    client, secret, redirect_uri = config(provider)
    binding = request.cookies.get('ntro_oauth_binding', '')
    with db() as con:
        con.execute('BEGIN IMMEDIATE')
        row = con.execute('SELECT * FROM oauth_states WHERE state=?', (digest(state),)).fetchone()
        if not row or row['provider'] != provider or row['expires'] < time.time() or not binding or not secrets.compare_digest(row['binding'], digest(binding)):
            raise HTTPException(400, 'Invalid or expired sign-in. Start again.')
        con.execute('DELETE FROM oauth_states WHERE state=?', (digest(state),))
    response = RedirectResponse('/?signin=failed', 303)
    response.delete_cookie('ntro_oauth_binding', path='/api/auth/oauth')
    if error or not code:
        return response
    try:
        data = dict(client_id=client, client_secret=secret, code=code, redirect_uri=redirect_uri, grant_type='authorization_code')
        if provider in {'google', 'github'}:
            data['code_verifier'] = row['verifier']
        r = requests.post(PROVIDERS[provider][1], data=data, headers={'Accept':'application/json'}, timeout=20, allow_redirects=False)
        r.raise_for_status()
        tokens = r.json()
        access = tokens['access_token']
        r = requests.get(PROVIDERS[provider][2], headers={'Authorization':'Bearer '+access, 'Accept':'application/json', 'User-Agent':'NTRO-Studio'}, timeout=20, allow_redirects=False)
        r.raise_for_status()
        profile = r.json()
        subject = str(profile['id'] if provider == 'github' else profile['sub'])
        if not subject or len(subject)>255:
            raise ValueError('Invalid subject')
    except (requests.RequestException, KeyError, ValueError, TypeError):
        return response
    # Stable provider identity only: never link accounts by an untrusted email/name.
    with db() as con:
        con.execute('BEGIN IMMEDIATE')
        user = con.execute('SELECT u.* FROM users u JOIN oauth_identities o ON u.id=o.user_id WHERE o.provider=? AND o.subject=?', (provider, subject)).fetchone()
        if row['user_id'] is not None:
            if user and user['id'] != row['user_id']:
                return response
            uid = row['user_id']
            if not user:
                con.execute('INSERT INTO oauth_identities VALUES(?,?,?)', (provider, subject, uid))
        elif not user:
            name = provider + '_' + secrets.token_hex(10)
            uid = con.execute('INSERT INTO users(username,password_hash) VALUES(?,?)', (name, hash_password(secrets.token_urlsafe(64)))).lastrowid
            con.execute('INSERT INTO oauth_identities VALUES(?,?,?)', (provider, subject, uid))
        else:
            uid = user['id']
        handoff = secrets.token_urlsafe(32)
        con.execute('INSERT INTO oauth_handoffs VALUES(?,?,?)', (digest(handoff), uid, time.time()+60))
    save_publishing(uid, provider, profile, tokens)
    response.headers['location'] = '/?signin=complete'
    cookie(response, 'ntro_oauth_handoff', handoff, 60)
    return response

@router.post('/session')
def session(request: Request):
    if request.headers.get('origin') != settings.oauth_base_url.rstrip('/'):
        raise HTTPException(403, 'Invalid origin')
    with db() as con:
        con.execute('BEGIN IMMEDIATE')
        row = con.execute('SELECT u.* FROM oauth_handoffs h JOIN users u ON u.id=h.user_id WHERE h.binding=? AND h.expires>?', (digest(request.cookies.get('ntro_oauth_handoff','')), time.time())).fetchone()
        if not row:
            raise HTTPException(401, 'Sign-in expired. Start again.')
        con.execute('DELETE FROM oauth_handoffs WHERE binding=?', (digest(request.cookies.get('ntro_oauth_handoff','')),))
    response = JSONResponse({'access_token':make_token(row['id'],row['username']), 'username':row['username']})
    response.delete_cookie('ntro_oauth_handoff', path='/api/auth/oauth')
    return response


def save_publishing(uid, provider, profile, tokens):
    from app.publishing import cipher, mailbox
    scopes = set(tokens.get('scope', PROVIDERS[provider][3]).replace(',', ' ').split())
    values = None
    if provider == 'google' and 'https://www.googleapis.com/auth/gmail.send' in scopes and profile.get('email_verified') is True:
        try:
            address = mailbox(profile['email'])
        except (KeyError, ValueError):
            return
        channel = 'email'
        values = {'kind':'gmail_oauth', 'label':'Gmail · '+address, 'from_email':address}
    if values is None:
        return
    values.update(access_token=tokens['access_token'], refresh_token=tokens.get('refresh_token',''), expires_at=time.time()+int(tokens.get('expires_in',3600)))
    with db() as con:
        old = con.execute('SELECT secret FROM connections WHERE user_id=? AND channel=?', (uid,channel)).fetchone()
        if old and not values['refresh_token']:
            try:
                previous = json.loads(cipher(uid).decrypt(old['secret'].encode()))
                if previous.get('kind') == values['kind'] and previous.get('from_email') == values.get('from_email'):
                    values['refresh_token'] = previous.get('refresh_token','')
            except Exception:
                pass
        encrypted = cipher(uid).encrypt(json.dumps(values).encode()).decode()
        con.execute('INSERT INTO connections(user_id,channel,label,secret) VALUES(?,?,?,?) ON CONFLICT(user_id,channel) DO UPDATE SET label=excluded.label,secret=excluded.secret,updated_at=CURRENT_TIMESTAMP', (uid,channel,values['label'],encrypted))
