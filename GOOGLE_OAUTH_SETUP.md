# Real-channel OAuth setup

No live connection or upload has been verified. The current local configuration has no Google client ID/secret and no saved channel credentials. Never send a client secret or token in chat.

## Configure Google Cloud

1. Open Google Cloud Console and select/create the project you will own for this installation. Under **APIs & Services → Library**, enable **YouTube Data API v3**.
2. Open **Google Auth Platform**. Configure Branding with the app name, support contact and developer contact. Configure the appropriate Audience: External for ordinary Google accounts, or Internal only for your organization's accounts. For initial testing, keep the app in Testing and add the Google account that manages your channel as a test user.
3. Under Data Access, configure the scopes the code actually requests: `https://www.googleapis.com/auth/youtube.readonly` and `https://www.googleapis.com/auth/youtube.upload`. Analytics scope is not requested by this release's connection flow.
4. Under Clients, create an OAuth client of type **Web application**. Register this exact authorized redirect URI: `http://127.0.0.1:8000/api/youtube/callback`. Do not substitute `localhost` for `127.0.0.1` in that URI unless you also change the backend setting and Google's registered URI to match. This backend OAuth flow does not require an authorized JavaScript origin; credentials are handled on the server.
5. Save the client ID and client secret **locally** in `backend/.env`, using `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET`. Set `GOOGLE_REDIRECT_URI=http://127.0.0.1:8000/api/youtube/callback`. Keep this file out of archives/version control. Do not overwrite unrelated keys or existing configuration.
6. Keep `YOUTUBE_UPLOADS_ENABLED=false`, `SCHEDULER_ENABLED=false` and `SEED_DEMO=false`. Start/restart the backend with `./start-backend.ps1` and frontend with `./start-frontend.ps1`. Open `http://127.0.0.1:5173`; sign in as the member who will own the connection. `FRONTEND_ORIGIN` controls the browser origin and post-OAuth redirect; its configured local default is `http://localhost:5173`, and both normal local frontend origins are allowed by CORS.
7. Choose **My Channels → Connect YouTube**. Complete Google's consent/channel selection yourself. The callback discovers channels using the authorized identity, stores encrypted backend credentials, and returns to Channels. A channel already owned by another member is rejected rather than transferred.
8. Confirm the **actual returned channel name and channel ID**, status and Health check. These values cannot be supplied in advance. After you save the configuration locally, tell Codex only that setup is complete; connection verification can then read the returned name/ID without exposing tokens. Do not claim live readiness until this succeeds.
9. For a later authorized upload test, review and approve the rendered revision and verify the destination name/ID. The safe startup script deliberately forces uploads off. Enabling the manual-upload backend flag requires a separately supervised run; do not enable the scheduler. Initiate a live upload yourself using **Upload Privately to YouTube**. The backend explicitly sends Private and never `publishAt`. Processing/private verification may remain pending; inspect Studio rather than retrying an uncertain outcome.

## Relevant backend variables

| Variable | Purpose |
|---|---|
| `GOOGLE_CLIENT_ID` | OAuth Web application client ID |
| `GOOGLE_CLIENT_SECRET` | OAuth secret; backend `.env` only |
| `GOOGLE_REDIRECT_URI` | Exact callback URI above |
| `FRONTEND_ORIGIN` | Browser origin and callback return destination |
| `TOKEN_ENCRYPTION_KEY` | Optional explicit Fernet vault key; otherwise derived from the persistent signing secret |
| `APP_SECRET_KEY` | Signing secret; blank uses persistent backend `.session_secret` |
| `YOUTUBE_UPLOADS_ENABLED` | Operator upload gate, false for handover |
| `YOUTUBE_TEST_CHANNEL_IDS` | Optional comma-separated upload channel allowlist |
| `SCHEDULER_ENABLED` | Keep false; explicit requested uploads have their own worker |

Do not rotate vault/signing keys casually: existing credentials must remain decryptable. The package contains examples, not your keys or database.

## Google restrictions and troubleshooting

- Testing mode is limited to configured test users (up to 100); YouTube-scope authorizations and offline refresh tokens expire after seven days. Production verification depends on the chosen audience and requested scopes. See [Google's audience requirements](https://support.google.com/cloud/answer/15549945).
- `redirect_uri_mismatch`: check the exact URI, port and host on both sides. `access_denied`/test-user errors: check Audience/test users and account policy. No channel returned: select/create an accessible YouTube channel. Revoked/expired credentials: reconnect; never supply a Google password to this app.
- Quota, channel permission, consent verification and processing restrictions are external requirements. No successful live call or quota availability is assumed. See [official YouTube OAuth setup](https://developers.google.com/youtube/v3/guides/auth/server-side-web-apps) and [videos.insert](https://developers.google.com/youtube/data/reference/rest/v3/videos/insert).
- A Private upload still goes to YouTube; it is not a native Studio draft and does not hide or change the uploader's IP. Download MP4 and copy metadata for manual Studio upload if the API is unavailable.
