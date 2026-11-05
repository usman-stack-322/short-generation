# AI Shorts Automation Platform

**Title to AI Short:** [workflow and configuration](TITLE_TO_SHORT.md) · [implementation/verification](TITLE_TO_SHORT_IMPLEMENTATION_REPORT.md). Open http://127.0.0.1:5173/title-to-short. [Live English acceptance completed](TITLE_TO_SHORT_LIVE_ACCEPTANCE_REPORT.md) through verified source URLs; no demo generation was substituted.

**Current implementation and evidence:** [IMPLEMENTATION_COMPLETION_REPORT.md](IMPLEMENTATION_COMPLETION_REPORT.md). Start supervised local use with `./start-backend.ps1` and `./start-frontend.ps1`; normal app http://127.0.0.1:5173, API port 8000. Both terminals must remain running. Uploads and daily scheduling are disabled by these scripts. See [DEPLOYMENT_PREPARATION.md](DEPLOYMENT_PREPARATION.md) for recovery and deployment requirements. The older day reports below describe historical states.

**Current Day 2 setup, migrations, implementation, verification, and remaining live checks:** [DAY2_REPORT.md](DAY2_REPORT.md). Publishing is disabled by default.

The sections below retain the original Day 1 baseline. Use the Day 2 report for current OAuth, research, scheduling, publishing, and settings behavior.

## Day 1 baseline

A Windows-first React/Vite + FastAPI + SQLite MVP. All mandatory generation dependencies run locally. Nothing uploads to YouTube.

## Run locally (PowerShell)

From `C:\Users\ua589\short generation`:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r .\backend\requirements.txt
Copy-Item .\backend\.env.example .\backend\.env
Set-Location .\backend
..\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

In a second PowerShell window:

```powershell
Set-Location 'C:\Users\ua589\short generation\frontend'
npm.cmd install
npm.cmd run dev
```

Open http://127.0.0.1:5173. API documentation: http://127.0.0.1:8000/docs.

These commands avoid PowerShell activation and `npm.ps1` execution-policy problems. If the servers are already running, use their existing URLs rather than starting duplicates.

Demo credentials (created on first backend startup):

| Role | Email | Password |
|---|---|---|
| Owner | owner@example.com | DemoOwner123! |
| Editor | editor@example.com | DemoEditor123! |

Owner has workspace-wide access. Editors generate/edit only for assigned channels. Viewers have read-only access to assigned channels. Team administration, channel/personality creation, approval, rejection, and deletion require an owner. Adding a member returns a generated password once; no email invitation is sent.

## Prerequisites and FFmpeg

Use Python 3.10+ and Node 20.19+ (or Node 22.12+). This implementation was tested on Windows with Python 3.14.7 and Node 24.21.0.

```powershell
ffmpeg -version
ffprobe -version
```

If missing, install FFmpeg and reopen the terminal:

```powershell
winget install --id Gyan.FFmpeg --exact
```

Alternatively set full executable paths in `backend/.env`:

```dotenv
FFMPEG_PATH=C:/tools/ffmpeg/bin/ffmpeg.exe
FFPROBE_PATH=C:/tools/ffmpeg/bin/ffprobe.exe
```

The FFmpeg build needs libx264, xfade, zoompan, and libass subtitle support. Rendering uses five original 1080×1920 illustrated slides, zoom/pan, crossfades, AAC narration, estimated phrase subtitles, safe margins, and a Pillow cover. The renderer accepts an optional local background-music path programmatically; a music picker is not exposed in this MVP.

## Configuration

The backend reads `backend/.env` when launched from `backend/`. The root `.env.example` is a reference copy. Never commit keys or `.env` files.

- `GEMINI_API_KEY`: optional Gemini key. Without it, scripts are explicitly labeled development examples.
- `GEMINI_MODEL`: configurable model identifier, default `gemini-flash-latest`.
- `TTS_PROVIDER=local`: free operating-system narration via pyttsx3. Google and ElevenLabs adapters are explicit placeholders; selecting them reports a failed job until implemented.
- `DATABASE_URL`: SQLite by default. SQLAlchemy separates database access from services; PostgreSQL needs its driver and a migration before switching.
- `GENERATED_DIR=../generated`: relative to the backend working directory.
- `FRONTEND_ORIGIN=http://localhost:5173`: both standard localhost development origins are allowed.
- `APP_SECRET_KEY`: optional local signing secret. If blank, a random persistent key is written to ignored `backend/.session_secret`.
- `SEED_DEMO=true`: set false to disable sample accounts on a new installation.

