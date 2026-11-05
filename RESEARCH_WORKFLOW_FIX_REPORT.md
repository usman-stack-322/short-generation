# Research-to-script investigation and fixes

23 October 2026. Existing audit/fix protections and UI layout were preserved.

## Actual affected job

Latest affected job: **`b82a60c0-0ec6-44f3-bbb8-8fb4e48033e5`**, Cristiano Ronaldo, Current Topic. Created `2026-10-23 12:16:15` UTC; held at `12:16:19` UTC. Saved status/current step: `verification_required`; no `topic_id`, no script, no failed script step, no script-provider warning. Its generation operation has one persisted request record.

Three saved candidates were found in that job's research window:

- `8c51ef48-039e-4fe8-8706-dde7a869de98`: an El Clásico preview mentioning the historical Messi/Ronaldo rivalry.
- `d1d4d721-e731-4e2b-853c-24b05c99dc5c`: a rolling football liveblog with an incidental Ronaldo reference.
- `5381290f-8f63-4b83-aabd-36bb81e1bdbd`: a club scoring-record discussion mentioning Ronaldo among several players.

All three came from **The Guardian**, each with only one independent source and `major_news` authority. Each saved decision required stronger corroboration. No candidate in that run was verified/selected. The selected candidate ID is therefore **none**; the old schema did not persist a direct per-job research trace, but the atomic selected-candidate API path would have saved a topic if selection had succeeded.

**Root cause:** legitimate insufficient evidence and weak topic focus from broad football feeds, combined with misleading/incomplete review messaging. The job never reached Gemini. The generic hold message was set in the no-verified-candidate branch before script generation; Gemini credential/model/quota/parser failures did not cause this job's hold. A genuinely verified-topic auto-continuation path already existed; it was not appropriate to bypass this hold or invent a separate manual script-start action.

Historical per-stage research logs were not durable; saved job/candidate state and the actual control flow establish the hold. No render log exists for a job that never reached rendering. The new trace and script-entry log improve future diagnosis without rewriting historical evidence.

## Read-only live RSS diagnostics

Executed the configured feeds separately for Cristiano Ronaldo/Ronaldo, without saving candidates or running generation:

| Configured feed | Actual result |
|---|---|
| BBC football RSS | No matching entries; no feed error |
| Guardian football RSS | Three matches; zero verified, three held under the then-current assessor |
| Google News football search RSS | No matching entries; no feed error |

The restricted-shell attempt encountered local WinError 10013. Repeating the authorized read-only diagnostic outside that restriction succeeded as above. This was not a confirmed live feed outage/configuration parse error. The feeds are broad football feeds, not a guarantee of focused Ronaldo news.

With the improved focus check, reassessing the three saved candidate payloads **without saving changes** rejects all three as incidental mentions. Historical candidate status/evidence remain unchanged. The real job's review serialization now returns `script_state=held`, three source cards, and a specific reason on every card.

## Changes

- Added durable per-job `research_trace`: active provider, candidate IDs, selected candidate ID and partial feed errors. The worker and explicit candidate-selection API both persist provenance. Candidates selected by the automatic worker are atomically marked selected. New holds use their exact candidate IDs rather than a shared time-window inference; historical jobs retain a bounded compatibility lookup.
- Preserved automatic research → verified topic → script → remaining pipeline execution. Added a safe script-entry log identifying job/candidate, without secrets.
- Held jobs expose specific verification/rejection reasons, source/independent counts, URLs and timestamps. Rejected candidates remain visible, rather than disappearing from review. Partial feed outages are recorded in candidate payloads and shown on review.
- Tightened relevance: an incidental mention late in a broad article, or a historical-era reference without headline focus, does not qualify a story as personality-focused. Authority, freshness, risk thresholds, claim matching, independent-source/syndication and rumor protections were not weakened.
- Review now distinguishes script not started due to verification, research failure, verified/queued script, running script and failed script. It no longer says “Script generation has not finished” for held research. Downstream regeneration remains blocked on holds; research retry remains available.
- Research retry can detach a previously attached unverified topic and obtain fresh evidence, preserving the old topic record. It resumes on the same job, with existing authorization, optimistic version checks and operation idempotency retained.
- Script failures retain their verified research and retry at script generation. Completed scripts/scenes are now committed **before the separate SEO request**. SEO failures/interruption record `seo_generation` and retry SEO without repeating successful script generation. This avoids unnecessary repeated provider work.

