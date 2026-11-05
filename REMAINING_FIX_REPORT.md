# Remaining Medium/Low fixes

Date: 23 October 2026 (Asia/Karachi).

Implemented M-01, M-02, M-03, L-01, L-02 and L-03 from the historical `AUDIT_REPORT.md`. Read the audit, `FIX_REPORT.md`, current implementation and repository instruction locations first; no applicable `AGENTS.md` was found. The three High fixes and migration `0006_high_fixes` remain in place.

## M-01 — empty/custom generated-output roots

**Cause:** the subtitle writer created the ASS directory but not the separate SRT parent. Rendering assumed some folders already existed.

**Change:** the renderer initializes its audio/images/videos/thumbnails/subtitles output folders. The subtitle writer independently creates both parents, including nested and unrelated ASS/SRT paths.

**Executed verification:** a real FFmpeg render starts with a completely empty temporary output root. It uses six original fixture images and a generated offline test-tone WAV located outside that root. No mocked file writer or cloud service is involved. The resulting MP4 is **30 seconds, 1080×1920, H.264 with AAC**, with real ASS, SRT and cover files. Separate nested subtitle-parent creation is also tested. This proves rendering/output creation, not a new human-narration or live-AI acceptance run.

## M-02 — authenticated cross-origin downloads

**Cause:** cross-origin anchors could not force a download, and the media response did not request attachment disposition.

**Change:** the existing signed media route accepts `download=true` after all existing signature, expiry, path, authentication and job/channel authorization checks. It responds with an attachment and a fixed safe filename derived from the authorized generated job ID and extension. Normal playback URLs retain normal FileResponse behavior. Review download links request attachment disposition; playback URLs do not.

**Executed verification:**

- API tests verify attachment filename, correct bytes, 206 byte-range behavior, anonymous rejection, another workspace's rejection and invalid-signature rejection.
- In headless Edge, with the frontend on **5177** and API on **8004**, clicked the actual Download MP4 control on **1440×1000 desktop and 390×844 mobile** views.
- On each viewport, a new file was saved to an empty per-run download directory. Each was **3,168,822 bytes**, SHA-256-identical to the authorized source; FFprobe confirmed H.264, AAC and 1080×1920.
- The browser stayed on the review route with its review DOM intact. Real playback also advanced successfully on both viewports before the download.

The downloaded browser fixture was an existing valid local MP4 copied into the disposable workspace. The independent M-01 test produced a fresh render. These are separate checks, not a claimed fresh live-generation/download chain.

## M-03 — consistent research provider selection

**Cause:** the picker always called live RSS, while normal jobs resolved demo/RSS through workspace/server configuration.

**Change:** picker and worker use shared provider resolution. Demo picker results are persisted as **demo**, not verified news, with explicit source/development labels. They can be selected only while demo is the active provider and become demo topics in the worker. The UI labels the demo action “Explore development topics.” Live configuration cannot accept these demo candidates. Live RSS failures retain actionable error responses and do not invoke demo fallback.

**Executed verification:**

- With network connection creation and both live research entry points forbidden, demo picker creation, candidate selection and the worker reaching the script boundary pass. The worker's automatic topic path without a selected candidate is tested as well.
- Live picker failure injection returns 422 with an actionable retry message. Existing live-worker failure tests continue to pass and ensure live RSS never silently becomes demo research.
- Switching the test process to RSS rejects a demo candidate with 409.
- Desktop/mobile browser research returns visibly labeled development topics without sending a generation request.

The normal application's `.env` was not changed to demo. Only the isolated test backend used process-scoped demo configuration. An initial browser harness inherited RSS instead; its missing-development-label assertion correctly failed. The harness was corrected to explicitly select demo before the final passing checks.

## L-01 — scoped duplicate personalities

**Cause:** creation had no equivalent-name check or transactional serialization.

**Change:** names are compared using Unicode NFKC normalization, case folding and collapsed whitespace. Scope is:

- Workspace themes: workspace + channel assignment + workspace visibility.
- Personal themes: workspace + creator member + channel assignment + personal visibility.

