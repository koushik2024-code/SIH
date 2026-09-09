"""Language choices and explicit, language-matched local narration configuration."""
import json
from pathlib import Path
from app.config import settings, resolve_path

LANGUAGES = {'English': 'en', 'Hindi': 'hi', 'Telugu': 'te', 'Tamil': 'ta', 'Kannada': 'kn',
             'Malayalam': 'ml', 'Marathi': 'mr', 'Bengali': 'bn', 'Gujarati': 'gu',
             'Urdu': 'ur', 'Spanish': 'es', 'French': 'fr', 'German': 'de',
             'Arabic': 'ar', 'Japanese': 'ja', 'Chinese': 'zh', 'Portuguese': 'pt'}


def language_code(language):
    for name, code in LANGUAGES.items():
        if language.casefold() == name.casefold() or language.casefold().split('-')[0].split('_')[0] == code:
            return code
    raise ValueError('Choose a supported output language')


def voice_for(language):
    code = language_code(language)
    configured = settings.piper_voices.get(code) or (settings.piper_model if code == 'en' else '')
    if not configured:
        raise ValueError(f'No {language} narration voice configured. Add a matching installed voice to PIPER_VOICES, or choose a text output.')
    path = resolve_path(configured)
    try:
        config = json.loads(Path(str(path) + '.json').read_text(encoding='utf-8'))
        actual = config.get('language', {}).get('code', '').replace('-', '_').split('_')[0]
        if not path.is_file() or actual != code:
            raise ValueError()
    except (OSError, ValueError, TypeError, AttributeError):
        raise ValueError(f'The configured {language} voice is missing or its .onnx.json language does not match.') from None
    return path


def choices():
    output = []
    for name, code in LANGUAGES.items():
        try:
            voice_for(name)
            voice_ready = True
        except ValueError:
            voice_ready = False
        output.append({'name': name, 'code': code, 'voice_ready': voice_ready})
    return output