For Gemini, create a key in Google AI Studio and put it only in `backend/.env`. The adapter uses the documented `generateContent` API with `x-goog-api-key` authentication: https://ai.google.dev/api/generate-content. Live Gemini calls were not tested because no key was supplied.

English, Spanish, and French script settings are supported. Local narration requires a matching OS speech voice; unavailable narration produces an explicit silent development WAV fallback and a review warning. No celebrity voice cloning is implemented. The latest acceptance sample used actual Windows narration.

Current Topic is **local demo research, not live news**. Manual topics are unverified angles. Development scripts teach source evaluation rather than inventing events. Demo assets and covers use original generic illustrations, not a celebrity photograph. A rights-cleared personality image provider remains future work.

## Day 1 workflow

1. Log in as owner; open Dashboard.
2. Add a member in Team. Copy the generated sign-in details if needed.
3. Add a manual channel and assign its member.
4. Create Cristiano Ronaldo in Personalities, assigned to that channel.
5. Open Create Short; choose channel, personality, current/manual topic, duration, narrator, language, and style.
6. Generate creates a persisted job and starts the in-process local worker. Review and Queue poll progress.
7. Inspect sources, script, narration provider, warnings, video, cover, and SEO metadata.
8. Edit a script or regenerate all/script/voice/video. Script edits invalidate approval; voice regeneration also rerenders the video.
9. Approve or reject. Approval changes local state only. Upload remains disabled for Day 2.

Stages: researching → script_generation → collecting_assets → voice_generation → rendering → ready_for_review → approved. Scheduling/upload statuses are reserved. Failures persist their error; regeneration increments retry_count. On restart, interrupted in-process jobs are marked failed and can be regenerated. Run a single Uvicorn worker for this local MVP.

Passwords use salted PBKDF2 hashes; sessions are signed and expiring. Media responses use short-lived signed URLs issued through authorized job responses. Such URLs can be shared until expiry. No uploads endpoint is enabled; local image validation enforces root containment, supported types, size, and image decoding. Real OAuth credentials are not collected; `ChannelAuthorization` reserves a reference for a future encrypted credential store.

## Exact source structure

```text
short generation/
├── .env.example
├── .gitignore
├── README.md
├── backend/
│   ├── .env.example
│   ├── requirements.txt
│   ├── pytest.ini
│   ├── e2e.py
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py
│   │   ├── models.py
│   │   ├── schemas.py
│   │   ├── core/{__init__.py,config.py,security.py}
│   │   ├── database/{__init__.py,session.py,seed.py}
│   │   ├── api/{__init__.py,access.py,auth.py,dashboard.py,members.py,channels.py,personalities.py,videos.py,media.py}
│   │   ├── ai/{__init__.py,scripts.py}
│   │   ├── research/{__init__.py,engine.py}
│   │   ├── tts/{__init__.py,providers.py,local_worker.py}
│   │   ├── video/{__init__.py,renderer.py,subtitles.py,cover.py}
│   │   ├── services/{__init__.py,pipeline.py}
│   │   │   └── assets/{__init__.py,providers.py,demo.py}
│   │   └── youtube/__init__.py
│   └── tests/{conftest.py,test_api.py,test_safety.py}
├── frontend/
│   ├── package.json
│   ├── package-lock.json
│   ├── vite.config.js
│   ├── index.html
│   ├── public/cover-placeholder.svg
│   └── src/
│       ├── App.jsx
│       ├── main.jsx
│       ├── styles.css
│       ├── components/{Shell.jsx,UI.jsx}
│       ├── pages/{Login.jsx,Dashboard.jsx,Team.jsx,Channels.jsx,Personalities.jsx,CreateShort.jsx,Videos.jsx,Review.jsx,Settings.jsx}
│       ├── services/api.js
│       ├── layouts/.gitkeep
│       ├── hooks/.gitkeep
│       └── utils/.gitkeep
└── generated/
    ├── audio/
    ├── images/
    ├── videos/
    ├── thumbnails/
    ├── subtitles/
    ├── acceptance-report.json
    └── review-frame.png
```

