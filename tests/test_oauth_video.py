import json
from urllib.parse import urlsplit, parse_qs
import pytest
from app.config import settings
from app.api import oauth
from app.db import db
from app import render, media
from PIL import Image

@pytest.fixture
def google(monkeypatch):
    monkeypatch.setattr(settings,'google_client_id','client')
    monkeypatch.setattr(settings,'google_client_secret','secret')
    class Reply:
        def __init__(self,data): self.data=data
        def raise_for_status(self): pass
        def json(self): return self.data
    monkeypatch.setattr(oauth.requests,'post',lambda *a,**k:Reply({'access_token':'private-access', 'refresh_token':'private-refresh','scope':'openid email https://www.googleapis.com/auth/gmail.send','expires_in':3600}))
    monkeypatch.setattr(oauth.requests,'get',lambda *a,**k:Reply({'sub':'google-123','email':'alice@example.com','email_verified':True}))

def begin(client):
    r=client.get('/api/auth/oauth/google/start',follow_redirects=False)
    assert r.status_code==302
    params=parse_qs(urlsplit(r.headers['location']).query)
    assert params['code_challenge_method']==['S256']
    return params['state'][0]

def test_google_login_connects_and_handoff_is_one_use(client,google):
    state=begin(client)
    response=client.get('/api/auth/oauth/google/callback',params={'state':state,'code':'test'},follow_redirects=False)
    assert response.headers['location']=='/?signin=complete'
    assert 'private-access' not in str(response.headers)
    r=client.post('/api/auth/oauth/session',headers={'Origin':settings.oauth_base_url})
    assert r.status_code==200
    with db() as con:
        saved=con.execute('SELECT * FROM connections WHERE channel="email"').fetchone()
        assert saved and 'private-access' not in saved['secret']
    assert client.post('/api/auth/oauth/session',headers={'Origin':settings.oauth_base_url}).status_code==401
    assert client.get('/api/auth/oauth/google/callback',params={'state':state,'code':'test'}).status_code==400

def test_callback_requires_browser_binding(client,google):
    state=begin(client)
    client.cookies.clear()
    assert client.get('/api/auth/oauth/google/callback',params={'state':state,'code':'test'}).status_code==400

def test_link_preserves_existing_user(client,google):
    r=client.post('/api/auth/oauth/connect/google',headers=client.headers_for('alice'))
    state=parse_qs(urlsplit(r.json()['url']).query)['state'][0]
    assert client.get('/api/auth/oauth/google/callback',params={'state':state,'code':'test'},follow_redirects=False).headers['location']=='/?signin=complete'
    with db() as con:
        assert con.execute('SELECT user_id FROM oauth_identities WHERE subject="google-123"').fetchone()[0]==client.users['alice']

def test_missing_scope_does_not_create_connection(client):
    oauth.save_publishing(client.users['alice'],'google',{'email':'alice@example.com','email_verified':True},{'scope':'openid email','access_token':'test'})
    with db() as con:
        assert not con.execute('SELECT * FROM connections').fetchone()

def test_svg_sharealike_thumbnail(monkeypatch):
    page={'pageid':1,'title':'Diagram','imageinfo':[{'mime':'image/svg+xml','width':1000,'height':800,'thumburl':'https://upload.wikimedia.org/diagram.png','descriptionurl':'https://commons.wikimedia.org/wiki/File:Diagram.svg','extmetadata':{'LicenseShortName':{'value':'CC BY-SA 4.0'},'LicenseUrl':{'value':'https://creativecommons.org/licenses/by-sa/4.0/'},'Artist':{'value':'Author'}}}]}
    monkeypatch.setattr(media,'fetch_public_url',lambda *a,**k:(json.dumps({'query':{'pages':{'1':page}}}).encode(),'application/json'))
    assert media.candidates(['diagram'])[0]['license']=='CC BY-SA 4.0'

def test_fallback_frame_has_visible_visuals(tmp_path,monkeypatch):
    monkeypatch.setattr(render,'_pick_local_image',lambda *a:None)
    path=tmp_path/'frame.png'
    token=render._video_options.set({'warnings':[]})
    try:
        result=render._scene_image({'scene':1,'caption':'Transformer architecture','visual_keywords':['attention']},path)
        assert result['provider']=='caption_card'
        with Image.open(path) as image:
            assert image.size==(1280,720)
            assert image.getpixel((980,190))!=image.getpixel((0,0))
    finally: render._video_options.reset(token)


@pytest.mark.parametrize('provider', ['linkedin', 'x'])
def test_old_social_button_opens_manual_connection(client, provider):
    assert client.post('/api/auth/oauth/connect/' + provider).status_code == 401
    response = client.post('/api/auth/oauth/connect/' + provider, headers=client.headers_for('alice'))
    assert response.status_code == 200
    assert response.json() == {'url': '/?connect=' + provider}
    assert 'set-cookie' not in response.headers

def test_manual_social_build_is_served(client):
    assert client.get('/api/health').json()['build'] == 'manual-social-3'
    page = client.get('/')
    assert '/app.js?v=manual-social-3' in page.text
    assert page.headers['cache-control'] == 'no-store'
