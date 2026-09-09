import io
import json
from pathlib import Path
from types import SimpleNamespace
from concurrent.futures import ThreadPoolExecutor
import pytest
from PIL import Image
from app import llm, publishing, media
from app.config import settings
from app.db import db
from app.languages import voice_for
from app.security import make_token


def generated(client, source, monkeypatch, kind='linkedin', scope='public'):
    cite = [f'EVID-{source}-0000']
    value = {'hook': 'Research update', 'body': ['The team reports an attention architecture.'],
             'takeaway': 'Review the findings.', 'hashtags': ['#Research'], 'citations': cite}
    if kind == 'x_post':
        value = {'posts': ['The team reports an attention architecture.', 'Review the research findings.'], 'citations': cite}
    if kind == 'email':
        value = {'subject': 'Research findings', 'greeting': 'Hello,', 'body': ['The team reports an attention architecture.'], 'call_to_action': '', 'sign_off': 'Regards', 'citations': cite}
    monkeypatch.setattr(llm, 'ollama_json', lambda *a, **kw: json.dumps(value))
    res = client.post('/api/transform', headers=client.headers_for('alice'), json={'source_ids': [source], 'output_types': [kind], 'content_scope': scope})
    assert res.status_code == 200, res.text
    return res.json()['outputs'][0]


def connect(client, channel='linkedin'):
    body = {'label': 'Test account', 'access_token': 'fixture-user-token-never-send', 'author_urn': 'urn:li:person:test123'}
    if channel == 'email':
        body = {'label': 'Test mail', 'smtp_host': 'smtp.gmail.com', 'smtp_port': 587,
                'smtp_username': 'sender@example.com', 'smtp_password': 'fixture-app-password', 'from_email': 'sender@example.com'}
    result = client.put('/api/publishing/connections/' + channel, headers=client.headers_for('alice'), json=body)
    assert result.status_code == 200, result.text
    return body


def preview(client, output, recipients=None):
    res = client.post(f"/api/publishing/{output['asset_id']}/preview", headers=client.headers_for('alice'), json={'recipients': recipients or []})
    assert res.status_code == 200, res.text
    return res.json()


def send(client, output, p, recipients=None):
    return client.post(f"/api/publishing/{output['asset_id']}/submit", headers=client.headers_for('alice'),
                       json={'preview_token': p['preview_token'], 'recipients': recipients or []})


def test_manual_version_retains_original_and_download(client, source, monkeypatch):
    original = generated(client, source, monkeypatch)
    edited = {**original['result'], 'hook': 'Edited opening'}
    response = client.post(f"/api/assets/{original['asset_id']}/edit", headers=client.headers_for('alice'), json={'result': edited})
    assert response.status_code == 200, response.text
    new = response.json()
    assert new['asset_id'] != original['asset_id'] and new['parent_asset_id'] == original['asset_id'] and new['version'] == 2
    assert new['verification']['factual_accuracy_verified'] is False
    assert client.get(new['download_url'], headers=client.headers_for('alice')).text.startswith('Edited opening')
    assert client.get(f"/api/assets/{original['asset_id']}", headers=client.headers_for('alice')).json()['result']['hook'] == 'Research update'


def test_edits_reject_foreign_assets_citations_and_invalid_schema(client, source, monkeypatch):
    original = generated(client, source, monkeypatch)
    path = f"/api/assets/{original['asset_id']}/edit"
    assert client.post(path, headers=client.headers_for('bob'), json={'result': original['result']}).status_code == 404
    for value in [{**original['result'], 'citations': ['EVID-999-0000']}, {'hook': 'Invalid'}]:
        assert client.post(path, headers=client.headers_for('alice'), json={'result': value}).status_code == 422


def test_revision_uses_light_model_language_and_evidence(client, source, monkeypatch):
    original = generated(client, source, monkeypatch)
    calls = []
    def model(messages, schema, model=None):
        calls.append((messages, model))
        return json.dumps({**original['result'], 'hook': 'नया शोध'})
    monkeypatch.setattr(llm, 'ollama_json', model)
    response = client.post(f"/api/assets/{original['asset_id']}/revise", headers=client.headers_for('alice'), json={'instruction': 'Make it concise', 'language': 'Hindi'})
    assert response.status_code == 200, response.text
    assert calls[0][1] == settings.revision_model
    request = json.loads(calls[0][0][1]['content'])
    assert request['target_language'] == 'Hindi' and request['evidence'][0]['evidence_id'] == f'EVID-{source}-0000'
    assert response.json()['controls']['language'] == 'Hindi'


