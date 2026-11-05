# Appearance and connected-channel analytics

Date: 23 October 2026. Existing audit and fix reports were treated as historical evidence; the current implementation and regression tests were inspected. No applicable repository `AGENTS.md` was found.

## Implemented

**Appearance:** Light / Dark / System selector in the app header and sign-in screen. System is the default. A synchronous script applies the preference before React/CSS rendering, follows device changes, synchronizes other tabs, and tolerates denied localStorage access. Shared CSS color tokens preserve the light palette and supply dark surfaces, text, borders and status colors. Native select semantics expose the selected option; keyboard focus remains visible. Existing layouts are retained. The supplied logo gets a light backing in dark mode for legibility; artwork, videos, images, subtitles and exports are not inverted or modified. There is no separate registration screen in the current frontend.

**Analytics:** Sidebar **Analytics** page (`/analytics`) and a compact **Channel performance** panel on the main dashboard. Authorized channel selector, default 28-day period, 7/90-day presets, custom dates, manual refresh, period metrics, daily charts with accessible value tables, and top ten videos. Includes channel videos uploaded outside this application. Titles/thumbnails come from the Data API, not app-job records.

Metrics use YouTube Analytics API reports: views and engaged views remain separate; watch hours are `estimatedMinutesWatched / 60`; aggregate average view duration comes directly from the aggregate report, never an unweighted average of video averages. Subscriber gains/losses are separate. Missing rows/values are not fabricated as zero. UI distinguishes missing OAuth, missing analytics consent, expired connection, loading, provider failure, cached stale data and absent reporting data. An explicitly returned zero remains zero.

Reports use Pacific calendar dates, ending before today, with inclusive ranges up to 366 days. Daily requests fit within one bounded 366-row page; top-video queries intentionally request only the top ten (`sort=-views`, `startIndex=1`, `maxResults=10`), not a complete channel inventory. The latest date shown is the latest returned daily row, not a promise of globally available data. Reports can be delayed and are not advertised as real-time or monetization-eligible public watch hours.

**Security/cache:** Every analytics endpoint checks workspace/channel access, including cache hits. Actual encrypted authorization records and granted scopes determine connection state; manual/demo channels never get synthetic live results. Before a provider refresh, `channels.list(mine=True)` must match the requested saved channel ID. Existing refresh-token handling is reused. Tokens remain encrypted/server-side and are absent from analytics responses. Publishing is independent and stays disabled.

Persistent cache keys include workspace, authorized channel, dates, report version and top-video parameters. Default TTL is 900 seconds; manual/provider attempts are limited to one per 60 seconds for the same report. A persisted five-minute lease deduplicates concurrent refreshes across processes; interrupted leases expire. Transient HTTP 429/5xx errors get at most three attempts with short backoff/jitter; 401/403 are not repeatedly retried. Requests have a transport timeout. Refresh failures retain successful cached data with an explicit error/stale indicator. Cached report metadata older than 30 days is removed on subsequent workspace report access. Disconnect/scope/authorization checks precede cached access. Channel/date sequence guards and abort cleanup prevent late frontend responses overwriting a newer selection; manual refresh retains loaded content.

## Google setup and live verification

**Live connected-channel analytics: NOT VERIFIED / BLOCKED.** A read-only inspection found **zero saved OAuth connections**, Google client credentials **not configured**, and `YOUTUBE_UPLOADS_ENABLED=false`. No real channel data was queried. Mocked results are not a live pass.

1. In the Google Cloud project, enable **YouTube Data API v3** and **YouTube Analytics API**.
2. Configure the OAuth consent screen/test users and a Web application OAuth client. Register the exact callback, normally `http://127.0.0.1:8000/api/youtube/callback`.
3. Set `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `GOOGLE_REDIRECT_URI` in `backend/.env`, and retain a stable `TOKEN_ENCRYPTION_KEY` for encrypted credentials. Keep secrets out of frontend files and chat. Existing vault configuration remains supported; do not rotate its key while stored credentials exist.
4. Restart the backend, then use **Channels → Connect YouTube** or **Analytics → Connect analytics** as the member who owns/authorizes that channel. Owners can inspect authorized workspace channels but cannot replace another member's connection by reconnecting it as their own. Viewers must ask the authorizing member to reconnect.
5. Consent includes existing `youtube.readonly` and `youtube.upload` functionality plus **`https://www.googleapis.com/auth/yt-analytics.readonly`**. No monetary or broad account-management scopes were added. Existing connections retain their publishing/read scope requirements; analytics permission is only required for analytics. Existing accounts need fresh consent to add it.
6. Return to Analytics and refresh. API enablement, consent-screen testing/verification requirements, revoked credentials or quota can still block the real request. Keep uploads disabled throughout read-only acceptance.

Optional cache configuration, added to both `.env.example` files:

```dotenv
ANALYTICS_CACHE_SECONDS=900
ANALYTICS_REFRESH_SECONDS=60
```

Official documentation checked during implementation:

