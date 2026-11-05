# AI Shorts handover — 30 October 2026

This is a local Windows release candidate. Live Google connection and YouTube upload are not verified. Nothing was deployed publicly or uploaded to YouTube.

## Start the existing installation

In two PowerShell terminals from the project folder:

```powershell
./start-backend.ps1
```

```powershell
./start-frontend.ps1
```

Open http://127.0.0.1:5173. The API uses port 8000. Keep both terminals open. Startup scripts force uploads and scheduling off. Demo seeding is off. Do not run multiple backend workers against this local in-process pipeline.

The production frontend build is in `frontend/dist`. Rebuild with `npm.cmd run build` in `frontend`. This build is a local artifact, not a public deployment.

## Install on another Windows computer

Use Python 3.14 and Node 24 for the environment closest to the verified workstation. Install FFmpeg/FFprobe, including libx264 and libass. Create `.venv`, install `backend/requirements.txt`, run `npm.cmd ci` inside `frontend`, and copy `backend/.env.example` to `backend/.env`. Never overwrite an existing configured `.env`.

From the extracted package root, using PowerShell:

```powershell
python -m venv .venv
./.venv/Scripts/python.exe -m pip install -r backend/requirements.txt
if (!(Test-Path backend/.env)) { Copy-Item backend/.env.example backend/.env }
Push-Location frontend
npm.cmd ci
npm.cmd run build
Pop-Location
```

Then configure your local keys/voice, bootstrap the first Owner if this is a fresh installation, and use the two startup commands above. No accounts, databases, backups, private pilot or OAuth credentials are distributed in the archive. For Google setup, follow [GOOGLE_OAUTH_SETUP.md](GOOGLE_OAUTH_SETUP.md). See [RELEASE_VERIFICATION.md](RELEASE_VERIFICATION.md) for the final results and [RELEASE_TEST_FAILURES.md](RELEASE_TEST_FAILURES.md) for the remaining full-suite failures.

Set the backend Gemini key/model, media location and matching frontend origin. Title research requires Gemini and accessible independent factual sources; no development evidence fallback is used. Narration requires an installed compatible system voice or the existing configured Kokoro runtime/model. The verified English configuration uses Kokoro `bm_george`; its external model/runtime files are not bundled. Urdu narration is unavailable on this workstation and is outside the handover flow.

For a fresh empty installation only, bootstrap an Owner from the backend directory:

```powershell
$env:PYTHONPATH='.'
../.venv/Scripts/python.exe tools/setup_owner.py --email YOUR_EMAIL --name 'Platform Owner'
```

The command prompts for a password and does not create demo data. Existing Owners can reset their own password locally with the same command and `--reset-password`. Web registration always creates a Member. Existing accounts, passwords and API keys have been preserved.

## Member guide

1. Sign in. Connect your own channel under **My Channels** through official Google OAuth. Check its returned name, channel ID and connection status.
2. In **Media Library**, create a personal collection. Confirm reuse rights, then use **Import Folder** or **Upload Images**. These upload selected files once; there is no folder synchronization. Review and correct descriptions/tags, then approve suitable images.
3. Under **Create Short**, enter a title, choose English and a configured narrator. Choose Local Library, Online Sources or Mixed. Select your collection. Mixed online fallback requires explicit consent.
4. Review retrieved research, claim support, any revised scope, and narration. Save edits before rendering. Local images never serve as factual evidence.
5. Select/replace scene images, exclude unsuitable ones, move images earlier, or lock selections. Confirmed tags guide matching; missing suitable media stops generation instead of silently substituting unrelated people.
6. Render, preview, listen, and download the MP4 and credit/source exports. Render failures preserve drafts and earlier renders.
7. For a completed title draft, choose your destination channel and metadata, then **Review rendered video for approval**. This creates an ordinary video job using the existing approval system.
8. Approve the rendered revision. **Upload Privately to YouTube** is a separate explicit action. Choose the audience setting yourself. The backend always sends `privacyStatus=private`; scheduling/Public/Unlisted requests are rejected.
9. After the returned ID is verified, open YouTube Studio. Publish or schedule manually there. This is a Private video, not a native Studio draft. Private upload still sends the video to YouTube and does not hide/change the uploader's IP.

If upload is unavailable, download the MP4, copy the displayed title/description, and upload manually in YouTube Studio. Do not blindly retry an uncertain upload; reconcile its video ID first. Export files remain available after upload failure.

## Admin guide

