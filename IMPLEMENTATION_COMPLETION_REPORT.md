# Latest: claim-level script review ready; explicit scope acceptance required — 29 October 2026

See [claim-level scope report](TITLE_TO_SHORT_CLAIM_SCOPE_REPORT.md) and [checkpoint](TITLE_TO_SHORT_CHECKPOINT.md). Real saved draft 83aed818-f7ff-489f-80fc-4573f844d628, revision 10, contains the supported Newton/Clark paraphrase while preserving and disclosing omissions from the original title. Scope acceptance remains unchecked; no MP4 is claimed. Live edits/reload and final factual audit passed. 86 combined regressions, 55 subsequent feature tests, final 20 scope/evidence tests and frontend build passed. Existing pilots preserved; uploads/scheduling disabled.

## Earlier reports retained below

# Latest: automatic research repaired; exact incident needs further evidence — 29 October 2026

See [automatic research report](TITLE_TO_SHORT_AUTOMATIC_RESEARCH_REPORT.md) and [checkpoint](TITLE_TO_SHORT_CHECKPOINT.md). Exact requested title retrieved three real sources automatically; independent corroboration for Gillie and exact headline quotation remain insufficient. No new Short or audio is claimed. 81 combined tests, final 49 feature tests and frontend build passed. Pilot hashes preserved; uploads and scheduling disabled.

## Earlier reports retained below

# Latest: Title to AI Short live English flow verified — 29 October 2026

See [live acceptance report](TITLE_TO_SHORT_LIVE_ACCEPTANCE_REPORT.md) and [checkpoint](TITLE_TO_SHORT_CHECKPOINT.md). Working output and actual research, voice, caption and complete preview/download evidence are available. 68 regressions and frontend build passed. Direct listening remains pending; Urdu/Roman Urdu stop before generation without a compatible narrator. Existing pilots preserved; uploads/scheduling disabled.

## Historical report retained below

# Latest continuation — Title to AI Short (29 October 2026)

Implemented the separate title-to-short draft/review/render workflow. Read [TITLE_TO_SHORT_IMPLEMENTATION_REPORT.md](TITLE_TO_SHORT_IMPLEMENTATION_REPORT.md) and [TITLE_TO_SHORT_CHECKPOINT.md](TITLE_TO_SHORT_CHECKPOINT.md). Final 50 relevant tests and frontend build passed. Live example is blocked at real web research; no successful live MP4 is claimed. Optional search configuration and compatible Urdu narration remain documented requirements. Existing pilots/revisions preserved; uploads and scheduling disabled.

## Prior implementation reports retained below

# AI Shorts implementation completion report

Date: 25 October 2026, Asia/Karachi. This report distinguishes work completed in this continuation from functionality already present. Existing accounts, workspaces, channels, media and historical failures were retained. No Windows network/security settings were changed. No YouTube upload, schedule or publication was performed; uploads remained disabled.

## Prior checkpoint readiness

**Latest outcome:** Three fresh normal-workspace pilots are now rendered and technically/visually verified, with authenticated downloads checked. See **Fresh-generation continuation — 25 October 2026** below for the new job IDs, paths, final 350-test result and remaining browser/audio-alignment limitations. The table immediately below records the earlier checkpoint.

| Area | Decision | Evidence / limit |
|---|---|---|
| Supervised local studio and existing-video review | Locally verified, usable with an operator | Normal UI, backend permissions, downloads and playback verified. Source holds require operator attention. |
| Fresh genuine end-to-end production pilot | Blocked at source verification | Three fresh normal-workflow jobs attempted; zero new MP4s. Do not treat old acceptance videos as fresh pilot output. |
| Unattended generation | Not ready | In-process serialized worker, manual restart retry, no durable external worker leases/monitoring; source discovery needs focused references. |
| Automatic YouTube publishing | Disabled / not ready | OAuth and upload safeguards have local mock coverage; no live OAuth/upload was attempted here. Explicit private test authorization is still required. |

No guessed completion percentage is used. The checklist below records the evidence for each deliverable.

## Implemented changes in this continuation

- `frontend/src/styles.css`: 248px desktop sidebar, readable queue text, responsive cards/forms, wrapping titles, larger controls, theme-aware secondary buttons, corrected checkbox sizing, library cards and shared review surfaces.
- `frontend/src/components/Shell.jsx`: named navigation links for the tablet icon rail and Escape dismissal for mobile navigation; logo and theme selector preserved.
- `frontend/src/pages/Dashboard.jsx` and `backend/app/api/dashboard.py`: live polling and a real permission-scoped processing count alongside ready, attention and scheduled totals.
- `frontend/src/pages/Videos.jsx`: language and stage, status-specific recovery/research/review actions, technical error details, explicit reversible test classification, timezone labels and filter recovery. All records appear by default. Classification is never inferred from names.
- `backend/app/api/videos.py`: authenticated classification endpoint; validates a real boolean and existing workspace/channel edit permissions. It changes only an operator label, leaving content revision and output intact.
- `frontend/src/pages/CreateShort.jsx`: explicit initialization and no-channel guidance; existing real generation and idempotent submission reused.
- `frontend/src/pages/MediaLibrary.jsx`: loading/error recovery and retry control; existing upload, assignment and review actions retained.
- `frontend/src/pages/Review.jsx`: saved-video failure explanation and read-only refresh action. Existing polling, revision-bound approval and edit endpoints retained.
- `frontend/src/components/UI.jsx`: understandable error notices with expandable technical details.
- `frontend/src/components/ScenePhotos.jsx`, `backend/app/services/pipeline.py`: actual photo/clip/card counts; legacy original illustrations and text cards are not reported as photographs. Existing source, author, license, archival labels and manual controls retained.
- `backend/app/services/assets/licensed.py`: restored the tested safe photo-padding color; preserved the failing pixel assertion.
- `backend/tests/test_daily_preparation_concurrency.py`: strengthened the multi-channel simultaneous-trigger assertion to require exactly the fixture plus two daily jobs on the first channel.
- `backend/tests/test_studio_completion.py`: explicit label/revision behavior, processing count, legacy card classification, and saved-stage retry regressions.
- `backend/tools/pilot_completion.py`, `backend/tools/verify_completion.py`: normal API pilot and read-only artifact evidence helpers, separate from isolated test fixtures.
- `start-backend.ps1`, `start-frontend.ps1`, `DEPLOYMENT_PREPARATION.md`, `compose.yaml`, backend/frontend Dockerfiles, Docker ignore files and `frontend/nginx.conf`: fixed normal ports, one worker, uploads/scheduler off, deployment preparation only. Container execution was not validated.

