# NTRO Studio — updated content workspace

**Upgrading an existing installation? Start with [docs/STUDIO_SETUP.md](docs/STUDIO_SETUP.md).**
Keep your `.env`, `.venv` and `data` folders. This release preserves existing accounts and history.

New: automatic Wikimedia images for video; 17 text-language choices and matched narration-voice configuration;
manual editing with live preview; separate lightweight Ollama revisions; encrypted LinkedIn/X/SMTP connections;
explicit review-and-submit; searchable history with individual/bulk deletion; responsive light/dark dashboard.

Publishing needs your own provider credentials and permissions. No content is sent on generation.
Video input remains speech transcription, not frame understanding. Text translation quality and voice
availability vary by language. See setup and validation documentation for tested limits.

---

# NTRO Content Transformation Platform

## Latest OCR, Video and Language Update

Start with [UPDATE_SETUP.md](docs/UPDATE_SETUP.md) for the current Tesseract/Piper
setup, data-preserving upgrade instructions, separate translation stage and UI
changes. It supersedes earlier statements below about language prompting and
requiring an explicit Piper executable. Run `python -m scripts.check_setup` to
check local executable and voice-file configuration.

An upgraded version of the supplied FastAPI/SQLite project. Local source ingestion,
DIRECT or semantic RAG routing, eight output contracts, signed evidence citations,
authenticated history, and deterministic narrated video composition share one API
and a plain HTML/CSS/JavaScript dashboard.

This is a runnable prototype, not an accredited government deployment. Validation
checks output structure and citation identity; it does not certify every claim.
See [SECURITY.md](docs/SECURITY.md) and [VALIDATION.md](docs/VALIDATION.md).

## Windows PowerShell quick start

