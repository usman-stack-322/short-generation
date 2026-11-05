# Automatic real-photo integration

Implemented 24 October 2026. **Live real-photo acceptance is BLOCKED, not passed:** the local host cannot resolve `commons.wikimedia.org` (`socket.gaierror`, Windows 11001), including an elevated read-only probe. The optional Pexels key is not configured. No live photo was downloaded and no finished video containing live-retrieved photographs is claimed. The real FFmpeg fallback render and fixture photo checks below are separate results.

## Implemented

- Existing news, historical/evergreen and explicit Review Draft pipelines reuse the same scene asset collector. Commons is always the primary live source; optional official Pexels search supplies contextual stock photography. `ASSET_PROVIDER=demo` stays offline and produces labeled neutral text cards.
- Commons uses official imageinfo metadata and structured MediaInfo depicts identifiers, plus Wikidata subject lookup. Ambiguous name matches are skipped. Identity-specific selection requires the selected subject identifier in depicts and a matching name in descriptive metadata. It does not treat a search ranking, shared surname or generic player as identity evidence. Sparse/uncertain identity metadata produces contextual photography or a text card, not a guessed person.
- Real-photo metadata is required by default. Known AI-generated/assisted imagery, common generator names, drawings, paintings, screenshots, composites and face-swap/deepfake metadata are rejected. These checks cannot guarantee authenticity. Missing metadata is handled conservatively.
- Automatic licenses: documented public domain/CC0 and supported CC BY versions with creator/license URL. Share-alike, noncommercial, no-derivatives, unknown rights and additional declared restrictions are excluded. Public availability alone is never treated as permission.
- Each selected photo retains provider, original file/source metadata, photographer, source page, download URL, license/version, full required credit, modification notes, dimensions, available date, content hash and scene number. Required credits include the title when supplied. Full credits are retained in JSON provenance rather than relying on the legacy 500-character attribution field.
- Required credits appear in the saved SEO description and review screen. Publishing validates their presence. Existing upload code avoids adding the same new credits again; older asset credits remain supported. Description-budget failures stop rather than truncate required attribution. Uploads remain disabled.
- Photos are downloaded only from fixed approved provider hosts through the existing HTTPS/public-DNS/redirect guard. Responses are size bounded; Pillow accepts only JPEG/PNG/WebP, minimum 400 pixels per side, at most 40 megapixels. Downloads are cached, revalidated and deduplicated by URL and content hash, including replacement operations. Search budgets are bounded to eight distinct queries; retryable fetches have at most two attempts. Long Retry-After responses are not bypassed.
- Images are proportionally fitted onto a padded vertical canvas; faces and watermarks are not edited. Existing FFmpeg narration, subtitles, crossfades and gentle motion consume these local scene images. Photos are labeled Archive photo or Illustrative image. Automatic selection never claims a specific-event photograph. Missing photos become neutral text cards. Image availability cannot upgrade story verification.
- **Review your Short → Scene photographs** has authenticated image previews, source/license links, find replacement, remove-to-text-card, and file upload with rights/authenticity attestation. Upload identity/event association remains a human review responsibility. Failed replacement preserves the current image. Changes increment the existing content/media revisions, invalidate approvals and mark the video outdated; Regenerate video is required before fresh approval. No image-edit route invokes Gemini. Held research cannot be cleared by editing assets. Read-only/cross-workspace access remains blocked by existing authorization.
- Approved navigation, layout, themes and existing research/generation protections are preserved.

## Setup and migration

Use these existing backend-only variables; real `.env` credentials were not changed:

```dotenv
ASSET_PROVIDER=commons
PEXELS_API_KEY=
YOUTUBE_UPLOADS_ENABLED=false
```

Commons requires working access/DNS for commons.wikimedia.org, www.wikidata.org and upload.wikimedia.org. Optional Pexels uses api.pexels.com and images.pexels.com. Fix Commons DNS/internet access, or configure a Pexels key for contextual images, then retry assets on an eligible existing job. You can also upload a photograph whose reuse rights you hold. No billing or paid generation is required by this implementation.

