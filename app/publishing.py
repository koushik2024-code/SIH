"""User-scoped encrypted connectors and explicit, deduplicated external submissions."""
import base64
import hashlib
import hmac
import ipaddress
import json
import re
import smtplib
import socket
import ssl
import time
from email.message import EmailMessage
from email.utils import make_msgid
from urllib.parse import quote
import requests
from cryptography.fernet import Fernet, InvalidToken
from fastapi import HTTPException
from pydantic import Field, model_validator
from typing import Literal
from app.config import settings
from app.db import db
from app.schemas import Contract
from app.security import _token, _decode
from app.api.assets import owned_asset
from app.render import render_text
from app.utils import audit

Channel = Literal['linkedin', 'x', 'email']


def mailbox(value):
    if not re.fullmatch(r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?\.[A-Za-z]{2,63}", value) or len(value) > 254:
        raise ValueError('Enter an email address only, without a display name')
    return value


class ConnectionRequest(Contract):
    label: str = Field(min_length=1, max_length=100)
    access_token: str = Field('', max_length=8192)
    author_urn: str = Field('', max_length=200)
    smtp_host: str = Field('', max_length=253)
    smtp_port: Literal[465, 587] = 587
    smtp_username: str = Field('', max_length=254)
    smtp_password: str = Field('', max_length=1000)
    from_email: str = Field('', max_length=254)

    @model_validator(mode='after')
    def no_header_injection(self):
        for value in self.model_dump().values():
            if isinstance(value, str) and any(c in value for c in '\r\n\x00'):
                raise ValueError('Connection fields cannot contain control characters')
        return self


class PublishPreview(Contract):
    recipients: list[str] = Field(default_factory=list, max_length=20)

    @model_validator(mode='after')
    def addresses(self):
        self.recipients = list(dict.fromkeys(mailbox(x.strip()) for x in self.recipients))
        return self


class PublishSubmit(PublishPreview):
    preview_token: str = Field(min_length=1, max_length=4096)


def cipher(user_id):
    key = hmac.new(settings.secret_key.encode(), f'ntro:connector:v1:{user_id}'.encode(), hashlib.sha256).digest()
    return Fernet(base64.urlsafe_b64encode(key))


def store_connection(user_id, channel, req):
    values = req.model_dump()
    if channel in {'linkedin', 'x'}:
        if not req.access_token:
            raise HTTPException(422, 'An OAuth user access token with posting permission is required')
        if channel == 'linkedin' and not re.fullmatch(r'urn:li:(person|organization):[A-Za-z0-9_-]+', req.author_urn):
            raise HTTPException(422, 'Enter the LinkedIn author URN for your authorized account')
        values = {k: values[k] for k in ['label', 'access_token', 'author_urn']}
    else:
        if req.smtp_host.casefold() not in [h.casefold() for h in settings.smtp_allowed_hosts]:
            raise HTTPException(422, 'SMTP host is not enabled by the operator; see SMTP_ALLOWED_HOSTS')
        try:
            mailbox(req.from_email)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from None
        if not req.smtp_username or not req.smtp_password:
            raise HTTPException(422, 'SMTP username and app password are required')
        values = {k: v for k, v in values.items() if k not in {'access_token', 'author_urn'}}
    encrypted = cipher(user_id).encrypt(json.dumps(values).encode()).decode()
    with db() as con:
        con.execute('INSERT INTO connections(user_id,channel,label,secret) VALUES(?,?,?,?) ON CONFLICT(user_id,channel) DO UPDATE SET label=excluded.label,secret=excluded.secret,updated_at=CURRENT_TIMESTAMP', (user_id, channel, req.label, encrypted))
    audit(user_id, 'connection.save', 'connection', channel)
    return {'channel': channel, 'label': req.label, 'configured': True, 'verified': False}


def connection(user_id, channel):
    with db() as con:
        row = con.execute('SELECT * FROM connections WHERE user_id=? AND channel=?', (user_id, channel)).fetchone()
    if not row:
        raise HTTPException(422, 'Configure this publishing account in Connections first')
    try:
        data = json.loads(cipher(user_id).decrypt(row['secret'].encode()))
    except (InvalidToken, ValueError):
        raise HTTPException(422, 'Stored credentials cannot be decrypted. Reconnect the account.') from None
    if data.get('kind') in {'gmail_oauth', 'linkedin_oauth'} and data.get('expires_at', 0) < time.time()+60:
        data = refresh_oauth(user_id, channel, data)
        with db() as con:
            row = con.execute('SELECT secret FROM connections WHERE user_id=? AND channel=?', (user_id,channel)).fetchone()
    return data, hashlib.sha256(row['secret'].encode()).hexdigest()


def prepare(asset_id, user_id, recipients):
    if not settings.allow_external_publish:
        raise HTTPException(403, 'External publishing is disabled by the operator')
    row = owned_asset(asset_id, user_id)
    meta = json.loads(row['metadata_json'])
    if meta.get('controls', {}).get('content_scope') == 'internal':
        raise HTTPException(403, 'Internal outputs cannot be submitted externally')
    channel = {'linkedin': 'linkedin', 'x_post': 'x', 'email': 'email'}.get(row['output_type'])
    if not channel:
        raise HTTPException(422, 'Submit supports LinkedIn text posts, X threads and email')
    if not meta.get('verification', {}).get('passed'):
        raise HTTPException(422, 'Output must pass structure and citation checks before submission')
    config, config_version = connection(user_id, channel)
    value = meta['result']
    if channel == 'email':
        if not recipients:
            raise HTTPException(422, 'Enter at least one recipient email address')
        if any(c in value['subject'] for c in '\r\n\x00'):
            raise HTTPException(422, 'Email subject cannot contain line breaks')
        payload = {'subject': value['subject'], 'body': '\n\n'.join(x for x in [value['greeting'], *value['body'], value['call_to_action'], value['sign_off']] if x),
                   'to': recipients, 'from': config['from_email']}
    elif channel == 'x':
        if recipients:
            raise HTTPException(422, 'Recipients are only supported for email')
        payload = {'posts': value['posts']}
    else:
        if recipients:
            raise HTTPException(422, 'Recipients are only supported for email')
        text = render_text(value, 'linkedin')
        if len(text) > 3000:
            raise HTTPException(422, 'Shorten the LinkedIn post to at most 3000 characters before submission')
        payload = {'text': text, 'author': config['author_urn'], 'visibility': 'PUBLIC'}
    # The fingerprint excludes asset ID and credential token, deduplicating the same
    # content/destination across versions and token refreshes.
    destination = config.get('author_urn') or config.get('from_email') or config['label']
    fingerprint = hashlib.sha256(json.dumps([channel, destination, payload], sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    return channel, config, config_version, payload, fingerprint


def preview(asset_id, user_id, recipients):
    channel, config, version, payload, fingerprint = prepare(asset_id, user_id, recipients)
    token = _token({'sub': str(user_id), 'type': 'publish', 'asset_id': asset_id,
                    'fingerprint': fingerprint, 'connection_version': version}, 10)
    return {'channel': channel, 'account': config['label'], 'payload': payload,
            'preview_token': token, 'message': 'Submit sends this exact saved version. Internal citation links are not included.'}


def _post(url, token, payload, headers=None):
    try:
        with requests.Session() as session:
            session.trust_env = False
            response = session.post(url, headers={'Authorization': 'Bearer ' + token, **(headers or {})},
                                    json=payload, timeout=30, allow_redirects=False)
    except requests.RequestException:
        raise RuntimeError('Delivery status unknown after a connection error. Check the destination before sending anything again.') from None
    if response.status_code not in {200, 201, 202}:
        # Never expose provider response bodies; they may reflect credentials/content.
        raise RuntimeError(f'Provider returned HTTP {response.status_code}. Check posting permissions, token expiry and account access.')
    return response


def _smtp(config, payload):
    host, port = config['smtp_host'], config['smtp_port']
    if host.casefold() not in [h.casefold() for h in settings.smtp_allowed_hosts]:
        raise RuntimeError('SMTP host is no longer enabled by the operator')
    addresses = list(dict.fromkeys(i[4][0] for i in socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)))
    if not addresses or any(not ipaddress.ip_address(ip).is_global for ip in addresses):
        raise RuntimeError('SMTP must resolve to public addresses')
    ctx = ssl.create_default_context()
    class PinnedSMTP(smtplib.SMTP):
        def _get_socket(self, requested_host, requested_port, timeout):
            return socket.create_connection((addresses[0], requested_port), timeout)
    class PinnedSSL(smtplib.SMTP_SSL):
        def _get_socket(self, requested_host, requested_port, timeout):
            raw = socket.create_connection((addresses[0], requested_port), timeout)
            return self.context.wrap_socket(raw, server_hostname=host)
    message = EmailMessage()
    message['Subject'], message['From'], message['To'] = payload['subject'], payload['from'], ', '.join(payload['to'])
    message['Message-ID'] = make_msgid(domain=payload['from'].split('@')[1])
    message.set_content(payload['body'])
    smtp = PinnedSSL(host, port, timeout=30, context=ctx) if port == 465 else PinnedSMTP(host, port, timeout=30)
    with smtp:
        if port == 587:
            smtp.ehlo()
            smtp.starttls(context=ctx)
            smtp.ehlo()
        smtp.login(config['smtp_username'], config['smtp_password'])
        refused = smtp.send_message(message)
    return {'message_id': str(message['Message-ID']), 'accepted': [x for x in payload['to'] if x not in refused],
            'refused': list(refused), 'note': 'SMTP acceptance does not confirm inbox delivery.'}


def submit(asset_id, user_id, req):
    claim = _decode(req.preview_token, 'publish')
    channel, config, version, payload, fingerprint = prepare(asset_id, user_id, req.recipients)
    if int(claim['sub']) != user_id or claim.get('asset_id') != asset_id or claim.get('fingerprint') != fingerprint or claim.get('connection_version') != version:
        raise HTTPException(409, 'Preview expired or changed. Open a fresh publishing preview.')
    with db() as con:
        con.execute('BEGIN IMMEDIATE')
        if not con.execute('SELECT id FROM assets WHERE id=? AND user_id=?', (asset_id, user_id)).fetchone():
            raise HTTPException(404, 'Output was deleted')
        old = con.execute('SELECT * FROM publications WHERE user_id=? AND fingerprint=?', (user_id, fingerprint)).fetchone()
        if old:
            return {'publication_id': old['id'], 'status': old['status'], 'result': json.loads(old['result_json']), 'duplicate_prevented': True}
        cur = con.execute('INSERT INTO publications(user_id,asset_id,channel,fingerprint,status) VALUES(?,?,?,?,?)', (user_id, asset_id, channel, fingerprint, 'sending'))
        publication_id = cur.lastrowid
    result, status = {'remote_ids': [], 'urls': []}, 'submitted'
    def checkpoint():
        with db() as con:
            con.execute('UPDATE publications SET result_json=? WHERE id=?', (json.dumps(result), publication_id))
    try:
        if channel == 'linkedin':
            response = _post('https://api.linkedin.com/rest/posts', config['access_token'],
                {'author': payload['author'], 'commentary': payload['text'], 'visibility': 'PUBLIC',
                 'distribution': {'feedDistribution': 'MAIN_FEED', 'targetEntities': [], 'thirdPartyDistributionChannels': []},
                 'lifecycleState': 'PUBLISHED', 'isReshareDisabledByAuthor': False},
                {'LinkedIn-Version': settings.linkedin_api_version, 'X-Restli-Protocol-Version': '2.0.0'})
            remote_id = response.headers.get('x-restli-id')
            if not remote_id:
                raise RuntimeError('Provider accepted the request but did not return a post ID. Check your account.')
            result = {'remote_ids': [remote_id], 'urls': ['https://www.linkedin.com/feed/update/' + quote(remote_id, safe=':') + '/']}
        elif channel == 'x':
            for text in payload['posts']:
                body = {'text': text}
                if result['remote_ids']:
                    body['reply'] = {'in_reply_to_tweet_id': result['remote_ids'][-1]}
                response = _post('https://api.x.com/2/tweets', config['access_token'], body)
                remote_id = str(response.json()['data']['id'])
                if not remote_id.isdigit():
                    raise ValueError('Invalid provider identifier')
                result['remote_ids'].append(remote_id)
                result['urls'].append('https://x.com/i/web/status/' + remote_id)
                checkpoint()
        else:
            result = _gmail(config, payload) if config.get('kind') == 'gmail_oauth' else _smtp(config, payload)
            if result['refused']:
                status = 'partial'
    except Exception as exc:
        status = 'partial' if result.get('remote_ids') else 'unknown'
        result['message'] = str(exc) if isinstance(exc, RuntimeError) else 'Submission could not be confirmed. Check the destination before retrying.'
    with db() as con:
        con.execute('UPDATE publications SET status=?,result_json=? WHERE id=?', (status, json.dumps(result), publication_id))
    audit(user_id, 'publish.' + status, 'asset', asset_id, {'publication_id': publication_id, 'channel': channel})
    return {'publication_id': publication_id, 'status': status, 'result': result, 'duplicate_prevented': False}


def refresh_oauth(uid, channel, data):
    if not data.get('refresh_token') or data.get('kind') != 'gmail_oauth':
        raise HTTPException(422, 'Authorization expired. Use Reconnect in Connections.')
    try:
        response = requests.post('https://oauth2.googleapis.com/token', data={'grant_type':'refresh_token','refresh_token':data['refresh_token'], 'client_id':settings.google_client_id,'client_secret':settings.google_client_secret}, timeout=20, allow_redirects=False)
        response.raise_for_status()
        result = response.json()
        data.update(access_token=result['access_token'], expires_at=time.time()+int(result.get('expires_in',3600)))
    except (requests.RequestException, KeyError, ValueError):
        raise HTTPException(422, 'Gmail authorization expired or revoked. Reconnect Google.') from None
    encrypted = cipher(uid).encrypt(json.dumps(data).encode()).decode()
    with db() as con:
        con.execute('UPDATE connections SET secret=?,updated_at=CURRENT_TIMESTAMP WHERE user_id=? AND channel=?', (encrypted,uid,channel))
    return data


def _gmail(config, payload):
    message = EmailMessage()
    message['Subject'], message['From'], message['To'] = payload['subject'], payload['from'], ', '.join(payload['to'])
    message.set_content(payload['body'])
    raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
    response = _post('https://gmail.googleapis.com/gmail/v1/users/me/messages/send', config['access_token'], {'raw':raw})
    return {'message_id':response.json()['id'], 'accepted':payload['to'], 'refused':[], 'note':'Gmail accepted the message; inbox delivery is not guaranteed.'}
