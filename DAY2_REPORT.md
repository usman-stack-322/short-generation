# Day 2 implementation and verification report

Day 2 extends the existing platform in place. **It is not signed off as fully complete:** real OAuth/Gemini credentials were intentionally not supplied, no browser is connected, and the live Ronaldo run correctly stopped for source verification. No real YouTube upload was performed. Publishing is disabled by default.

## 1. Features implemented

- Official Google OAuth web-server flow with offline access, PKCE, one-use expiring state, browser-bound HttpOnly cookie, and encrypted token storage. Only YouTube read and upload scopes are requested; no Google password or email/profile scope is collected.
- Automatic authenticated YouTube channel discovery, profile/statistics fields, member assignment, connection checks, disconnect, refresh, and revoked-token handling.
- Channel policies `owner_only`, `member_only`, `either`, and `both`. `both` requires two distinct people, including the authorizing member and an owner. Owner-wide visibility is preserved; editors/viewers remain scoped to assigned channels.
- RSS research with configurable public feeds, source/date/summary/credibility metadata, weighted ranking, recent-story similarity checks, stored rejected candidates, and reasons.
- Sensitive claims always require human source review and two credible source domains. Single-source stories are held. Numeric inconsistencies are also held. Domain corroboration is a screening mechanism, not a guarantee of independent reporting or factual truth.
- Gemini structured script and scene hints, bounded malformed-JSON retries, and validated SEO generation. Safe development fallbacks remain available and are blocked from publishing.
- Deterministic 6–12-scene plans with narration coverage, weighted timing, captions, visual queries, and emphasis words.
- Wikimedia Commons and optional Pexels asset adapters with license, creator, source, download URL, and local-file metadata. Missing/unacceptable licenses or long attribution fall back to original local illustrations. No protected photo scraping is used.
- Configurable local, Google Cloud TTS, and ElevenLabs narrator providers. Google supports API key or application credentials. ElevenLabs requires an explicitly configured narrator allowlist. Cloud failure falls back to local speech; development silence is clearly labeled and cannot be uploaded.
- Sentence/word-highlight captions, safe margins, font/position/word-count/highlight settings, scene-aligned zoom/pan/crossfades, optional ducked licensed music, and render command/log artifacts.
- Vertical covers with branding, bounded text fitting, safe placement, and contrast/overflow checks. Face detection is not performed; covers use a lower panel to avoid the central portrait area.
- Recorded approvals tied to content revisions; edit/regeneration invalidates prior approval. Review includes Approve, final-confirmed Approve & Upload, Schedule, scoped regeneration, Reject with note, and interrupted-upload reconciliation.
- Official resumable YouTube upload service, progress/history, explicit privacy and made-for-kids fields, bounded transient retries, channel identity validation, and an atomic approved-revision lock before sending.
- Database-backed upload schedules with IANA timezone/offset validation, cancellation, and a backend scheduler. The browser need not remain open. The backend must run; overdue approved schedules are picked up on restart. This schedules upload start, not a guaranteed publication instant or YouTube-native `publishAt` release.
- Queue tabs/filters; owner/member dashboard data; channel overview/health; configured-status settings; licensed music ingestion; in-app notifications; analytics model and optional sync endpoint.
- Component recovery reuses persisted script, assets, or voice as appropriate. Required downstream work reruns when an upstream component changes.

## 2. Files created/modified

New backend modules:

```text
backend/app/core/{vault.py,network.py,logging.py}
backend/app/api/{youtube.py,publishing.py,research.py,settings.py}
backend/app/youtube/{oauth.py,permissions.py,upload.py}
backend/app/research/live.py
backend/app/services/{preferences.py,scheduler.py,scene_planner.py}
backend/app/services/assets/licensed.py
backend/app/database/migrate.py
backend/migrations/{env.py,day1_schema.py}
backend/migrations/versions/{0001_day1.py,0002_day2.py}
backend/alembic.ini
backend/day2_acceptance.py
backend/probe_research.py
backend/probe_assets.py
backend/tests/test_day2_{oauth,publishing,research,assets_tts}.py
```

Existing backend files extended:

```text
backend/app/{main.py,models.py,schemas.py}
backend/app/core/config.py
backend/app/api/{channels.py,dashboard.py,videos.py}
backend/app/ai/scripts.py
backend/app/tts/{providers.py,local_worker.py}
backend/app/services/pipeline.py
backend/app/services/assets/{providers.py,demo.py}
backend/app/video/{renderer.py,subtitles.py,cover.py}
backend/tests/conftest.py
backend/e2e.py
backend/requirements.txt
backend/.env.example
```