Owners can promote multiple existing Members to Admin and demote Admins. Admins manage account activation and invitations/member creation. Only an Owner can grant administrator delegation. Ordinary Admins cannot change Owners or appoint other Admins. Last active Owner protection is enforced in the backend. The Admin Panel includes account audit history and excludes passwords, OAuth credentials and private video content.

Role and activation changes are checked from the database on existing authenticated sessions. Admin status does not confer another member's channel credentials or private file access. Admins can also use their own member workflow.

Existing channel approval policies are retained. If a legacy channel uses Owner-only approval, its owning member can select **Configure → My approval**. Ownership assignments and historical approval rows were not automatically rewritten.

## External setup required before a real-channel test

The actual backend has a Gemini key and working English narrator/FFmpeg. Both `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET` are absent, and there are zero stored OAuth channel credentials.

Create a Google Cloud OAuth Web application, enable YouTube Data API v3, configure its consent screen/test users, and register the exact redirect URI `http://127.0.0.1:8000/api/youtube/callback`. Put the client ID/secret in the backend `.env`; never in frontend files. The release requests YouTube read/upload scopes. Production consent verification and account restrictions depend on the Google project. Keep the signing secret and token encryption configuration stable across restarts.

Uploads remain disabled. A later authorized real-upload test requires explicitly enabling the backend upload flag for that supervised run and starting Uvicorn without the safe startup script overriding it. Scheduling can remain disabled because an explicit upload click now dispatches its worker directly. Do not enable uploads merely to demonstrate the UI.

Official requirements checked on 30 October 2026:

- [OAuth web-server setup](https://developers.google.com/youtube/v3/guides/auth/server-side-web-apps): official OAuth, redirect URI matching, backend client secret storage.
- [Google testing audience restrictions](https://support.google.com/cloud/answer/15549945): Testing projects are limited to configured test users; relevant authorizations/refresh tokens expire after seven days.
- [Current videos.insert reference](https://developers.google.com/youtube/data/reference/rest/v3/videos/insert): explicitly set Private because omitted visibility can default to Public. The current page states that unverified API projects are not restricted to Private and describes an upload quota bucket of 100 calls/day. Do not rely on older claims of automatic Private locking; check the project's actual Cloud Console quota and API responses.
- [Resumable uploads](https://developers.google.com/youtube/data/guides/using_resumable_upload_protocol): the existing worker uses resumable requests and persisted upload state. Interrupted uncertain outcomes require reconciliation before a new upload; automatic cross-restart resumption is not claimed.

## Recovery and verification

Before cleanup a recoverable database/config backup was made at `backend/backups/handover-20261030T044449718843`. It contains secrets: keep it local and exclude it from any shared release. `HANDOVER_CLEANUP.json` records exact affected IDs and preserved counts. No generated media files were deleted. Restore only while the backend is stopped, retaining the matching `.env` and signing secret.

The additive database migration is `0015_private_members`; it was applied successfully. Existing legacy Editor/Viewer roles map to Member; existing Owners stay Owners. No existing user was promoted to Admin automatically.

Final checkpoint verification: the three correction tests passed (3 passed, 9 deselected). The release-critical tests passed together (99 passed, 1 warning). The full backend suite finished with 371 passed, 71 failed, 6 errors and 1 warning. These are distinct runs, not added counts. Exact failures are listed in RELEASE_TEST_FAILURES.md. The final frontend production build passed; no frontend test script is configured. A full-suite pass and unconditional release sign-off are not claimed. The archive is produced using the explicit allowlist in `backend/tools/package_release.py`; archive extraction/startup results are recorded in RELEASE_VERIFICATION.md.

The resumed browser smoke check explicitly targeted `http://127.0.0.1:5186` with API at `http://127.0.0.1:8026`, using a copied database and uploads/scheduling/seeding disabled. Both servers returned HTTP 200. Chrome was unavailable to the browser tool and the in-app browser navigation timed out. Browser interaction remains Blocked; API/integration checks passed as described above. Normal startup ports remain 8000/5173.

## Demonstration

Preserved approval-backed pilot: `generated/videos/267bb2ff-06d7-4085-8a10-b2dd1cc7b406/short.mp4`. It is a historical development illustration sample, not proof of a live factual generation or upload. `release/evidence/sample-verification.json` records its hash, streams, complete decode and audio measurements; `release/evidence/sample-scenes.jpg` shows all six scene midpoints and burned-in captions.

Technical result: 30 seconds, 1080×1920 H.264, mono AAC 22050 Hz, complete decode without errors, mean audio -20.4 dB and peak -0.4 dB. Six illustrated scenes/captions were visually inspected. Actual listening review was not performed; the handover operator must listen to the complete file before client demonstration.