There is no Git repository in this checkout, so a trustworthy before/after Git diff is unavailable. Existing files were edited in place; no reset or checkout was used.

## Backend validation

Run commands from `C:\Users\ua589\short generation\backend` using `..\.venv\Scripts\python.exe`.

| Command / evidence | Passed | Failed | Skipped | Errors |
|---|---:|---:|---:|---:|
| `-m pytest tests/test_daily_preparation_concurrency.py tests/test_remaining_fixes.py tests/test_high_fixes.py -q --junitxml=../generated/implementation-affected-results.xml` | 21 | 0 | 0 | 0 |
| First full suite, `implementation-full-results.xml` | 337 | 1 | 0 | 0 |
| Overlapping diagnostic full suite, `implementation-suite-results.xml`, same pre-fix source | 337 | 1 | 0 | 0 |
| `-m pytest tests/test_daily_preparation_concurrency.py tests/test_real_photos.py -q --junitxml=../generated/implementation-corrections-results.xml` | 36 | 0 | 0 | 0 |
| Full suite after initial Studio regressions, `implementation-final-results.xml` | 340 | 0 | 0 | 0 |
| Full suite including legacy card regression, `implementation-final-verified-results.xml` | 341 | 0 | 0 | 0 |

Final checkpoint and full-suite results are appended below after execution. The one known warning is Starlette's deprecation warning for its httpx TestClient integration. Python commands initially stalled under the execution sandbox; successful runs used the functioning approved runtime outside that sandbox. Stalled invocations were not counted as passing tests.

The initial full-suite failure was `test_download_safe_cached_padded_and_credited`: expected safe-border RGB (23,25,43), observed maximum delta 11. The renderer canvas was restored to that intended color; the assertion and tolerance were not relaxed. The overlapping diagnostic run was started while diagnosing delayed output, not used as a green-only rerun.

### pytest.ini, conftest.py and existing tests

`backend/pytest.ini` and `backend/tests/conftest.py` were already modified when this continuation began and were not changed here. Without a Git baseline, their earlier exact delta cannot be reconstructed. Current pytest settings use backend import path, tests directory, project generated cache and an e2e marker; no failures are filtered out. Current conftest creates a unique temporary database/media root per test session, turns scheduling/uploads off, clears the Gemini key and uses demo providers. It sets a session-local pytest basetemp and cleans up at exit. The publishable fixture disables its automatic channel on teardown. These protect normal data and keep independent tests from leaving active daily-preparation channels. Existing assertions were retained; the multi-channel job-count assertion was strengthened.

### Concurrency and recovery evidence

The full suite includes the original broader preparation module, not only the single-channel recheck. Four threads synchronize on a barrier and call preparation simultaneously. The multi-channel case requires exactly two new first-channel jobs and one second-channel job, with exactly three worker dispatches. The single-slot case requires one new job, one durable GenerationRequest and one dispatch. Other cases cover channel isolation, timezone day boundaries and retained claims after interrupted-worker recovery. Six concurrent ordinary generation requests must return the same durable job ID; concurrent regeneration is also covered.

The existing implementation already reset retry jobs to a legal active state before dispatch and retained generation identities durably. Historical `failed -> creating_cover` and `failed -> collecting_assets` messages remain in old records; they were not erased or hidden. Saved-stage retry tests exercise the API and pipeline rather than merely modifying those records. Single-process behavior is verified; this is not a claim of distributed-worker safety.

## Frontend and normal review evidence

`cd frontend; npm.cmd run build` passes. No standalone frontend test/lint script is configured. Browser checks use the real normal application at http://127.0.0.1:5173 and backend port 8000. Screenshots for Dashboard, Create Short, Video Queue, Channels, Review and Media Library exist at 1440, 1024, 768 and 360px in `generated/implementation-screenshots/`. `generated/implementation-layout-checks.json` records all 24 document-width checks; none exceed the viewport. Long tables deliberately scroll within their table containers.

Additional screenshots cover dark mobile queue, dark desktop review, empty filtered queue and backend-offline queue. Loading was observed during real requests. Empty filtering can be recovered with Clear filters. Offline polling retains loaded jobs, displays a readable failure and technical details, and recovers when the backend returns. Mobile navigation and keyboard video playback were exercised. Backend permissions, media authorization, edit approval invalidation, cancellation, mocked upload locking and recovery are covered in the full backend suite; not every destructive edit was repeated against user records.

