# AI Shorts project audit

**Date:** 23 October 2026 (Asia/Karachi)  
**Overall assessment: PARTIALLY WORKING.** Suitable for supervised local testing, but the current verification, artifact-readiness and duplicate-request behavior prevents calling the complete factual-content workflow reliable.

This is an audit of the current code and fresh executions, not an endorsement of earlier reports. No application fixes were implemented. No existing workspace records were intentionally changed, no credentials were changed, and no live AI generation, deployment, YouTube upload or publishing was performed. New files are this report and temporary audit scripts/evidence under `generated/`.

## 1. What was actually inspected and tested

### Project health

- Searched for repository/ancestor `AGENTS.md` instructions; none were found in the inspected project and ancestor locations.
- Read the application composition, schemas/models, access helpers, authentication, members/channels/personalities/dashboard/video/research/media/publishing routes, research ranking/verification/source registry, Gemini retry/script/SEO code, local/cloud voice adapters, scene/assets/render/subtitle/cover flow, scheduler/recovery, migrations, configuration, frontend routes/forms/review/queue/settings and dependency manifests. Read documentation for context, then checked its claims against code/execution.
- Current runtime: Python **3.14.7**, Node **24.21.0**. FFmpeg and FFprobe are available.
- `backend: ..\.venv\Scripts\python.exe -m pytest -q`: **149 passed, 0 failed**, 63.60 seconds. One existing Starlette/httpx TestClient deprecation warning.
- `frontend: npm.cmd run build`: **passed**, Vite 6.4.5, 1606 modules, no build warnings. The first restricted-shell run failed with esbuild filesystem access denied; the permitted rerun outside that restriction passed. This was an audit execution restriction, not a source build failure.
- `.venv\Scripts\python.exe -m pip check`: **No broken requirements found**.
- `frontend: npm.cmd ls --depth=0`: succeeded; React/React DOM 18.3.1, React Router 6.30.6, Vite 6.4.5 and plugin-react 4.7.0 resolved.
- Existing loopback backend `/api/health` and frontend `/` both returned **200**. These read-only checks did not log into the existing workspace.
- Read the actual SQLite database using `mode=ro`: migration version **0005_workspace_privacy**, matching the single Alembic head; integrity check **ok**, foreign-key violations **0**. Fresh isolated databases also migrated from empty through 0005 successfully. No migration was applied to the existing database during this audit.
- No Git repository metadata was present in the project listing. `.gitignore` covers `.env`, local signing key, databases and normal media folders; historical secret commits cannot be assessed without version history. No secret values were printed.

### Current configuration, values redacted by design

| Item | Observed |
|---|---|
| Gemini key configured | Yes; presence only, validity not live-tested |
| Primary model | `gemini-flash-latest` |
| Fallback model configured | Yes |
| Research | `rss` |
| Assets | `commons` |
| Default narration | `local` |
| Google OAuth configured | No |
| Google TTS configured | No |
| ElevenLabs configured | No |
| Scheduler configured | Enabled; publishing tick exits while uploads are disabled |
| YouTube uploads | **false** |
| Demo seeding | Enabled |

### Isolated API and state probes

Created fresh disposable databases/media directories, an owner, two editors, a viewer and a separate-workspace owner. Background generation was intercepted during permission/duplicate probes. All factual verification fixtures were explicitly synthetic; they are not news reports. No configured Gemini key was used for generation.

- Login/registration, member/channel/personality creation, persistence and cross-workspace authorization were exercised.
- Reciprocal editor ID substitution on channels, videos, themes and logs returned **404**; analytics/action access was similarly denied. A separate-workspace owner also received **404**. Same-workspace owner reads returned **200**. Anonymous protected reads returned **401**.
- Signed media: owning member/owner **200**; another member and another workspace **404**; anonymous **401**. Existing tests additionally cover cookie authentication and bearer identity taking precedence.
- Viewer personality creation returned **403**. Existing tests cover additional viewer mutations and explicit channel assignments.
- Private theme read returned **404** before owner sharing, owner share returned **200**, then the newly authorized member read returned **200**.
- Empty, whitespace-only and one-character personality names returned **422**. Duplicate `Lionel Messi` names returned **201 twice**, producing distinct entries.
- On a verification-held job, script/voice/video/assets/SEO/cover regeneration and approval returned **409**; research retry returned **200**. Existing risk tests exercise the worker stopping before script generation and rejecting manual attempts to override insufficient evidence.
- Identical manual generation requests returned distinct jobs and queued separate workers: verified finding H-03.
- Injected SEO failure was stored as `failed` / `script_generation`; previously committed script data was retained. A second application lifespan preserved the failed job and script. Existing tests also verify interrupted-worker recovery and voice-only checkpoint reuse.
- Synthetic contradictory event matching, stale render approval and demo-provider inconsistency were exercised: findings below.

