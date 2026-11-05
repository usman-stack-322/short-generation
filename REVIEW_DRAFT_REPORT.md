# Review Draft mode

Implemented 24 October 2026. Existing credentials, data and upload settings were not changed. No database migration is required.

## Configuration and use

Set `REVIEW_DRAFTS_ENABLED=true` in `backend/.env` and restart FastAPI to opt in. The default is false; both example environment files document it. The job/settings APIs expose the enabled flag without secrets.

On a held job's review page, eligible candidates show **Generate review draft**. This explicit action checks the actual source page, then queues the existing job once. Research, polling and evergreen suggestions do not invoke Gemini. The original latest → 7 → 14 day retrieval and verified generation path are preserved.

## Meaning of the score

There was no calibrated truth-confidence model. Existing `overall_score` is a 0–1 ranking heuristic, displayed multiplied by 100:

- Freshness: 30%, decreasing with age within the active retrieval window.
- Personality relevance: 30%, based on name/alias matching, with separate focus rejection rules.
- Reliability: 25%, configured source metadata, not proof of a particular claim.
- Headline appeal: 15%, the existing heuristic based on headline vocabulary.

It is **not a probability that the story is true**. A ranking of at least 50/100 is necessary, never sufficient. The UI states this and shows the missing corroboration separately.

## Safety and persistence

Draft candidates must retain current-date validity, credibility, direct personality relevance, theme vocabulary matching and duplicate-history checks. Rejected candidates cannot use the draft endpoint. Contradictory evidence and sensitive personal allegations remain blocked regardless of score. Sensitive classifications also cover abuse, crime, diagnoses and other health conditions.

At least one credible, identifiable source must be fetched through the existing bounded public-HTTPS/SSRF protections (at most three source-access attempts per explicit action). An accessible article heading and text must match the specific event/claim; an RSS entry, unrelated page, paywall, failed request or matching personality alone is insufficient. A discovered core contradiction blocks the draft. Syndicated coverage never becomes independent corroboration.

The saved topic has `verification_status=limited_verification`, a failed verification flag, persisted ranking reasons, source links/dates, accessibility-check timestamp and missing corroboration. The candidate itself is not promoted to verified. Generation/retry rechecks eligibility. Existing revision-based approvals and optimistic concurrency protect competing actions; concurrent draft requests queue only one worker and do not create additional jobs.

Script instructions require supported claims only, named source attribution, the exact publication date, explicit missing corroboration and no invented details or breaking/today framing. Output validation rejects absent attribution/date and prohibited current-news wording. No demo script fallback is permitted for this mode. The full narrative still requires human factual review; these conservative checks are not a semantic proof of every sentence.

Rendered drafts allow an explicit **Approve reviewed draft only** action. Approval does not convert verification status. Upload and schedule controls remain blocked, and the backend uploader independently requires a verified topic even if a limited draft has approval. Upload configuration remains unchanged/disabled.

For missing, unsafe or inadequate current evidence, **Find sourced evergreen topic** retrieves a separate Wikipedia biography suggestion and links its original references for review. It does not invent a current event, select a topic, generate a script or automatically approve a biography. Ambiguous/unavailable biographies return a clear error. Evergreen suggestions remain source-review suggestions rather than an automatic factual-generation bypass.

## Changed files

- `backend/app/core/config.py`, both `.env.example` files: opt-in configuration.
- `backend/app/research/drafts.py`: draft policy, accessible-claim checks, separate evergreen sourcing.
- `backend/app/research/verification.py`: sensitive-claim classification.
- `backend/app/api/videos.py`, `backend/app/api/settings.py`: authorized explicit actions, persisted topic/evidence, eligibility rechecks and status exposure.
- `backend/app/services/pipeline.py`: separate limited mode, persistent warnings/review metadata and normal downstream stages.
- `backend/app/ai/scripts.py`: grounded draft instructions, attribution/date validation, no demo fallback.
- `frontend/src/pages/Review.jsx`, `frontend/src/components/PublishPanel.jsx`: existing-design draft controls, evidence/reasons, evergreen offer and explicit review-only approval.
- `backend/tests/test_review_drafts.py`: isolated regression fixtures.

## Actual validation

- Full backend suite: **219 passed**, one existing Starlette/httpx deprecation warning. This run collected 16 new draft tests; three additional draft tests were added afterward.
- Final draft-focused suite: **19 passed**, one existing deprecation warning. Covers the verified path, limited eligibility, sensitive holds, contradictions, missing/inaccessible sources, theme mismatch, below-50 score, explicit generation, saved limited state, concurrency, duplicate prevention, endpoint authorization, evergreen sourcing, script attribution/date guards and publishing rejection.
- Earlier focused regression run: **61 passed**, including research windows/continuation, risk verification and the High fixes.
- Final frontend production build: **passed**, Vite 6.4.5, 1,610 modules. PowerShell script policy required `npm.cmd`; sandbox directory restrictions required the approved build escalation. No execution policy was changed.
- No real Gemini/TTS generation, external write, upload, publishing or deployment was performed. Source/AI tests use labeled mocks and disposable SQLite/media roots. Existing user records were not changed.
- This change was not manually browser-tested; responsive/visual behavior is unverified beyond the successful build. No live biography/article-access or live draft-generation success is claimed.

## Limitations

Conservative literal theme/event matching may reject valid pages with different wording or dynamic layouts. Restricted, unavailable and ambiguous pages remain blocked; no access protections are bypassed. The evergreen offer requires source review before any subsequent generation. Limited-draft publishing remains intentionally unavailable even after local manual approval. Enable the configuration only when ready for supervised acceptance testing.
