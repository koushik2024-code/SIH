# Studio validation record

Validation date: 2026-09-09. Runtime: Linux, Python 3.12.

## Current release

The complete suite passes **66 tests**. Python compilation and JavaScript syntax
checks pass. Static DOM wiring checks found 107 unique HTML IDs and verified all
100 literal ID references in the application script.

The suite exercises real FastAPI endpoints, SQLite transactions, authentication,
embedded Qdrant filtering, document parsing, Tesseract OCR and FFmpeg composition.
Model responses, narration WAVs, internet image responses and external sends use
explicit test fixtures. Production code never substitutes these fixtures.

New coverage includes:
- Manual edits preserve the original, validate citations and generate a new downloadable version.
- Lightweight revisions receive the configured model name, selected language and original evidence.
- Invalid revisions receive one repair attempt and are not saved.
- Foreign-user edits, downloads, connector reads, publishing and deletions are rejected.
- Connector tokens are encrypted at rest and absent from read responses.
- Preview tokens cannot authenticate ordinary API requests, and ordinary access tokens cannot submit.
- Changed recipients or credentials invalidate the publishing preview.
- Submitted LinkedIn content matches the preview; duplicate requests make one adapter call.
- Concurrent submit requests reserve one delivery; deleting an actively sending asset is blocked.
- Partial X threads retain successful post IDs and are not automatically resent.
- Email recipient/header validation and SMTP host controls.
- Atomic selected deletion, owned-file cleanup and citation-preserving source deletion.
- Source deletion is blocked while the user's generation is active, avoiding index resurrection races.
- Wikimedia license/host screening, HTML-stripped credits, bounded image decode and re-encoding.
- Internal image mode never calls the web adapter; network failures use caption-card fallback.
- Language/voice mismatch detection and inherited DIRECT/RAG, OCR and media regression coverage.

## Unverified checks

- Live Wikimedia lookup: the execution environment could not resolve the public
  host. Retrieval behavior is tested with representative Commons JSON and real
  Pillow image bytes; production access/rate limits and image relevance remain unverified.
- Live LinkedIn/X/SMTP delivery: no real credentials were used and no posts/emails
  were sent. Tests verify adapters and orchestration with fixtures, not provider approval.
- Live Ollama, revision-model quality, multilingual translation quality, embedding
  semantics, Whisper inference and Piper speech synthesis: local model weights/services
  were unavailable. Video composition uses synthetic WAV fixtures and real FFmpeg.
- Browser visual/interaction QA: local Chromium downloads timed out; the available
  cloud browser rejected the local dashboard URL with ERR_BLOCKED_BY_CLIENT. No
  visual screenshot or completed browser interaction test is claimed. HTML assets,
  JavaScript syntax and literal DOM targets were checked.
- Windows execution and complex-script video typography/voice quality remain
  unverified. Install the update and run the acceptance steps below on your laptop.

## Acceptance checks on your machine

1. Apply `STUDIO_SETUP.md`, retain existing configuration/data and sign in.
2. Paste a short source; generate LinkedIn and email in English, then a selected language.
3. Edit a field and save; confirm both versions appear in History. Ask AI for a
   revision and confirm the new version preserves the intended facts/citations.
4. Generate video with automatic images and a configured voice. Inspect image
   credits, relevance, narration, captions and timing. Try internal mode and local mode.
5. Configure your own provider credentials. Preview the exact destination and
   content before explicitly submitting a harmless test post/email you approve.
6. Confirm submitted/partial/unknown receipts in Connections. Do not resend unknown
   deliveries without checking the external account.
7. Search/filter History, select versions and delete them. Confirm other versions
   and externally published posts remain. Delete an unused source.
8. Test desktop/mobile layout, dark mode, keyboard navigation, copy/download and video playback.

Historical records follow for context; they describe earlier release counts.

---

# Validation record

## Follow-up update

The OCR/Piper diagnostics, separate translation stage, email formatting and frontend
error/status changes passed a fresh full run: **46 tests passed**. Python compilation
and JavaScript syntax checks passed. Translation tests use fixture model responses;
live translation quality and Windows/Piper voice synthesis remain unverified.
Browser visual QA has not been completed. Earlier records below describe the base
release; UPDATE_SETUP.md contains the current setup and upgrade instructions.

Validation date: 2026-09-08. Runtime: Linux, Python 3.12.

## Completed checks

- `python -m compileall app scripts`: passed.
- `node --check frontend/app.js`: passed.
- `python -m pytest -q`: 42 tests passed. Two installed Starlette/TestClient
  dependency deprecation warnings appeared; no test failures remained.