Creation acquires a short database workspace-row write lock before checking and inserting. This serializes concurrent creation on SQLite and PostgreSQL without imposing a new uniqueness constraint on historical records. A new entry returns 201; an equivalent entry returns **200 with its existing ID and `reused=true`**. The inline picker refreshes/selects that ID immediately. Search also normalizes equivalent whitespace/Unicode forms.

If historical duplicates exist, an enabled equivalent is preferred, then the oldest stable entry. Existing duplicate rows and references are never merged or deleted. If every equivalent entry is disabled, creation returns a clear 409 rather than silently reactivating it. Different channels, visibility and personal creators remain intentionally distinct. No private entry from another member is returned through duplicate detection.

**Executed verification:** five concurrent equivalent submissions produce one 201, four 200s and one ID. Tests cover case/whitespace/Unicode equivalence, normal creation, different channel/visibility/creator scopes, private access denial, reusing the member's own entry, enabled equivalents among historical duplicates, and unchanged historical job references. Desktop/mobile inline creation of `  LIONEL   messi ` selects existing `Lionel Messi`; the database still has one such original browser fixture entry.

## L-02 — persisted workspace identity and selected duration

**Cause:** the sidebar rendered literal Demo Workspace/Free workspace, and the preview headline always said 60 seconds.

**Change:** authenticated settings return only the current workspace's persisted ID/name. The sidebar displays that name and its initial, with neutral “Workspace” text instead of an invented subscription plan. A real persisted Demo Workspace still displays its genuine name. Both preview duration locations use the selected duration.

**Executed verification:** owner/editor settings show a temporary persisted workspace rename. In desktop/mobile browser checks, the sidebar uses **Local Acceptance Studio**, does not show Free workspace, and the preview text follows **30, 45 and 60 seconds**. No production workspace was renamed. Existing layout, branding, colors and card CSS were preserved.

## L-03 — initial loading, background errors and recovery

**Cause:** the queue initialized to an empty list with no loaded state, errors were not cleared on successful polling, and interval polling could overlap requests.

**Change:** a shared polling hook tracks initial loading, successful data and poll errors separately. Polls run serially after the previous request completes. Cleanup aborts requests, cancels timers and marks the effect inactive. Route tokens and mutation epochs reject responses from an old route or a poll predating a newer local action response. Queue and review retain already-loaded content during refresh/failure; successful polling clears poll errors. Action errors remain separate from transient polling failures.

The queue displays loading until a response, a retrying error state on initial failure, “No videos yet” only after a successful empty response, and filter-empty feedback when actual loaded records do not match.

**Executed browser fault injection on both desktop/mobile:**

- Delayed first response: loading visible, no premature empty state, only one active poll. React development StrictMode's aborted initial request is excluded from the active-request count.
- Successful empty response: genuine empty state.
- Failed poll followed by success: error appears then clears.
- Failed background refresh with loaded rows: rows stay visible.
- Delayed request followed by navigation/unmount: late response does not replace the new page.
- Review poll failure/recovery: video/review content remains visible and the transient error clears.
- Late response for an old review ID: it cannot overwrite the newly selected review.

## Changed application/test files

- `backend/app/video/renderer.py`
- `backend/app/video/subtitles.py`
- `backend/app/api/media.py`
- `backend/app/api/research.py`
- `backend/app/api/videos.py`
- `backend/app/api/personalities.py`
- `backend/app/api/settings.py`
- `backend/app/research/selection.py` — new shared resolution/development-candidate helper
- `backend/app/services/personality_identity.py` — new scoped identity/locking helper
- `backend/app/services/pipeline.py`
- `frontend/src/hooks/usePollingResource.js` — new serial, cancellable polling hook
- `frontend/src/pages/Review.jsx`
- `frontend/src/pages/Videos.jsx`
- `frontend/src/pages/CreateShort.jsx`
- `frontend/src/components/ResearchPicker.jsx`
- `frontend/src/components/PersonalityPicker.jsx`
- `frontend/src/components/Shell.jsx`
- `backend/tests/test_remaining_fixes.py` — seven meaningful regression/integration tests