The existing review Short `5cadcccf-a369-4fc3-bc8b-004ebdd8188c` loaded with readyState 4 at 1080x1920, 30 seconds. Keyboard playback advanced to 3.495 seconds; evidence: `generated/implementation-browser-playback.json`. The native Download MP4 action completed. The normal API helper fetched all six existing MP4s with HTTP 200 and attachment headers. Before/after job counts and statuses matched: opening and downloading did not generate anything. These are existing development/acceptance outputs, not genuine fresh pilot videos. Standalone narration duration can differ from the output because rendering fits full narration to the target duration.

Normal review links require an authorized signed-in account. Signed media URLs are intentionally short-lived; use the stable review URLs below to obtain fresh links.

## Fresh live-provider pilot

`..\.venv\Scripts\python.exe tools/pilot_completion.py` created one new normal workspace channel, Supervised Pilot October 2026, with automatic scheduling disabled, and three genuine subject personalities. Each requested a fresh 30-second English Short with local narration and automatic historical fallback. This used the signed-in owner's ordinary authenticated API and normal database, not a cloned acceptance database. No keys or tokens were written to evidence files. Configured Gemini and Wikimedia operator contact were present locally; the contact was not requested again or printed.

| Subject | Normal review URL | Outcome |
|---|---|---|
| Cristiano Ronaldo | http://127.0.0.1:5173/videos/d10771ad-506f-4931-9e96-367908145336 | Verification hold |
| Lionel Messi | http://127.0.0.1:5173/videos/d8706d5b-9add-4481-9567-e5e0685c2799 | Verification hold |
| Thierry Henry | http://127.0.0.1:5173/videos/0eb9a0be-aef2-47d6-a357-a36267f22f9f | Verification hold |

All three reported: “No eligible verified news or historical story found. Review candidate reasons, retry research, or change the personality/theme or research sources.” Live feeds returned candidates, but available evidence did not meet relevance, publisher and independent-source policy. Historical discovery also exhausted its eligible candidates. This is a source-evidence blocker, not a demonstrated missing Gemini key, exhausted paid quota or a verified Commons denial. Narration, subtitles, media relevance, credits and rendering for these fresh jobs could not be inspected because generation correctly stopped before those stages. No fresh MP4 was produced. Do not bypass verification to get a pilot success.

Full sanitized outcomes, research traces, historical access decisions, MP4 paths and ffprobe data are saved in `generated/implementation-normal-workflow.json`. Next step: configure focused reputable historical references for the pilot channel, review candidate reasons and retry research. This continuation did not weaken credibility or independence rules or manufacture source claims. Commons serialized identification/caching/Retry-After logic and truthful language availability behavior remain covered locally; fresh licensed-photo retrieval was not reached by this live pilot.

## Exact next-use instructions

From `C:\Users\ua589\short generation`, run in two terminals:

```powershell
.\start-backend.ps1
```

```powershell
.\start-frontend.ps1
```

Open http://127.0.0.1:5173. If the validation servers are still running, use them instead of starting duplicates. Both processes must remain running; no additional worker exists. Do not run multiple API workers. On an interrupted job, open Queue → Recover job → Retry failed step. The retry resumes suitable saved checkpoints and invalidates affected approval. The scripts disable scheduling and uploads. No temporary review port is required.

Use the existing private backend/.env; backend/.env.example is the secret-free variable template. Deployment preparation, persistent storage requirements, backups and the later explicitly authorized private-upload procedure are in DEPLOYMENT_PREPARATION.md. No external hosting resources were created.

## Evidence checklist

| Deliverable | Verification status |
|---|---|
| Real dashboard counts and refreshed five main workflows | Implemented, locally/browser verified |
| Desktop/mobile, themes, loading/empty/offline behavior | Locally verified, screenshots saved |
| Owner/member/workspace isolation | Locally verified by full backend suite |
| Broad synchronized scheduler scenario and durable identity | Locally verified by full backend suite |
| Recovery, retry, cancellation and approval invalidation | Locally verified; new saved-stage regressions plus existing tests |
| Normal existing review/play/download | Live local app verified, six HTTP 200 MP4 downloads |
| Archival credits and actual media coverage | Implemented and locally verified; no fresh media stage reached |
| Three fresh genuine Shorts | Attempted live; three source-verification holds, zero fresh MP4s |
| OAuth/upload duplicate protection | Existing implementation locally tested with mocks; live upload unverified and disabled |
| Startup/deployment preparation | Files supplied; local startup verified; containers untested |


## Existing normal-app MP4 review URLs and paths

- Review: http://127.0.0.1:5173/videos/5cadcccf-a369-4fc3-bc8b-004ebdd8188c — HTTP 200, 3126367 bytes. MP4: C:\Users\ua589\short generation\generated\videos\5cadcccf-a369-4fc3-bc8b-004ebdd8188c\short.mp4
- Review: http://127.0.0.1:5173/videos/e510e333-9f2c-4ce8-8646-a089a5429395 — HTTP 200, 3204654 bytes. MP4: C:\Users\ua589\short generation\generated\videos\e510e333-9f2c-4ce8-8646-a089a5429395\short.mp4
- Review: http://127.0.0.1:5173/videos/ff926ae3-5797-465d-bdd3-f54bc2c5120a — HTTP 200, 3204654 bytes. MP4: C:\Users\ua589\short generation\generated\videos\ff926ae3-5797-465d-bdd3-f54bc2c5120a\short.mp4
- Review: http://127.0.0.1:5173/videos/ebb10475-7b67-42f1-b54c-935fa7e9ce01 — HTTP 200, 4806739 bytes. MP4: C:\Users\ua589\short generation\generated\videos\ebb10475-7b67-42f1-b54c-935fa7e9ce01\short.mp4
- Review: http://127.0.0.1:5173/videos/267bb2ff-06d7-4085-8a10-b2dd1cc7b406 — HTTP 200, 3168822 bytes. MP4: C:\Users\ua589\short generation\generated\videos\267bb2ff-06d7-4085-8a10-b2dd1cc7b406\short.mp4
- Review: http://127.0.0.1:5173/videos/ecaf80d1-25ce-41ef-9b24-af320b2086da — HTTP 200, 3051360 bytes. MP4: C:\Users\ua589\short generation\generated\videos\ecaf80d1-25ce-41ef-9b24-af320b2086da\short.mp4

