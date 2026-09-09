# NTRO Studio upgrade

This release keeps the FastAPI + HTML/CSS/JavaScript project structure and the
local Ollama generation pipeline. It adds an interactive dashboard, automatic
video image retrieval, versioned editing, lightweight revisions, publishing
connectors and selected history deletion.

## Apply the update on Windows

1. Stop Uvicorn with Ctrl+C and back up your project folder.
2. Replace `app`, `frontend`, `scripts`, `tests`, `requirements.txt`,
   `requirements-dev.txt`, `README.md` and `docs` with the files in this ZIP.
3. **Keep your existing `.env`, `.venv` and `data` directories.** Do not replace
   your secret key. It signs logins/citations and encrypts saved connector secrets.
4. From your project folder, with its virtual environment active:

```powershell
python -m pip install -r requirements.txt
ollama pull qwen2.5:1.5b
python -m scripts.check_setup
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload --no-access-log
```

Open http://127.0.0.1:8000 and refresh with Ctrl+F5. Sign in with your existing
account. New SQLite tables are created automatically; old sources and outputs
remain accessible. No model is downloaded on normal application startup.

## New configuration

Append these keys to `.env` if you want to override the defaults. Edit existing
entries instead of creating duplicates.

```dotenv
REVISION_MODEL=qwen2.5:1.5b
ENABLE_WEB_IMAGES=true
ALLOW_EXTERNAL_PUBLISH=true
LINKEDIN_API_VERSION=202608
PIPER_VOICES={}
VIDEO_FONTS={}
SMTP_ALLOWED_HOSTS=["smtp.gmail.com","smtp.office365.com","smtp.mail.yahoo.com"]
```

The revision model is separate from `OLLAMA_MODEL=llama3.2:3b`. The smaller model
is a configurable default, not a quality or latency guarantee. It must be
installed with Ollama. An unavailable revision model produces a readable error;
it does not silently use a cloud model. Set `REVISION_MODEL` to another installed
local model when you need stronger multilingual editing.

Keep your working `FFMPEG_EXE`, `TESSERACT_CMD`, `PIPER_EXE` and `PIPER_MODEL`
settings. This upgrade does not change your executable paths.

## Create and revise

1. Use Upload files, Paste text or Web link. Select the stored sources to use.
2. Select one or more of the eight output formats, audience, tone and language.
3. The route preview shows DIRECT or RAG. RAG displays a topic query field.
4. Generate, then choose **Edit** for individual content fields and a live preview.
5. **Save new version** keeps the original in history. Video edits render a new MP4.
6. Choose **Ask AI to revise**, enter suggestions and optionally change language.
   The smaller local model receives the last saved output and the evidence used
   in that output. Save manual changes first if you want the AI to revise them.
7. Each revision is validated against the output schema and allowed evidence IDs.
   One repair attempt is allowed. Invalid revisions do not replace existing work.

The editor preserves citation fields. The API validates edited citations too.
Neither these checks nor successful translation prove that every statement is
supported by the source. Review the final wording and factual support.

## Multilingual text and video

The language selectors include English, Hindi, Telugu, Tamil, Kannada, Malayalam,
Marathi, Bengali, Gujarati, Urdu, Spanish, French, German, Arabic, Japanese,
Chinese and Portuguese. Generation uses an English base followed by a separate
local translation pass. Revisions use the smaller model directly in the selected
language. Language quality depends on the model; no automatic language-quality
certification is implemented.

Video narration requires a Piper-compatible installed voice for that language.
The UI reports whether a matching voice file is configured. It does not imply
that Piper distributes a voice for every language in the text selector.

`PIPER_MODEL` remains the English fallback. For additional languages, map ISO
language codes to installed `.onnx` files in `PIPER_VOICES`; the matching
`.onnx.json` must be beside each file. Example paths below are illustrative:

```dotenv
PIPER_VOICES={"en":"./data/voices/en_US-lessac-medium.onnx","hi":"./data/voices/your-installed-hindi-voice.onnx"}
VIDEO_FONTS={"hi":"C:/Windows/Fonts/Nirmala.ttf","te":"C:/Windows/Fonts/Nirmala.ttf","ar":"C:/Windows/Fonts/arial.ttf"}
```

Use files that actually exist. The voice config's `language.code` must match the
selected language. Unsupported or missing voices stop video rendering with a
clear message; the app does not narrate Hindi/Telugu using an English voice.
A matching Unicode font is required for captions; complex-script rendering also
depends on the installed Pillow/font build. Inspect the generated MP4.

OCR uses installed Tesseract language packs, independently of output language:

```dotenv
OCR_LANGUAGES=eng+hin+tel
```

Only use languages whose traineddata is installed. Video input still extracts
speech using FFmpeg + Whisper; it does not interpret the video frames.

## Automatic images for every video

Automatic mode attempts Wikimedia Commons search for each scene using its visual
keywords. No API key is required. It chooses raster images from supported
public-domain, CC0 and CC BY metadata, preserves source/creator/license details,
and includes credits within the video and its scene metadata. It excludes
share-alike, non-commercial, no-derivatives and ambiguous license metadata.

This is metadata screening, not independent legal or visual verification. Review
images for relevance and any additional restrictions. They are **illustrations**,
not evidence or a claim that a depicted event is the event in your source.

Images are downloaded into the temporary render directory, bounded in bytes and
pixels, decoded with Pillow, resized and removed after composition. The video
retains attribution metadata. The current renderer uses 1280×720, 30 FPS, H.264
video with AAC narration. Scene length follows the measured narration WAV.