### Offline generation and output

Attempted a completely new 30-second offline job with a development script, original local illustrations and installed Windows narrator. This exposed M-01: rendering failed because a fresh output root lacked `subtitles/`.

To continue testing downstream stages, created **only that folder in the disposable test fixture**, retained the failure evidence, and retried the render checkpoint. No application fix was made. The resumed job reached `ready_for_review`; FFprobe reported **1080×1920 H.264 video, AAC audio, 30.000000 seconds**. Its authenticated MP4 GET returned **200**. Subtitles and cover were generated in the isolated directory. This is a development-content/render test, not a verified-news or live-Gemini end-to-end pass.

Initial restricted-shell speech attempts encountered Windows SAPI access denial. An unrestricted local voice check found Microsoft David and Zira, and the documented backend-working-directory run generated narration successfully. Speech availability outside this tested Windows environment remains machine-dependent.

### Fresh browser audit

No browser was connected through the browser connector. Used a new headless Edge profile and separate loopback frontend/backend against an audit-only database; did not reuse the prior screenshot results.

- **17 fresh checkpoints passed**: owner dashboard, channels, team, personalities, settings, Create Short; two members' dashboards/channels/queues; held review; ready review; desktop and 390px mobile views. These checkpoints are layout/access observations, not 17 complete generation runs.
- Inspected newly captured desktop/mobile screenshots. No horizontal page overflow was detected at the tested widths. Held review showed the real fixture topic, compact empty state, disabled downstream regeneration and research retry; language name/locale were separate. Owner/member navigation and member-only channel isolation matched the tested permissions.
- Created `Lionel Messi` and `LeBron James` through the inline modal and observed automatic selection. On a later login/page load, searched `LeBron` and found the persisted entry.
- Submitted the actual login form successfully. A ready fixture MP4 loaded and **played**: 1080×1920, playback advanced beyond two seconds, no media error. This browser fixture used a copied existing local MP4; the separate offline test above produced a fresh MP4.
- Clicked **Download MP4** and observed a real export-control defect, M-02.
- The complete risk-detail panel with every live-source variation, all languages, every breakpoint and prolonged playback were not exhaustively exercised. Browser fixtures used synthetic review data, not current external news.

Evidence: [API/render results](generated/audit-20261023/api-results.json), [state probes](generated/audit-20261023/state-results.json), [browser checkpoint list](generated/audit-20261023/browser-fresh/report.json), [login/search/playback/download results](generated/audit-20261023/browser-followup.json). PNG screenshots are beside the browser checkpoint list. Audit scripts are `generated/audit_probe.py`, `audit_state_probe.py`, `audit_browser.py`, and `audit_browser_followup.py`.

## 2. Findings — verified bugs and gaps

No Critical finding was verified. This does not establish the absence of Critical vulnerabilities.

### H-01 — High: an outdated MP4 can regain ready/approved status after a script edit

**Files/endpoints:** `backend/app/api/videos.py:178` (script editing), `backend/app/services/pipeline.py:257` and `:276`, `backend/app/youtube/permissions.py:approve`; PATCH `/api/videos/{id}/script`, POST `/{id}/regenerate`, POST `/{id}/approve`.

**Reproduction:** Start with a rendered isolated job. Edit its script; the endpoint correctly marks its video `outdated`. Request regeneration with `scope=cover`. The worker skips the MP4 render because a video already exists, then unconditionally sets the video/job ready. Approve the job.

**Expected:** Readiness/approval must remain blocked until narration and MP4 correspond to the edited script's current revision.

**Actual:** Edit **200**, cover regeneration **200**, job `ready_for_review`, MP4 SHA-256 unchanged, approval **200**. Repeated with a synthetic `verified` topic fixture and external AI/TTS calls forbidden; same result. No upload was attempted.

**Recommended fix:** Track artifact input/content revisions and validate them before readiness, approval and publishing. Cover/SEO-only work must not clear stale narration/video state. Add regression tests for editing followed by every partial-regeneration scope.

### H-02 — High: similar reporting can be falsely treated as corroboration of the same event

**Files:** `backend/app/research/live.py:78`, especially peer selection at `:106`; `backend/app/research/verification.py:108`.

**Reproduction:** Pass two fresh synthetic credible-source rows to `assess`: “Cristiano Ronaldo wins award at Portugal ceremony” and “Cristiano Ronaldo wins award at Madrid ceremony”, with summaries describing separate recognition events. Use distinct configured BBC/Guardian URLs and different summary wording.

