"""Bounded Wikimedia Commons retrieval; assets are illustrations, never evidence."""
import io
import json
import re
import warnings
from urllib.parse import urlencode, urlsplit
from bs4 import BeautifulSoup
from PIL import Image, ImageOps
from app.config import settings
from app.utils import fetch_public_url


def _text(value):
    value = str(value or '')
    return BeautifulSoup(value, 'html.parser').get_text(' ', strip=True) if '<' in value else value.strip()


def _https_host(url, host):
    p = urlsplit(url)
    return p.scheme == 'https' and p.hostname == host and not p.username and not p.password and p.port in {None, 443}


def candidates(words, diagnostics=None):
    diagnostics = diagnostics if diagnostics is not None else []
    # Only the bounded visual keywords leave the machine. No documents or captions.
    query = ' '.join(re.findall(r'[\w-]+', ' '.join(words)))[:160]
    if not query:
        return []
    params = {'action': 'query', 'format': 'json', 'generator': 'search', 'gsrsearch': query,
              'gsrnamespace': 6, 'gsrlimit': 8, 'prop': 'imageinfo',
              'iiprop': 'url|mime|size|extmetadata', 'iiurlwidth': 1280, 'iiextmetadatalanguage': 'en'}
    raw, _ = fetch_public_url('https://commons.wikimedia.org/w/api.php?' + urlencode(params),
                              accepted_types=('application/json',), max_bytes=2 * 1024 * 1024,
                              user_agent=settings.media_user_agent)
    pages = json.loads(raw).get('query', {}).get('pages', {})
    found = []
    for page in sorted(pages.values(), key=lambda p: p.get('index', 999)):
        info = (page.get('imageinfo') or [{}])[0]
        meta = info.get('extmetadata', {})
        field = lambda key: _text(meta.get(key, {}).get('value', ''))
        license_name, license_url = field('LicenseShortName'), field('LicenseUrl')
        # Accept explicit attribution licenses; retain share-alike obligations in credits.
        permitted = license_name in {'Public domain', 'CC0'} or bool(re.fullmatch(r'CC BY(?:-SA)? (1\.0|2\.0|2\.5|3\.0|4\.0)', license_name))
        if not permitted or info.get('mime') not in {'image/jpeg', 'image/png', 'image/webp', 'image/svg+xml'}:
            diagnostics.append('Rejected unsupported image format or license: ' + page.get('title', 'Image'))
            continue
        if info.get('mime') == 'image/svg+xml' and not info.get('thumburl'):
            diagnostics.append('SVG has no raster thumbnail')
            continue
        if license_name.startswith('CC BY') and (not _https_host(license_url, 'creativecommons.org') or ('/licenses/by-sa/' if license_name.startswith('CC BY-SA') else '/licenses/by/') not in license_url):
            continue
        url, source = info.get('thumburl') or info.get('url', ''), info.get('descriptionurl', '')
        if not _https_host(url, 'upload.wikimedia.org') or not _https_host(source, 'commons.wikimedia.org'):
            continue
        title, creator = field('ObjectName') or page.get('title', 'Image'), field('Artist')
        if not creator or len(title) > 200 or len(creator) > 220 or len(source) > 1000:
            diagnostics.append('Missing or oversized attribution metadata')
            continue
        if info.get('width', 0) < 640 or info.get('height', 0) < 360:
            continue
        found.append({'url': url, 'source_url': source, 'credit_url': 'https://commons.wikimedia.org/?curid=' + str(page['pageid']), 'title': title, 'creator': creator,
                      'license': license_name, 'license_url': license_url, 'provider': 'Wikimedia Commons',
                      'changes': 'Resized and padded; caption overlay', 'share_alike': license_name.startswith('CC BY-SA'), 'illustrative': True})
    return found


def fetch_scene_image(words, target, used=None, diagnostics=None):
    diagnostics = diagnostics if diagnostics is not None else []
    used = used if used is not None else set()
    def entries():
        seen_queries = set()
        for query in [words, words[:2], words[:1]]:
            key = ' '.join(query)
            if not key or key in seen_queries:
                continue
            seen_queries.add(key)
            try:
                found = candidates(query, diagnostics)
                if not found:
                    diagnostics.append('No acceptable Wikimedia images for query: ' + key)
                yield from found
            except Exception:
                diagnostics.append('Wikimedia lookup failed; check network access and MEDIA_USER_AGENT')
    for entry in entries():
        if entry['source_url'] in used:
            continue
        try:
            raw, _ = fetch_public_url(entry['url'], accepted_types=('image/jpeg', 'image/png', 'image/webp'),
                                      max_bytes=10 * 1024 * 1024, user_agent=settings.media_user_agent)
            with warnings.catch_warnings():
                warnings.simplefilter('error', Image.DecompressionBombWarning)
                with Image.open(io.BytesIO(raw)) as image:
                    if image.width * image.height > 20000000:
                        continue
                    ImageOps.pad(image.convert('RGB'), (1280, 720), color='#10233d').save(target, 'PNG')
            used.add(entry['source_url'])
            return entry
        except Exception:
            diagnostics.append('Image download or decoding failed: ' + entry['title'])
            continue
    return None
