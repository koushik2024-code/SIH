import json
from app import llm
from app.config import settings
from app.diagnostics import video_setup_errors


def sample():
    return {'subject': 'Research update', 'greeting': 'Hello,', 'body': ['The team studied attention.'],
            'call_to_action': '', 'sign_off': 'Regards', 'citations': ['EVID-1-0000']}


def test_separate_translation(monkeypatch):
    translated = {**sample(), 'subject': 'Informe', 'greeting': 'Hola,',
                  'body': ['El equipo estudio la atencion.'], 'sign_off': 'Saludos'}
    responses = iter([sample(), translated])
    calls = []
    def model(messages, schema):
        calls.append(messages)
        return json.dumps(next(responses))
    monkeypatch.setattr(llm, 'ollama_json', model)
    value, report = llm.generate('email', {'language': 'Spanish'}, [{'evidence_id': 'EVID-1-0000', 'content': 'The team studied attention.'}])
    assert value == translated and len(calls) == 2
    assert report['language_processing'] == 'separate_local_translation'
    assert report['translation_quality_verified'] is False


def test_translation_preserves_provenance_and_topology():
    assert not llm.translation_structure(sample(), {**sample(), 'citations': ['EVID-2-0000']})
    assert not llm.translation_structure(sample(), {**sample(), 'body': []})


def test_voice_configuration_sidecar(monkeypatch, tmp_path):
    model = tmp_path / 'voice.onnx'
    model.write_bytes(b'test')
    monkeypatch.setattr(settings, 'piper_model', str(model))
    assert any('configuration' in e for e in video_setup_errors())
    model.with_suffix('.onnx.json').write_text('{}')
    assert not any('configuration' in e for e in video_setup_errors())


def test_setup_requires_login(client):
    assert client.get('/api/setup').status_code == 401
    data = client.get('/api/setup', headers=client.headers_for('alice')).json()
    assert 'ocr' in data and 'video_output' in data
