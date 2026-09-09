import hashlib
import json
import ipaddress
import socket
from urllib.parse import urlsplit, urlunsplit
from app.db import db
from app.config import settings

def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()

def audit(user_id, action, object_type=None, object_id=None, details=None):
    with db() as con:
        con.execute('INSERT INTO audit_events(user_id,action,object_type,object_id,details_json) VALUES(?,?,?,?,?)',
                    (user_id, action, object_type, str(object_id) if object_id is not None else None, json.dumps(details or {}, ensure_ascii=False)))

def resolve_public_url(url):
    if any(ord(c) < 33 for c in url) or '\\' in url:
        raise ValueError('Invalid URL characters')
    parsed = urlsplit(url)
    if parsed.scheme not in {'http', 'https'} or not parsed.hostname or parsed.username is not None or parsed.password is not None:
        raise ValueError('Only public HTTP(S) URLs without credentials are accepted')
    port = parsed.port or (443 if parsed.scheme == 'https' else 80)
    if port not in {80, 443}:
        raise ValueError('Only ports 80 and 443 are accepted')
    host = parsed.hostname.encode('idna').decode('ascii')
    try:
        addresses = list(dict.fromkeys(info[4][0] for info in socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)))
    except OSError:
        raise ValueError('Cannot resolve URL host') from None
    if not addresses or any(not ipaddress.ip_address(ip).is_global or ipaddress.ip_address(ip).is_multicast for ip in addresses):
        raise ValueError('Private/internal network targets are blocked')
    return parsed, host, port, addresses

def validate_public_url(url):
    resolve_public_url(url)
    return url

def fetch_public_url(url, accepted_types=None, max_bytes=None, user_agent=None):
    """Pin the connection to the validated IP; preserve TLS hostname/SNI and Host.

    requests delegates to urllib3; a direct pool avoids proxy/DNS rebinding between
    validation and connection. Redirects and retries to alternate hosts are disabled.
    """
    import urllib3
    parsed, host, port, addresses = resolve_public_url(url)
    ip = addresses[0]
    options = {'timeout': urllib3.Timeout(connect=settings.request_timeout_seconds, read=settings.request_timeout_seconds),
               'maxsize': 1, 'block': True}
    if parsed.scheme == 'https':
        pool = urllib3.HTTPSConnectionPool(ip, port=port, server_hostname=host, assert_hostname=host, cert_reqs='CERT_REQUIRED', **options)
    else:
        pool = urllib3.HTTPConnectionPool(ip, port=port, **options)
    path = urlunsplit(('', '', parsed.path or '/', parsed.query, ''))
    host_header = f'[{host}]' if ':' in host else host
    if port != (443 if parsed.scheme == 'https' else 80):
        host_header += f':{port}'
    response = None
    try:
        response = pool.urlopen('GET', path, headers={'Host': host_header, 'User-Agent': user_agent or 'NTRO-Local-Ingest/2', 'Accept-Encoding': 'identity'},
                                redirect=False, retries=False, preload_content=False)
        if 300 <= response.status < 400:
            raise ValueError('Redirects are disabled. Supply the final public webpage URL.')
        if response.status != 200:
            raise ValueError('Webpage returned an unsuccessful HTTP status')
        content_type = response.headers.get('Content-Type', '').lower()
        if content_type.split(';')[0].strip() not in (accepted_types or ('text/html', 'application/xhtml+xml', 'text/plain')):
            raise ValueError('URL must return an HTML or text webpage; upload documents as files')
        limit, chunks, count = max_bytes if max_bytes is not None else settings.max_url_mb * 1024 * 1024, [], 0
        for block in response.stream(65536, decode_content=True):
            count += len(block)
            if count > limit:
                raise OverflowError('URL content too large')
            chunks.append(block)
        return b''.join(chunks), content_type
    finally:
        if response is not None:
            response.close()
        pool.close()
