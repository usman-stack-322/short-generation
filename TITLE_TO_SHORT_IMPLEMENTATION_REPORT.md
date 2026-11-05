# Latest: Title to AI Short live English flow verified — 29 October 2026

See [live acceptance report](TITLE_TO_SHORT_LIVE_ACCEPTANCE_REPORT.md) and [checkpoint](TITLE_TO_SHORT_CHECKPOINT.md). Working output and actual research, voice, caption and complete preview/download evidence are available. 68 regressions and frontend build passed. Direct listening remains pending; Urdu/Roman Urdu stop before generation without a compatible narrator. Existing pilots preserved; uploads/scheduling disabled.

## Historical report retained below

# Title to AI Short — implementation and verification (29 October 2026)

The feature is implemented in the existing React/Vite + FastAPI application at http://127.0.0.1:5173/title-to-short . The final backend and frontend are running locally. Uploads and scheduling remain disabled. Existing Ronaldo r21, Messi r20 and original Henry r32 media hashes and database revisions are unchanged.

## Behavior delivered

- Four required inputs: title/topic, 30/45/60 seconds, English/Urdu/Roman Urdu, educational/storytelling/documentary. The model selects one narrow angle rather than generating a long video or squeezing a full history into a short.
- Bounded title analysis and repair: a live model initially proposed a 45-minute overview. That finding led to a deterministic broad/long-angle rejection guard and one repair attempt. Rejected angles never become scripts. The final live attempt selected a narrow naming-origin question, not a timeline.
- Actual web discovery followed by bounded public HTTPS article retrieval. The existing trusted-source registry, academic/government domains and explicit institutional sources gate discovery. At least two reliable accessible domains are required. Snippets, invented URLs or inaccessible articles never count as completed research. Private destinations and redirects outside the approved source host family are blocked. Optional official Brave search adapter is available when public RSS discovery cannot supply suitable URLs; it is not activated without explicit server configuration.
- Source-backed script and scene planning: narration, concise on-screen summary, visual description, image query, AI image prompt, motion and transition per scene. All narration concatenates into one duration-budgeted script. Exact source excerpts and claim IDs are checked, followed by a second source/language audit. Urdu uses native script; Roman Urdu uses Latin script. Scene times are provisional until replaced by final narration timings.
- Explicit script review before rendering. Per-scene narration can be edited and saved. Final source checks run again before assets/speech/rendering. Unsaved edits disable rendering. Stale or concurrent writes return 409 instead of silently overwriting.
- Two individual-scene actions: visual regeneration preserves narration; source-checked scene rewriting updates only the requested scene and returns to script review. Other scenes/assets remain unchanged; old renders remain preserved.
- Relevant unique licensed photos through existing Commons/Pexels integration, original proportions, clean-source images, restrained camera motion and smooth transitions. Photo creator, license, URLs and modifications are retained. AI image prompts are planning outputs only: AI image generation is not configured and no generated imagery is presented as authentic evidence. Missing permitted visuals fail explicitly; no placeholder cards/stock success is invented.
- Actual narration through an explicit local narrator by default, reviewed Kokoro bm_george for English when available. Compatible Urdu narration is required for Urdu/Roman Urdu. No automatic paid voice fallback and no silent narration. Script/audio-bound native timestamps are mandatory; unsupported estimated captions are not marked synchronized. Speech must occupy 80% of the requested budget and finish inside its limit; excess speech requests an edit instead of truncation or forced acceleration.
- Existing clean renderer: 1080×1920, 30 fps, AAC audio, box-free captions. Ready status requires a successful full-file decode. Actual narration determines the scene boundaries and output duration. Final preview/download, version history, downloadable photo credits and research sources use authenticated media sessions, with Range support. No upload task is created by this feature.
- Durable workspace/creator-scoped drafts, visible saved stage progress, explicit errors/retries and restart recovery. Owners see workspace drafts; editors see their own drafts. API keys stay on the server.

## Checks actually performed

Final combined regression: **50 passed**, zero failures, one existing Starlette/httpx deprecation warning. Evidence: generated/title-to-short-verification/final-regression.xml. Modules: title shorts, native alignment, quality revision, scene motion review, local voice cost boundary.

