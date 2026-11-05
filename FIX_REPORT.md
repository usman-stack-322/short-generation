# Verified High findings — fix report

Date: 23 October 2026 (Asia/Karachi).

Implemented the three authorized High fixes from `AUDIT_REPORT.md`. Repository/ancestor `AGENTS.md` searches found no applicable instruction files. Inspected the audit reproductions and actual routes, models, worker, verification and approval code before changing them. The approved visual design, existing authorization rules and workspace privacy remain in place.

## H-01: stale videos regaining approval

**Root cause:** editing invalidated approval but did not bind the stored MP4 to its narration/script inputs. Cover/SEO-only work skipped rendering and unconditionally restored readiness. Approval also lacked a client-reviewed revision and a concurrent-update guard.

**Fix:**

- Jobs and rendered videos now track `media_revision`. Changes requiring new rendered content advance that revision; completed rendering records the revision it produced. Metadata/cover-only work cannot clear a mismatch, at either the API or worker entry point.
- Narration records a script digest. Rendering cannot silently reuse audio for an edited script; a changed script causes narration regeneration before rendering.
- Approval requires the current `content_revision`, current media and a ready/approved job. Missing or stale review versions return 409. Publishing/scheduling requests also carry and validate the reviewed revision; the uploader independently rejects outdated media.
- The frontend sends the displayed revision for approval. Publishing confirmation retains the revision captured when its modal opened, so subsequent polling cannot silently authorize newer content.
- SQLAlchemy optimistic row versioning protects job writes. Concurrent edit/approval or competing regeneration cannot commit an old job state over a newer one. Even a first approval under the two-person policy participates in this compare-and-swap. Superseded worker results are discarded.
- Failed-step retry resolves its effective scope before advancing media revision. In particular, retrying a failed cover checkpoint does not invalidate an otherwise current render. Research holds still permit research retry and reject downstream work.

**Reproduction result:** script edit succeeds; cover/SEO-only requests then return 409; old-version and missing-version approval return 409. A simulated current render permits current-version approval. A stale session attempting approval after a concurrent edit raises the optimistic-concurrency conflict and leaves no restored approval. Two competing regeneration requests yield one 200, one 409 and one queued worker.

## H-02: unrelated stories falsely corroborating each other

**Root cause:** headline similarity selected peer reports, while the verifier mostly checked source authority, independence, freshness, numbers and negation. Similarity did not establish the same event or material claim.

**Fix:** added conservative local claim matching before evidence can contribute to corroboration. It checks claim categories, subject/name overlap and supplied personality matches, concrete event anchors (such as location, opponent, date/quantity, injury body part, recognized award/competition), and incompatible outcomes. Missing material details do not acquire credibility merely because another row mentions the same personality. Conflicting anchors/outcomes retain a hold.

Source authority, freshness, rumor rejection, canonical URLs, publisher grouping, originating-wire detection, summary/quote duplication and risk-based source thresholds remain enforced. Existing official-primary low-risk single-source handling is retained. Shared or syndicated coverage cannot provide an additional independent source. The exact Portugal/Madrid audit fixture now remains `verification_required`.

Tests also cover broad contract headlines without an event anchor, differing claim categories despite a shared year, conflicting contract outcomes, different awards, a positively matched specific contract event, and syndication. Two older positive corroboration fixtures were updated to supply a concrete 2028 contract detail; their former broad wording no longer demonstrates event-specific corroboration.

**Limit:** this is conservative deterministic screening, not a universal semantic fact checker. Extraction is primarily English and recognizes a bounded set of anchors/categories. Ambiguous or unrecognized reporting is held rather than guessed. It cannot guarantee that every paraphrase, misleading article or model-generated sentence is factually correct; human review remains necessary. No live current-news or paid AI validation was performed.

## H-03: duplicate generation jobs

**Root cause:** general generation requests inserted a new job on each submission. Only the verified-candidate selection branch had a claim guard; the frontend's loading button was not backend idempotency.

**Fix:**

- A durable `generation_requests` table uniquely binds workspace/operation identity to one job and input fingerprint, in the same database transaction as job creation. Concurrent uniqueness losers return the committed existing job and do not enqueue another worker.
- Permissions and personality/channel assignment are checked before any existing-operation response.
- Requests without an explicit operation ID use a deterministic identity over inputs and relevant defaults/provider configuration. Replaying that operation returns the existing job, including a failed job with its visible retry controls.
- The API accepts a bounded `operation_id` for an explicit new attempt. Reusing it with different inputs returns 409; changed inputs or a new explicit operation can create legitimate new work. Existing topic/candidate duplicate protections still apply.
- Create Short retains the same operation ID in session storage across a failed network request/reload. After an acknowledged successful submission, a later new form submission uses a new ID. No UI controls or styling were redesigned.
- Existing failed-step regeneration remains available, with its own concurrency protection; failed operations are not permanently unusable.

**Reproduction result:** six concurrent identical requests produced one job, one durable operation record and one queued worker. Replays returned the same job. Failed-job retry remained available; changed input and explicit new-attempt cases worked; an operation ID reused with conflicting input was rejected. Browser-intercepted request failure/retry reused its ID, while the next new submission used a different ID. No real generation request was sent in that browser test.

## Changed application and test files