**Expected:** Two distinct events must not verify each other's factual claims. Location/event/award mismatches require separation or a hold.

**Actual:** Both rows returned `verified`, two independent sources, no conflicting claims. Headline similarity establishes the peer set, and the verification logic mainly checks authority/freshness, duplication, differing headline numbers and simple negation. It does not establish that the sources support the same material claim.

**Recommended fix:** Match event identity and claim-level entities/dates/locations/outcomes before counting corroboration; preserve unresolved differences as a hold. Test both contradictory reports and similar but unrelated events. Do not weaken the existing high-risk requirements.

### H-03 — High: repeated general generation requests queue duplicate potentially billable work

**Endpoint/file:** POST `/api/videos/generate`, `backend/app/api/videos.py:23`.

**Reproduction:** Submit the same authorized manual-topic request twice, without `candidate_id`. During the audit, intercept the background worker to avoid any provider charge.

**Expected:** A retry/double-click/replayed request should return the existing job or reject duplicate active intent before provider calls.

**Actual:** Both accepted requests create different jobs and queue separate workers. The candidate-ID path has an atomic candidate claim, but the general request path has no idempotency key or equivalent active-job constraint. A disabled frontend button does not protect multi-tab, retry or direct API submissions.

**Recommended fix:** Add persisted request idempotency and an atomic deduplication policy scoped to workspace/channel/personality/request inputs; define explicit intentional-regeneration semantics. Test concurrent submissions and dropped-response retries. Charge duplication is a risk demonstrated by duplicate queued work; no paid calls were made to measure charges.

### M-01 — Medium: a fresh/custom generated directory fails at subtitle output

**Files:** `backend/app/video/subtitles.py:66–68`, `backend/app/video/renderer.py:render_video`, `backend/app/main.py` output initialization.

**Reproduction:** Point an isolated process at an empty `GENERATED_DIR`, then run a new offline job from the documented backend working directory. Do not pre-create media subdirectories.

**Expected:** The renderer creates its required output directories.

**Actual:** `FileNotFoundError` writing `<generated>/subtitles/<job>.srt`; job correctly becomes `failed` at rendering. The writer creates the ASS parent but not the separate SRT parent. The standard repository's already-present subtitle directory masks this on existing installations. After test-fixture-only folder preparation, checkpoint retry rendered successfully.

**Recommended fix:** Ensure both subtitle parents/output folders exist and add a real renderer test against a completely empty temporary output root.

### M-02 — Medium: Download MP4 navigates away instead of downloading

**Files/endpoints:** `frontend/src/pages/Review.jsx:104`, `frontend/src/services/api.js`, `backend/app/api/media.py` FileResponse.

**Reproduction:** Open a ready review with frontend and API on their standard separate origins/ports. Click **Download MP4**.

**Expected:** Download an MP4 while retaining the review page.

**Actual:** Browser navigated to `/generated/videos/<id>/short.mp4`; review DOM disappeared. Response was **200 video/mp4**, with no `Content-Disposition`. The cross-origin anchor's `download` attribute did not force attachment behavior. Playback and authenticated GET otherwise worked.

**Recommended fix:** Provide an authorized attachment response with a safe filename, or a properly handled authenticated blob download. Preserve media range/auth behavior and test the actual cross-origin button in a browser.

### M-03 — Medium: research picker ignores demo-provider configuration

**Files/endpoints:** `backend/app/api/research.py:29`, `frontend/src/components/ResearchPicker.jsx`; POST `/api/research/candidates`.

**Reproduction:** In an isolated workspace configured for `demo`, invoke the picker endpoint. Replace only the live adapter in the test with a sentinel failure to prevent network access.

**Expected:** Picker and worker honor the same configured provider or clearly state an explicit live-only action.

**Actual:** The live adapter was called once and endpoint returned **422** with the sentinel error. The endpoint always calls `research_live`; normal job execution chooses demo/RSS from preferences. Thus an offline demo can show configured development research while its picker still requires external RSS.

**Recommended fix:** Resolve providers consistently at both entry points, retaining the rule that failed live RSS never silently becomes demo research.

### L-01 — Low: duplicate personality entries are accepted without warning

**Files/endpoints:** `backend/app/api/personalities.py:35`, `frontend/src/components/PersonalityPicker.jsx`, Personality model/schema; POST `/api/personalities`.

**Reproduction:** Create the same `Lionel Messi` name twice for the same member/channel.

**Expected:** Defined duplicate semantics: reuse/prompt/reject an equivalent entry, while permitting intentionally distinct channel/visibility variants.

