# Title to AI Short — live English acceptance, 29 October 2026

**The real English flow completed.** Review: http://127.0.0.1:5173/title-to-short/97e2bfd4-2c9b-4144-ab64-f410062a05b7 . Title: Cristiano Ronaldo: Who won the 2008 Ballon d'Or?. Selected target: 30 seconds; actual complete-narration output: **24.64 seconds**, within the configured 80%-to-limit duration policy. This is a separate Title Short output revision 9, not a change to the Ronaldo pilot. Intermediate draft/failed attempts remain preserved.

## Working artifacts

- Actual browser-downloaded MP4: generated/title-short-live/acceptance-download.mp4
- Immutable rendered MP4: C:\Users\ua589\short generation\generated\title-shorts\97e2bfd4-2c9b-4144-ab64-f410062a05b7\render-9\videos\97e2bfd4-2c9b-4144-ab64-f410062a05b7\revision-9\short.mp4
- SHA256 (both): 50ee0227ff8ebd745dc08b4f24749501f962ef7942e9e301a1d21fc71c38ceed
- Research/source download: generated/title-short-live/downloaded-sources.json
- Photo-license/credit download: generated/title-short-live/downloaded-credits.txt
- Representative screenshot: generated/title-short-live/final-preview-card.png
- Scene, caption and transition frame sheets: scene-contact-sheet.jpg, caption-contact-sheet.jpg and transition-contact-sheet.jpg in the same evidence directory.

## Exact research diagnosis and fix

The failure did not mean reliable sources did not exist. The live public RSS discovery response for an AI/Dartmouth query returned keyboard-testing pages; the award query mostly returned Wikipedia/social/profile pages. The application's trusted-source filter correctly rejected those. The earlier implementation reduced these outcomes to a generic fewer-than-two-sources error. A prior run also recorded a source DecodingError; it was not reproducible on the direct primary pages in this pass. Current direct Dartmouth and Stanford retrieval succeeded with actual HTML. No claim is made that a TLS/SSRF restriction was bypassed or that a particular remote cache caused the bad results.

Discovery now constructs an explicit encoded query URL, retains query/feed metadata, and records each candidate's URL, relevance/trust decision and each article fetch/readability failure. Unrelated results are rejected. Automatic discovery may still be insufficient: the UI now accepts up to six supplied source URLs at creation or retry. They pass the **same public HTTPS, trusted-source, redirect-host, bounded readable-content, two-domain, exact supporting-excerpt and final factual-script audit rules**. Supplied URLs are not a verification override. Retry invalidates the previous plan and requires script review again while preserving render history. Unsafe/private and untrusted URLs are rejected.

For this live run the source-URL form was populated with two actual accessible, trusted sources:

1. Sky Sports: https://www.skysports.com/football/news/4575921/ronaldo-wins-ballon-d-or — 705 readable words; fetched-body SHA256 57b39e89d93c8bf60f5e2edef3f8b0f0f1af4ee623a392dee2ab3bb167b9f531.
2. UEFA: https://www.uefa.com/uefachampionsleague/news/01d4-0e707fe4919f-772c18bc5bc3-1000--ballon-d-or-crowns-ronaldo-s-golden-year/ — 638 readable words; fetched-body SHA256 0ebd8bd8c3d41a421ad4cc2c27760f14afab1674115419716b9abea857d85f05.

Both actual bodies, URLs, source IDs and claim excerpts are retained separately from the video. The selected angle is the 2008 award result/voting, not a compressed career history. No invented research, source URL or quotation was substituted.

A second external failure was the configured primary Gemini model: repeated 503/read timeouts, then quota/rate-limit rejection. Title-only TITLE_SHORT_AI_MODEL now explicitly selects the **already configured fallback gemini-3.5-flash-lite**, restricted to the configured primary/fallback names. Global GEMINI_MODEL remains unchanged. Existing bounded retry/error handling and mandatory factual audit remain enabled; no new account, key, subscription or model name was guessed. The final render passed the actual source audit using the configured fallback. Failed attempts remain recorded rather than being relabeled successful.

## Script, regeneration, visuals and narration

The source-backed draft stopped at script review. Browser edits were saved and read back from the server. Editorial review removed the rhetorical ending and unnecessary career-first wording; the final script uses directly supported award, voting, age and season facts. An initial natural narration was too short; the duration guard stopped it. A sourced age detail was added rather than slowing speech or inserting silent padding. All revised narration passed source audit again before the successful render.

Final narration:

Who finished ahead of Messi and Torres in 2008? Cristiano Ronaldo won that year's Ballon d'Or for Manchester United. The Portuguese winger was twenty-three years old when the award was announced. The France Football poll involved ninety-six journalists. Ronaldo received four hundred and forty-six points, while Messi finished second with two hundred and eighty-one. Fernando Torres took third place. Ronaldo's award followed a forty-two-goal season that included Premier League and Champions League titles.

Individual-scene visual regeneration was exercised through the real UI/API. Scene 2 motion changed **pan_right → pan_left**. Exact narration and the other two scene plans were compared and remained unchanged during that operation. Final narration was subsequently edited deliberately in the review UI; those edits did not mutate the other pilots. Evidence: scene-regeneration.json, review-before.json, review-edited.json and final-reviewed-script.json.