Runtime files include ignored `backend/ai_shorts.db`, `backend/.session_secret`, `.venv/`, `frontend/node_modules/`, and `frontend/dist/`. The schema contains User, Workspace, WorkspaceMember, Channel, Personality, Topic, VideoJob, Script, SEOData, VoiceGeneration, Asset, Video, Thumbnail, and ChannelAuthorization. Timestamps and foreign keys are enabled. Future schema changes need migrations; `create_all` does not upgrade an old schema.

## Tests and verification

From the project root:

```powershell
Set-Location .\backend
..\.venv\Scripts\python.exe -m pytest -q
..\.venv\Scripts\python.exe -m e2e --keep-approved
Set-Location ..\frontend
npm.cmd run build
```

`pytest`: **17 passed, 0 failed**. A Starlette/httpx TestClient deprecation warning remains; it does not affect the checks. Unit/API tests use an isolated temporary database and media folder.

`e2e`: real login → dashboard → member → channel → Ronaldo personality → research → script → SEO → local narration → five images → FFmpeg → cover/subtitles → queue/review → approval passed. A separate earlier run verified rejection and the silent-audio fallback. The command creates new acceptance data and takes longer than unit tests. It leaves an approved sample; omit `--keep-approved` to also test rejection. Stop a running backend before invoking this in-process acceptance script to avoid its startup recovery interacting with live jobs.

The acceptance report records the real sample path, exact dimensions, duration, provider, and checks. FFprobe confirmed a 30-second 1080×1920 MP4 with audio. A frame was visually inspected. Live HTTP health, login, dashboard, approved review, MP4 byte-range streaming, and Vite serving also passed. Production frontend build passed. No browser was available to perform a visual/click-through UI acceptance test; that verification remains open.

## Remaining for Day 2

- Google OAuth and real YouTube channel authorization.
- Approved upload/scheduling flow, quotas, and resumable upload handling.
- Verified live research, evidence-backed factual generation, and licensed personality photography.
- Real configured Google/ElevenLabs TTS integrations and optional higher-quality local engines.
- Forced subtitle alignment, richer visuals, and a background-music picker.
- Invitation delivery, password change/reset, session revocation, and production auth hardening.
- Database migrations/PostgreSQL, durable background workers, concurrency limits, and deployment hardening.
- Complete visual browser acceptance on desktop and mobile.

## Gemini availability retries

Live Gemini script and SEO requests use at most three primary-model attempts. Temporary HTTP 500/502/503/504 and transport failures wait approximately 2 then 5 seconds, with up to 0.25 seconds of jitter. No delay follows the final attempt. Malformed structured responses get at most one correction retry within the same request budget. Authentication, permission, malformed-request, unsupported-model, and quota errors do not enter availability retries.

`GEMINI_MODEL` remains environment-driven. Optional `GEMINI_FALLBACK_MODEL=` is blank by default. A distinct explicitly configured fallback model receives one attempt only after temporary primary availability exhaustion; the API must accept that model for the account. No replacement model is guessed.

When a key is configured, failed live generation never becomes demo content or derived SEO. The job is failed with a frontend-safe message and can retry its failed step; temporary Gemini failures are marked retryable. Sanitized HTTP/API/model details remain in backend logs. Development responses remain available only when no Gemini key is configured. YouTube uploading is unaffected and remains disabled unless separately configured.


## Multi-language generation

Ten output languages, channel defaults, per-video overrides, RTL subtitles/covers and compatible narrator selection are implemented. See [MULTILANGUAGE.md](MULTILANGUAGE.md) for setup, provider limitations and acceptance evidence. Install the updated backend requirements (including fontTools) before starting.

## Automatic historical fallback

In **Channels → Configure**, enable historical fallback to continue automatic/current-topic generation from latest, 7-day and 14-day news research into separately researched, fully verified historical stories. Optional public reference URLs improve source coverage. Manual topic generation and explicit limited-verification Review Drafts remain separate. No story is invented to fill the queue.