Saved-stage and scheduler regression command: `..\.venv\Scripts\python.exe -m pytest tests/test_studio_completion.py tests/test_daily_preparation_concurrency.py -q --junitxml=../generated/implementation-checkpoints-results.xml` — **10 passed, 0 failed, 0 skipped, 0 errors**. Both reported failure stages reached ready_for_review while script/narration provider calls were forbidden and the saved narration bytes were unchanged.


README.md now links this report and the normal startup instructions. Dashboard errors also use expandable details; schedule strings consistently label the device timezone, while daily totals and created-date filtering explicitly use UTC.


## Representative screenshots

Desktop Dashboard:

![Dashboard at 1440px](generated/implementation-screenshots/dashboard-1440.png)

Mobile queue:

![Queue at 360px](generated/implementation-screenshots/queue-360.png)

Dark mobile queue:

![Dark queue](generated/implementation-screenshots/queue-dark-360.png)

Offline recovery:

![Offline queue with retained records](generated/implementation-screenshots/queue-offline-360.png)

Final production frontend build: `cd frontend; npm.cmd run build` — exit 0; Vite 6.4.5, 1615 modules, JavaScript 311.61 kB (91.35 kB gzip), CSS 62.43 kB (15.45 kB gzip). Build includes final queue wrapping, 18px checkboxes, review media recovery, library retry and dashboard details.

## Final delivery validation

From `backend`, exact final command:

```powershell
..\.venv\Scripts\python.exe -m pytest -q --junitxml=../generated/implementation-delivery-results.xml
```

**343 passed, 0 failed, 0 skipped, 0 errors; 1 deprecation warning; 164.36 seconds.** This final run includes the synchronized broader scheduler scenario and both saved-stage retries. Machine-readable evidence: `generated/implementation-delivery-results.xml`. There are no remaining backend test failures in the final tree. Earlier failure counts above remain recorded rather than removed.

The normal backend was restored after the offline check. It runs with scheduler and uploads disabled. The frontend remains at port 5173. The original historical failure records remain visible; successfully testing their recovery logic does not rewrite their history.


## Fresh-generation continuation — 25 October 2026

This section supersedes the earlier fresh-pilot readiness checkpoint above. Earlier tests and attempts remain historical evidence. Expected workspace confirmed at `C:\Users\ua589\short generation`; no `.git` directory and no applicable AGENTS.md found in the project or parent directories. No account, permission, Studio layout, subscription or deployment was changed. The existing supervised pilot channel received direct historical reference URLs; automatic preparation stayed off. Runtime scheduling and YouTube uploads were explicitly disabled.

### Original three holds — database investigation

Read the normal database records and candidate IDs, completion report, AUTO_EVERGREEN_FALLBACK_REPORT.md and RISK_VERIFICATION.md, plus relevant research, pipeline, recovery, media and API code. Full source-level evidence: `generated/pilot-blocker-investigation.json`. These were research verification holds, with no script, narration or render stage reached. Historical fallback did execute; it did not silently fail to run.

| Original job | Historical discovered / attempted / accessible | Exact outcome |
|---|---|---|
| `d10771ad-506f-4931-9e96-367908145336` | 48 / 10 / 0 | Discovered pool exhausted; zero usable articles. Credibility/relevance/corroboration failed. |
| `d8706d5b-9add-4481-9567-e5e0685c2799` | 48 / 9 / 0 | Discovered pool exhausted; zero usable articles. Credibility/relevance/corroboration failed. |
| `0eb9a0be-aef2-47d6-a357-a36267f22f9f` | 48 / 8 / 0 | Discovered pool exhausted; zero usable articles. Credibility/relevance/corroboration failed. |

Original recent-news candidate reasons are retained per job in the evidence JSON: Ronaldo included 113 low-credibility, 12 insufficient-corroboration, and incidental-topic rejections; Messi 104 low-credibility and 5 insufficient-corroboration rejections; Henry 26 low-credibility, 2 insufficient-corroboration and one conflicting-claim rejection. Historical candidates were Google aggregator landing pages or unrecognized publishers. These counts describe saved candidate records, not independent sources. Holds were legitimate for the evidence obtained; they did not establish that the Internet had no suitable story.

### Root causes and corrections

- Discovery relied heavily on Google News landing pages. Added one bounded direct-publisher historical search; direct configured references remain available. Aggregator landing pages now get an actionable explanation. Latest → 7 days → 14 days → historical progression, access cache, article/source/time budgets and independent-source policy remain in force.

- Publisher menu text could exceed the first 1,000-character focus window, rejecting a reachable Sky article. Article extraction now begins at the article heading where available and otherwise prefers readable paragraphs. Originating-wire detection still scans full parsed text, including bylines. Real Sky/Guardian probes confirmed accessible dated Ronaldo claims.

