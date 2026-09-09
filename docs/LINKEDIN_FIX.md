# LinkedIn connection update

This build is manual-social-3. The uploaded archive already used manual social credentials; the reported OAuth error indicates a different running build or stale frontend.

Stop the server, copy the contents of this project folder over C:\ntro5 (especially app and frontend), then restart from C:\ntro5. Preserve your .env, .venv and data. No new models or environment are needed.

Run: python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload --no-access-log

Open /api/health and confirm build is manual-social-3, then refresh the dashboard. Connections shows the build label. LinkedIn and X use Enter credentials. Old authenticated social connect URLs now lead to the manual form after signing in again. Google email OAuth remains separate.

Enter a provider-issued user access token, not your account password. LinkedIn also needs an author URN. Saving encrypts credentials locally; publishing still requires valid provider permissions and explicit approval.