`0011_photo_assets` adds only `assets.provenance` (non-null JSON text, default `{}`). The existing startup migration runner takes a SQLite backup before upgrade. An isolated copy was upgraded from 0010; channels, personalities, topics, jobs, scripts, voice and video row counts were preserved and foreign-key checks were empty. The running project reloader subsequently applied 0011; the real database still contains its existing five channels. Existing assets/references were not merged or deleted. `/api/health` on localhost:8000 returned 200.

## Changed files

- `backend/app/services/assets/licensed.py`, `providers.py`; new `policy.py`, `credits.py`.
- New `backend/app/api/assets.py`; `backend/app/main.py`, `models.py`, `services/pipeline.py`, `youtube/upload.py`, `video/renderer.py`.
- `backend/app/database/migrate.py`; new `backend/migrations/versions/0011_photo_assets.py`.
- New `backend/tests/test_real_photos.py`.
- New `frontend/src/components/ScenePhotos.jsx`; `frontend/src/pages/Review.jsx`, `frontend/src/styles.css`.
- Root/backend `.env.example`, `README.md`, this report and the companion link in `AUTO_EVERGREEN_FALLBACK_REPORT.md`.
- Isolated local verification harnesses/artifacts under `generated/photo-acceptance/`, `generated/verify_photo_fallback.py`, `generated/photo_browser_app.py`, `generated/verify_photo_browser.py`.

## Actual validation

- Photo regression suite: **30 passed**, covering compatible/rejected licenses, missing attribution, correct subject/depicts matching, namesake/unknown identity rejection, synthetic-image markers, absent Pexels credentials, cache/padding/credits, invalid bytes/hosts, binary duplicates, replacement hash exclusion, provider failure, bounded retries, safe upload, stale edits/approvals, concurrent stale approval sessions, cross-workspace previews/actions and verification holds.
- Full backend suite: **280 passed, 0 failed**, final run 106.16 seconds. This includes the existing High/Medium/Low regressions and all 30 final photo tests. One existing Starlette/httpx deprecation warning; no application warning was suppressed.
- Frontend `npm.cmd run build`: **passed**, Vite 6.4.5, 1611 modules. The sandboxed initial build failed on parent-directory access; the same build passed outside that filesystem restriction.
- Headless Edge, separate origins `127.0.0.1:5199` and `127.0.0.1:8099`, isolated SQLite database, transport guards blocking external HTTP/sockets: **8 browser checkpoints passed**. Desktop/mobile scene controls, image preview, decoded authenticated MP4 download while review stays open, failed replacement preserving assets, approval-invalidating removal, upload form, actual multipart upload button with fixture credits, and persistence after refresh. Screenshots inspected for mobile layout/readability and the fallback video frame. Fixture upload uses a labeled test JPEG to exercise transport; it is not evidence of an authentic real photograph. Provider success is not inferred from this fixture.
- Real local FFmpeg render: **passed** using an existing explicitly OFFLINE research/script fixture and cached real local Windows narration, with newly generated neutral text fallback scenes. 30 seconds, 1080x1920, H.264/AAC; full decode passed, authenticated preview/download passed. Mean audio -20.0 dB, peak -0.4 dB. Readable captions and safe margins were visually inspected; a missing bullet glyph in the fallback label was corrected to ASCII and the render rerun. This is not a live news/Gemini/photo acceptance result.
- Fixture job: `575c3fac-60b9-453e-9848-bcc7ab511582` in an isolated copied database only. MP4: `generated/photo-acceptance/downloaded.mp4`. Browser download and screenshots/report are also under `generated/photo-acceptance/`.
- Actual Commons API access: **BLOCKED** by DNS 11001, not an empty-success search. Read-only public DNS probes showed Wikidata/CDN resolving while the Commons canonical host did not. An official mobile endpoint probe redirected/fell back into the same resolution problem; no host/IP override or protection bypass was introduced.
- Pexels live API: **BLOCKED/not configured**. Optional-key absence is fixture-tested and does not prevent attempting Commons.
- No Gemini/cloud narration requests, no real upload/publish, no deployment, no real credential changes. `YOUTUBE_UPLOADS_ENABLED=false` confirmed from the running configuration.

## Remaining limitations