- Historical extraction could select somebody else’s award because the requested subject appeared later as a previous winner. It now rejects an award/result category preceding the configured subject and excludes dated Live related-story cards. Two invalid selections discovered during this run were quarantined with original source evidence and identities saved in `quarantined-pilot-selection.json` and `quarantined-henry-related-card.json`; unused reservations were released. Original topics and pilot job IDs remain preserved.

- Explicit contemporaneous “last night” statements can use a trustworthy publication year, with the date basis and original excerpt recorded. January 1 is rejected to avoid inventing the event year across the boundary. Output retains year precision; internal January 1 storage is not presented as an exact event day. Player/Footballer of the Year wording is recognized as an award under the existing risk policy.

- Grounding incorrectly treated “won” as a new match-result category when paraphrasing “was named Player of the Year.” Award outcome synonyms now normalize while added scored-goal/match-result categories remain blocked. No source corroboration threshold or publisher authority registry was changed.

- Representative frames exposed overlapping text during all-card crossfades. All-text-card timelines now concatenate with clean cuts and exact scene lengths. Ronaldo/Messi were rerendered from saved script, SEO, assets and narration using video-only regeneration. No successful script was regenerated for those renderer fixes.

### Concurrency, checkpoints and approval safety

No new daily-preparation production defect was reproduced. Synchronized multi-channel and same-slot requests still create one durable request per slot. A new four-thread duplicate-delivery regression checks that workers neither overlap nor repeat completed work. Existing restart recovery retains daily identities, marks interrupted jobs explicitly failed, and stage retries preserve committed artifacts. Actual supervised restarts in this run retained all three new job IDs. The worker remains a serialized in-process worker; multi-process/distributed leases are not claimed. Keep the documented one-worker startup.

Revision-bound approval and stale-media checks remain in force and are covered by the suite. All three pilots remain unapproved; no publishing or upload action ran. Research-only retry reaches research_ready before explicit generation.

### Fresh pilot outputs

| New job ID | Topic | Source / fallback type | Verification | Generation status | Photo / clip / card scenes | MP4 path | Playback / download |
|---|---|---|---|---|---|---|---|
| `230904a6-bfc0-4182-b240-c4d498cd99fe` | Cristiano Ronaldo: 2008 Ballon d Or | Verified historical fallback; Sky + Guardian | Verified; 2 independent source group(s) | ready_for_review | 0 / 0 / 6 | `C:\Users\ua589\short generation\generated\videos\230904a6-bfc0-4182-b240-c4d498cd99fe\short.mp4` | Decode + authenticated 200 download/hash verified; HTTP 206 range verified; browser unverified |
| `7f51b5de-a19d-4faf-9318-43dc15ba2b06` | Lionel Messi: 2009 Ballon d Or | Verified historical fallback; UEFA | Single authoritative source; 1 independent source group(s) | ready_for_review | 0 / 0 / 6 | `C:\Users\ua589\short generation\generated\videos\7f51b5de-a19d-4faf-9318-43dc15ba2b06\short.mp4` | Decode + authenticated 200 download/hash verified; HTTP 206 range verified; browser unverified |
| `0f4ddd93-61f6-452d-abfb-b4c6f212f3b2` | Thierry Henry: 2004 PFA Player of the Year | Verified historical fallback; UEFA | Single authoritative source; 1 independent source group(s) | ready_for_review | 0 / 0 / 6 | `C:\Users\ua589\short generation\generated\videos\0f4ddd93-61f6-452d-abfb-b4c6f212f3b2\short.mp4` | Decode + authenticated 200 download/hash verified; HTTP 206 range verified; browser unverified |

Each row is a new job created through the normal authenticated application API in the existing workspace, with a newly rendered MP4. Existing acceptance MP4s do not count. Source claims and verification decisions are in `generated/fresh-verification/results.json`. Ronaldo uses two independent publisher groups under the existing policy; Messi/Henry use the already-configured low-risk authoritative-source rule. That is the system’s source-independence assessment, not proof against undisclosed syndication. Manual editorial approval remains required.

### Measured video and download checks

Full evidence and downloaded copies: `generated/fresh-verification/`. For each completed output, ffprobe, full FFmpeg decoding, volumedetect, blackdetect, authenticated download hash, unauthenticated access rejection, HTTP Range requests, subtitles and seven sampled frames (1/5/10/15/20/26/29 seconds) were inspected.

| Job | Resolution / seconds | Full decode | Audio mean / peak | Black intervals | Download |
|---|---|---|---|---|---|
| `230904a6-bfc0-4182-b240-c4d498cd99fe` | 1080×1920 / 30.000000 | exit 0 | mean_volume: -20.5 dB; max_volume: -0.8 dB | 0 | HTTP 200; SHA-256 matches; anonymous 401 |
| `7f51b5de-a19d-4faf-9318-43dc15ba2b06` | 1080×1920 / 30.000000 | exit 0 | mean_volume: -20.3 dB; max_volume: -0.9 dB | 0 | HTTP 200; SHA-256 matches; anonymous 401 |
| `0f4ddd93-61f6-452d-abfb-b4c6f212f3b2` | 1080×1920 / 30.000000 | exit 0 | mean_volume: -20.7 dB; max_volume: -0.9 dB | 0 | HTTP 200; SHA-256 matches; anonymous 401 |