The regression includes real FFmpeg rendering and authenticated cookie preview, Range request, exact-byte download, source/credit downloads and complete decoding. Its narration and research were clearly identified synthetic/test fixtures in an isolated temporary database, not a live researched production generation. Those fixtures are not delivered or represented as a completed user short. Tests also cover missing keys, inaccessible research, invented supporting excerpts, unsupported factual edits, language/writing systems, review boundaries, stale requests, cross-user/anonymous access, failed narration, broad-angle repair, and preservation of other scenes during individual regeneration.

Final frontend production build passed: Vite v6.4.5, 1617 modules. Browser verification used installed Edge on the real local frontend/API. The title form and actual saved acceptance draft rendered without page errors. The final research error is visibly displayed on desktop and mobile, the unverified angle is labeled Proposed angle, and the mobile page has no horizontal overflow. This does not claim successful live script review/voice/render playback; the real example was correctly blocked before those stages.

Database migration 0014_title_shorts applied successfully. Automatic SQLite backup: backend/backups/ai_shorts-before-day2-20261028T183534912010.db. New table: title_short_drafts. Current pilot preservation, version and disabled flags were read and hash-verified in generated/title-to-short-verification/installation.json.

## Actual live acceptance outcome and blockers

Saved example: http://127.0.0.1:5173/title-to-short/64011c1f-3b14-4425-8c53-e55dbe50ab52 . Input: The Complete History of Artificial Intelligence, 45 seconds, English, educational.

The initial configured Gemini request timed out; a minimal provider probe returned HTTP 503 UNAVAILABLE. The final implementation reuses the application's bounded Gemini retry policy with server-configured fallback only. A later live attempt succeeded at analysis and proposed: Who coined the term Artificial Intelligence at the 1956 Dartmouth Workshop, and how did it get its name? This is an unverified research angle, not a factual claim approved by this report.

**Current blocker: real public web discovery did not yield the required two accessible reliable source domains.** One preceding attempt also encountered source DecodingError. The final attempt stopped at researching with an explicit error, zero accepted sources, zero scenes and no script, voiceover or completed video. No successful acceptance MP4 is claimed or simulated. Configure working public search/source access, or explicitly configure TITLE_SHORT_SEARCH_PROVIDER=brave and BRAVE_SEARCH_API_KEY, then retry this saved draft. No subscription, purchase or Brave API request was made.

Installed system speech inventory was actually inspected: Microsoft David and Microsoft Zira, both en-US; no installed Urdu narrator was found. Therefore Urdu/Roman Urdu live rendering currently also needs a compatible Urdu system voice, or separately authorized/allowlisted multilingual ElevenLabs configuration. Reviewed Kokoro is English-only. No cloud voice, AI-image generation, purchase, upload or publication was attempted. Roman Urdu text is passed to a compatible Urdu narrator; pronunciation still needs listening review. Direct listening was unavailable in this session.

AI-generated visuals are not connected; permitted-photo retrieval is the supported visual path. Live asset retrieval, live voice synthesis and live completed-video playback for the new example remain unverified because research correctly stopped first. Existing pilot playback results are not reused as proof of new-feature acceptance.

## Configuration and continuation

Read TITLE_TO_SHORT.md for exact server variables, licensing/attribution behavior and workflow. Gemini uses the existing configured key/model. Optional Brave requires a separate key; default public RSS discovery has no added subscription. Local voice remains the default cost boundary; an explicit allowlisted cloud voice configuration requires authorization.

Implementation: backend/app/services/title_shorts.py, backend/app/api/title_shorts.py, additive model/migration, auth media-cookie scope and startup recovery; frontend/src/pages/TitleShort.jsx and TitleShort.css with route/sidebar integration. Existing rendering, speech, asset, authentication and UI patterns are reused.

Evidence directory: generated/title-to-short-verification/ . Key files: live-draft.json, live-retry.json, live-final.json, final-ui-check.json, final-error-desktop.png, final-error-mobile.png, title-form.png, live-research-probe.json, installation.json and final-regression.xml. Failed live attempts remain visible; previous pilot revisions were not overwritten. Exact machine continuation: generated/title-to-short-verification/checkpoint.json.

Next: resolve search access/configuration, retry the saved draft, inspect actual source-backed script, and explicitly render only after script review. Then verify live photo relevance, narration pronunciation, caption sync, complete preview/download playback and visual quality. Keep uploads disabled.