- Actual Uvicorn startup and an HTTP health request passed in an isolated local process.
- The required `python -m scripts.create_user demo xyz` module command passed and stored an Argon2 hash.
- All seven text-output types were rendered, persisted and downloaded through the API.
- Real FastAPI request handling and SQLite transactions were exercised through
  TestClient, with isolated temporary data stores and user accounts.
- Real embedded Qdrant indexed, searched, filtered and deleted points. Tests use
  deterministic synthetic vectors; the semantic quality of embedding weights was
  not evaluated.
- Real pypdf extraction, DOCX paragraphs/tables, XLSX sheets/rows, Tesseract image
  OCR and scanned-PDF rendering/OCR were exercised.
- Real FFmpeg extracted video audio and rendered/concatenated a four-scene MP4.
  WAV inputs were fixtures with different durations. The test checks the stored
  measured durations and probes final encoded duration within packet/frame tolerance.

## Requested smoke cases and evidence

| Requested case | Coverage | Actual versus fixture components |
| --- | --- | --- |
| TXT → DIRECT → LinkedIn | Passed | Actual ingestion/routing/validation/storage; fixture Ollama JSON |
| Small PDF → DIRECT → executive summary | Passed | Actual PDF parser/API; fixture Ollama JSON |
| Large PDF / automatic RAG / query bar | Large-PDF API flow passed; browser query-bar interaction pending | Actual 35-page PDF parser, route preview and Qdrant; synthetic vectors and fixture Ollama |
| Large multi-topic route preview recommends query | Passed | Actual preview endpoint and oversized source |
| Scanned PDF → OCR → summary | Passed | Actual PDF rendering/Tesseract; fixture Ollama JSON |
| Image → OCR → email | Passed | Actual Tesseract; fixture Ollama JSON |
| Excel → structured extraction | Passed | Actual openpyxl/pandas parser and located evidence; output contract covered separately |
| Audio → Whisper → summary | Adapter path passed | Fixture Whisper segments; actual timestamps, API and validation |
| Video input → audio extraction → transcript → output | Passed with STT fixture | Actual FFmpeg, fixture Whisper/Ollama |
| Multiple sources → Qdrant RAG | Passed | Real Qdrant, synthetic vectors, fixture Ollama |
| Invented citations rejected | Passed | Invalid model fixture rejected after one repair; never saved as trusted asset |
| Cross-user source access denied | Passed | Actual authentication/ownership queries |
| Cross-user Qdrant retrieval isolation | Passed | Real embedded index with identical vectors across tenants |
| Signed citation opens evidence | Passed | Actual JWT signature and SQLite lookup |
| Expired/mismatched citation rejected | Passed | Actual JWT and evidence binding |
| Video scenes → narration → measured durations → MP4 | Composition passed | Fixture WAV narration; actual Pillow, FFmpeg and ffprobe |
| Generated history | API persistence/download passed | Actual unique files and owned history; browser rendering not visually tested |

Additional tests cover empty content, all eight schemas, X length, unsupported
advisory severity, extra keys, one repair attempt, access/citation token separation,
URL IP pinning, redirect rejection, public-address policy, response/upload limits,
local-backend errors and multi-output partial success.

## Checks that could not be completed here

No Ollama server/model, SentenceTransformer weights, Whisper weights or Piper voice
was available in this environment. No live inference quality or complete
Piper-speech test is claimed. The production application has no fixture fallback;
missing services produce explicit errors. Install/provision those components as
shown in README and repeat the requested end-to-end examples on your machine.

Browser visual/interaction QA was attempted, but no browser executable was
installed and the Playwright Chromium download timed out. HTML/CSS serving and
JavaScript syntax passed; responsive appearance, clipboard access, video playback
and query-bar interaction still require a real browser check.

Windows PowerShell commands, portable pathlib paths and module entrypoints are
provided, but a Windows host was unavailable. This ZIP does not contain native
executables, model weights or a platform-specific resolved dependency lockfile.
The requirements use compatible version ranges; record a tested lockfile after
installation in the intended deployment environment.

## Operator acceptance run

1. Install dependencies; run setup_env, create_user and local Ollama.
2. Run the PowerShell API example in README and inspect output claims/citations.
3. Provision embeddings, select broad source material, verify automatic RAG and
   enter a specific topic query. Compare retrieved source passages to that topic.
4. Try a scanned PDF/image and inspect page/OCR metadata in citations.
5. Provision Whisper and upload spoken audio/video, checking timestamps.
6. Configure Piper/FFmpeg and an approved voice; request video and compare narration,
   captions, scene timing and evidence. Confirm the correct language/font.
7. Generate twice; confirm both outputs remain separately available in History.
8. Sign in as another user and confirm sources/history are isolated.
