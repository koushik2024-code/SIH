# Social sign-in, publishing connections, and video frames

This update retains existing accounts, sources, history, and settings. Keep your `.env`, `.venv`, and `data` directory. Stop the server and back up the project before replacing application files. Install `requirements.txt`, then restart. New database tables are created automatically.

## One consent flow per provider

- Google: signs in and requests Gmail **send-only** access. After consent, the encrypted Gmail connection is saved automatically. No SMTP host, app password, or manual token entry is needed.
- GitHub: signs in; it cannot authorize Gmail, LinkedIn, or X.
- To retain an existing local account's history, first sign in with that account, then use **Connections → Connect with Google**. This attaches the identity to that account. Starting with social login creates a separate account if the identity has never been linked. Matching email addresses do not silently merge accounts.
- LinkedIn and X are configured after login under **Connections**. Enter a provider-issued user access token with posting permission; LinkedIn also needs the authorized member or organization author URN. Credentials are encrypted on the server.
- Connections provides connection status, update, and disconnect controls. Other email providers still have the manual SMTP option.
- Each provider must show its own consent page. There is no single authorization that grants access to unrelated providers. Sending still requires destination preview and Submit.

## Operator setup, once

Add these entries to your existing `.env` without replacing unrelated settings:

```dotenv
OAUTH_BASE_URL=http://127.0.0.1:8000
GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=
GITHUB_CLIENT_ID=
GITHUB_CLIENT_SECRET=
```

The values come from apps you register with the providers. Never use your account password in these fields. Keep secrets only on the backend. Buttons stay disabled until their provider is configured. Use exactly the configured origin in your browser; do not switch between localhost and 127.0.0.1. Hosted installations require HTTPS.

| Provider | Register this exact callback for the default local origin |
|---|---|
| Google | `http://127.0.0.1:8000/api/auth/oauth/google/callback` |
| GitHub | `http://127.0.0.1:8000/api/auth/oauth/github/callback` |

Google: create a Web application OAuth client, configure the consent screen and test users, enable the Gmail API, and add `openid`, `profile`, `email`, and `https://www.googleapis.com/auth/gmail.send`. External/public deployment may require Google's verification process. Testing-mode authorizations can expire; reconnect when requested.

GitHub: register an OAuth App. It requests `read:user`; no repository access is requested.

LinkedIn and X: create provider developer applications and obtain user-context access tokens with posting permission. Enter those tokens only after login under **Connections**. LinkedIn also requires the authorized author URN. App-only bearer tokens cannot publish as a user.

Official references:
- https://developers.google.com/identity/openid-connect/openid-connect
- https://developers.google.com/workspace/gmail/api/auth/scopes
- https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.messages/send
- https://docs.github.com/apps/oauth-apps/building-oauth-apps/authorizing-oauth-apps
- https://learn.microsoft.com/en-us/linkedin/consumer/integrations/self-serve/share-on-linkedin

## Security and renewal

Authorization state is short-lived, browser-bound, provider-bound, and single-use. Google/GitHub use PKCE. Authorization codes are exchanged by the backend. Provider access and refresh tokens are encrypted per user and never returned to JavaScript. A single-use HttpOnly cookie hands the application session back to the browser; access tokens are kept in browser memory. Existing output ownership and duplicate-send protections remain in place.

Google access tokens refresh on demand. Expired/revoked authorization requires reconnecting. Replace LinkedIn or X credentials in Connections when they expire. Disconnect removes local publishing credentials; revoke the app at the provider to revoke its authorization there.

Keep SECRET_KEY stable because it encrypts stored connections. If rotating a previously exposed key, reconnect stored providers afterward. Do not copy credentials into support messages.

## Video visuals

Regenerate old videos: existing MP4s are not changed automatically.

- Automatic mode searches Wikimedia, accepts explicitly attributed CC BY and CC BY-SA images, and requests PNG thumbnails for SVG diagrams.
- Shorter keyword searches are attempted if images are unavailable or downloads fail.
- Retrieval and rejection warnings appear under **Image sources & credits**.
- If web/local images are unavailable, a visible illustrated caption card is rendered, with a warning. This is not an AI-generated image or a source diagram.
- **Download scene frames** exports each rendered PNG plus timeline/attribution JSON. These are storyboard frames, one per scene, not all 30 frames per second.
- MP4 encoding explicitly maps the image video stream and narration audio stream.
- Internal outputs do not send keywords to Wikimedia. Use local images for internal content.
- This release retrieves existing images; it does not run an AI image generation model. Search relevance is not guaranteed.

CC BY-SA assets retain their license and `share_alike` marker in the timeline. Review the source license and preserve attribution and applicable share-alike terms when distributing adaptations; a Commons result is not a blanket clearance for every use.

## Run in Windows PowerShell

```powershell
cd C:\ntro_v3
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
notepad .env
python -m scripts.check_setup
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload --no-access-log
```

Open http://127.0.0.1:8000 and press Ctrl+F5.

## Validation limits

Validation: 72 tests passed, plus JavaScript syntax checking. Automated tests exercise OAuth state, callback replay protection, browser binding, encrypted connection creation, explicit linking, SVG thumbnail acceptance, and visible fallback rendering. Existing rendering tests invoke FFmpeg with fixture narration. Real provider consent, token renewal, external posting/email delivery, live Wikimedia retrieval, and Windows Piper synthesis require operator credentials/network and have not been exercised in this environment.