- `backend/app/models.py`
- `backend/migrations/versions/0006_high_fixes.py` — new migration
- `backend/app/database/migrate.py`
- `backend/app/schemas.py`
- `backend/app/services/generation_requests.py` — new durable request identity helper
- `backend/app/services/pipeline.py`
- `backend/app/api/videos.py`
- `backend/app/api/publishing.py`
- `backend/app/youtube/permissions.py`
- `backend/app/youtube/upload.py`
- `backend/app/main.py`
- `backend/app/research/claims.py` — new conservative claim matcher
- `backend/app/research/verification.py`
- `frontend/src/components/PublishPanel.jsx`
- `frontend/src/pages/CreateShort.jsx`
- `backend/tests/test_high_fixes.py` — nine regression tests
- `backend/tests/test_day2_publishing.py` — include reviewed revisions in the updated API contract
- `backend/tests/test_risk_verification.py` — specific corroboration fixtures

Temporary browser harnesses/evidence are under `generated/`; `AUDIT_REPORT.md` was not rewritten to erase the original findings.

## Migration and existing data

Migration **0006_high_fixes** adds job/media concurrency fields, narration script digest and the generation-operation table. It was exercised on isolated fresh databases, then applied to the existing SQLite database with the existing automatic pre-upgrade backup workflow. No existing records/media were deleted and no credentials were changed. The backend was restarted with the updated implementation.

Post-migration verification: version `0006_high_fixes`, SQLite integrity `ok`, **0 foreign-key errors**, `YOUTUBE_UPLOADS_ENABLED=false`.

Historical videos receive an unknown render revision (`0`), rather than inventing proof that their MP4 matches their script. Their files/history remain accessible, but new approval/publishing requires a rerender and fresh review. Historical scheduled content similarly needs cancellation/rerender/reapproval before future publishing. This is intentional conservative migration behavior.

On another local checkout, stop the backend and run:

```powershell
cd 'C:\Users\ua589\short generation\backend'
..\.venv\Scripts\python.exe -m app.database.migrate
..\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Startup also invokes the migration runner. Keep a single local worker as documented.

## Executed validation and actual results

| Check | Result |
|---|---|
| Final targeted High/risk/publishing regression run | **41 passed, 0 failed**, 22.02 seconds |
| Final full backend suite | **158 passed, 0 failed**, 55.80 seconds |
| Warnings | One existing Starlette/httpx TestClient deprecation; no new SQLAlchemy flush deprecation in final runs |
| Final frontend production build | **Passed**, Vite 6.4.5, 1606 modules, no build warnings |
| Isolated browser layout/role/create/review checkpoints | **17 passed**, fresh test database/profile and desktop/mobile screenshots |
| Browser current-version approval | **Passed** |
| Browser edit → stale approval and cover-only request | Edit **200**, stale approval **409**, cover-only **409** |
| Browser network-failure retry / explicit next operation | **Passed**, matching retry IDs and a different new-operation ID; **0 real generation requests** |
| Browser login, persisted personality search, existing local MP4 playback | **Passed**; playback advanced, 1080×1920, no media error |
| Existing database migration/integrity | **Passed**, head 0006, integrity ok, zero FK violations |

Commands used:

```powershell
# From backend
..\.venv\Scripts\python.exe -m pytest tests/test_high_fixes.py tests/test_risk_verification.py tests/test_day2_publishing.py -q
..\.venv\Scripts\python.exe -m pytest -q

# From frontend
npm.cmd run build
```

Initial runs exposed the intentional approval-request contract change and stricter evidence requirements; callers/fixtures were updated and failures resolved. The final passing counts above were actually rerun. Build/browser execution required the permitted unrestricted shell because the restricted shell denies esbuild/SAPI access; this was not addressed by changing application security or credentials.

Browser evidence: `generated/high-fix-browser/report.json`, `approval-results.json`, `operation-ui-results.json` and adjacent PNGs. Harnesses: `generated/verify_high_fixes_ui.py`, `verify_high_approval_ui.py`, `verify_generation_intent_ui.py`. Browser video playback used copied existing local media; a fresh real render/live AI chain was not claimed as tested in this fix pass.

## Remaining limitations and unresolved audit findings

- Live Gemini generation, real current-news acceptance, cloud voices and real YouTube/OAuth/upload/scheduling publication remain **unverified/blocked by the no-paid-generation/no-publishing scope and missing OAuth configuration**. No upload or deployment was performed; uploads remain disabled.
- Deterministic claim matching may hold legitimate paraphrases and non-English reporting. It is not semantic proof of every claim. Existing fact-checking/privacy limitations documented in the audit remain relevant.
- The normal frontend carries explicit intent IDs. API clients should retain an ID across retries and deliberately choose a new one for a new attempt. Requests with no ID intentionally reuse their deterministic operation; use the returned job's retry/regeneration route or an explicit new ID when appropriate.
- Optimistic database guards protect current state. The in-process worker is still designed for one local worker; distributed execution and immutable per-worker output storage were not added.
- All Medium and Low findings remain for a separate pass: **M-01** fresh subtitle output folder, **M-02** cross-origin download behavior, **M-03** demo research picker inconsistency, **L-01** personality duplicates, **L-02** hardcoded labels, **L-03** queue loading/transient-error states. The browser still reproduced the download navigation defect; it was not silently counted as fixed.

No unrelated refactor, UI redesign, secret change, paid generation, data deletion, deployment or publishing was performed.