Frames show readable in-frame captions/cards and clean cuts without the observed ghosting. No unrelated people or invented photo credits were substituted. Commons failed with timeouts/unreachable-provider messages; available licensed-photo retrieval did not succeed. The supported locally-created informational cards are explicitly labeled. The configured Gemini primary/fallback names were preserved; successful script provider and local narration provider are saved per job.

Limitations: no subjective listening-quality assessment or word-level subtitle/audio alignment is claimed. Narration is fully decodable and non-silent; captions use the existing estimated phrase timing, end within the narration window and retain the script ending. Representative visual checks are not a frame-by-frame editorial review. IAB localhost navigation failed with ERR_CONNECTION_TIMED_OUT. Windows Computer Use then stopped because it could not determine the current browser URL confidently enough to enforce policy; no further UI actions were attempted. Browser playback, browser seeking and a browser-clicked download therefore remain unverified. Authenticated HTTP download and range delivery were tested through the actual normal app.

### Validation

- `fresh-focused-results.xml`: 45 tests, 0 failures, 0 errors, 0 skipped.
- `fresh-parser-render-results.xml`: 39 tests, 0 failures, 0 errors, 0 skipped.
- `fresh-delivery-results.xml`: 350 tests, 0 failures, 0 errors, 0 skipped.
- Frontend `npm.cmd run build`: exit 0, Vite 6.4.5, 1615 modules; JavaScript 311.61 kB / gzip 91.35 kB, CSS 62.43 kB / gzip 15.45 kB. No Studio design changes.

The intermediate full run `fresh-current-full-results.xml` had 347 passes and one real new-regression failure: named Player of the Year wording was not recognized. It was corrected, not skipped. Earlier full runs passed 344, 346 and 349 tests at their respective intermediate source states. The delivery run above is the final-source result. Starlette/httpx deprecation warning remains. Isolated tests did not create persistent accounts or replace normal credentials/data.

Review locally at `http://127.0.0.1:5173/videos/<job ID>`. Use the normal authorized sign-in; short-lived signed URLs are intentionally not permanent download links. The supervised backend uses port 8000 with scheduler/uploads off. No deployment or publishing was performed.


## Motion, narration and media-only continuation — 26 October 2026

Current decision: supervised local review outputs are available. **Production readiness is NOT established.** Subjective listening, sports-name pronunciation approval and uninterrupted human audiovisual review remain blocked. No video was uploaded externally, no public/private YouTube upload ran, no unattended publishing was enabled, and no deployment or push occurred.

### Inspection and preserved checkpoint

No applicable AGENTS.md was found in the project or checked parent directories. Read the completion, photo integration, workspace verification, voice and deployment reports; inspected renderer, native speech worker, caption alignment, media collection/replacement, retry/review and publishing safeguards. The historical imagery evidence matches Ronaldo revision 11, Messi 10, Henry 12, four photo scenes plus two cards each, unchanged scripts, zero clips and disabled uploads. The historical delivery XML contains 357 tests; it was not treated as current proof. Existing video frames and source/timing records were inspected. Listening was unavailable before selecting the fix; no listening pass is claimed.

Checkpoint MP4s remain in generated/imagery-continuation/renders/<job>/revision-<11|10|12>/short.mp4. Additional before copies, original narration/SRT/job records and all rendered intermediate revisions from this continuation are retained under generated/motion-continuation/<job>/. No original source photo or prior revision was deleted.

### Observed causes and implemented changes

- The renderer previously changed narration speed to fit a fixed target. This could substantially stretch a short source narration and alter its pacing. It now uses the original provider pace, complete source narration plus a 0.6-second ending tail, and holds rather than cuts or accelerates narration exceeding the requested duration limit. Shorter output is intentional. No factual script edit was made.

- Photos previously zoomed only about 0.00018 per frame, giving barely visible motion. They now alternate restrained 7% zoom in/out over the scene, using a 2x working canvas to reduce pixel rounding jitter. Aspect ratio, padded framing, subject focal coordinates, archival labels and subtitle safe margins remain intact. All five transitions use 0.4-second dissolves; full-frame text/card fallback is rejected.

- Missing-photo, provider-failure and reviewer-removal paths produced informational cards. They now retain an addressable missing-media sentinel and actionable reason for authenticated upload/replacement controls. Both the pipeline and renderer reject missing media and legacy cards on generation/retry. Generic stadium/stock substitutes were removed from subject-photo fallback; exact subject identity and licensing gates remain. Historical card records remain viewable.

- Existing approved collection clips are prioritized. Clip audio is excluded from the output map. Clips are trimmed at normal speed; clips shorter than the scene are held with an explicit replacement message, never looped or slowed. No approved clips exist in the normal library or for any pilot, so all final scenes use relevant photos. No new stock or external clip service was introduced.

- Local speech failure previously wrote one second of silent development audio. It now raises NarrationUnavailable. Empty/all-zero local audio and invalid/incomplete native word boundaries cannot be reported as successful local narration. Selected compatible system voice and language resolution remain in use.

- An attempted 48 kHz SAPI capture exposed invalid native event positions beyond the WAV duration. The integration test caught it; capture was restored to the working 16 kHz path before final synthesis. Final MP4 audio is resampled to 48 kHz AAC. No invented timestamp rescaling was used to hide that failure.

- Final captions use the exact final WAV/script hashes and synthesis word events at natural speed. Displayed captions retain the original spelling, with full script word correspondence. No unverified pronunciation substitutions were introduced. Saved scene plans and recorded output duration now match the actual rendered timeline.

- Browser verification exposed an expired token trapping the review UI outside the login screen. Authenticated API 401 responses now clear stale local session state and return to sign-in. Sign-in and playback recovered successfully.

