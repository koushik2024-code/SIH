# Latest Studio upgrade

For the current dashboard, editing, automatic images, multilingual configuration,
publishing and deletion features, follow [STUDIO_SETUP.md](STUDIO_SETUP.md).
The older OCR/FFmpeg/Piper instructions below still apply to local dependencies.

---

# OCR, Video, Languages and UI Update

## Install this update without losing accounts

Stop Uvicorn with Ctrl+C. Back up your existing project first. Extract the updated
ZIP to a separate directory, then replace the existing `app/`, `scripts/` and
`frontend/` folders with the updated copies. Preserve your `.env`, `.venv/` and
`data/` directories: these contain configuration, installed packages, accounts,
sources and history. The SQLite schema is unchanged.

New frontend features: local setup-status panel, readable errors instead of raw
JSON, and an email preview with separate subject and message body. Email prompts
now request send-ready paragraphs without hashtags, report headings, repeated
CTAs or invented sender details. Prompt compliance remains model-dependent.

## Tesseract for image and scanned-PDF OCR

`pytesseract` is a Python wrapper, not the OCR executable. Install the Windows
Tesseract build linked from the official documentation:
https://tesseract-ocr.github.io/tessdoc/Installation.html

Configure your actual path in `.env`:

```dotenv
TESSERACT_CMD=C:/Program Files/Tesseract-OCR/tesseract.exe
OCR_LANGUAGES=eng
```

The update also searches PATH and the standard Program Files installation.
To read Hindi or Telugu scans, install the corresponding Tesseract language data,
then configure, for example, `OCR_LANGUAGES=eng+hin+tel`. Output language and OCR
language are separate: OCR_LANGUAGES describes the writing in source images.

```powershell
& "C:\Program Files\Tesseract-OCR\tesseract.exe" --version
& "C:\Program Files\Tesseract-OCR\tesseract.exe" --list-langs
```

## Piper for generated videos

Whisper transcribes input audio. It does not speak generated narration. Install
Piper plus an approved voice for video output:

```powershell
python -m pip install piper-tts
New-Item -ItemType Directory -Force data/voices
python -m piper.download_voices en_US-lessac-medium --data-dir data/voices
```

The download must include both `en_US-lessac-medium.onnx` and
`en_US-lessac-medium.onnx.json`. For this update, `.env` can contain:

```dotenv
PIPER_EXE=
PIPER_MODEL=./data/voices/en_US-lessac-medium.onnx
FFMPEG_EXE=C:/tools/ffmpeg/bin/ffmpeg.exe
```

An empty PIPER_EXE now uses `python -m piper` when the package is installed.
A configured PIPER_EXE is still respected; clear stale paths. Change the FFmpeg
path to your actual installation, or use `FFMPEG_EXE=ffmpeg` if it is on PATH.
Test the actual voice separately:

```powershell
python -m piper -m ./data/voices/en_US-lessac-medium.onnx -f test.wav -- "This is a local briefing."
python -m scripts.check_setup
```

Piper documentation: https://github.com/OHF-Voice/piper1-gpl/blob/main/docs/CLI.md
The sample voice speaks English, not arbitrary languages. Other narration
languages require a matching installed Piper voice and a suitable VIDEO_FONT.
Automatic language-to-voice selection is not implemented. Status checks verify
executables/files, not successful synthesis, model checksums or voice quality.

## Multilingual processing

Previously, the language control was only an instruction in the generation
prompt. This update adds a separate local Ollama translation stage for non-English
output: generate and validate the English contract, translate prose, then validate
again. One repair attempt is allowed for translation. Schema topology, citation
IDs, scene numbers, media keywords, hashtags and severity labels are protected.
Those protected labels remain in the base language intentionally.

This is an LLM-based translation pass, not a dedicated translation model or a
verified language-quality system. It does not guarantee faithful translation,
preserve every numeral deterministically, or detect that the model returned the
requested language. Small llama3.2:3b may produce weak Hindi/Telugu translations.
English-first BGE embeddings also limit cross-language retrieval. These limitations
are independent of having a separate translation stage. Non-English generation
can take up to four calls including both repair attempts.

## Video input versus output

Video input already exists: upload MP4/MOV/AVI/MKV/WEBM/MPEG/MPG; FFmpeg extracts
audio and local Whisper produces timestamped speech text. There is no visual-frame
understanding. Video output uses Piper narration plus local images/cards and FFmpeg.
Both need FFmpeg; only video output needs Piper.

## Restart and validate

```powershell
python -m scripts.check_setup
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload --no-access-log
```

Reload the browser and log in to see setup status. Test an English image, then
an English video output after the voice test succeeds. Test requested non-English
output separately and review the translation manually.

Validation: added tests for translation-stage execution, protected citation/shape
fields, missing voice configuration and authenticated setup status. Live model
translation quality, Piper synthesis on Windows and browser visual QA are not
verified in this environment. See VALIDATION.md for earlier coverage.