def test_bad_revision_repair_does_not_save(client, source, monkeypatch):
    original = generated(client, source, monkeypatch)
    calls=[]
    def model(*a, **kw):
        calls.append(1)
        return json.dumps({**original['result'], 'citations': ['EVID-999-0000']})
    monkeypatch.setattr(llm, 'ollama_json', model)
    res=client.post(f"/api/assets/{original['asset_id']}/revise", headers=client.headers_for('alice'), json={'instruction':'Rewrite'})
    assert res.status_code == 422 and len(calls)==2
    assert len(client.get('/api/assets',headers=client.headers_for('alice')).json())==1


def test_encrypted_connection_is_private_and_disconnects(client):
    connect(client)
    with db() as con:
        encrypted=con.execute('SELECT secret FROM connections').fetchone()['secret']
    assert 'fixture-user-token' not in encrypted
    result=client.get('/api/publishing/connections',headers=client.headers_for('alice'))
    assert 'secret' not in result.text and 'access_token' not in result.text
    assert client.get('/api/publishing/connections',headers=client.headers_for('bob')).json()==[]
    assert publishing.connection(client.users['alice'],'linkedin')[0]['access_token']=='fixture-user-token-never-send'
    client.delete('/api/publishing/connections/linkedin',headers=client.headers_for('alice'))
    assert client.get('/api/publishing/connections',headers=client.headers_for('alice')).json()==[]


def test_linkedin_submit_exact_payload_and_duplicate_guard(client, source, monkeypatch):
    output=generated(client,source,monkeypatch);connect(client);p=preview(client,output)
    calls=[]
    def post(url,token,payload,headers=None):
        calls.append((url,payload,headers));return SimpleNamespace(headers={'x-restli-id':'urn:li:share:1234'})
    monkeypatch.setattr(publishing,'_post',post)
    first=send(client,output,p);second=send(client,output,p)
    assert first.json()['status']=='submitted' and second.json()['duplicate_prevented'] and len(calls)==1
    assert calls[0][1]['commentary']==p['payload']['text'] and calls[0][1]['visibility']=='PUBLIC'
    assert '/api/citations/' not in calls[0][1]['commentary']
    assert calls[0][2]['LinkedIn-Version']==settings.linkedin_api_version


def test_publish_preview_token_binding_and_access_token_separation(client, source, monkeypatch):
    output=generated(client,source,monkeypatch);connect(client);p=preview(client,output)
    assert client.get('/api/assets',headers={'Authorization':'Bearer '+p['preview_token']}).status_code==401
    res=client.post(f"/api/publishing/{output['asset_id']}/submit",headers=client.headers_for('alice'),json={'preview_token':make_token(client.users['alice'],'alice')})
    assert res.status_code==401
    connect(client) # replacing credentials invalidates old preview, even if identical
    monkeypatch.setattr(publishing,'_post',lambda *a,**kw:pytest.fail('Must not send'))
    assert send(client,output,p).status_code==409
    assert client.post(f"/api/publishing/{output['asset_id']}/preview",headers=client.headers_for('bob'),json={}).status_code==404


def test_internal_publish_blocked_and_global_disable(client, source, monkeypatch):
    output=generated(client,source,monkeypatch,scope='internal');connect(client)
    assert client.post(f"/api/publishing/{output['asset_id']}/preview",headers=client.headers_for('alice'),json={}).status_code==403
    monkeypatch.setattr(settings,'allow_external_publish',False)
    assert client.post(f"/api/publishing/{output['asset_id']}/preview",headers=client.headers_for('alice'),json={}).status_code==403


def test_x_partial_thread_preserves_ids_and_does_not_retry(client, source, monkeypatch):
    output=generated(client,source,monkeypatch,'x_post');connect(client,'x');p=preview(client,output);calls=[]
    def post(url,token,payload,headers=None):
        calls.append(payload)
        if len(calls)==2:raise RuntimeError('Provider rejected second post')
        return SimpleNamespace(json=lambda:{'data':{'id':'123'}})
    monkeypatch.setattr(publishing,'_post',post)
    result=send(client,output,p).json()
    assert result['status']=='partial' and result['result']['remote_ids']==['123']
    assert calls[1]['reply']=={'in_reply_to_tweet_id':'123'}
    assert send(client,output,p).json()['duplicate_prevented'] and len(calls)==2


