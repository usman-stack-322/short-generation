# Automatic verified evergreen fallback

Implemented and checked 24 October 2026 (Asia/Karachi). This report separates fixture/media validation from the live research attempt. **No live research-to-Gemini video success is claimed.** Uploads remain disabled.

## Implemented behavior

- An explicitly requested automatic/current-topic generation now follows latest → 7 days → 14 days → separate historical research when the channel enables evergreen fallback. News retrieval still performs new date-filtered requests for expanded windows. An inaccessible, unrelated, duplicate or insufficiently verified news candidate cannot end the search early as a usable selection.
- News access results are cached within the operation to avoid repeatedly fetching rejected stories across windows. Public source requests are bounded. Provider/network failures are distinguished from a successful search with no eligible candidate.
- Historical discovery uses public Bing RSS and a separate Google News RSS search bounded before the news window. Optional channel reference URLs provide stable starting points when search coverage is inadequate. Discovery snippets are not evidence: the actual public article must be accessible and focused on the configured person/business.
- The article parser extracts readable text, title/section, publication metadata and originating-wire signals. It selects explicit, dated historical claims with the subject central to the sentence and matching the channel niche/theme. Stored evidence contains supported excerpts, URLs, publisher identity, access-check time, publication date when available, event year and date precision. A year is not presented as an invented January 1 event date.
- Historical verification retains the existing authority, credibility, risk, claim-match, contradiction and independent-source rules. The only temporal difference is explicit historical policy: older publications can support a dated past event; this does not relax news freshness. Syndicated copies count once. Low-risk facts may pass the existing authoritative-primary-source rule; other claims need normal independent corroboration.
- Historical ranking uses source reliability (60%), direct relevance (30%) and the existing appeal component (10%), after verification gates. It is not a truth probability. Review Draft's separate existing ranking and 50/100 rule were not repurposed or weakened.
- Selection, evidence, content type, fallback reason and generation settings are persisted before script generation. The existing script → SEO → scenes → assets → narration → subtitles → FFmpeg → cover → review pipeline then runs. Historical prompts require supported facts, past-event framing and the event year. Output checks reject missing years, misleading current-news wording, extra numerical figures/dates, unsupported material claim categories, introduced sensitive claims, unsupported quotations/causal explanations and unverified present-day personal status. These are conservative checks, not a semantic proof of every sentence; manual factual review remains required. Historical SEO and the opening scene retain the year. No demo script is substituted for historical Gemini failure/unavailability.
- Historical metadata and fallback reason appear on the review page. Progress distinguishes expanded news windows, historical research, selection, script, narration and rendering. Held jobs have no selected content type and display the concise fallback outcome plus individual candidate reasons. A saved script or research result is never presented as a completed video.
- Topic/event identity uses normalized subject, claim type, year and event anchors, rather than only an exact headline. Incidental vote totals and reporting locations cannot make the same award into a new story. Channel-scoped database uniqueness reserves selected events. Duplicate candidates are skipped in favor of another eligible event; queued reservations and prior generated topics both count. Distinct dated events in the same historical profile can still be used; a source URL does not permanently consume all events in a profile.
- Existing operation-key uniqueness and job revision checks remain in force. Workers ignore duplicate deliveries after completion. Failed stages preserve their checkpoints and use the existing explicit retry flow.
- Research-only retries can research/select historical content for the existing held job but still do not invoke Gemini. They refresh corrected channel reference URLs/niche/fallback settings while retaining duration, voice and job identity. Explicit generation is required afterward. Manual-topic workflows do not silently invoke historical fallback.
- Limited-verification drafts remain an explicit action under `REVIEW_DRAFTS_ENABLED`. They are not promoted to verified, and their rendering/retry labels, approval rules and publishing blocks remain separate.

## Channel configuration

Open **Channels → Configure**:

1. Set the channel niche, or leave it blank to use the assigned personality/theme category.
2. Optionally enter public historical/reference article URLs, one HTTPS URL per line. Credential-bearing URLs and unsupported schemes are rejected; fetch-time SSRF protection still applies.
3. Enable **Automatically research verified historical stories when no usable news is found**.
4. Optionally enable **Prepare daily videos automatically**, set duration (30/45/60), daily target, language, narrator and voice style. Assign at least one enabled theme to that channel.

Both switches default to **off** for all existing channels. No existing channel was opted in by this implementation.

Daily preparation did not previously exist: the old scheduler only processed uploads. The new preparation worker uses the existing generation API/queue with durable keys for channel + UTC day + target slot. It prepares up to the saved daily target while the backend is running, starting immediately for an unfilled enabled day's slots. Repeated/concurrent ticks and restarts do not create another job for the same slot. Failed/interrupted jobs remain visible and use an explicit stage retry rather than an endless automatic failure loop. Preparation works even while YouTube publishing is disabled. It never approves or uploads a video.

Example environment files now document:

```dotenv
EVERGREEN_SEARCH_URL=https://www.bing.com/search
EVERGREEN_MAX_SOURCES=12
```

The source budget is validated at 1–20. No new paid service or mandatory API key was added. Existing Gemini, narration and asset configuration is reused. `REVIEW_DRAFTS_ENABLED` remains separate. `YOUTUBE_UPLOADS_ENABLED` was not enabled.

## Migrations and preservation

- `0009_auto_evergreen`: opt-in channel switches, niche/duration and nullable channel-scoped topic/event reservations.
- `0010_evergreen_references`: optional channel reference URLs. Kept separate because the running reload backend had already applied 0009 during development.
- Both migrations are additive. Existing topics retain null event identities and are not merged or deleted. The normal migration runner creates pre-upgrade SQLite backups.
- A disposable database was upgraded to 0008, populated with existing workspace/channel/theme/topic rows, then migrated through 0009 and 0010. Names and topic rows were preserved, new switches defaulted off, and `PRAGMA foreign_key_check` passed. Evidence: `generated/verify_evergreen_migration.py`.
- The running project's database was read at `0010_evergreen_references`: five existing channels, zero automatic-preparation switches enabled and zero fallback switches enabled. Existing credentials/settings were not replaced. No uploads, deployment or publication occurred.

## Actual automated/build results

- Final full backend suite: **250 passed**, **0 failed**, one existing Starlette/httpx deprecation warning, 119.69 seconds. Includes previous approval/corroboration/idempotency/privacy fixes, research windows and Review Draft regressions.
- **28 evergreen regressions passed as part of that final suite**; an earlier standalone subset passed 21 tests. Covers fresh-news preservation, historical selection and pipeline checkpoints, no eligible fallback, settings disabled/manual-only behavior, NBA/Stephen A. Smith/Gilbert Arenas/Gil’s Arena/boxing/business relevance, accessibility, syndication/conflicts, duplicate event selection, distinct events in one profile, held outcomes, channel configuration permissions, scheduled/concurrent idempotency, language/duration settings, render-failure preservation, historical framing/claim grounding, event identity, corrected-reference retry and input validation.
- A focused mixed regression run also passed **60 tests** before the final two evergreen tests were added.
- Final frontend production build: **passed**, Vite 6.4.5, 1,610 modules. Used `npm.cmd run build` with the approved sandbox escalation; no security/execution-policy setting was changed.

## Browser results — fixtures, not live providers

An isolated backend on port 8007, frontend on port 5180 and dedicated headless Edge profile were used. The fixture blocks external socket/HTTP generation, supplies labeled research/script/voice/render results and uses a prerecorded playable MP4 for preview checks. It does not prove live AI or new media generation.

**12 checkpoints passed**, including desktop/mobile setting visibility, saving the switch, progress display, automatic verified selection, source/year display, playable 1080×1920 preview and disabled limited-draft publishing. Screenshots were inspected for desktop/mobile layout and overflow. Evidence: `generated/auto-evergreen-browser/report.json`, screenshots in the same directory, and `generated/verify_auto_evergreen_ui.py`.

## Real local media result — offline research/script fixture