Extract the ZIP, then open PowerShell **inside `ntro_content_platform_v2`**.
Use 64-bit Python 3.12 as the baseline for the native ML dependency stack. The code
uses Python 3.10+ syntax, but Python 3.13 wheels must be checked for your selected
Torch, CTranslate2 and other native dependency versions. The automated checks for
this delivery ran on Linux/Python 3.12; Windows execution was not available here.

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
Copy-Item .env.example .env
python -m scripts.setup_env
ollama pull llama3.2:3b
python -m scripts.create_user admin
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload --no-access-log
```

`create_user` prompts for a password. The originally requested
`python -m scripts.create_user admin xyz` also works for a disposable demo account;
a command-line password can be retained in shell history. Account names do not
implicitly grant administrator privileges. `scripts` is a proper Python package.

If activation is blocked by machine policy, use the interpreter directly:

```powershell
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe -m scripts.setup_env
.venv\Scripts\python.exe -m scripts.create_user admin
.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --no-access-log
```

Open [the local workspace](http://127.0.0.1:8000), sign in, add text and select
LinkedIn. No embedding, OCR, STT or TTS model is needed for that first DIRECT flow.
Ollama must be running. Its Windows application normally starts the local service;
run `ollama serve` only if the service is not already running.

`setup_env` generates a random signing key and preserves existing configuration.
Startup rejects `CHANGE_ME` and secrets shorter than 32 characters. Do not copy a
real `.env`, database, model cache or uploaded material into a distributable ZIP.

## Local component setup

| Component | What it does | Setup |
| --- | --- | --- |
| Ollama | Generates output JSON | Install Ollama, pull `llama3.2:3b`, keep the service running on loopback |
| SentenceTransformers | Embeds documents and queries locally | Run the explicit model download command below once |
| Qdrant | Stores/searches embeddings with user and source filters | Embedded mode needs no server or Docker |
| Tesseract + pypdfium2 | OCR images and scanned PDF pages | Install Tesseract executable; Python PDF renderer is in requirements |
| faster-whisper | Timestamped audio transcription | Cache the Whisper model with `--whisper` below |
| Piper | Turns scene narration into WAV | Install Piper and a voice; set the executable/model paths |
| FFmpeg | Extracts video audio and composes MP4 | Install a Windows build and set `FFMPEG_EXE` or PATH |

### Ollama and context

`.env` defaults to `OLLAMA_MODEL=llama3.2:3b`, `OLLAMA_NUM_CTX=16384` and
`OLLAMA_NUM_PREDICT=3000`. Each request supplies the full Pydantic JSON schema in
Ollama's `format` field. Invalid JSON, missing/empty content, unknown fields,
invalid citations and format violations get **one** repair attempt with explicit
validation feedback. A second failure returns 422. Unavailable Ollama returns 502.
There is no cloud-model fallback.

For a small machine, reducing context/output budgets may lower memory use; reduce
`DIRECT_MAX_TOKENS` accordingly. Do not raise direct limits without reserving room
for prompts and output. Startup checks their relationship, and generation checks
the assembled prompt before sending it. Estimates are heuristics, not the exact
Ollama tokenizer. Structured output cannot guarantee factual support.

### Embeddings, Whisper and optional reranker

Run these commands during provisioning with an approved internet connection:

```powershell
python -m scripts.download_models
python -m scripts.download_models --whisper
# Optional, only if you plan to enable the local reranker:
python -m scripts.download_models --reranker
```

These commands download model weights; they do not process or transmit source
content. `MODELS_LOCAL_ONLY=true` is the runtime default: missing model files cause
a clear ingestion/retrieval failure instead of an automatic download. For offline
machines, provision the caches in advance or configure absolute local model paths.
`trust_remote_code` is disabled. Model weights are not included in this ZIP.

Whisper defaults to `small`, CPU, `int8`. Audio ingestion stores language,
duration and per-segment start/end times. Video input first extracts audio with
FFmpeg, then follows the same transcription path. Silent video without useful
text is rejected; visual frame understanding is not implemented.

### Qdrant

```dotenv
QDRANT_MODE=local
QDRANT_PATH=./data/qdrant
```

The Qdrant Python client runs embedded and persists its index to disk. Use **one
application worker** in this mode: multiple processes cannot safely share the
same embedded store. The client closes during application shutdown/reload.

For an operator-managed trusted Qdrant server, set:

```dotenv
QDRANT_MODE=server
QDRANT_URL=http://127.0.0.1:6333
```

SQLite owns the canonical evidence. Indexing is lazy on first RAG use and proceeds
in batches; retry safely upserts the same deterministic point IDs. DIRECT avoids
the embedding cost. The collection name includes an embedding-model-name hash to
avoid mixing models. Each point includes `user_id`, `source_id`, `source_name`,
`evidence_id`, `chunk_index`, location metadata and content. Every search/count/
delete filter includes both the authenticated user and selected sources. Search
results are rebound to SQLite evidence before generation.

Changing weights at the same model path requires a new `QDRANT_COLLECTION` value
or rebuilding the index. Collections for earlier models are not automatically
removed. The index is rebuildable from canonical evidence.

### OCR on Windows

Install Tesseract using the Windows installation options linked from the
[official Tesseract documentation](https://tesseract-ocr.github.io/tessdoc/Installation.html).
Then set your actual executable path, for example:

```dotenv
TESSERACT_CMD=C:/Program Files/Tesseract-OCR/tesseract.exe
```

```powershell
& "C:\Program Files\Tesseract-OCR\tesseract.exe" --version
```

`pypdf` extracts normal PDF pages. Pages with fewer than 20 alphanumeric extracted
characters are rendered by pypdfium2 and OCR'd. Page order, page numbers, OCR flags
and empty pages are recorded. OCR quality depends on scan quality and installed
language data. The current OCR call uses Tesseract's default language; change its
local configuration for other source languages.

### FFmpeg on Windows

Choose an approved Windows build through the
[FFmpeg download page](https://ffmpeg.org/download.html), extract it and set:

```dotenv
FFMPEG_EXE=C:/tools/ffmpeg/bin/ffmpeg.exe
```

```powershell
& "C:\tools\ffmpeg\bin\ffmpeg.exe" -version
```

Alternatively put its `bin` directory on PATH and leave `FFMPEG_EXE=ffmpeg`.
No shell command strings are built from source content.

### Piper voice and executable

Use [Piper's installation and CLI instructions](https://github.com/OHF-Voice/piper1-gpl/blob/main/docs/CLI.md).
For a compatible Windows Python environment:

```powershell
python -m pip install piper-tts
New-Item -ItemType Directory -Force data/voices
python -m piper.download_voices en_US-lessac-medium --data-dir data/voices
(Get-Command piper).Source
```

Set the actual absolute paths printed/created on your machine:

```dotenv
PIPER_EXE=C:/your/project/.venv/Scripts/piper.exe
PIPER_MODEL=C:/your/project/data/voices/en_US-lessac-medium.onnx
```

Keep `en_US-lessac-medium.onnx.json` beside the ONNX file. If your Windows/Python
combination has no compatible Piper wheel, install an approved compatible Piper
executable and set `PIPER_EXE` to it. It must support `-m MODEL -f OUTPUT.wav` and
UTF-8 narration on stdin. The sample voice is English: select a matching voice
for other narration languages and configure `VIDEO_FONT` for required glyphs.
The platform does not automatically switch voices by language.

Check your installed voice before requesting video:

```powershell
"A short local briefing." | & "C:\your\project\.venv\Scripts\piper.exe" -m "C:\your\project\data\voices\en_US-lessac-medium.onnx" -f "test.wav"
```

## Routing and the query bar

| Condition | Route |
| --- | --- |
| Current evidence fits the budget, up to 5 documents, no retrieval flags | DIRECT |
| Estimated evidence tokens exceed 6000 | RAG |
| More than 5 documents | RAG |
| Force retrieval or persistent knowledge enabled | RAG |

Thresholds are configurable heuristics, not universal page-count rules. Estimates
include evidence metadata/chunk overlap. Two small sources can use DIRECT; two
large sources exceed its budget. `persistent_knowledge` requests RAG over the
**selected owned sources**; it does not search other users or all history.

The dashboard calls `POST /api/route` whenever selection or retrieval flags change.
RAG shows **What part of the source should be retrieved?**, and recommends a query
for broad material. Enter, for example, `Security recommendations and affected
systems`. The exact non-empty query is embedded for retrieval. If blank, the
backend builds a query from output type, objective, audience, source titles and
additional instruction. It never embeds the first N document characters as the
retrieval query. A specific objective can prefill the bar; the operator can edit it.
DIRECT hides the field and ignores any supplied retrieval query.

The default retrieves 15 candidates and passes the best 6 to generation, with an
optional local cross-encoder reranker. RAG passes retrieved evidence only, without
an unrelated prefix of the original document. Retrieval relevance is not a
completeness guarantee; topic-focused retrieval can miss other sections.

## Citations, storage and history

Evidence IDs are assigned by the backend as `EVID-{source_id}-{index:04d}`. Chunking
stays inside PDF pages, DOCX blocks, spreadsheet rows or transcription segments.
Oversized blocks split at paragraph/sentence boundaries when possible, with
character fallback for long unbroken text. Location metadata follows each chunk.

Both routes give the model a fixed evidence-ID set. Unknown fields and invented
citations are rejected and never promoted to trusted links. Each output needs a
citation, as does each slide/scene. Advisory severity must appear in cited text
or be omitted; this lexical check is not semantic entailment verification.

Links contain a signed 10-minute JWT bound to a user and evidence ID. They display
source name, page/sheet/timestamp metadata and the exact evidence text. These are
short-lived **bearer links**: possession permits viewing that one passage until
expiry, without a second login. Do not forward them. Citation tokens cannot serve
as normal access tokens. Reopen an output in History to mint fresh links; downloads
also refresh links. Expired links return 401.

SQLite retains users, canonical sources, evidence, output JSON, assets and audit
events. Raw uploaded files are deleted after ingestion by default. Every successful
output uses a new UUID filename, so regeneration does not overwrite prior history.
The dashboard provides open/copy/download, refreshed citation links,
search, manual edits, AI revisions and individual/bulk deletion. Back up SQLite and assets together.

Multi-output generation records each successful result. If some formats fail,
the API returns the successful outputs plus an `errors` array. If all fail, it
returns 422/502 as appropriate. Nothing invalid is stored as a successful asset.

## Deterministic video

The local LLM produces 4–6 validated factual scenes. For each scene:

1. Piper converts narration to a local WAV.
2. The backend measures `frames / sample_rate` from that WAV.
3. Automatic mode searches Wikimedia Commons using scene keywords. Supported
   license metadata is screened and source/creator credits are retained. Internal
   mode disables online search. If no online image is available, visual keywords
   match local filenames or `.tags.txt` sidecars under `data/media_library`.
4. Pillow makes a captioned card when no image matches and overlays captions on
   matching images too.
5. FFmpeg combines the still image and WAV with that measured target duration.
6. FFmpeg concatenates the scene MP4s into a playable MP4.

There are no arbitrary fixed scene durations. Automatic mode downloads scene
images into a bounded temporary render directory. Credits appear in the video.
Encoded durations are quantized to video frames/audio packets; exact mathematical
identity with arbitrary WAV lengths is not possible in a 30fps MP4. Narration
lengths and media choices are retained in asset metadata and a timeline sidecar.
Temporary scene files are cleaned up. The dashboard loads video through an
authenticated request into an HTML5 video player.

## Default API test request (PowerShell)

Run the server first. Use your chosen account password instead of the sample.

```powershell
$loginBody = @{ username = "admin"; password = "xyz" } | ConvertTo-Json
$login = Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/auth/login" -Method Post -ContentType "application/json" -Body $loginBody
$headers = @{ Authorization = "Bearer $($login.access_token)" }
$sourceBody = @{ name = "Demo report"; text = "The research team reports a Transformer architecture. It uses attention to process sequences. The report describes improved translation quality." } | ConvertTo-Json
$source = Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/sources/text" -Method Post -Headers $headers -ContentType "application/json" -Body $sourceBody
$body = @{ source_ids = @($source.source_id); output_types = @("linkedin", "executive_summary"); audience = "AI professionals"; tone = "professional"; language = "English"; detail_level = "medium"; objective = "Explain the reported contribution"; style = "educational"; retrieval_requested = $false; persistent_knowledge = $false } | ConvertTo-Json -Depth 6
$result = Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/transform" -Method Post -Headers $headers -ContentType "application/json" -Body $body
$result | ConvertTo-Json -Depth 12
```

For RAG, set `retrieval_requested = $true` and add
`retrieval_query = "Main contribution and attention architecture"` to the body.

## API endpoints

| Endpoint | Purpose |
| --- | --- |
| `POST /api/auth/login` | Argon2 login, JWT access token |
| `POST /api/sources/text` | Canonical pasted text |
| `POST /api/sources/upload` | One multipart file, including audio/video |
| `POST /api/sources/url` | Bounded public webpage import with SSRF checks |
| `GET /api/sources` / `GET /api/sources/{id}` | Owned source list/detail |
| `POST /api/route` | Route preview and query recommendation |
| `POST /api/transform` | Generate one or more validated outputs |
| `GET /api/assets` / `GET /api/assets/{id}` | Owned history/detail |
| `GET /api/assets/{id}/download` | Authenticated text/MP4 download |
| `GET /api/citations/{evidence_id}?token=...` | Signed evidence view |
| `POST /api/assets/{id}/edit` / `POST /api/assets/{id}/revise` | Save a manual or lightweight-model revision |
| `DELETE /api/assets/{id}` / `POST /api/assets/delete-selection` | Delete selected saved outputs |
| `DELETE /api/sources/{id}` | Remove an unused source and vectors |
| `GET/PUT/DELETE /api/publishing/connections[/{channel}]` | Manage encrypted per-user provider credentials |
| `POST /api/publishing/{id}/preview` / `POST /api/publishing/{id}/submit` | Review exact payload, then explicitly send |
| `GET /api/publishing/history` | Submission receipts and partial/unknown outcomes |
| `GET /api/setup` | Authenticated language/voice/model setup status |
| `GET /api/health` | Application process health, not model readiness |

Malformed contracts/parsing/verification produce 422; unsupported uploads 400;
authentication failures 401; citation mismatch 403; missing or foreign-owned
records 404; oversized uploads/URL responses 413; local backend failures 502.
Login throttling returns 429. Browser responses omit server stack traces.

## Validation and limitations

```powershell
python -m pip install -r requirements-dev.txt
python -m compileall app scripts
python -m pytest -q
# Optional if Node is installed:
node --check frontend/app.js
```

See [VALIDATION.md](docs/VALIDATION.md) for tests run, fixtures and unavailable
components. The tests isolate their database and use fixtures for model replies;
they never secretly substitute fixtures in the shipped application.

Remaining limits: no public-web fact checker; no hallucination-free guarantee;
no VLM/frame semantics; no live microphone recorder (upload audio through the
same source endpoint); no native PPTX or raster infographic output; no social
media-file uploading or OAuth token-refresh UI; no async job queue/cancellation; no production RBAC,
malware scanner, cryptographic audit chain or encrypted database. Large documents
and video can occupy a worker for a long time. English-first embeddings, OCR and
the sample TTS voice limit multilingual quality. Select/test multilingual models
and fonts for your deployment. The X limit uses Unicode code points, not the
platform's full weighted URL/emoji counting rules.

## Project files and change inventory

See [PROJECT_TREE.md](docs/PROJECT_TREE.md) for the full tree and
[CHANGES.md](docs/CHANGES.md) for changed/added files. Every file in the ZIP contains
its complete final contents; no patch application or disconnected project is needed.

Implementation references: [Ollama structured outputs](https://docs.ollama.com/capabilities/structured-outputs),
[Qdrant Python local mode](https://github.com/qdrant/qdrant-client),
[Qdrant filters](https://qdrant.tech/documentation/search/filtering/),
[SentenceTransformer local model loading](https://sbert.net/docs/package_reference/sentence_transformer/model.html),
[faster-whisper](https://github.com/SYSTRAN/faster-whisper).