def test_email_recipient_binding_and_no_header_injection(client, source, monkeypatch):
    output=generated(client,source,monkeypatch,'email');connect(client,'email');to=['person@example.com'];p=preview(client,output,to)
    calls=[]
    monkeypatch.setattr(publishing,'_smtp',lambda config,payload: calls.append(payload) or {'accepted':payload['to'],'refused':[]})
    assert send(client,output,p,['other@example.com']).status_code==409
    assert send(client,output,p,to).json()['status']=='submitted'
    assert calls[0]['subject']==output['result']['subject'] and calls[0]['to']==to
    assert client.post(f"/api/publishing/{output['asset_id']}/preview",headers=client.headers_for('alice'),json={'recipients':['person@example.com\r\nBcc: victim@example.com']}).status_code==422


def test_smtp_host_controls(client):
    req={'label':'Bad','smtp_host':'127.0.0.1','smtp_username':'x','smtp_password':'x','from_email':'x@example.com'}
    assert client.put('/api/publishing/connections/email',headers=client.headers_for('alice'),json=req).status_code==422


def test_bulk_delete_atomic_and_files_removed(client, source, monkeypatch):
    a=generated(client,source,monkeypatch);b=generated(client,source,monkeypatch)
    with db() as con:paths=[Path(r['path']) for r in con.execute('SELECT path FROM assets')]
    assert client.post('/api/assets/delete-selection',headers=client.headers_for('alice'),json={'ids':[a['asset_id'],99999]}).status_code==404
    assert all(p.exists() for p in paths)
    assert client.delete('/api/assets/'+str(a['asset_id']),headers=client.headers_for('bob')).status_code==404
    result=client.post('/api/assets/delete-selection',headers=client.headers_for('alice'),json={'ids':[a['asset_id'],b['asset_id']]})
    assert result.status_code==200 and all(not p.exists() for p in paths)
    assert client.get('/api/assets',headers=client.headers_for('alice')).json()==[]


def test_source_deletion_preserves_citations_until_outputs_deleted(client, source, monkeypatch):
    output=generated(client,source,monkeypatch)
    assert client.delete('/api/sources/'+str(source),headers=client.headers_for('alice')).status_code==409
    client.delete('/api/assets/'+str(output['asset_id']),headers=client.headers_for('alice'))
    calls=[]
    monkeypatch.setattr('app.vector_store.delete_source_vectors',lambda uid,sid:calls.append((uid,sid)))
    assert client.delete('/api/sources/'+str(source),headers=client.headers_for('alice')).status_code==200
    assert calls==[(client.users['alice'],source)]
    assert client.get('/api/sources/'+str(source),headers=client.headers_for('alice')).status_code==404


def test_voice_language_match_and_missing_language(monkeypatch,tmp_path):
    path=tmp_path/'voice.onnx';path.write_bytes(b'fixture');Path(str(path)+'.json').write_text('{"language":{"code":"en_US"}}')
    monkeypatch.setattr(settings,'piper_model',str(path));assert voice_for('English')==path
    with pytest.raises(ValueError,match='No Hindi'):voice_for('Hindi')
    monkeypatch.setattr(settings,'piper_voices',{'hi':str(path)})
    with pytest.raises(ValueError,match='does not match'):voice_for('Hindi')


def commons_page(license='CC BY 4.0',url='https://upload.wikimedia.org/test.jpg'):
    field=lambda v:{'value':v}
    return {'pageid':1,'title':'File:Research.jpg','index':1,'imageinfo':[{'width':1280,'height':720,'mime':'image/jpeg','thumburl':url,'descriptionurl':'https://commons.wikimedia.org/wiki/File:Research.jpg','extmetadata':{'LicenseShortName':field(license),'LicenseUrl':field('https://creativecommons.org/licenses/by/4.0/'),'Artist':field('<a>Test Author</a>'),'ObjectName':field('Research')}}]}