Frontend additions: `components/PublishPanel.jsx`, `ResearchPicker.jsx`, `Notifications.jsx`.

Frontend modifications: `components/Shell.jsx`, `UI.jsx`; `pages/Channels.jsx`, `CreateShort.jsx`, `Dashboard.jsx`, `Review.jsx`, `Settings.jsx`, `Videos.jsx`; `services/api.js`; `styles.css`.

Documentation/configuration: root `.env.example`, `.gitignore`, `README.md`, this report. Generated evidence stays ignored by Git.

## 3. Database migrations performed

- `0001_day1`: frozen baseline; the pre-existing schema was recognized and stamped, not recreated or deleted.
- `0002_day2`: additive Day 2 columns/tables with SQLite batch migrations for foreign keys.
- A consistent SQLite backup was taken before upgrade in `backend/backups/`.
- All **13 existing data tables retained their exact record counts** during migration. `PRAGMA foreign_key_check` passed.
- Evidence: `generated/day2-migration-report.json`. New acceptance data was added only after this comparison.
- Startup now applies migrations, with an explicit CLI also available. Destructive downgrades are intentionally disabled; restore a verified backup with the backend stopped if needed.

## 4. Backend test result

**52 passed, 0 failed** in the complete suite. The original 17 remain passing. New coverage includes OAuth/PKCE/replay protection, discovery, encryption, token refresh/revocation, sensitive-source holds, ranking, duplicates, scene timing, captions, bounded Gemini retries, approval policies, role/workspace restrictions, schedule validation/cancellation, persisted scheduler tasks, official-library upload simulation, upload errors/reconciliation, unsafe media/network rejection, licensed metadata, and cloud-TTS request handling.

One warning remains: Starlette deprecates its httpx-backed TestClient in favor of httpx2. It does not affect runtime or test results. A scheduler test initially encountered queued work from another test; its assertion was corrected to inspect the current task, and the complete suite passed afterward.

## 5. Frontend build and UI acceptance

`npm.cmd run build` passed with no build warnings. Final output is approximately 251 KB JavaScript before gzip.

Live HTTP checks passed for login, dashboard, channels, members, personalities, queue, settings, notifications, music, MP4 range streaming, and Vite serving.

The code includes responsive layouts, loading/errors, progress polling, modal focus trapping/Escape behavior, and explicit publishing confirmation. **Manual browser acceptance is not passed:** browser/app discovery returned no connected surfaces. A rendered video frame was visually inspected, but that is not a substitute for a browser walkthrough.

When a browser is connected, inspect login → dashboard → sidebar → channels → team → personalities → Create Short → queue → review → settings at desktop and mobile widths. Exercise modal focus, errors, source selection, consent redirect, progress, and final confirmation with a test channel. Do not publish a production test.

## 6. OAuth status

Implemented and tested with mocked official-client responses, including discovery and encrypted credential persistence. The configured-status endpoint reports **Not Configured** and Connect returns a meaningful HTTP 503 when credentials are missing. A live Google consent/discovery/refresh flow remains unverified because no credentials were supplied.

Create a Google Cloud project, enable YouTube Data API v3, configure its OAuth consent screen/test users, and create a Web application OAuth client. Register the exact callback below. Each member must connect their own account.

## 7. Gemini status

Implemented, structured, bounded-retry, source-grounded prompt construction, and testable. No key was supplied, so live generation remains unverified. Development scripts remain visibly labeled and are not eligible for YouTube publishing.

## 8. Research status

Live public RSS requests succeeded for BBC Sport, Guardian Football, and Google News RSS. The recorded Ronaldo run produced **98 candidates: 14 held for verification and 84 rejected**, with no automatically verified eligible story. Controversial comments, disciplinary claims, injuries, rumors, low-credibility outlets, stale dates, and missing corroboration are not promoted to factual news.

The UI lets an authorized reviewer open source evidence and confirm review only when at least two credible source domains exist. It cannot override a rejected rumor/low-credibility candidate. Source corroboration and review do not approve upload.

## 9. TTS and assets status

Actual Windows local narration succeeded in the compatibility acceptance video. Cloud request/validation behavior is covered with mocks; Google/ElevenLabs live calls remain unverified without credentials. ElevenLabs is never mandatory and no cloning API is used.

The Commons adapter's live probe failed DNS resolution (`getaddrinfo failed`). No external licensed photograph was downloaded in this run. License filtering is unit-tested, and original illustrations keep rendering functional. Pexels requires an optional API key and was not live-tested. Publication review must still consider likeness/privacy/context rights beyond copyright licensing.