A separate normal-API job used explicit offline research/script fixtures, original local graphics, **real local pyttsx3 narration**, **real FFmpeg**, subtitles and cover generation. External generation was blocked. The helper initially failed at voice enumeration because its subprocess module path differed from documented backend startup; correcting the helper's `PYTHONPATH` and retrying **the same job** resumed from the saved voice checkpoint. Production TTS was not modified for this helper issue.

- Job: `575c3fac-60b9-453e-9848-bcc7ab511582`.
- MP4: `generated/auto-evergreen-offline/media/videos/575c3fac-60b9-453e-9848-bcc7ab511582/short.mp4`.
- Ready for review; 30.000 seconds; 1080×1920 H.264 video and AAC audio.
- Full audio/video decode passed. Source narration was 32.44 seconds and the existing tempo fitting mapped it into the narration window; SRT ends at 29.4 seconds and contains the event year. Audio mean volume was −20.0 dB, peak −0.4 dB, with nonzero source waveform RMS. A rendered frame was inspected for readable captions/safe margins. No human listening-quality assessment is claimed.
- This is visibly/spoken-labeled **OFFLINE TEST FIXTURE**, not a live factual Short. It must not be published. Evidence: `generated/auto-evergreen-offline/result.json`, `probe.json`, `frame.png`, render logs and `generated/run_offline_evergreen_render.py`.

## Live research-to-video attempt — BLOCKED before Gemini

The configured application detected Gemini, its primary/fallback models, local narration, Commons assets and RSS. Uploads were false. A disposable workspace/database/channel used the normal current-topic generation endpoint, 30-second English settings, local narration only and a two-source access budget. No real workspace channel settings were changed.

- Job: `be6d3173-3033-48b3-b3c8-8871ffcea44c`, isolated database `generated/auto-evergreen-live/acceptance.db`.
- Live latest/7/14-day news research produced no usable verified news.
- Separate historical research read the configured Sky Sports and UEFA references. Sky Sports supplied the dated 2008 award claim, but its two matching excerpts were correctly counted as **one independent publisher/source**. The UEFA reference returned a read timeout in the application's public fetcher. No second accessible independent source or usable authoritative primary source remained.
- Final state: **verification_required**, no selected topic, no script, no MP4. The actionable no-eligible-fallback explanation and candidate reasons were saved.
- Gemini was not called: the job stopped at the selection gate before the script branch. No real Gemini output, narration or render is claimed for this attempt. This result does not establish anything about earlier provider usage outside this attempt.
- Read-only diagnostics also found unrelated Bing results (rejected by focus checks) and HTTP 403 from Wikipedia's API. Restricted/unavailable pages were not bypassed. Discovery success alone is never treated as verification.

