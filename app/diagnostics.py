"""Local dependency discovery; never downloads models or changes configuration."""
import importlib.util
import os
import shutil
import sys
from pathlib import Path
from app.config import settings, resolve_path


def tesseract_command():
    if settings.tesseract_cmd:
        return settings.tesseract_cmd
    found = shutil.which('tesseract')
    if found:
        return found
    for root in (os.environ.get('ProgramFiles', ''), os.environ.get('LOCALAPPDATA', '')):
        if root:
            candidate = Path(root) / 'Tesseract-OCR' / 'tesseract.exe'
            if candidate.is_file():
                return str(candidate)
    return 'tesseract'


def executable_exists(command):
    return bool(shutil.which(command) or Path(command).is_file())


def piper_command():
    if settings.piper_exe:
        return [settings.piper_exe]
    if importlib.util.find_spec('piper'):
        return [sys.executable, '-m', 'piper']
    return ['piper']


def video_setup_errors(model_override=None):
    model = model_override or settings.piper_model
    errors = []
    if not executable_exists(settings.ffmpeg_exe):
        errors.append('Install FFmpeg and set FFMPEG_EXE in .env.')
    if not executable_exists(piper_command()[0]):
        errors.append('Install Piper: python -m pip install piper-tts, or set PIPER_EXE.')
    if not model or not resolve_path(model).is_file():
        errors.append('Download a Piper voice and set PIPER_MODEL to its .onnx file.')
    elif not Path(str(resolve_path(model)) + '.json').is_file():
        errors.append('The voice .onnx.json configuration must be beside its .onnx file.')
    return errors


def setup_status():
    ocr = executable_exists(tesseract_command())
    errors = video_setup_errors()
    return {'ocr': {'configured': ocr, 'languages': settings.ocr_languages,
                    'message': 'Tesseract found; language packs must also be installed.' if ocr else 'Install Tesseract and set TESSERACT_CMD.'},
            'video_output': {'configured': not errors, 'messages': errors or ['FFmpeg, Piper and voice files found. Synthesis still requires a compatible voice.']},
            'video_input': {'configured': executable_exists(settings.ffmpeg_exe),
                            'message': 'Video input uses FFmpeg + Whisper speech transcription, not visual frame understanding.'},
            'languages': __import__('app.languages', fromlist=['choices']).choices(),
            'revision_model': settings.revision_model,
            'web_images_enabled': settings.enable_web_images,
            'publishing_enabled': settings.allow_external_publish,
            'smtp_allowed_hosts': settings.smtp_allowed_hosts,
            'multilingual': {'mode': 'separate_local_translation_pass', 'quality_verified': False}}