**Prepare daily videos automatically** is a separate opt-in setting using assigned enabled themes, channel language/narrator, duration and daily target. While the backend runs, preparation uses durable channel/UTC-day slots. Existing channels default to both settings off. Preparation never approves or publishes; failed/interrupted jobs retain the existing stage retry controls.

Startup applies additive migrations `0009_auto_evergreen` and `0010_evergreen_references` with the normal SQLite backup. Keep `YOUTUBE_UPLOADS_ENABLED=false`. See [AUTO_EVERGREEN_FALLBACK_REPORT.md](AUTO_EVERGREEN_FALLBACK_REPORT.md) for configuration, tests, browser fixtures, the real offline render and the evidence blocker in live acceptance.


### Automatic real photographs

Set `ASSET_PROVIDER=commons` in `backend/.env` and restart the backend. Wikimedia Commons is queried through its official Action API, without a key. Optional `PEXELS_API_KEY` enables official Pexels contextual stock search after Commons; missing credentials do not disable Commons. Existing `ASSET_PROVIDER=pexels` also uses Commons first. `demo` stays offline and uses explicitly labeled neutral text cards.

The default selection policy accepts real-photo metadata, public domain/CC0 and compatible CC BY licenses. It excludes known synthetic artwork and share-alike/noncommercial/no-derivatives licenses. Identity-specific photos require matching structured depicts metadata and an unambiguous subject identifier; uncertain matches are skipped. Other photos are labeled ?Illustrative image.? Identity photos are labeled ?Archive photo,? never presented as evidence of the reported event. Provider metadata cannot guarantee authenticity; review the sources before approval.

Images retain their aspect ratio on a padded vertical canvas with safe margins. Cached downloads are bounded and validated. Source, photographer, full credit, license/version and modifications are stored per scene. Required credits are included in the review description and retained for export. If credits exceed the description budget, shorten metadata or remove photos; credits are never silently truncated. Pexels attribution links appear in the scene review and description.

On **Review your Short ? Scene photographs**, expand a scene to preview its image, inspect source/license, find a different eligible photo, remove it (use a neutral text card), or upload a photograph with rights/authenticity confirmation. Uploads accept JPEG/PNG/WebP up to 15 MB, at least 400 pixels per side, at most 40 megapixels. Changes invalidate approval and mark the rendered video outdated; choose **Regenerate video**, then review and approve again. No script/Gemini call is made by image edits. A missing photo never upgrades story verification.

Migration `0011_photo_assets` adds asset provenance with an empty default for existing records. Startup applies it non-destructively, using the existing SQLite backup process. Existing assets and references are retained.

Validation and live-provider limitations: [REAL_PHOTO_INTEGRATION_REPORT.md](REAL_PHOTO_INTEGRATION_REPORT.md).


### Diagnose live-photo connectivity in your normal Windows terminal

