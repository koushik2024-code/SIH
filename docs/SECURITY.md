# Security assumptions and controls

This prototype supports local-first processing. It is not NTRO-certified, audited
for classified workloads or ready for unrestricted public exposure. Operators
must control the host, model files, configuration, network and media library.

## Implemented controls

- Generation is restricted to a loopback Ollama address. No public LLM API or
  credentials are required. Model requests disable environment proxies and
  redirects. The local Ollama service itself must be trusted and locally hosted.
- Embeddings, optional reranking, OCR, STT, TTS and video processing run locally.
  Runtime model loading uses local-only files by default. Provisioning scripts
  download weights only when explicitly invoked by an operator.
- Argon2 hashes account passwords. JWT access tokens require `exp`, `iat`, `sub`
  and the `access` type. A random signing key is required before server startup.
- Ownership is checked for sources, assets, route previews and transformations.
  Qdrant search/count/deletion filters include authenticated user and selected
  source IDs. Search payloads are rebound to owned SQLite evidence.
- Signed citations have a distinct `citation` token type, user ID, evidence ID and
  expiry. Citation tokens cannot authenticate normal API operations. Evidence
  lookups enforce the token's user and source ownership.
- SHA-256 records source-byte identity. Audit events record login, ingestion,
  route decisions, output creation/failure, downloads and citation opens. Passwords,
  JWTs and raw source text are not put in these application audit events.
- Source data is untrusted. Prompts establish this boundary; strict schemas and
  citation allowlists reject malformed outputs. The LLM has no tool-execution
  capability. Prompt boundaries alone do not reliably prevent all prompt injection.
- The frontend escapes source and generated strings, uses no remote scripts/fonts,
  and keeps login tokens in memory. CSP blocks inline scripts, frames and objects.
  Responses set `no-store`, `nosniff`, `no-referrer` and frame denial.
- Uploaded bytes are bounded at request and file ingestion layers. Expanded Office
  archive size, extracted text length, PDF pages, image pixel limits and media
  processing time have limits. Raw uploads and intermediate video files are removed
  after processing. Media processing uses argument lists and timeouts, not shell
  interpolation.
- URL ingestion rejects credentials, non-HTTP(S) schemes, unusual ports and any
  DNS answer that is not public/global. Connections are pinned to a validated IP
  with the original Host and TLS server name. Redirects and proxies are disabled;
  responses are streamed with a decoded byte limit and network timeouts.
- Automatic video images use bounded Wikimedia search and raster downloads. Only
  HTTPS Commons metadata/upload hosts are accepted; downloads inherit IP pinning,
  byte limits, no redirects and TLS verification. Pillow validates and re-encodes
  raster images; external HTML is stripped from attribution. Supported license
  metadata is screened and attribution retained; relevance/rights still require review.
- Internal outputs and local-image mode disable image search. Internal status is
  preserved by revisions and blocks publishing. This is a per-output operator
  choice, not organizational classification enforcement. Model keywords cannot
  become local paths; local media symlinks outside the approved directory are ignored.
- Connector secrets are encrypted with per-user Fernet keys derived using HMAC
  from the server secret. They never enter the LLM context, API responses or audit
  details. The server secret must be protected separately from the database.
- Publishing requires a distinct expiring preview token bound to user, asset,
  payload, recipients and connector version. Access/citation/publish tokens are
  not interchangeable. External submission is never triggered by generation/editing.
- Durable request fingerprints block repeated content/destination submissions;
  X thread checkpoints preserve accepted IDs. Unknown/partial outcomes are not
  automatically retried. API endpoint URLs are fixed. SMTP hosts are operator
  allowlisted, public-IP pinned, and use verified TLS; header injection is rejected.
- Edits use owned evidence and create immutable new versions. Deletion validates
  ownership for every requested ID before mutation, checks active sends, confines
  file cleanup to the assets root, and retains minimal publishing receipts/audit.
- Expensive model/media operations have per-process backpressure: one operation
  per user and two globally. This is not a durable job queue or a distributed limit.
- Sign-in has a basic per-IP, per-process throttle (10 requests per minute).
  This is a prototype safeguard, not a distributed rate limiter.

## Citation bearer-link assumption

A signed citation URL is a short-lived capability. Anyone possessing it can view
that one evidence passage until it expires. It does not additionally require an
access token because ordinary clicked links cannot add Authorization headers.
Do not forward citation URLs. Use `--no-access-log` as shown in README and configure
reverse proxies to redact query strings so signed tokens do not enter logs. Browser
history may retain visited URLs. Rotate the signing key to invalidate all tokens;
there is no per-token revocation store. A stricter deployment should require an
interactive authenticated evidence viewer instead of transferable links.

## What verification does not prove

An allowed citation ID proves the referenced chunk exists in the chosen context;
it does not prove that the generated sentence is entailed by that chunk or that
the source is true. The advisory severity check is lexical only. No external fact
checking, claim decomposition, contradiction detection or provenance trust score
is implemented. Operators must review claims, numbers, omissions and permissions
before distributing any output. The system exposes this scope in every result.

## Production measures required

Deploy with HTTPS, a hardened reverse proxy, request deadlines and shared rate
limits. Restrict trusted hosts/origins and configure proxy forwarding explicitly.
Keep model services and Qdrant private; authenticate/protect server-mode Qdrant at
the service/network layer (this prototype has no Qdrant API-key integration).
Restrict outbound connections at the OS/firewall level; `MODELS_LOCAL_ONLY` is not
a network sandbox. URL ingestion intentionally makes public network connections.

Use disk encryption, encrypted database/backups where required, a secrets manager,
OS user isolation, least-privilege access and explicit RBAC. The username `admin`
is just an account name here. Protect and rotate signing keys. Audit logs are
ordinary SQLite rows and are not tamper-evident.

Add malware scanning and OS/container sandboxing for PDF/Office/image/media parsers;
resource limits cannot neutralize parser vulnerabilities, decompression bombs or
all pathological files. A large audio file may be decoded before Whisper reports
its duration. Use worker CPU/RAM quotas and durable asynchronous jobs with
cancellation. FastAPI multipart parsing can consume temporary disk before file
validation; protect host disk and enforce reverse-proxy body limits too.

Maintain approved model checksum and dependency allowlists, inspect model and
media licenses, use a tested lockfile for the target Windows machine, and disallow
unreviewed media sidecars. Model-name collection suffixes are not model checksums.
If local weights change at the same path, explicitly rebuild/version the index.

Define retention, deletion, incident response, recovery and secure backup rules.
Canonical sources, outputs and evidence persist in plaintext SQLite and files by
default; no automatic expiry or source/output encryption exists. The UI supports explicit
selected-output deletion and unused-source deletion; connector secrets are encrypted.
Use one process with embedded Qdrant. A compromised host, operator or signing key
is outside the application's isolation guarantees.