def test_web_image_license_host_and_decode(monkeypatch,tmp_path):
    pages={'1':commons_page(),'2':{**commons_page('CC BY-SA 4.0'),'pageid':2},'3':{**commons_page(url='http://127.0.0.1/image.jpg'),'pageid':3}}
    binary=io.BytesIO();Image.new('RGB',(1280,720),'green').save(binary,'JPEG');calls=[]
    def fetch(url,**kwargs):
        calls.append((url,kwargs))
        return (json.dumps({'query':{'pages':pages}}).encode(),'application/json') if 'api.php?' in url else (binary.getvalue(),'image/jpeg')
    monkeypatch.setattr(media,'fetch_public_url',fetch)
    selected=media.fetch_scene_image(['research'],tmp_path/'scene.png',set())
    assert selected['creator']=='Test Author' and selected['license']=='CC BY 4.0'
    assert Image.open(tmp_path/'scene.png').size==(1280,720) and len(calls)==2
    assert calls[1][1]['max_bytes']==10*1024*1024


def test_internal_video_never_fetches_web(monkeypatch,tmp_path):
    from app import render
    monkeypatch.setattr(render,'_pick_local_image',lambda words:None)
    monkeypatch.setattr(media,'fetch_scene_image',lambda *args:pytest.fail('Internal media leaked keywords'))
    token=render._video_options.set({'web':False})
    try:
        result=render._scene_image({'scene':1,'caption':'Internal research','visual_keywords':['private']},tmp_path/'scene.png')
        assert result['provider']=='caption_card'
    finally:render._video_options.reset(token)


def test_web_failure_falls_back(monkeypatch,tmp_path):
    from app import render
    monkeypatch.setattr(render,'_pick_local_image',lambda words:None)
    def fail(*args):raise OSError('network unavailable')
    monkeypatch.setattr(media,'fetch_scene_image',fail)
    opts={'web':True,'used':set(),'warnings':[]};token=render._video_options.set(opts)
    try:
        result=render._scene_image({'scene':1,'caption':'Research','visual_keywords':['research']},tmp_path/'scene.png')
        assert result['provider']=='caption_card' and opts['warnings']
    finally:render._video_options.reset(token)


def test_source_delete_blocked_during_generation(client, source):
    from app.limits import _active, _guard
    uid=client.users['alice']
    with _guard:_active.add(uid)
    try:
        res=client.delete('/api/sources/'+str(source),headers=client.headers_for('alice'))
        assert res.status_code==429
        assert client.get('/api/sources/'+str(source),headers=client.headers_for('alice')).status_code==200
    finally:
        with _guard:_active.discard(uid)


def test_concurrent_submit_reserved_once(client, source, monkeypatch):
    from threading import Event
    output=generated(client,source,monkeypatch);connect(client);p=preview(client,output)
    entered, release=Event(),Event();calls=[]
    def post(*args,**kwargs):
        calls.append(1);entered.set()
        assert release.wait(10)
        return SimpleNamespace(headers={'x-restli-id':'urn:li:share:555'})
    monkeypatch.setattr(publishing,'_post',post)
    req=publishing.PublishSubmit(preview_token=p['preview_token'])
    with ThreadPoolExecutor(max_workers=2) as pool:
        first=pool.submit(publishing.submit,output['asset_id'],client.users['alice'],req)
        try:
            assert entered.wait(5)
            second=publishing.submit(output['asset_id'],client.users['alice'],req)
            assert second['status']=='sending' and second['duplicate_prevented']
            assert client.delete('/api/assets/'+str(output['asset_id']),headers=client.headers_for('alice')).status_code==409
        finally:release.set()
        assert first.result(timeout=10)['status']=='submitted'
    assert len(calls)==1


def test_outbound_http_has_fixed_token_headers_no_proxy_or_redirect(monkeypatch):
    captures={}
    class Session:
        trust_env=True
        def __enter__(self):captures['session']=self;return self
        def __exit__(self,*args):pass
        def post(self,url,**kwargs):captures.update(url=url,**kwargs);return SimpleNamespace(status_code=201)
    monkeypatch.setattr(publishing.requests,'Session',Session)
    publishing._post('https://api.x.com/2/tweets','fixture-token',{'text':'fixture'})
    assert captures['session'].trust_env is False
    assert captures['allow_redirects'] is False and captures['timeout']==30
    assert captures['headers']['Authorization']=='Bearer fixture-token'