Live Commons search also failed with connection reset/no HTTP response. The working fallback reuses three **distinct licensed clean-source workspace photos** for the matching subject. Workspace/channel access, recorded rights/real-photo flags, permitted CC BY license and duplicate-hash checks apply; files are copied into the new draft's media root, leaving originals read-only. Creator, license, original URL, photo-date/context and required credit are retained. These are contextual archival photographs, not award-ceremony footage, a voting document or AI-generated historical evidence. The visual plan is labeled as a plan in the UI; actual photo provenance is shown separately. AI image generation remains unconfigured and was not used.

Actual narrator: **Microsoft David Desktop - English (United States)**, local Windows SAPI, en-US, compatible installed generic system voice. It was explicitly selected in the input form. No celebrity imitation, paid/cloud narration, silent placeholder or speech acceleration was used. Native SAPI synthesis word events are bound to the exact script and final WAV, then mapped through the renderer's final-audio processing. Final scene timing follows that narration. The renderer keeps proportional/native-detail foreground photos, restrained varied motion, clean transitions and box-free captions without corner labels or bottom panels.

## Performed verification

- Final **68 combined regression tests passed**, zero final failures; existing Starlette/httpx deprecation warning remains. Modules cover title flow, source verification, source-URL fallback, before-generation language blocking, native alignment, immutable media revisions, scene motion, local voice cost boundaries and Gemini retry/model selection. The existing synthetic-fixture renderer regression remains explicitly a test fixture; this report's delivered MP4 uses actual live SAPI speech and actual fetched research.
- Final frontend production build passed (Vite v6.4.5, 1617 modules). Actual final desktop/mobile UI was checked; no horizontal overflow, sources visible. Real preview and downloaded playback reported no page/media errors.
- **Rendered file and exact browser download both fully decoded with FFmpeg -xerror**, empty error logs. Their hashes match. Export: H.264, **1080×1920, 30 fps**, AAC **48 kHz**.
- Observed final audio: **-15.32 LUFS**, **-1.12 dBTP**, **zero clipped decoded PCM samples**. Genuine non-silent narration validated. No background music was mixed, so speech/music balance is not applicable.
- **17 caption cues**, exact final-script words, no overlaps/duplicates, inside final narration, at most two lines. Exact script/WAV timing hashes validate. Maximum cue-start difference from the matching native first-word span: **0.0075 seconds**. The verifier was corrected to match character spans because SAPI can emit multiple events per hyphenated word; a naive event-count comparison was not treated as a rendered sync defect.
- Every caption midpoint, beginning/middle/end of each scene and before/mid/after each transition was extracted from actual MP4 bytes and inspected. Captions remain readable and below faces; source photos retain proportions, camera movement varies, and clean cut/dissolve boundaries show no black flashes or awkward new crop. Full-file black-frame detection (0.05 s) and freeze detection (0.7 s) both completed with exit 0 and found no events. An initial helper used the rejected duration spelling .7; this was corrected to 0.7 and rerun, and successful detector exits are now mandatory. This is frame sampling plus technical detection, not a claimed full perceptual watch.
- Installed Edge played the **entire app preview** with audio enabled to ended, then downloaded through the actual Download MP4 button and played that exact local file to ended. Both reached 24.64 s, 1080×1920, with increasing decoded audio bytes and no sampled media errors. Source and photo-credit download endpoints returned **200**. There is no evidence here of a rendered-file defect; browser decoding/playback is distinguished from direct listening.
- Actual API requests for Urdu/Roman Urdu returned **422** before allocating work; generation job count was unchanged. The language UI showed the missing-voice message and disabled generation. A private source URL was also rejected. These were live requests, not only mocked tests.
- Original normal pilots are preserved by both database revision and MP4 hash: Ronaldo r21, Messi r20, original Henry r32. Uploads and scheduling remain disabled. No upload task, publication or deployment was performed.

## Remaining limits and next step

Direct listening is unavailable in this session. Pronunciation, perceived clarity/naturalness and listening-based caption sync still require human listening review; decoded audio and native timestamps do not establish those perceptual approvals. No editorial/upload approval is recorded.

Urdu and Roman Urdu need a compatible narrator: this machine has only English David/Zira system voices. The application now reports this before research/generation rather than failing after visuals. Install a compatible Urdu system narrator or explicitly authorize/configure an allowlisted multilingual voice; no automatic paid fallback was enabled. Reviewed Kokoro remains English-only.

Automatic public discovery and live Commons retrieval may remain unreliable. Verified supplied-source URLs and relevant licensed workspace-photo reuse are working alternatives, not relaxed gates. AI visuals remain unconfigured. The live output is 24.64 s for a 30-second target; complete speech determined timing and was not padded or cut off.

Review the working video and listen before any separately supervised upload. Keep uploads/scheduling disabled.

Evidence root: generated/title-short-live/. Key records: research-diagnosis.json, direct-source-probe.json, source-retrieval-check.json, prepare.json, api-preflight.json, scene-regeneration.json, ready.json, playback.json, technical-verification.json, final-regression.xml, installation.json and final-page.json.