## 10. YouTube upload and thumbnail status

Official resumable upload code passed mocked service tests for success/history and failure handling. **No real upload occurred.** Uploading remains disabled. A job must have current required approval, verified research, real narration, source-grounded content, a valid rendered MP4, an active authorized member, matching OAuth channel identity, and explicit publishing intent.

An interrupted/ambiguous upload is held as `upload_uncertain`. It is never blindly restarted. The reviewer must reconcile a matching channel/title video ID or explicitly confirm absence after checking Studio before another final-confirmed retry.

The app saves a 1080×1920 cover and provides download access. It does **not** claim Shorts thumbnail assignment succeeded or call `thumbnails.set` automatically. Current official guidance describes Shorts cover upload through Studio where supported; account and display-surface behavior can differ:

- https://support.google.com/youtube/answer/72431?hl=en
- https://developers.google.com/youtube/data/reference/rest/v3/thumbnails/set
- https://developers.google.com/youtube/data/guides/uploading_a_video

## 11. Environment variables still required

Put credentials only in `backend/.env`, never frontend code or chat. `.env.example` has placeholders.

For live Google OAuth/channel discovery:

```dotenv
GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=
GOOGLE_REDIRECT_URI=http://127.0.0.1:8000/api/youtube/callback
```

For live Gemini:

```dotenv
GEMINI_API_KEY=
GEMINI_MODEL=gemini-flash-latest
```

For optional cloud narration:

```dotenv
TTS_PROVIDER=local
GOOGLE_TTS_API_KEY=
GOOGLE_APPLICATION_CREDENTIALS=
GOOGLE_TTS_VOICE=en-US-Neural2-D
ELEVENLABS_API_KEY=
ELEVENLABS_VOICE_ID=
ELEVENLABS_ALLOWED_VOICE_IDS=
```

Google TTS can use a key or application-credentials file. ElevenLabs voice IDs must identify authorized generic narrators in the allowlist. Voice speed is normalized by the fixed-duration renderer, so final timing also depends on script length.

Research/assets and scheduling:

```dotenv
RESEARCH_PROVIDER=demo
RESEARCH_MAX_AGE_HOURS=72
RSS_FEEDS=https://feeds.bbci.co.uk/sport/football/rss.xml,https://www.theguardian.com/football/rss,https://news.google.com/rss/search?q=football%20when%3A3d&hl=en-US&gl=US&ceid=US%3Aen
ASSET_PROVIDER=commons
PEXELS_API_KEY=
SCHEDULER_ENABLED=true
YOUTUBE_UPLOADS_ENABLED=false
YOUTUBE_TEST_CHANNEL_IDS=
TOKEN_ENCRYPTION_KEY=
APP_SECRET_KEY=
```

Use Settings → Research → RSS or `RESEARCH_PROVIDER=rss` for live jobs. The default stays demo to preserve Day 1 behavior. The Research button itself explicitly queries real feeds. If enabling publishing later, set `YOUTUBE_UPLOADS_ENABLED=true` and preferably restrict `YOUTUBE_TEST_CHANNEL_IDS` during acceptance. Enabling the worker does not bypass approvals, but it can process previously confirmed pending/due tasks; review/cancel those first.

If `TOKEN_ENCRYPTION_KEY` is blank, a Fernet key is derived from the ignored persistent local signing secret. Keep the secret stable and back it up securely. Changing it without reconnecting invalidates encrypted credentials and sessions. A dedicated configured Fernet key is recommended for deployment.

## 12. Exact Windows commands

From the project root in PowerShell:

