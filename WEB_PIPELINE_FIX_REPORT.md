# Web pipeline configuration fix

The running API detects Gemini, primary `gemini-flash-latest`, a configured fallback,
RSS research, and Commons assets. YouTube uploads remain disabled.

- Backend `.env` resolves from the backend directory, independent of working directory.
  Relative SQLite/generated paths also resolve consistently against that directory.
- Header and sidebar use authenticated provider status, with loading/unavailable states.
- Existing workspace demo preferences cannot downgrade `RESEARCH_PROVIDER=rss`.
- RSS failures stay at the research step with a visible error and manual retry. No demo substitution.
- Startup recovery preserves committed artifacts and the interrupted step. Retry reuses saved checkpoints.
- Successful new scripts record their actual Gemini model in existing job provider information.
- Two competing/unresponsive Uvicorn reloaders were replaced with one clean backend.

## New live web job

Job: `c1a2eaeb-6dfd-4f9b-8f7e-4a939accc69d`.
Created through POST `/api/videos/generate` with Ronaldo, Current Topic and 30 seconds.
The active providers were retrieved from the running authenticated `/api/settings` endpoint.
Live RSS yielded a Guardian story published 2026-10-21 and a stale story rejected by validation.
The current story lacks a second independent credible source, so the NEW job correctly stopped
at `verification_required`. No script, demo research, or demo narration was substituted.
Gemini was NOT called for this job because factual verification is a prerequisite.
The previous successful direct Gemini test is not counted as successful web-pipeline generation.

Full source URLs, publication dates and rejection reasons are preserved in
`generated/web-pipeline-verification.json` and the research candidate records.
Old demo/failed jobs were not regenerated or rewritten.

## Verification

99 backend tests passed (one existing Starlette/httpx deprecation warning).
Frontend production build passed. Browser automation has no connected browser,
so the UI changes were verified by build and running API responses, not a visual inspection.
The full live RSS ? Gemini ? rendered-video acceptance is not complete until a
candidate passes source verification. Reliability/source thresholds were not weakened.

The clean backend runs on http://127.0.0.1:8000 without reload while validating jobs.
After restarting it manually, use the existing backend commands. Avoid two simultaneous
Uvicorn instances and avoid code reloads during a local render.
