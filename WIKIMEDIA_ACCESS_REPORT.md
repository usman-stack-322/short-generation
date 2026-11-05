# Wikimedia access fix and genuine photo acceptance

Date: 24 October 2026.

## Actual cause and header inspection

The previous normal provider used `AIShortsPlatform/0.2 (local user-operated research)` from `NETWORK_USER_AGENT`; no override or operator contact was configured. The previous diagnostic helper constructed an httpx client without that header and would send `python-httpx/0.28.1` (confirmed with the actual installed client's built request). This was an identification/configuration defect. The user's earlier server denial was `HTTP 403 / Please respect our robot policy`, reference **768589d**. A missing contact is a policy defect, but that message alone cannot prove the server's entire blocking rationale.

The operator supplied a real contact, now saved only in ignored `backend/.env` as `WIKIMEDIA_OPERATOR_CONTACT`. Other environment values were preserved. All Wikimedia paths now use `ShortsEnginePhotoBot/1.0 (configured real contact)`. A configured contact in `NETWORK_USER_AGENT` can be reused if the dedicated setting is blank; absent/placeholder contact stops requests locally. No fabricated operator identity or browser User-Agent is used.

## Changes

- New shared Wikimedia transport for Commons search/imageinfo, Wikidata subject lookup, Commons MediaInfo identity queries, preflight and image downloads. Core `public_get` accepts the explicit application header while retaining public-host/SSRF validation, redirect checks, bounded responses, `trust_env=False`, and default TLS verification.
- Thread and cross-process locks serialize this project's backend/helper requests, including acceptance runs with separate output roots. Shared lock/cooldown files live in the OS temporary directory under a project-derived hashed name. No system DNS/firewall/hosts/TLS settings changed.
- Successful Action API responses are cached for 900 seconds by default; configurable `WIKIMEDIA_CACHE_SECONDS`. Metadata cache is under the configured generated directory; existing binary photo caching stays intact. `maxlag=5` is sent for Action API calls. `--live-check` bypasses success cache for one genuine check, but never bypasses a provider cooldown.
- At most two attempts for temporary HTTP/network failures; short Retry-After delays are honored. Long numeric/date Retry-After stores a cooldown and returns rather than waiting/retrying early. HTTP 403 is terminal, records a shared cooldown of at least five minutes or the longer server delay, and does not cause automatic repeated scene/search calls.
- Streamed HTTP error bodies are retained within 8 KiB. The provider's sanitized message and reference are preserved, including references beyond the ordinary message excerpt. Helper output distinguishes configuration, DNS, TLS, provider denial, provider HTTP and provider API errors. Suppressed/cached requests are identified instead of being claimed as new TLS handshakes. Actual HTTP 200 with an API `maxlag` error is labeled **HTTP 200 / API maxlag**, not falsely reported as a wire HTTP 503.
- Actual live acceptance exposed a bounded first-five search problem: those hits were share-alike/signatures/non-photo material. Search now examines up to 20 hits and removes the synthetic trailing search hint `photograph`. MIME, reuse-license, restricted-license and known-generated-content checks remain. Real camera Make+Model is photographic metadata evidence where a file page lacks the literal word photograph; it is not an authenticity guarantee, never overrides synthetic exclusions, and never establishes subject identity.
- Exact-name search returned two identically named entries. The selected personality's existing **Football** category now disambiguates only when exactly one exact-name result has the matching category in its description. Generic categories and ambiguous matches remain rejected. No celebrity Q ID is hardcoded. Every subject photograph still requires its Commons `depicts` identifier to match the resolved subject.
- Acceptance helper explicitly records subject-matched versus contextual-only results. No demo/fixture image can establish live acceptance. Genuine script/SEO/narration checkpoints are reused; cloud generation and uploads remain disabled.

These choices follow [Wikimedia User-Agent policy](https://foundation.wikimedia.org/wiki/Policy:Wikimedia_Foundation_User-Agent_Policy) and [MediaWiki API etiquette](https://www.mediawiki.org/wiki/API:Etiquette).

## Actual live results

Executed with the existing project virtual environment in the normal Windows runtime, with authorized outside-sandbox execution for network comparison:

- Commons `https://commons.wikimedia.org/w/api.php?action=query&format=json&meta=siteinfo`: **HTTP 200**, fresh response, verified TLS, configured descriptive User-Agent.
- `commons.wikimedia.org`: DNS resolved `103.102.166.224` and IPv6; `upload.wikimedia.org`: `103.102.166.240` and IPv6.
- No proxy override, alternate DNS, IP/identity rotation, robots bypass or TLS bypass.
- Live diagnostic: `generated/photo-network-20261024T103406-fd7fcd/diagnostics.json`.
- Early attempts were NOT counted as photo success. Wikidata temporarily reported maxlag, then its recovered search exposed the namesake ambiguity. Early runs produced text cards only. A follow-up metadata console initially hit a Windows Unicode output error for one filename; the provider request itself succeeded, and the normal JSON helper handles Unicode filenames.

Final normal helper execution:

```powershell
cd "C:\Users\ua589\short generation\backend"
..\.venv\Scripts\python.exe tools\photo_acceptance.py --accept --serve-review
```

Final isolated evidence directory: `generated/photo-network-20261024T110701-37b5f4/`.

- Job: `ad438fac-2cee-4c8e-8aa4-e929f27d18eb`, **ready_for_review**, zero approvals, uploads false.
- One freshly retrieved, licensed subject photograph plus five neutral text cards. This does not claim six real photographs or a five-photo acceptance.
- Subject resolution: **Q11571**, photo `depicts: [Q11571]`. Camera metadata: Canon / Canon EOS 650D. This is metadata-based identity corroboration, not face recognition.
- [Photo source](https://commons.wikimedia.org/wiki/File:Cristiano_Ronaldo_-_Ballon_d%27Or_%28cropped%29.jpg): **Anish Morarji from St Albans, England**, **CC BY 2.0**, [license](https://creativecommons.org/licenses/by/2.0/).
- Source photograph date: **2015-01-15**; it concerns the 2014 award. It is labeled **Archive photo** and used illustratively with the historical 2008 script; it must not be described as a photograph taken at the 2008 event. Review source/context before approving publication.
- Actual image host: `upload.wikimedia.org`, file `Cristiano_Ronaldo_-_Ballon_d%27Or_%28cropped%29.jpg`. Fresh response **2,095,010 bytes**, SHA-256 `fb4568e60d02af52146ad4b78f10b6f1bac1133193e9fa4e630857e7a2ec066c`.
- MP4: `generated/photo-network-20261024T110701-37b5f4/media/videos/ad438fac-2cee-4c8e-8aa4-e929f27d18eb/short.mp4`.
- Real FFmpeg render, H.264/AAC, 1080x1920, full decode passed. Saved genuine script equality was checked against the source acceptance database; no new Gemini or cloud TTS request.
- `selected-photo.jpg` and `rendered-photo-frame.png` were actually viewed. The same photograph appears in the rendered frame with the archive label and readable subtitles. Required attribution is present in saved SEO description.
- Seven browser checks passed against the actual acceptance API: video playback advancing, authenticated photo preview, creator/license display, Commons source link, enabled replacement controls (not clicked), desktop/mobile layout, and the actual MP4 download. Downloaded file SHA-256 equals the rendered MP4. Browser evidence: `browser-report.json`, screenshots and `browser-downloads/` in the same evidence directory.
- `acceptance-result.json` was marked fully accepted only AFTER actual image/frame inspection and browser checks. This is genuine live-photo retrieval, not a fixture result.

## Review and runtime

**Review URL:** http://127.0.0.1:5212/videos/ad438fac-2cee-4c8e-8aa4-e929f27d18eb

**Isolated review API:** http://127.0.0.1:8012 — left running by `--serve-review`.

This is the existing isolated acceptance test account, not a Google account:
- Email: `evergreen-acceptance@example.com`
- Password: `IsolatedAcceptance123!`

The separate frontend was started with process-local `VITE_API_URL=http://127.0.0.1:8012` and Vite port 5212; no existing frontend environment file was changed.

The verified project backend on **http://127.0.0.1:8000** was restarted with the documented virtualenv/uvicorn command to load the supplied contact. Before stopping it, its command line and project virtualenv were verified and active generation count was zero. Only that project's backend/reloader was stopped; startup completed and `/api/health` returned 200. Existing data/settings were retained. No migration required for this fix.

## Tests and limits

- Final focused headers, caching/serialization, Retry-After, persistent denial, 403 body/reference, DNS/TLS separation, category disambiguation, camera/synthetic/identity gates and existing photo/helper regressions: **60 passed, zero failures**, one existing Starlette/httpx deprecation warning. `generated/wikimedia-focused-final.txt`.
- Broader research/evergreen run: an earlier run passed 100 tests. A later combined run had **102 passed, one failed**: `test_concurrent_daily_triggers_do_not_duplicate` observed worker call_count 0 after a StaleDataError. Its isolated recheck passed. This intermittent daily-preparation concurrency issue is recorded, not silently counted as an entirely green broad run, and no unrelated scheduler changes were made. `generated/wikimedia-final-tests.txt` / `generated/wikimedia-scheduler-recheck.txt`.
- Seven real-output browser checks passed. No user-connected browser was available; this was a separate headless Edge test session.
- No frontend source changes, so no frontend build was rerun for this backend/provider fix. No full backend-suite claim in this pass.
- Wikimedia can deny access or return maxlag again; honest identification is not an exemption from provider policy. Such failures remain explicit with no 403 retry loop. Photographic metadata cannot guarantee authenticity. The video remains unapproved and requires editorial review.

## Changed files

- `backend/app/core/config.py`, `backend/app/core/network.py`
- New `backend/app/services/assets/wikimedia.py`; `licensed.py`, `policy.py`
- `backend/app/services/pipeline.py`, `backend/app/api/assets.py` (pass existing personality category)
- `backend/tools/photo_acceptance.py`
- New `backend/tests/test_wikimedia_access.py`; updated `backend/tests/test_real_photos.py`
- Root/backend `.env.example`, README, this report and `REAL_PHOTO_INTEGRATION_REPORT.md`
- Ignored `backend/.env`: supplied operator contact only; never copied API keys into documentation/tests.
- Generated live diagnostics, isolated acceptance database/media and read-only browser helper/evidence.