Temporary browser harnesses/evidence are under `generated/`; the original audit and High fix report remain historical records.

## Validation results

| Check actually executed | Result |
|---|---|
| Seven new regression tests, including real empty-root FFmpeg render | **7 passed**, no skipped tests |
| Targeted remaining/High/risk/live-configuration/workspace-privacy tests | **45 passed**, 55.26 seconds |
| Final full backend suite | **165 passed, 0 failed, 0 skipped**, 96.71 seconds |
| Additional network-forbidden automatic demo-worker assertion | **1 passed**, 5.15 seconds |
| Final frontend production build | **Passed**, Vite 6.4.5, 1607 modules, no build warnings |
| Baseline isolated role/create/review browser checkpoints | **17 passed** |
| Focused desktop/mobile remaining-fix checks | **Passed** for both viewports, including saved-file verification and polling fault injection |
| Browser preservation of High approval behavior | Current approval succeeds; after edit, stale approval **409**, cover-only regeneration **409** |
| Browser playback after polling changes | Playback advanced, 1080×1920, no media error |

One existing Starlette/httpx TestClient deprecation warning remains. No new application/build warning was introduced. Browser harness retries corrected test setup issues (explicit provider configuration, StrictMode abort accounting and fresh download directories); final passing checks were rerun and are not inferred from HTTP 200 alone.

Commands:

```powershell
# backend
..\.venv\Scripts\python.exe -m pytest tests/test_remaining_fixes.py -q
..\.venv\Scripts\python.exe -m pytest tests/test_remaining_fixes.py tests/test_high_fixes.py tests/test_risk_verification.py tests/test_live_configuration.py tests/test_workspace_privacy.py -q
..\.venv\Scripts\python.exe -m pytest -q

# frontend
npm.cmd run build
```

Fresh browser scripts: `generated/verify_remaining_base_ui.py`, `verify_remaining_focus_ui.py`, `verify_remaining_high_playback_ui.py`. Evidence: `generated/remaining-browser/report.json`, `remaining-results.json`, `approval-results.json`, PNG screenshots and downloaded MP4s under `downloads/`. Desktop/mobile screenshots were inspected. No horizontal page overflow was detected at tested widths.

## Data, migration and High-fix preservation

**No new migration is required.** Existing schema remains `0006_high_fixes`. No records/references were automatically merged, deleted or reassigned. Temporary account/workspace changes were confined to isolated databases. The normal backend was restarted to load the changes; integrity check is **ok**, foreign-key errors **0**, and uploads remain **false**. Credentials and the real research configuration were not changed.

The High regression suite still covers stale-version approval, concurrent edit/approval, competing regeneration, unrelated-event/claim corroboration, syndication, and concurrent generation idempotency. The full suite includes these checks. Demo candidate support does not permit demo stories to bypass live verification or publishing guards. Legacy media still needs a rerender before new approval as required by migration 0006.

## Remaining limitations and readiness

**Ready to attempt a supervised live-provider generation/review acceptance test, subject to separately authorized provider usage and available configuration.** This is not a claim that a live end-to-end acceptance run or production readiness was proven here.

- No paid generation, cloud TTS, real YouTube authorization/upload, publication or deployment was performed. Those live checks remain **unverified/blocked by this task's scope**. Uploads stay disabled.
- The real offline render uses a deterministic test tone, not a newly generated human narrator. Browser playback/download uses copied existing local media. Neither substitutes for a fresh live researched/narrated Short.
- Deterministic claim matching remains conservative and primarily English; insufficient evidence still holds. Human factual review remains necessary.
- Browser coverage is Edge at the tested desktop/mobile viewport sizes, not physical-device Safari/Firefox certification.
- All-disabled duplicate personality scopes intentionally return an explicit conflict. This pass did not add general theme editing, reactivation or unsharing UI.
- Separate suspected audit risks (distributed worker durability, broader session hardening, portable license manifests, large-workspace scale and complete analytics/live-account behavior) were not reclassified as fixed or folded into these six changes.

No skipped or blocked live check is counted as passing above.