```powershell
.\.venv\Scripts\python.exe -m pip install -r .\backend\requirements.txt
if (!(Test-Path .\backend\.env)) { Copy-Item .\backend\.env.example .\backend\.env }
Set-Location .\backend
..\.venv\Scripts\python.exe -m app.database.migrate
..\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Second terminal:

```powershell
Set-Location 'C:\Users\ua589\short generation\frontend'
npm.cmd install
npm.cmd run dev
```

Open http://127.0.0.1:5173. API docs: http://127.0.0.1:8000/docs. Existing demo owner login remains `owner@example.com` / `DemoOwner123!`.

Testing from the project root:

```powershell
Set-Location .\backend
..\.venv\Scripts\python.exe -m pytest -q
Set-Location ..\frontend
npm.cmd run build
```

With the backend stopped (these scripts use an in-process app lifespan/recovery):

```powershell
Set-Location 'C:\Users\ua589\short generation\backend'
..\.venv\Scripts\python.exe -m e2e --keep-approved
..\.venv\Scripts\python.exe -m day2_acceptance
..\.venv\Scripts\python.exe -m probe_research
..\.venv\Scripts\python.exe -m probe_assets
```

These probes add local acceptance records and public-source evidence; they do not perform a real upload. Use one backend worker for the local scheduler. FFmpeg/FFprobe must be on PATH, or configure `FFMPEG_PATH` and `FFPROBE_PATH`.

## 13. Remaining limitations

- Live OAuth, Gemini, cloud TTS, and real YouTube upload need configured credentials and authorized test-channel verification.
- Manual browser acceptance remains open; no connected browser was available.
- A verified current Ronaldo factual-news Short was not generated. The system correctly held current candidates instead of inventing verification.
- Commons network access failed in this environment; Pexels was not configured. Illustrated fallback output is functional.
- Subtitle/scene timing is estimated from narration words and fitted audio, not forced speech alignment.
- Cover checks cover layout/contrast, not face detection or empirical CTR ranking. One selected layout is generated; multiple creative variants are not implemented.
- Local generation is still in-process; schedules are durable, but interrupted generation is marked failed for component retry. Run one local scheduler/worker. Exact scheduled publication time is not guaranteed.
- Source corroboration is conservative heuristic screening with human review for sensitive claims, not comprehensive automated fact-checking. Independent reporting and quotations still need review.
- Daily targets guide preparation/display; automatic daily content production is not enabled. No full auto-publishing setting exists.
- The application is a local MVP, not a production security/deployment sign-off. Dedicated secret management, stronger session lifecycle/rate limiting, durable distributed workers, and broader operational monitoring remain future work.

## 14. End-to-end evidence

**Compatibility generation passed:** owner login → dashboard → member → manual channel → Ronaldo personality → demo research → development script/SEO → actual Windows narration → six original safe illustrations → scene-timed FFmpeg → cover/subtitles → queue/review → recorded local approval.

Output: `generated/videos/267bb2ff-06d7-4085-8a10-b2dd1cc7b406/short.mp4`, 30 seconds, 1080×1920, H.264/AAC. `generated/acceptance-report.json` records the result. The frame `generated/day2-render-frame.png` was visually inspected. This development-copy video is intentionally not publishable.

**Live current-topic run safely blocked:** owner login → test channel/personality → real RSS research → candidate storage/ranking → zero eligible verified topics → `verification_required` → no factual-news script/video generation → upload request blocked HTTP 409. OAuth/Gemini were not configured. No upload was performed.

Evidence files:

```text
generated/day2-acceptance-report.json
generated/day2-research-probe.json
generated/day2-assets-probe.json
generated/day2-migration-report.json
generated/day2-http-report.json
generated/acceptance-report.json
generated/day2-render-frame.png
```

The live run is **not** reported as a completed real researched Short.

## 15. Security checks performed

- OAuth nonce entropy, PKCE, state expiry, single-use atomic consume, browser binding, declined authorization, member activity/role, and callback replay.
- Least-privilege scopes; encrypted access/refresh tokens and resumable URIs; no normal API response contains tokens, client secrets, or passwords.
- Access-log redaction for OAuth callback codes/state and signed media query capabilities.
- Workspace and channel authorization on discovery, generation, review, approval, publishing, schedules, health, settings, notifications, music, and analytics.
- Approval tied to content revision, distinct approvers for `both`, live role/activity rechecks, atomic pre-send revision lock, and active channel-authorizer validation.
- Explicit publishing confirmation, explicit private/unlisted/public setting, explicit made-for-kids choice, default-disabled upload worker, optional test-channel allowlist, and no production test upload.
- One persisted task per job, atomic scheduler claims, bounded official resumable retries, and manual reconciliation for ambiguous outcomes.
- Public HTTPS source validation, private-address blocking, redirect validation, size/time limits, feed entity rejection, license checks, and no arbitrary protected page scraping.
- Safe generated filenames/root containment; image decoding/type/size checks; bounded audio ingestion and FFprobe validation with network protocols disabled.
- Narrow local CORS origins, bearer-auth mutations, HttpOnly OAuth cookie, escaped React output, signed expiring media, and no automatic upload approval bypass.
- Existing PBKDF2 password hashing and expiring signed sessions retained. `.env`, session key, SQLite files/backups, generated artifacts, and dependencies are ignored by Git. No credentials were committed.