Changed application/test files:

- `backend/app/models.py`
- `backend/migrations/versions/0008_research_trace.py`
- `backend/app/database/migrate.py`
- `backend/app/research/live.py`
- `backend/app/services/pipeline.py`
- `backend/app/services/recovery.py`
- `backend/app/api/videos.py`
- `frontend/src/pages/Review.jsx`
- `frontend/src/components/SourceCard.jsx`
- `backend/tests/test_research_continuation.py`

Browser fixture harnesses/evidence: `generated/research_browser_app.py`, `generated/verify_research_flow_ui.py`, `generated/research-flow-browser/`.

## Migration and existing data

**0008_research_trace** adds one non-null text column with `{}` as the default. Existing evidence, topics, scripts, jobs, approvals and accounts are not replaced, merged or deleted. A copy of the retained 0007 database backup was upgraded independently: users/channels/personalities/jobs/scripts/candidate counts were unchanged; integrity `ok`, no foreign-key violations.

The running documented reload backend applied 0008 with its normal SQLite backup. The actual affected job remains held with no topic; it was **not automatically retried**. `/api/health` returned **200**; database integrity `ok`, zero foreign-key errors. Uploads remain **false** and credentials/settings were not changed.

## Validation

Eight isolated regression tests cover:

1. Verified research automatically saves a script and reaches ready-for-review with fixture media providers; refreshed API returns the saved script and selected ID.
2. Insufficient evidence holds without a script-provider call; research retry with new authoritative evidence automatically continues on the same job.
3. RSS failure is stored as a research-stage failure, without a script call or fake hold.
4. Gemini script failure is a retryable script-stage error; retry reuses verified research.
5. An explicitly selected verified candidate reaches the worker and saved script.
6. Incidental personality mentions are rejected.
7. A held attached topic can be replaced on retry without deleting historical data.
8. SEO failure retains the script and retries only SEO.

Targeted new tests: **8 passed**. The earlier combined continuation/High/live-configuration run passed **21 tests** before the additional SEO checkpoint test was added. Final complete backend suite: **187 passed, 0 failed, 0 skipped**, 115.35 seconds. This includes existing stale-approval, false-corroboration, duplicate-operation, privacy and Medium/Low regression tests. One existing Starlette/httpx TestClient deprecation warning remains. Final production build: **passed**, Vite 6.4.5, 1610 modules, no build warnings.

Browser acceptance: **22 checkpoints passed**, real local frontend/API on separate ports **5179/8006**, isolated accounts/database, desktop 1440×1000 and mobile 390×844. Clicked the actual **Retry research** button: the real endpoint/worker selected verified fixture evidence and automatically saved a labeled fixture script on the **same job**. Reload showed the persisted script. Both hold and resulting script screenshots were inspected. The browser fixture deliberately fails at assets after the saved script; this is not a claim of a fresh real-news/video render. Separate regression tests exercise the complete pipeline with mocked downstream providers, while the full suite retains the real offline FFmpeg test.

**Live Gemini acceptance: BLOCKED by the no-paid-generation authorization boundary.** No deliberate live Gemini acceptance test was run. An initial browser fixture had an inadequate blank environment override on Windows: the SEO step could read the configured real key and stalled. That run was stopped. No successful provider response or saved SEO was recorded; whether an outbound attempt reached Google or incurred usage cannot be determined locally. This is a test-isolation mistake, not a verified live pass. The corrected fixture explicitly clears the key inside its process and forbids external HTTP POSTs; subsequent browser checks passed offline. Normal application credentials were untouched.

## Remaining blocker / next step

The affected job can use **Retry research** without creating a replacement job. However, success cannot honestly be promised with the currently observed feed results: there is **no focused, verified Ronaldo event** available from those results. Add/configure legitimate permitted sources with focused current evidence, or wait for corroborating reporting, then retry. A fresh authoritative low-risk primary report or independently corroborated matching event will automatically proceed; insufficient evidence will continue to hold.

Do not choose the three unrelated/incidental stories merely to unlock Gemini. A separately approved live Gemini acceptance run is still required after suitable evidence exists. Uploading, publishing and deployment were not performed. Existing broader audit risks remain outside this fix.