### Final revisions and exact artifacts

Each final revision has **six photo scenes, four distinct reviewed genuine photos (two reused), zero clips, zero standalone text cards, zero approvals**. Dates/labels identify archival illustration rather than claiming to depict the narrated award event.

| Subject | Revision | Actual duration | Preserved final MP4 | Stable authenticated review |
|---|---:|---:|---|---|
| Ronaldo | 17 | 25.428563s | `C:\Users\ua589\short generation\generated\motion-continuation\230904a6-bfc0-4182-b240-c4d498cd99fe\revision-17\short.mp4` | http://127.0.0.1:5173/videos/230904a6-bfc0-4182-b240-c4d498cd99fe |
| Messi | 16 | 23.791667s | `C:\Users\ua589\short generation\generated\motion-continuation\7f51b5de-a19d-4faf-9318-43dc15ba2b06\revision-16\short.mp4` | http://127.0.0.1:5173/videos/7f51b5de-a19d-4faf-9318-43dc15ba2b06 |
| Henry | 18 | 16.594313s | `C:\Users\ua589\short generation\generated\motion-continuation\0f4ddd93-61f6-452d-abfb-b4c6f212f3b2\revision-18\short.mp4` | http://127.0.0.1:5173/videos/0f4ddd93-61f6-452d-abfb-b4c6f212f3b2 |

The normal authenticated preview/download serves generated/videos/<job>/short.mp4. The revision-specific paths above are preserved review copies with the same final MP4 bytes. Full source/creator/license/date records remain in generated/imagery-continuation/curated-photos.json and the current job asset records. No newly downloaded media was added: former card scenes 2 and 5 reuse each subject's previously reviewed photos from scenes 1 and 4. Existing CC BY 2.0 attribution, source pages and archival dates remain in the SEO description and asset provenance; no watermarks or restrictions were removed.

### Verification: separate kinds of evidence

Before the final cached-audio guard: `cd backend; ..\.venv\Scripts\python.exe -m pytest -q --junitxml=../generated/motion-final-verified-results.xml` — **362 passed, 0 failures/errors/skips**, one existing Starlette/httpx deprecation warning, 420.41 seconds while renders also ran. The suite covers research holds, script/provider failure/retry, privacy/owner/member permissions, media replacement, revision approval invalidation, duplicate delivery, scheduling/concurrency and restart recovery. These are isolated local tests, not new live research/provider/publishing acceptance.

Frontend: `cd frontend; npm.cmd run build` — exit 0; Vite 6.4.5, 1615 modules, JS 312.03 kB (91.52 kB gzip), CSS 62.43 kB (15.45 kB gzip). No production application source changed after that build except backend scene-timeline/clip safeguards.

Intermediate results remain available: motion-full-results.xml (339 pass/18 fail), motion-focused-results.xml (75 pass/7 fail; edits were still in flight), motion-final-results.xml (355 pass/2 fail), motion-delivery-results.xml (360 pass/1 fail), motion-release-results.xml (361 pass). Failures were resolved, not skipped. Fixture changes explicitly replace old card/silence/fixed-padding expectations or mock media collection in tests focused on retry/direction persistence; identity and licensing assertions were retained. New policy tests cover natural audio/no atempo, alternating motion, clip-audio exclusion, missing-media rejection, duration-limit holds, local failure, and persisted scene timing.

| Subject | Decode | Resolution | Download/hash | Anonymous | Range | Black intervals | Native events | Source clipped samples |
|---|---|---|---|---|---|---:|---:|
| Ronaldo | exit 0 | 1080×1920 H.264/AAC | 200, hash matches=True | 401 | 206 | 0 | 77 | 0 |
| Messi | exit 0 | 1080×1920 H.264/AAC | 200, hash matches=True | 401 | 206 | 0 | 69 | 0 |
| Henry | exit 0 | 1080×1920 H.264/AAC | 200, hash matches=True | 401 | 206 | 0 | 45 | 0 |

Automated: full FFmpeg decode, ffprobe, blackdetect, volumedetect, nonzero source PCM, exact source/script native-boundary validation, caption text equality, motion-region differences and output/download SHA-256 checks passed. All native caption endings lie within complete narration; original words are retained. These checks do not establish natural pronunciation or subjective audio quality.

Browser: all three final revisions played from the start through ended=true at their actual durations, with readyState 4 and 1080×1920. Screenshots were inspected during active playback and at each ending; opening/all five dissolve midpoints/ending were visually inspected in transition sheets. Photos, aspect ratios and caption margins were readable at the inspected points. Henry's Download MP4 browser action completed; authenticated HTTP downloads and anonymous rejection were verified for all three.

**Blocked/manual:** tools cannot hear local playback. Subjective voice quality, sports-name pronunciation, audible repeated/missing words, and listening-based caption synchronization are NOT passed. Browser playback plus sampled visual inspection is not an uninterrupted human audiovisual watch of every frame; that editorial check remains required before approval. No cloud voice quality claim is made.

Evidence: generated/motion-continuation/pilots.json; verification/results.json; alignment-motion-evidence.json; browser-playback.json; publishing-readiness.json; per-job inspection/transitions.jpg; revision directories with render commands, captions, logs and render-timeline.json.

### Startup and remaining blockers