- [Reports query: scopes, dates, identifiers and pagination](https://developers.google.com/youtube/analytics/reference/reports/query)
- [Supported channel report combinations and top-video constraints](https://developers.google.com/youtube/analytics/channel_reports)
- [Metric definitions: minutes, duration, views and engaged views](https://developers.google.com/youtube/analytics/metrics)
- [Pacific reporting dates](https://developers.google.com/youtube/analytics/dimensions)
- [Header-based mapping and metadata refresh requirements](https://developers.google.com/youtube/analytics/data_model)

## Changed files

- `frontend/public/appearance.js` — new prepaint appearance controller.
- `frontend/src/components/AppearanceSelector.jsx` — new accessible selector.
- `frontend/src/components/ChannelAnalytics.jsx` — shared dashboard/detail analytics UI.
- `frontend/src/pages/Analytics.jsx` — detailed page.
- `frontend/index.html`, `frontend/src/App.jsx`, `frontend/src/components/Shell.jsx`, `frontend/src/pages/Login.jsx`, `frontend/src/pages/Dashboard.jsx`, `frontend/src/styles.css`.
- `backend/app/youtube/channel_analytics.py` — provider reports, mapping, date validation, cache/leases and safe errors.
- `backend/app/api/analytics.py` — authorized read-only endpoints.
- `backend/app/youtube/oauth.py` — incremental analytics consent and explicit required-scope handling while preserving old connections.
- `backend/app/models.py`, `backend/app/core/config.py`, `backend/app/main.py`, `backend/app/database/migrate.py`.
- `backend/migrations/versions/0007_channel_analytics.py`.
- `backend/tests/test_channel_analytics.py` — 14 new regression cases including parameterized cases.
- `.env.example`, `backend/.env.example`, this report.
- Browser harness/evidence: `generated/verify_theme_analytics_ui.py`, `generated/theme-analytics-browser/` (disposable databases, JSON results, screenshots). These are labeled test fixtures, not live reports.

## Migration

Non-destructive **0007_channel_analytics**, after **0006_high_fixes**, adds only the channel-period cache table. It does not rewrite existing jobs, approvals, themes, media, OAuth tokens or user records. Migration startup head detection was updated. Existing databases receive the normal pre-upgrade SQLite backup.

Executed the upgrade against an isolated SQLite backup of the actual database: existing users/channels/jobs/personalities row counts unchanged; integrity `ok`; no foreign-key violations. Fresh isolated test databases also migrated through 0007. The normal user database was not upgraded during this pass; backend startup applies the migration, or run it explicitly after stopping the backend:

```powershell
cd 'C:\Users\ua589\short generation\backend'
..\.venv\Scripts\python.exe -m app.database.migrate
..\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Frontend:

```powershell
cd 'C:\Users\ua589\short generation\frontend'
npm.cmd run dev
```

## Executed validation

- Targeted analytics/OAuth tests: **19 passed**, zero failed. Covers mapping/conversion, invalid/reversed/future/oversized dates, missing scopes, disconnection, anonymous/member access, cache range isolation, cache failure/recovery, concurrent request deduplication, quota/availability errors, bounded retry counts, legacy scope compatibility, authenticated-channel mismatch and outside-app video metadata. Existing OAuth refresh/revocation tests pass.
- Final complete backend suite: **179 passed, 0 failed, 0 skipped**, 68.32 seconds. Includes all nine audit-fix regressions, stale/concurrent approval, claim-specific corroboration, generation idempotency, privacy, network-forbidden demo research and the real empty-root offline FFmpeg render.
- One existing Starlette/httpx TestClient deprecation warning remains. No new build warning.
- Final production build: **passed**, Vite 6.4.5, 1610 modules. No build warnings.
- Headless Edge browser acceptance: **43 checkpoints passed**, using separate frontend/API ports **5178/8005**, disposable accounts/database and labeled browser-only analytics fixtures. Real provider generation and uploads are never called. Desktop 1440×1000 and mobile 390×844 screenshots were captured; selected dark desktop/mobile analytics and mobile login screenshots were visually inspected. Details are recorded in `generated/theme-analytics-browser/report.json`.
- Browser checks include previous owner/member/private channel layouts, personality inline creation/selection, held/ready review, theme switching/persistence, device preference changes, storage denial, analytics loading/reconnect, custom date controls, stale channel/date response rejection, retained content after failure and recovery, dark representative pages and login. This is viewport testing, not physical-device certification or a complete screen-reader audit.

Early validation exposed a legacy OAuth test double lacking `granted_scopes`; compatibility handling was corrected before the final passing suite. Browser harness selector quoting and a programmatic-focus assumption were corrected and rerun using real Tab events. Failed harness runs are not counted as acceptance passes.

## Remaining limitations

- Real Google OAuth/Analytics API enablement, live scopes, token refresh against Google and actual channel totals remain unverified until setup/consent. No paid AI, uploads, publishing, deployment or real channel content mutation occurred. `.env` credentials were not changed.
- Reports are channel-wide across supported video formats; this implementation is not a Shorts-only monetization or revenue dashboard. Top videos are limited to ten by design. Metadata unavailable from Google is explicitly labeled.
- Browser coverage is Edge at two viewport sizes; cross-browser, physical mobile and comprehensive accessibility certification remain outside the executed checks.
- Existing local-MVP authentication/worker/session hardening and other suspected audit risks remain separate; this feature does not claim production readiness.
- Ready for a **supervised read-only live analytics acceptance test after Google setup**, with uploads kept disabled. Mocked tests do not substitute for that test.