When lookup fails, no acceptable image is found or the service rate-limits the
app, it falls back to local images in `data/media_library`, then caption cards.
No online lookup can guarantee a suitable image for every scene. Configure
`MEDIA_USER_AGENT` with an identifiable application/contact string if required
by your Wikimedia usage. Network access to `commons.wikimedia.org` and
`upload.wikimedia.org` is required. Automatic image retrieval does not use Google
image scraping or image generation models.

**Keep this output internal** disables web-image requests and external Submit for
that output and its revisions. An operator can disable web images globally with
`ENABLE_WEB_IMAGES=false`. Choosing local images also avoids these web requests.
Only visual keywords are sent in automatic mode; keywords can still be sensitive,
so select internal mode for private material. This switch is not a classification
system or a host-level network sandbox.

## Connect LinkedIn

Create/configure your own LinkedIn developer app and obtain an OAuth **user**
access token with posting permission. For member posts this is `w_member_social`;
organization posting requires the corresponding permissions and authorized page
role. Use your actual authorized author URN, `urn:li:person:...` or
`urn:li:organization:...`.

In Connections → LinkedIn → Connect account, enter an account label, access token
and author URN. Tokens are encrypted per user on the backend. The UI never reads
saved secrets back. This prototype accepts provisioned OAuth tokens; it does not
implement a browser OAuth redirect/refresh flow. Update expired tokens in
Connections. Access depends on your app's product permissions and approval.

The connector uses `POST https://api.linkedin.com/rest/posts`, a configured
`LinkedIn-Version` header and `X-Restli-Protocol-Version: 2.0.0`. It submits
text-only public posts. It does not upload generated MP4s or images to LinkedIn.
Update `LINKEDIN_API_VERSION` as provider versions expire.

Official references:
- https://learn.microsoft.com/en-us/linkedin/marketing/community-management/shares/posts-api
- https://learn.microsoft.com/en-us/linkedin/shared/authentication/authorization-code-flow

## Connect X

Use your own X developer app with write access and an OAuth **user-context** token.
An app-only bearer token cannot post on your behalf. Provision the required
`tweet.write`, `tweet.read` and `users.read` scopes through the provider's OAuth
flow. Account/API access and provider charges depend on your current X plan;
this project does not supply free API access.

Save the token and a recognizable account label under Connections → X. Use the
same label when rotating a token for the same account. The connector sends
`POST https://api.x.com/2/tweets` and links later thread posts as replies to the
previous returned post ID. Provider weighted text limits can be stricter than
this prototype's 280-codepoint schema, especially for URLs and non-Latin text;
provider rejections are surfaced rather than truncating content silently.

Official references:
- https://docs.x.com/x-api/posts/create-post
- https://docs.x.com/fundamentals/authentication/oauth-2-0/authorization-code

## Connect email

Connections → Email accepts an operator-allowed SMTP host, port 587 with STARTTLS
or port 465 with TLS, SMTP username, app password and authorized sender address.
Use your provider's supported credentials; some organizations disable SMTP
password authentication and require a provider-specific OAuth adapter that this
prototype does not implement.

Allow additional hosts explicitly through `SMTP_ALLOWED_HOSTS`. Arbitrary/private
SMTP targets are blocked. The server verifies TLS and authenticates before sending.
At submission time, enter exact recipient addresses separated by commas. All
recipients appear in To; Bcc and attachments are not implemented. The message
includes the subject and formatted plain-text body without internal citation links.
SMTP acceptance is not proof of inbox delivery.

## Review and submit

Open a saved LinkedIn, X or email output → **Review & submit**. The preview shows
the exact saved content, destination and (for email) recipients. Then press
**Submit**. Generation, revision and saving connections never send content.

Preview tokens expire after 10 minutes and are bound to the user, saved output,
content/destination and connector version. Changed credentials/recipients require
a fresh preview. Private signed evidence links are not posted externally.

Duplicate requests for identical content/destination are blocked, including most
identical saved revisions. Submission activity records remote post IDs/links and
whether the request was accepted, partially sent or unconfirmed. X thread IDs
are checkpointed after every successful post. If a network failure occurs after
sending, check the destination before taking further action. The app does not
blindly retry an unknown/partial delivery. Exactly-once delivery cannot be
promised across external networks. A process crash during submission can leave a
`sending` record; reconcile it against the provider before changing its status.

## History and deletion

History supports text search, format filtering, selecting outputs, individual
deletion and bulk deletion (up to 100 IDs per API request). Deleting a version
removes that output's stored metadata and file; sibling/parent versions remain.
It does not delete social posts already published or recall sent mail. Submission
receipts and minimal audit records remain for reconciliation.

Unused sources can be deleted from Sources. Sources used by saved outputs cannot
be removed until those outputs are deleted, protecting their citation links.
Raw uploads were already removed after ingestion; stored canonical text and
Qdrant evidence are deleted when the source is removed. File cleanup failures
are reported rather than claimed successful. Backups require their own retention
policy; workspace deletion is not forensic secure erasure.

## Security scope

This is a local-first prototype for the problem statement, **not an NTRO-certified
system or an approved environment for classified material**. The current account
model provides tenant isolation, not organizational RBAC; `admin` is only a
username. Host disk/database encryption, parser sandboxing, centrally managed
secrets, reviewed egress policy, HTTPS and operational controls remain deployment
work. See `SECURITY.md` for controls and limitations. Run on loopback by default.