From `C:\Users\ua589\short generation`, run `.\start-backend.ps1` in one PowerShell terminal and `.\start-frontend.ps1` in another. Open http://127.0.0.1:5173 and use the existing authorized account. Backend is http://127.0.0.1:8000. Keep both terminals running and use one Uvicorn worker. Reuse existing listeners rather than starting duplicates. The scripts force SCHEDULER_ENABLED=false and YOUTUBE_UPLOADS_ENABLED=false; the private file defaults must not be mistaken for these supervised runtime settings. After interruption, use Queue → Retry failed step. Held scenes retain upload/replacement controls.

| Remaining blocker | Evidence | Next concrete action |
|---|---|---|
| Listening/editorial approval | No local audio listening tool; native timing is technical evidence only | Listen to all three MP4s start-to-end, verify names and ending captions, then approve only the exact reviewed revisions. |
| Higher-quality cloud narration, if local voice remains unacceptable | Google TTS unconfigured; ElevenLabs key present but default voice absent and allowlist empty | Configure an approved generic narrator ID in the existing ElevenLabs default and allowlist (or existing Google credentials); explicitly choose provider and regenerate, then repeat listening/alignment review. No key or voice ID was exposed or invented. |
| YouTube private test | Google OAuth configuration absent, token-encryption key absent, zero channel authorization records | Configure the existing callback and encrypted token storage, connect the intended channel, obtain explicit one-video private-test authorization. |
| Unattended hosting | Local SQLite/media and serialized in-process worker; no external durable worker | Provision persistent database/media storage, backups/restore rehearsal, durable task queue/leases, one scheduler leader, monitoring and target-host narration validation. Hosting/container deployment remains untested. |
| Scene media availability | No approved clips; provider failures hold | Add approved relevant licensed footage/photos via the existing library/replacement workflow; preserve source, identity and rights records. No arbitrary stock fallback. |
| Fresh external provider acceptance | This continuation reused verified research/scripts/photos and exercised real local TTS/rendering | Run a later supervised fresh research/media provider acceptance when needed; the mocked suite is not evidence of live external uptime. |

### Subsequent controlled private YouTube upload verification — not executed

1. Finish listening/editorial review. Select one exact approved revision and one explicitly authorized channel. Confirm facts, archival disclosure, all credits, made-for-kids choice and private visibility.

2. Configure GOOGLE_CLIENT_ID/GOOGLE_CLIENT_SECRET and the existing callback `http://127.0.0.1:8000/api/youtube/callback`, plus a stable TOKEN_ENCRYPTION_KEY and durable storage. Connect the channel through the existing OAuth UI; verify account/channel ownership. Do not log tokens or secrets.

3. Obtain explicit authorization for that single private upload test. Keep scheduler and automatic preparation off. Use the existing test-channel allowlist and guarded upload path, enable uploads only for the controlled test window, and approve the current revision.

4. Submit once with private privacy. Record returned YouTube ID, job/revision and upload-task state. Verify private visibility, playback/audio/captions/credits in Studio. Reconcile an uncertain result in Studio before any retry to avoid duplicate uploads.

5. Disable uploads immediately after the test, verify the disabled flag and no pending schedules, and retain the evidence. Public/unlisted publication, unattended enabling and deployment require a separate task.


Measured narration pacing cause: saved checkpoint timing records show the original provider audio was expanded to 27.222222 seconds: Ronaldo 24.828563 seconds (+9.64%), Messi 23.186750 (+17.40%), Henry 15.994313 (+70.20%). Final rendering removes this tempo transformation. This proves a pacing alteration, not a subjective listening diagnosis. Source evidence: generated/motion-continuation/narration-root-cause.json. All three final source WAVs pass the new cached-audio guard and native hash/word coverage checks.


### Final-source verification after cached-audio retry guard

This supersedes the earlier 362-test checkpoint above. Final command: `cd backend; ..\.venv\Scripts\python.exe -m pytest -q --junitxml=../generated/motion-cached-audio-final-results.xml` — **363 passed, 0 failures/errors/skips**, one existing Starlette/httpx deprecation warning; 236.19 seconds.

The renderer now validates cached narration as non-silent 16-bit PCM before rendering, so a saved silent WAV cannot bypass the new-synthesis failure check during retries. All three final pilot WAVs pass this guard and retain valid exact native word boundaries. This validation change does not alter their MP4 bytes; final revisions remain **Ronaldo 17, Messi 16, Henry 18**. The running supervised backend was restarted with the final source, scheduler false and YouTube uploads false.

`caption-integrity.json` records positive, nonoverlapping cue intervals, full script words and final caption ends of 24.829 / 23.187 / 15.994 seconds, within WAV duration to SRT millisecond rounding. Listening-based synchronization and pronunciation remain blocked. The final Henry revision 18 browser download completed to the normal Downloads folder; all three final authenticated HTTP downloads match the preserved MP4 hashes and reject anonymous access.

No production-ready declaration is made. The next editorial action is listening to the three linked final outputs before approving these exact revisions. No upload, deployment or push was performed.


## Pilot quality continuation — 27 October 2026

Superseding the historical revision checkpoint: final candidates are Ronaldo 20, Messi 19 and Henry 32. See [PILOT_REVIEW_CHECKPOINT.md](PILOT_REVIEW_CHECKPOINT.md) for exact paths, measured results, actual findings and remaining limitations. Full render/download decoding, hash equality, caption integrity, no detected black/frozen intervals and consistent measured narration levels passed for all three; 44 relevant regression tests passed. Listening and browser playback remain unavailable and unpassed. Existing committed narration was reused without new provider synthesis. All prior versions remain retained. Uploads are disabled in backend/.env and supervised runtime; zero approvals, no publication/deployment.