**Actual:** **201 twice**, separate IDs; no name normalization/duplicate warning. Empty and whitespace names were correctly rejected.

**Recommended fix:** Define a scoped normalized identity policy and provide actionable duplicate feedback; do not impose an indiscriminate workspace-wide name uniqueness rule.

### L-02 — Low: workspace/preview text is hardcoded and can misrepresent selection

**Files:** `frontend/src/components/Shell.jsx:49`, `frontend/src/pages/CreateShort.jsx:125`.

**Reproduction:** Register a workspace with a different name, or select a 30/45-second Short and inspect the preview.

**Expected:** Actual workspace identity and selected duration.

**Actual:** Shell always renders `Demo Workspace`/`Free workspace`; preview always says “in 60 seconds” while its separate duration label can say 45 seconds. The contradictory duration was visible in the fresh screenshot. Non-demo workspace mislabeling is verified from unconditional code, not from changing the existing workspace.

**Recommended fix:** Render persisted workspace identity and selected duration; keep development labels explicit where genuinely applicable.

### L-03 — Low: queue loading and transient errors have misleading states

**File:** `frontend/src/pages/Videos.jsx:10–18` (also review polling error handling).

**Reproduction:** Delay the initial `/api/videos` response; or fail one poll and let the next poll succeed.

**Expected:** Loading feedback until the first response; recovered transient errors clear after successful polling.

**Actual, code-inspected:** Rows start as `[]`, so the initial render displays “No videos match these filters” before loading completes. The success path updates rows but does not clear a previous error. This exact network-fault sequence was not browser-injected; it is a deterministic state-handling issue identified in code.

**Recommended fix:** Separate loading/empty/error states and clear recovered errors appropriately; test slow and interrupted requests.

## 3. Privacy observations and suspected risks — not established broader exploits

- **Private-theme boundary is narrower than the label suggests.** An explicitly channel-assigned member received **404** for another creator's personal theme endpoint but could read that theme's name through an authorized job's `personality_name`. This observation is verified; whether channel sharing intentionally shares the job's theme identity needs a product policy decision. No unauthorized-channel or cross-workspace access was demonstrated. Clarify the boundary and test it consistently rather than claiming total theme invisibility.
- **Concurrent regeneration remains a suspected race.** The endpoint checks current status then changes it; it does not atomically claim a revision before scheduling a worker. Sequential running-job retries are blocked, but simultaneous requests were not stress-tested. A process-local worker lock serializes execution; it does not make request claims durable/idempotent.
- **Generated factual accuracy is not independently validated after generation/editing.** Prompts request source-grounded facts and JSON shape is validated, but there is no demonstrated claim-by-claim entailment validator for model output or manual edits. Human review is still necessary; schema-valid text is not proof of factual accuracy.
- **Sessions are local-MVP strength.** Signed 24-hour bearer tokens live in localStorage. Logout deletes the media cookie/client token but does not revoke an already-copied bearer token. Login has no rate limiting, default demo credentials are displayed and seeded when enabled, and invited “temporary” passwords have no forced-change flow. These are deployment-hardening risks, not a demonstrated remote compromise in this loopback audit.
- **Licensed media needs portable rights checks.** Provider attribution is stored and appended by upload code, but raw MP4 export does not carry a companion attribution manifest. The Commons license filter uses broad string prefixes; commercial/derivative compatibility and all source-specific requirements were not independently verified on a live asset. Local original graphics are an intentional fallback; adapter exceptions are swallowed, reducing diagnosis when all assets fall back.
- **Scale and worker durability are limited.** List/dashboard paths load and serialize many related records without pagination; worker locking is per process and startup recovery assumes a single local worker. No large-workspace load test, multi-worker safety test or abrupt process-kill test was performed. The documented single-worker limitation matters.
- **Research beyond sports needs configuration.** Personalities are generic and arbitrary entries work, but default feeds are football-oriented; adding an NBA/business theme does not by itself provision appropriate feeds or trusted-source metadata. This is a configured-source coverage limitation, not a search-widget failure.
- **Sharing management is incomplete.** Owner sharing assigns a theme to one channel; there is no implemented unshare-to-private endpoint or general theme editing/deletion lifecycle. Do not infer those controls from the working create/share flow.

## 4. Workflow status and previous-claim verification