Source links: [Sky Sports historical award report](https://www.skysports.com/football/news/4575921/ronaldo-wins-ballon-dor), [UEFA historical award reference](https://www.uefa.com/uefachampionsleague/news/01d4-0e707fe4919f-772c18bc5bc3-1000--ballon-d-or-crowns-ronaldo-s-golden-year/).

Smallest remaining live-acceptance action: restore access to the authoritative reference, or configure another accessible independent credible article supporting the same specific event; retry research on the held job, then choose explicit generation after a verified selection. Do not mark the Sky-only story verified or use a limited draft as automatic fallback. Evidence: `generated/auto-evergreen-live/result.json`, `manifest.json`, `generated/run_auto_evergreen_live.py` and source diagnostic files.

## Changed application files

- `backend/app/models.py`, `backend/app/schemas.py`, `backend/app/core/config.py`, `backend/app/core/network.py`.
- `backend/app/database/migrate.py`, `backend/migrations/versions/0009_auto_evergreen.py`, `0010_evergreen_references.py`.
- `backend/app/research/evergreen.py`, `grounding.py`, `live.py`, `verification.py`, `claims.py`, `sources.json`.
- `backend/app/services/automatic_research.py`, `preparation.py`, `scheduler.py`, `pipeline.py`, `job_research.py`, `generation_requests.py`, `scene_planner.py`.
- `backend/app/api/channels.py`, `videos.py`, `backend/app/ai/scripts.py`.
- `frontend/src/pages/Channels.jsx`, `CreateShort.jsx`, `Review.jsx`, `frontend/src/components/SourceCard.jsx`.
- Both `.env.example` files, `README.md`, `backend/tests/test_auto_evergreen.py`, this report; disposable validation helpers/evidence under `generated/`.

## Remaining limits

Default public discovery may return no usable direct source; some Google RSS results are aggregator pages rather than accessible publisher articles. Unknown publishers, dynamic/restricted articles, ambiguous or undated claims and insufficient corroboration remain held. Optional reference URLs improve discovery coverage but do not bypass verification. Historical extraction is conservative and currently selects year-dated claims from readable article sentences using English claim patterns, not arbitrary PDFs/tables or a model-invented biography. Output still uses the job's chosen language, but non-English historical generation was not live-validated; the text checks are not an exhaustive multilingual factual verifier. It may miss valid differently worded claims or reject a script that needs a narrower rewrite. Daily preparation uses UTC daily slots and requires an enabled assigned theme and a running backend. Fully live generation and subjective voice quality remain unverified for the blocked acceptance case.

## Companion: real-photo integration

The shared scene collector now supports conservatively licensed, identity-checked Commons photography, optional contextual Pexels photography, retained credits, neutral text fallback and revision-safe review controls. Actual provider availability and the distinction between live retrieval and fixtures are documented in [REAL_PHOTO_INTEGRATION_REPORT.md](REAL_PHOTO_INTEGRATION_REPORT.md). Live real-photo acceptance remains blocked by Commons DNS and absent optional Pexels credentials; it is not claimed as completed.

## Live acceptance follow-up — 24 October 2026

**A genuine isolated research → live Gemini → local narration → subtitles → video → browser preview/download flow now passed. Authentic internet-photo acceptance remains BLOCKED.** The video uses the expressly permitted neutral text-card fallback, not demo research/script and not substituted photographs. Earlier results above remain historical records, not claims about this new run.

### Why the old attempt held

Inspected `generated/auto-evergreen-live/acceptance.db`, its saved candidates, research trace, manifest, result and the actual acceptance helper. That helper explicitly set `EVERGREEN_MAX_SOURCES=2`. Both configured references occupied the two returned discovery slots: Sky supplied two matching excerpts of the same 2008 award report; UEFA timed out. The exception handler did not terminate the article loop. However, discovery sliced the combined reference/search list before URL deduplication and credibility/access filtering. Later alternatives were not tried. Thus both configured references were attempted, but the broader discovery results were **not** proven exhausted. Sky correctly counted once; the original hold was legitimate for that restricted attempt.

### Implemented corrections

- Discovery keeps a bounded pool of alternatives (up to four times the article budget, capped at 80) and deduplicates canonical URLs before article access. A separate focused historical query supplements broad Bing and date-bounded Google News discovery.
- Publishers are interleaved. Repeated publisher coverage cannot take every access slot before another publisher is considered. Unknown/untrusted publishers and duplicate URLs do not consume credible-article fetch slots.
- Historical/discovery fetches use 10-second HTTP timeouts and at most two attempts for transient transport/429/5xx failures. Permission/restricted responses are not repeatedly retried; long Retry-After responses are respected. Article traversal has a 150-second soft cutoff checked between articles, in addition to the configured source count. This is not a hard OS/DNS wall-clock deadline.
- Failed articles and ineligible claims continue to other options within these bounds. Persisted diagnostics distinguish network/provider failures, irrelevant candidates, missing dated claims, access counts, remaining unattempted candidates and budget exhaustion versus candidate exhaustion. Diagnostics survive even an empty candidate list. The review UI shows a concise budget/network explanation alongside existing per-candidate reasons.
- Added explicit Press Association/PA Media origin matching to existing syndication checks. No verification threshold, event matching, source-authority rule, duplicate-generation protection or approval rule was relaxed.
- The genuine run exposed a second defect: JSON mode requested scene hints only through prose. The fallback returned JSON that failed mandatory visual-keyword/scene validation. The script request now supplies an explicit supported JSON schema with all required sections and 6–12 scenes. Local validation remains in place. Reference: [official Gemini structured output documentation](https://ai.google.dev/gemini-api/docs/structured-output).
- The next real structured response was rejected by historical grounding. The historical prompt now explicitly lists supported and forbidden claim categories; rejection errors identify unsupported categories. The safety guard was not loosened. One final bounded same-job script-stage retry passed. Script is committed before separate SEO work, so a provider error does not discard research or duplicate a job.
- Photo integration was inspected end to end: Commons/Wikidata identifiers and licenses, optional Pexels, safe downloads/cache, scene assignments, credits, review controls and FFmpeg consumption already exist. Pexels retry handling now respects long rate-limit Retry-After values. A real rendered-frame inspection exposed an unsupported bullet glyph in the neutral label; it was replaced with ASCII and only the asset/video stage was rerun, with cloud generation blocked in that helper.

### Genuine acceptance evidence

- Isolated channel: `ISOLATED Ronaldo Evergreen Acceptance`; fallback enabled, English, 30 seconds, local narration. Database: `generated/live-fallback-acceptance/acceptance.db`. Real workspace settings/data and credentials were not changed. This isolated job is not imported into the normal workspace queue.
- **Job:** `ad438fac-2cee-4c8e-8aa4-e929f27d18eb`.
- **Selected candidate:** `7ac64783-1c4e-40e7-aa70-8d6ce7739e5c`.
- **Topic:** Cristiano Ronaldo's 2008 Ballon d'Or win, ahead of Lionel Messi and Fernando Torres. Historical framing uses **2008**, not an invented January 1 event date or current/breaking-news framing.
- Sources supporting the same specific award/year/outcome: [Sky Sports](https://www.skysports.com/football/news/4575921/ronaldo-wins-ballon-dor) and [The Guardian](https://www.theguardian.com/football/2008/dec/02/ronaldo-manchesterunited). Both articles were retrieved by the application and their claim excerpts/access metadata saved. UEFA references continued to produce connection/read failures and were not counted as accessible corroboration.
- Normal verification: LOW-risk award; three matched excerpts, **two distinct credible publisher groups**. Sky's duplicate URL/excerpt counted once. Saved metadata supplied no shared named originating wire and the configured similarity/conflict checks passed. This is the system's evidence-based independence assessment, not proof of the absence of undisclosed syndication; Guardian includes an agencies contribution. Manual editorial approval remains mandatory. No source or verification flag was fabricated or manually forced.
- Historical research diagnostics: 48 discovered rows, 12 credible article attempts, two accessible articles; traversal reached its budget with 21 alternatives unattempted. Those two articles supplied a usable verified selection, so the job continued normally. A budget limit is not reported as global Internet exhaustion. Details and rejected-source reasons: `generated/live-fallback-acceptance/evidence-summary.json` and persisted research candidate data.
- Research and selected candidate were preserved across retries; the acceptance database still contains **one video job**. Initial script attempt: three primary ReadTimeouts, then fallback JSON failed visual hints. Schema retry: primary timeout/503 failures, then fallback structured data failed the grounding guard. Final narrowed-prompt retry: primary HTTP 503/UNAVAILABLE or timeout responses, then **`gemini-3.5-flash-lite` succeeded**. Primary remained **`gemini-flash-latest`**; no `.env` model was overwritten and no retry loop was added. SEO also completed after bounded primary failures through the configured fallback.
- Script provider saved on the job: **Gemini (`gemini-3.5-flash-lite`)**. No mock/development script. Actual returned structured sections/scene hints: `generated/live-fallback-acceptance/script-response.json`; saved script, scenes and SEO are in the isolated database/result. The script passed the existing historical date/numeric/sensitive-claim/claim-category guards. It is a concise acceptance narration; editorial polish and publication approval are separate.
- Narration: **Local narrator (pyttsx3)**. No celebrity voice cloning or cloud TTS. Output: **ready_for_review**; no approval/upload.
- **MP4:** `generated/live-fallback-acceptance/media/videos/ad438fac-2cee-4c8e-8aa4-e929f27d18eb/short.mp4`.
- Media: 30.000 seconds, 1080×1920, H.264/AAC, full FFmpeg decode passed. Audio signal: mean −20.2 dB, peak −0.3 dB. Captions include the historical year and final narration phrase. Frames at 4/15/26 seconds inspected for readable captions, labels and safe margins. No human listening-quality evaluation is claimed; AAC playback, decoding and non-silent signal were checked.

### Photo provenance and exact remaining blocker

The real collector ran, but `commons.wikimedia.org` still fails DNS resolution with Windows **11001**. The optional Pexels key is absent. **Zero real photographs were downloaded.** The six persisted assets are `Local text card`, `Original text layout`, with scene numbers, generated local paths and specific provider-failure reasons. They are labeled “No event photograph.” No photograph/photographer/license credit was invented; no external-photo credits are required for these locally created text layouts.

Commons remains the primary source and no-key operation is supported when connectivity works. Optional Pexels remains contextual-only. Configured licensing/identity checks, attribution, upload/replace/remove controls and revision invalidation pass fixture regressions; their successful live retrieval/real-photo crop/scene relevance remain **unverified**. Current official references checked: [MediaWiki imageinfo](https://www.mediawiki.org/wiki/API:Imageinfo), [Pexels API](https://www.pexels.com/api/documentation/). Restore Commons DNS/access or configure a valid free Pexels key, then regenerate **assets/video only** on this acceptance job to test real photos without another research/script call. No host/IP override or protection bypass was introduced.

### Actual validation results

- Final full backend suite: **288 passed, 0 failed**, 116.68 seconds, one existing Starlette/httpx deprecation warning. Focused research/photo/High-fix regressions: **73 passed**; Gemini structured-schema regressions: **15 passed**; focused historical/Gemini checks after prompt tightening: **49 passed**.
- Frontend production build: **passed**, 1611 modules. Approved layout/styles retained; only the held research explanation was added.
- Browser: **8 checkpoints passed** using dedicated headless Edge, frontend `127.0.0.1:5201` and backend `127.0.0.1:8101`. **Five checkpoints inspected the genuine completed job:** historical topic/source links, real MP4 playing with advancing time, a fresh authenticated download that fully decodes, desktop review and mobile review without horizontal overflow. **Three separate clearly labeled fixture checkpoints** checked the budget/network hold explanation and desktop/mobile display. The browser backend used a disposable database snapshot and external-network guards; it did not substitute any genuine job research/script/media or perform generation/upload actions. Evidence: `generated/live-fallback-acceptance/browser-report.json`, screenshots and fresh download directory.
- A media-only rerender corrected the fallback label, reusing saved real script/SEO/audio with cloud generation explicitly forbidden. It did not create a job or rerun research.
- No new migration in this follow-up. Existing schema stays `0011_photo_assets`. Uploads remain **false**, approvals unchanged, no deployment/publication and no real channel content changes. Live calls used the user's confirmed free-tier authorization; provider-side token accounting/billing for timed-out requests was not independently established.

### Follow-up changed files

`backend/app/core/network.py`, `backend/app/research/evergreen.py`, `verification.py`, `grounding.py`, `backend/app/services/automatic_research.py`, `backend/app/ai/scripts.py`, `backend/app/services/assets/licensed.py`, `backend/app/api/assets.py` (label only), `frontend/src/pages/Review.jsx`, and corresponding `test_auto_evergreen.py`, `test_gemini_reliability.py`, `test_real_photos.py`. Acceptance helpers/artifacts are under `generated/` and `generated/live-fallback-acceptance/`.

**Result:** genuine live text-card fallback Short is ready and browser-verified. Successful live internet-photo integration is the remaining externally blocked acceptance component; it is not claimed passed by fixture tests.