1. A finished video with actual live-retrieved photos still needs acceptance after provider connectivity is available. No successful Commons download, Pexels download, celebrity identity match, or live-photo crop/scene relevance is claimed from mocked metadata.
2. Structured depicts/photo provenance coverage is incomplete on Commons. Conservative skips and strict license conditions can yield several text cards. Identity-specific matches do not fall back to guessing from names alone.
3. All automatic photos are treated as archival or contextual; specific-event association is deliberately not inferred from a search result. No automated authenticity guarantee is offered. Manual uploaded-image attestation is not independent verification.
4. Share-alike exports are unsupported and skipped. Existing historical assets are retained, not retroactively reclassified. Provider licensing/metadata can change; manual source review remains necessary.
5. Successful live automatic replacement remains unverified while the providers are inaccessible. Failure handling, upload, removal and revision safeguards are tested.

Official references consulted: [MediaWiki imageinfo](https://www.mediawiki.org/wiki/API:Imageinfo), [Commons machine-readable metadata](https://commons.wikimedia.org/wiki/Commons:Machine-readable_data), [MediaInfo JSON](https://www.mediawiki.org/wiki/Extension:WikibaseMediaInfo/Data_Model/JSON), [Pexels API documentation](https://www.pexels.com/api/documentation/), [Creative Commons reuse guidance](https://creativecommons.org/reusing-cc-licensed-content/).

## Live follow-up — 24 October 2026

The genuine research/Gemini/local narration/render flow now produced job `ad438fac-2cee-4c8e-8aa4-e929f27d18eb`, with a browser-tested 30-second MP4. The collector actually ran but Commons DNS still fails (11001) and Pexels is unconfigured, so its six assets are correctly labeled neutral text cards. **No successful live real-photo download/render is claimed.** Pexels now respects long Retry-After values; the fallback label's unsupported bullet was replaced and the media stage rerendered. Full source, independence, model, media and browser evidence is appended to [AUTO_EVERGREEN_FALLBACK_REPORT.md](AUTO_EVERGREEN_FALLBACK_REPORT.md). Restore provider access, then regenerate assets/video using the saved script to complete the remaining authentic-photo acceptance check. Uploads remain disabled.

## Connectivity investigation and normal-terminal handoff — 24 October 2026

**Live-photo acceptance is still NOT passed.** This pass distinguishes observed agent failures from untested normal-host behavior; it does not repeat the earlier assumption that the entire Windows host necessarily has broken DNS.

### Tested environments and exact targets

| Environment | Commons DNS / HTTPS | Image CDN DNS / HTTPS | Evidence/limit |
|---|---|---|---|
| Agent PowerShell, existing project `.venv/Scripts/python.exe` | `commons.wikimedia.org`: `socket.gaierror`, Windows 11001; HTTPS `ConnectError` | `upload.wikimedia.org`: resolves to `103.102.166.240`; HTTPS `ConnectError` | Actual read-only probes in this pass. Both `trust_env=False` and `trust_env=True` failed. No HTTP status was received. |
| Running application on `127.0.0.1:8000` | Outbound behavior not directly retested inside its worker | Outbound behavior not directly retested inside its worker | `/api/health` returned 200. Health is NOT proof of external reachability. Prior isolated worker failures remain historical evidence, not a new unrestricted-runtime comparison. |
| Normal Windows terminal outside agent sandbox | **BLOCKED/unverified** | **BLOCKED/unverified** | Automatic approval review did not execute the requested read-only comparison because the session usage limit was reached. This was a review failure, not an unsafe-action finding. |
| User browser | **Unavailable/unverified** | **Unavailable/unverified** | Browser inventory returned no connected browsers/apps. No success is inferred from a different environment's documentation search. |

Exact public metadata probe:
`https://commons.wikimedia.org/w/api.php?action=query&format=json&meta=siteinfo`

The application's actual search uses the official same-host `/w/api.php` endpoint, `action=query`, `generator=search`, `gsrnamespace=6`, `prop=imageinfo`, `iiprop=url|extmetadata|mime|size|sha1|timestamp`, `iiurlwidth=1600` and the scene/subject query. DNS fails before query/path evaluation, so changing query parameters cannot fix this observed lookup failure.

CDN transport probe: `https://upload.wikimedia.org/`. The collector allows image downloads only from `upload.wikimedia.org` (or optional Pexels `images.pexels.com`). **No exact new Commons image-file URL was returned in this pass**, because metadata retrieval failed first. A CDN root request is only a transport probe, never a successful photo download. The helper records/tests the actual metadata-returned image URL when available.

### Classification and application configuration

The configured Commons hostname and API path match the [official imageinfo documentation](https://www.mediawiki.org/wiki/API:Imageinfo). The existing public fetcher uses TLS verification, explicit public-host/DNS checks, bounded reads and `trust_env=False`. No HTTP_PROXY/HTTPS_PROXY/ALL_PROXY/NO_PROXY environment variables were present in the tested agent process; changing trust_env for the fixed-host diagnostic did not improve access. Browser/system proxy settings and unrestricted-host egress remain unverified.

Consequently there is **no evidence supporting an application URL/proxy/TLS configuration change**. It remains unresolved whether Commons failure is limited to the execution environment or also affects the normal host/backend. DNS, firewall, hosts files, proxies, SSRF guards and TLS verification were not changed or bypassed.

### Pexels status corrected

The repository's real variable is **`PEXELS_API_KEY`**, loaded backend-only as `settings.pexels_api_key`. It is **unconfigured**; no Pexels API call or secret output was made. Pexels remains optional, and absent credentials do not disable Commons.

The [official Pexels help article](https://help.pexels.com/hc/en-us/articles/900004904026-How-do-I-get-an-API-key) currently states that new API-key issuance is paused. README and both example configurations now say **existing keys only**; obtaining a new key is not presented as an available remedy. The helper will test an existing configured key privately if one is later supplied. No alternative paid service was introduced.

### Runnable normal-Windows helper

Created `backend/tools/photo_acceptance.py`. Run from a **normal user PowerShell terminal** with the documented backend environment:

```powershell
cd "C:\Users\ua589\short generation\backend"
..\.venv\Scripts\python.exe tools\photo_acceptance.py
```

This uses the same project interpreter and `backend/.env`, performs fixed-host DNS/HTTPS diagnostics with TLS verification enabled, reports proxy-presence types without values, tests the official Commons adapter, and records the actual image download URL/hash when retrievable. An existing optional Pexels key is tested without printing it. It saves `generated/photo-network-*/diagnostics.json`; exit 2 means Commons API diagnostics did not pass. This normal-terminal execution is **not claimed run** by the agent.

If the diagnostic works, perform genuine photo-only acceptance:

```powershell
..\.venv\Scripts\python.exe tools\photo_acceptance.py --accept --serve-review
```

The helper clones the prior genuine live job database into a new directory; original data, credentials, MP4 and narration remain intact. It copies saved local narration, uses the normal authenticated `/api/videos/{id}/regenerate` assets action and real provider APIs, and renders into a fresh media root/cache. It does not rerun research or Gemini. Cloud generation is actively blocked and uploads are false. If neither provider is reachable it stops before rendering placeholder output.

Technical success requires all of: a normal eligible Commons/Pexels asset, a **new successful internet download observed by the real fetcher**, a ready-for-review MP4 with H.264/AAC at 1080×1920, full decode, authenticated image preview and full image credits in the description. It writes source/creator/license/scene metadata, download URL/bytes/hash, `selected-photo.jpg`, `rendered-photo-frame.png`, MP4 path and `acceptance-result.json`. `full_live_photo_acceptance` remains false/manual inspection pending: visually compare the selected photograph with the rendered frame/video and verify correct identity/context and credits before claiming full acceptance. Fixtures, text cards and cached/bundled photos cannot establish this test's fresh-photo success.

On a technical success, `--serve-review` starts the isolated review API at port 8012. In a second normal terminal:

```powershell
cd "C:\Users\ua589\short generation\frontend"
$env:VITE_API_URL="http://127.0.0.1:8012"
npm.cmd run dev -- --host 127.0.0.1 --port 5212 --strictPort
```

Use the existing isolated acceptance account defined in `generated/run_live_fallback_acceptance.py`, open the saved job, and inspect **Scene photographs**, source/license links, preview and replacement controls. Approval controls remain in force. Existing application processes/ports and `.env` credentials are untouched. Stop the isolated processes with Ctrl+C.

### Concrete remedy based on those results

- If normal-terminal DNS/HTTPS succeed while the agent fails, treat it as an agent execution restriction. Run the helper's acceptance mode in that normal terminal; no system DNS/firewall change is justified.
- If Commons DNS also fails there, the blocker is host/network name resolution for `commons.wikimedia.org`. Restore legitimate resolution/access through the user's network administrator/provider, then rerun the diagnostic. The application cannot fetch licensing metadata until that host resolves.
- If DNS succeeds but HTTPS fails there, use the recorded precise exception/HTTP status to resolve the host's egress, configured proxy or certificate-trust problem. Do not disable TLS verification. A direct/proxy difference must be demonstrated before changing app request configuration.
- An existing valid Pexels key is an optional contextual-photo path. New key issuance being paused is not an application failure and is not solved by repeatedly trying to create a key.

### Checks and current outcome

**35 focused tests passed**, zero failures, one existing Starlette/httpx deprecation warning: helper reporting/redaction/path safety/DNS failure plus existing image license/identity/credits/upload/privacy/approval regressions. Helper `--help` ran successfully. These are offline checks; neither `--accept` nor a successful normal-terminal network test was run here. Frontend application code was unchanged, so its build/browser tests were not rerun in this pass. The user browser was unavailable and approval review prevented launching an outside-sandbox comparison.

Changed files: new `backend/tools/photo_acceptance.py`, new `backend/tests/test_photo_acceptance_helper.py`, README, root/backend `.env.example` comments and this report. No migration or production application request-configuration change. No data deletion, credential change, upload, publication or deployment.

**Photo source/attribution/new photo-video path for this pass: none — blocked before metadata/download.** The earlier real researched text-card MP4 remains available, but it does not establish authentic-photo acceptance. The next evidence needed is the normal-terminal diagnostic report; the exact commands above make that comparison and the subsequent live acceptance reproducible.

### User-supplied normal-terminal results (2026-10-24)

The pasted terminal transcript establishes that this failure is not confined to the agent sandbox:
- Normal project Python: Commons metadata lookup fails with `gaierror 11001`; both diagnostic trust_env settings fail before HTTPS.
- Windows default resolver: `Resolve-DnsName commons.wikimedia.org -Type A -DnsOnly` returns `DNS_ERROR_RCODE_NAME_ERROR`.
- Explicit read-only queries to both 1.1.1.1 and 8.8.8.8 return the Commons CNAME and an A record. This isolates the immediate problem to the default DNS resolution path, rather than a nonexistent Commons hostname. It does not establish why that resolver fails.
- Normal-terminal `upload.wikimedia.org` root probe reaches HTTPS and returns HTTP 403. That root response is not a test of an actual image file and must not be interpreted as failed photo-download authorization.
- Two normal-terminal acceptance attempts stop at `provider_connectivity`; no fresh photograph or photo-render acceptance was achieved. Pexels remains unconfigured.

The same pasted transcript includes older reload/KeyboardInterrupt traces and a transient scripts.py indentation error followed by successful application startup. The current `backend/app/ai/scripts.py` passes `python -m py_compile`; that historical traceback does not establish a current syntax defect.

No DNS, hosts, proxy, firewall, TLS or application provider configuration was changed. The smallest next action is to have the user's network administrator/provider correct default resolution for Commons (public-resolver comparisons already supplied). Once ordinary `Resolve-DnsName commons.wikimedia.org` succeeds, rerun `tools/photo_acceptance.py`, followed by `--accept --serve-review`. Do not hardcode the returned CDN IP: addresses can change and metadata/TLS/host protections must remain intact.

## 24 October 2026 — Wikimedia access and genuine photo acceptance resolved

Superseding the earlier DNS/403-blocked outcomes: the supplied real operator contact was configured, provider and helper headers unified, and the fresh Commons siteinfo request returned HTTP 200 over verified TLS. Final acceptance genuinely downloaded a CC BY 2.0 subject photo, matched Q11571 through structured depicts, rendered it with the saved genuine script/narration, inspected the actual frame, and passed seven browser playback/preview/credit/download checks. It is one archival 2015 photo plus five text cards, not six subject photos or a photograph of the 2008 event. Uploads remain disabled and approvals zero.

See [WIKIMEDIA_ACCESS_REPORT.md](WIKIMEDIA_ACCESS_REPORT.md) for exact files, provenance, test results (including an intermittent broader scheduler-test failure), the active isolated review URL and limitations. Evidence: `generated/photo-network-20261024T110701-37b5f4/acceptance-result.json` and `browser-report.json`.