| Stage/previous claim | Current evidence and classification |
|---|---|
| Login → workspace/dashboard | Working in API and actual browser login. Owner aggregate/team views and member-scoped views observed. Workspace name hardcoding remains. |
| Search/add/select personalities beyond Ronaldo | Working for Messi/LeBron, immediate selection and later search verified. Input validation works; duplicates remain a gap. |
| Private themes/owner sharing | Endpoint policy works in tested cases; linked-job identity caveat above. Owner access is workspace-limited, not global. |
| Channel/theme selection → request | Working for manual demo channels and assigned themes. Real OAuth channel connection is implemented but currently blocked by missing configuration. |
| Research → verification | Modular RSS and risk/independence checks exist and tests pass. Held jobs stop downstream actions. Claim-level false corroboration H-02 prevents treating the label as proof. |
| Live Gemini script/SEO | Environment detection and bounded retry/parser paths verified by code/unit tests, not by a paid/live call. No silent mock switch after configured live errors in tested paths. |
| Scene planning/assets | Implemented. Local illustrations exercised. Commons/Pexels adapter paths inspected and existing tests passed; no new live image collection/rights acceptance test. |
| Voice/render/subtitles/cover | Real local narrator and fresh 30-second output exercised after isolated folder preparation; M-01 blocks a clean custom root. Cloud voices are configurable but not configured/tested live. |
| Review/approval | Browser review/playback works. Held actions reject correctly; stale-output readiness H-01 remains. Approval-only does not upload. |
| Export/download | Authorized MP4 GET and playback work; browser download interaction fails as M-02. No other export package format is implemented. |
| Improved layout/source/language controls | Fresh desktop/mobile screenshots and browser checks support the narrow claim; duplicated verification sections remain, and preview/loading labels have issues. Not an exhaustive accessibility/layout certification. |
| Worker interruption handling | Startup recovery and checkpoint tests pass; failures stay failed and committed script survives restart. Local in-process execution is not a durable distributed job queue. |
| Migration 0005 | Actual database and migration head match; integrity/FKs clean; fresh migrations succeeded. Existing data was not migrated/deleted during audit. |
| 149 tests / 17 browser checkpoints | Both counts independently reproduced. They do not cover the newly demonstrated defects or prove full real-world readiness. |
| YouTube upload disabled | Actual configuration is false; scheduler guard and uploader flag check inspected. No upload/publish action was executed. |

Scheduling, upload history, analytics foundation and OAuth refresh/state logic are present and covered by mocked tests. They are not live-verified services in this audit. Auto-publishing was not enabled. Demo scripts/local illustration fallbacks are intentional development features and were labeled as such in the offline run; they must not be presented as verified current news.

## 5. Blocked and unverified checks

| Check | Status and reason |
|---|---|
| Complete live verified-news → Gemini → real assets → render chain | **BLOCKED** for full acceptance: no paid/external generation permitted in this audit. Offline and mocked stages do not substitute for a live pass. |
| Live Gemini primary/fallback/model availability/quota | **BLOCKED** by the no-paid-generation instruction. Key presence is confirmed; no new inference request was sent. Earlier successful reports were not used as current live evidence. |
| Real YouTube OAuth/channel discovery/refresh | **BLOCKED**: Google OAuth credentials are not configured; no real account authorization attempted. State/replay/refresh behavior only tested with mocks. |
| Real uploads, scheduling publication, remote analytics | **BLOCKED** by explicit no-publishing instruction; uploads stay false. No test upload to any channel. |
| Google/ElevenLabs narration | **BLOCKED**: not configured and potential paid calls prohibited. |
| Current RSS availability, particular live factual claims | **UNVERIFIED**: no new external feed/article validation performed. Synthetic adapter/policy tests and source-code inspection establish behavior, not the truth of a current story. |
| Live Commons/Pexels results and all license obligations | **UNVERIFIED**: no new live collection performed; Pexels credentials were not needed for the offline audit. |
| Dependency CVEs and repository secret history | **UNVERIFIED**: dependency resolution checks are not a vulnerability scan; no Git history was available and no remote advisory scan was run. |
| All installed languages, full accessibility, load and long-running recovery | **UNVERIFIED** beyond the specific tests/views described above. |

## 6. Five highest-priority next actions

1. **Bind readiness/approval to current rendered artifact revisions** and prevent cover/SEO work from approving stale narration/video (H-01).
2. **Strengthen event/claim matching before corroboration**, preserving holds on unresolved mismatches (H-02).
3. **Persist atomic generation idempotency** and test concurrent/retried requests without provider charges (H-03).
4. **Make rendering work with a completely empty output root**, then add a real isolated first-run render regression test (M-01).
5. **Repair and browser-test authenticated downloads across frontend/API origins** (M-02).

After those changes are separately authorized and implemented, rerun this audit's negative probes as regression tests, then arrange explicitly authorized live-provider acceptance. No fixes were made as part of this audit.