As of 24 October 2026, [Pexels reports that new API-key issuance is paused](https://help.pexels.com/hc/en-us/articles/900004904026-How-do-I-get-an-API-key). `PEXELS_API_KEY` remains optional and is usable if you already have a valid key. This project does not require acquiring a new Pexels key; Commons remains the no-key primary provider.

Run the read-only diagnostic with the same interpreter/cwd as documented backend startup:

```powershell
cd "C:\Users\ua589\short generation\backend"
..\.venv\Scripts\python.exe tools\photo_acceptance.py
```

It prints only safe configuration status, DNS results for Commons/the image CDN, fixed-host HTTPS results, proxy-presence types (never proxy credentials), an actual Commons API search, and the actual image download URL/bytes/hash if metadata is retrieved. An existing Pexels key is tested privately; absent credentials are reported unconfigured. Results are saved under `generated/photo-network-*/diagnostics.json`. Exit 2 means Commons API diagnostics did not pass. A CDN-root 403/404 establishes transport only, not an image download. This does not change DNS, proxies, TLS, firewall settings, credentials or the database.

Once Commons or an existing optional Pexels connection works, run:

```powershell
..\.venv\Scripts\python.exe tools\photo_acceptance.py --accept --serve-review
```

This requires the prior genuine job in `generated/live-fallback-acceptance/acceptance.db`. It clones that test database to a fresh directory, copies the saved local narrator audio, and calls normal authenticated asset regeneration/render APIs. It does not rerun research/Gemini, use bundled photos or alter the original database/media. Cloud generation is blocked, publishing is disabled, and fresh internet image bytes plus eligible persisted photo metadata are mandatory for the technical pass. If neither provider is reachable, it stops before rendering placeholders.

Success produces `acceptance-result.json`, `selected-photo.jpg`, `rendered-photo-frame.png` and a new MP4 under that fresh directory. Verify that the same correct archival/contextual photograph is visible in the frame/video and its full credit appears in the description. Technical download/render success does **not** automatically mark manual visual acceptance passed.

With `--serve-review`, a successful test serves its isolated API on port 8012. In another normal PowerShell terminal:

```powershell
cd "C:\Users\ua589\short generation\frontend"
$env:VITE_API_URL="http://127.0.0.1:8012"
npm.cmd run dev -- --host 127.0.0.1 --port 5212 --strictPort
```

Use the existing isolated acceptance account defined in `generated/run_live_fallback_acceptance.py` (not a Google password), open its saved job and expand **Scene photographs**. Inspect the authenticated preview, source/license links and replacement controls before declaring live-photo acceptance. These commands leave your existing frontend/backend ports and `.env` settings intact. Ctrl+C stops the isolated processes.

## Media Library and Hybrid Shorts

See [MEDIA_COLLECTIONS_UPGRADE_REPORT.md](MEDIA_COLLECTIONS_UPGRADE_REPORT.md) for implementation, tested evidence and live acceptance limits.

Create a collection in **Media Library**, assign its channel, upload rights-cleared media with creator/license/source information and approve it. In **Create Short**, use **Hybrid** and select the collection; automatic Hybrid preparation also resolves matching approved channel collections. **My Assets** avoids online media search but retains factual verification and labeled text-card fallback. Uploaded and generated audio have separate preview controls. Approved audio can be explicitly shared by an owner into workspace background music.

Owners can save inheritance defaults and editable presets in **Settings / Channel defaults and presets**. Existing channels require Preview changes and explicit confirmation. Review scene edits invalidate the render and approval; regenerate video before approving again. Library removal archives assets for future selection and preserves prior job copies.

Non-destructive migrations run at backend startup. To run them explicitly:

```powershell
cd "C:\Users\ua589\short generation\backend"
..\.venv\Scripts\python.exe -m app.database.migrate
..\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Keep `YOUTUBE_UPLOADS_ENABLED=false`. Live acceptance with real photos requires either five user-supplied rights-cleared subject photos or working Commons DNS/API access. The isolated fixture renders documented in the report are not real-photo acceptance.

## Wikimedia operator identification

Commons metadata, Wikidata identity checks, preflight and image downloads share one identified, serialized transport. In `backend/.env`, set `WIKIMEDIA_OPERATOR_CONTACT` to **your real contact email or public project HTTPS URL**. It is sent publicly as `ShortsEnginePhotoBot/1.0 (your contact)`; never use an API key or copy a placeholder. A real contact already configured in `NETWORK_USER_AGENT` can be reused when the dedicated setting is blank. Restart the backend after changing environment values.

Optional `WIKIMEDIA_CACHE_SECONDS=900` controls successful metadata caching. HTTP 403 preserves the provider message/reference and suppresses automatic repeated requests. Respect Retry-After and any provider denial; do not change IPs/identities or disable TLS to evade it.

```powershell
cd "C:\Users\ua589\short generation\backend"
..\.venv\Scripts\python.exe tools\photo_acceptance.py --live-check
# Only after access succeeds, refresh real licensed photos and serve isolated review:
..\.venv\Scripts\python.exe tools\photo_acceptance.py --accept --serve-review
```

`--live-check` makes a fresh identified siteinfo check (no generation), but honors provider cooldowns. Diagnostics distinguish HTTP access denial, API maxlag, DNS and TLS failures. See [WIKIMEDIA_ACCESS_REPORT.md](WIKIMEDIA_ACCESS_REPORT.md) for actual successful real-photo evidence, the isolated review URL and remaining limitations. YouTube uploads stay disabled.
