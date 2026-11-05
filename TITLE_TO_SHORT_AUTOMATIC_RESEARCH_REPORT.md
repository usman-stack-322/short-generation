# Automatic research repair — exact-title live result

29 October 2026. This report supersedes automatic-research claims in earlier reports; the previous English source-URL acceptance remains a separate preserved result.

**Outcome: automatic discovery fixed; this exact title did not complete a Short.** The saved draft is revision 5, not a rendered-video revision. No source URLs were supplied. Research retrieved three real readable articles, then correctly stopped because the complete incident lead lacked independently corroborated support for Gillie's specific response. The title quote remains unverified and excluded. No substitute topic/video was generated.

[Open actual saved review](http://127.0.0.1:5173/title-to-short/83aed818-f7ff-489f-80fc-4573f844d628) · [Review screenshot](generated/automatic-research-clark/evidence-review.png) · [Machine checkpoint](generated/automatic-research-clark/checkpoint.json) · [Final live browser/API evidence](generated/automatic-research-clark/final-automatic.json)

Input: Ryan Clark & Gillie GO OFF On Cam Newton For Dissing Jalen Hurts: “YOU NEVER WON!”

## Root causes and implementation

1. Real requests to configured Bing RSS succeeded at transport level but returned unrelated WhatsApp, webcam and other pages even for neutral name queries. They were correctly rejected. The evidence does not establish DNS failure or explain Bing's internal response mismatch. Brave credentials are absent, so that optional integration was unavailable; no subscription or new paid service was introduced. See before-diagnosis.json and final discovery diagnostics.
2. Added public DuckDuckGo HTML discovery after Bing, with neutral entity/name/claim variants and original podcast/interview queries. This exact title produced relevant results. Some variants returned search challenges; these were recorded and not bypassed. Snippets remain discovery leads, never verification content.
3. Explicitly reviewed specialist publishers were added to the identity registry: Awful Announcing, Pro Football Network, VIBE, BET, Philadelphia Inquirer, Sporting News, Panthers Wire and Yahoo Sports distribution. Yahoo without an identified original publisher is ineligible; VIBE/Yahoo or Panthers Wire/Yahoo copies count with their original publisher. No arbitrary discovered host is automatically trusted.
4. Replaced the two-domain gate with origin grouping: publisher ownership, canonical/original URLs, recognized syndication attribution, near-duplicate bodies and shared original episode/post references collapse into one group. Two differently hosted copies do not manufacture corroboration. Every incident claim also needs supporting passages in two distinct groups.
5. Initial incident-audit JSON constraints were rejected by the configured Gemini provider (HTTP 400); simplified the response schema while retaining server validation. A further live problem was AI paraphrasing purported exact evidence excerpts. The final audit selects server-provided passage IDs; the server reconstructs evidence text directly from retrieved bodies. Invalid IDs or insufficient groups fail closed, with one bounded repair attempt. Quotes must have exact wording and attributed support; metadata is insufficient.
6. YouTube public oEmbed records title/creator only and explicitly reports missing transcript access. Public trusted publisher RSS with podcast:transcript text/plain or text/vtt is supported and unit-tested; no usable original transcript was retrieved for this incident. No undocumented caption scraping, access bypass or owner-only captions-download claim was used. The discovered Cam Newton link c32ptG91d2Q describes Jayden Daniels; metadata does not establish the Hurts incident.
7. UI separates search failures, AI-service failures and evidence insufficiency; it shows sources, sanitized retrieval reasons, partial supported context, excluded quotes and missing evidence. Scripts/assets/render history survive retries. Unsaved edits must be saved before retry. Latest failed research blocks rendering. Default automatic retry rediscovers sources; explicit refresh_sources=false can recheck the already fetched evidence. Revision compare-and-swap rejects concurrent/stale actions. Scoped deterministic request IDs plus database primary-key uniqueness prevent a network retry creating a duplicate job. Explicit New short resets that client request key.

Changed implementation: backend/app/services/title_research.py, title_evidence.py, title_shorts.py; backend/app/api/title_shorts.py; backend/app/research/sources.json; frontend/src/pages/TitleShort.jsx. Existing frameworks, local narrator options and clean renderer were retained. No migration or publishing integration was added.

## Actual sources and claim support

| Automatically retrieved source | Public reporting supports | Verification limit |
|---|---|---|
| [Pro Football Network, 24 July 2025](https://www.profootballnetwork.com/cam-newton-jalen-hurts-criticism/) | Newton questioning Hurts' top-quarterback standing; Clark defending Hurts on Get Up and mentioning Newton's Super Bowl performance | G1; readable body, selected passages recorded; no confirmation of the headline quote |
| [Awful Announcing, 23 July 2025](https://awfulannouncing.com/nfl/cam-newton-ryan-clark-dan-orlovsky-afraid-criticize-jalen-hurts.html) | The Newton/Hurts debate and Clark's ESPN response | G2; readable body and independent publisher context; linked metadata alone is not speech verification |
| [VIBE, 25 July 2025](https://www.vibe.com/news/entertainment/gillie-roasts-cam-newton-jalen-hurts-take-1235089357/) | Reports Gillie's response and the Super Bowl comparison | G3; only one retrieved origin supports this specific response, so it was excluded from independently verified claims. Embedded social repost is not an authenticated original transcript |

The final audit retained two context claims concerning Newton/Hurts and Clark; it did not mark the complete title true. The exact phrase YOU NEVER WON! has no verified wording/attribution in the retrieved readable evidence. It was not used in a script or captions.

Primary-channel metadata was found for 4th&1 With Cam Newton videos including WP-ya-JU_Io, 10MiFfm76T4 and fCpGTyP07ZE. The exact sensational title also appeared on a Celeb Arena compilation (o6uVXeL-9iU). These are metadata leads, not transcripts or licensed visual assets, and none was counted as a second source of spoken evidence.

## Actual live acceptance and verification

- Exact title submitted through the real English UI with zero manual URLs; API, database-backed stages and source links exercised. Same draft ID reused for retries. Final browser page errors: zero. Final saved stage: evidence insufficient; sources and the review remain accessible.
- Full combined relevant regression run: **81 passed**, one warning. After the final retry/generic-topic guards, final feature rerun: **49 passed**, one warning. Coverage includes irrelevant search results, DDG parsing/challenges, syndication/shared episodes, source-owned passage IDs, unavailable transcripts, unsupported quotes, idempotent creation, stale writes and saved-plan retry preservation, plus existing TTS/alignment/renderer/provider checks.
- Final frontend production build passed: 1,617 modules. The evidence-review screenshot was visually inspected; supported-context source links were expanded in the final browser capture.
- Real FFmpeg renderer/download coverage in the isolated test suite uses explicitly synthetic test media. It is not live completion for this title.
- Pilot preservation verified by stored revision and SHA256: Ronaldo r21, Messi r20 and original Henry r32 all match. No pilot or prior rendered file was overwritten. Uploads and scheduling verified disabled; no upload, scheduling, publication or deployment was performed.

## Remaining blocker and media status

Need a second independently originating readable source supporting Gillie's specific response, or legitimate original transcript evidence plus policy-compliant independent corroboration. To include the exact title quote, also need readable original/authorized transcript or other independently verifiable attributed wording. Quote exclusion alone need not block a supported narrower story; the present full-lead gate stops because Gillie's participation does not pass corroboration.

No new search key is required for the working DDG path. Optional Brave remains unconfigured. Owner-authorized YouTube transcript access is not configured; ordinary third-party metadata does not grant permission to download protected captions. Public publisher transcripts may be used when legitimately available.

Selected English UI narrator option: installed local system narrator. **Narrator actually used: none**; narration was never invoked for this blocked title. The existing prior English acceptance used Microsoft David, but that is not evidence of speech generation here. Target 30 seconds; actual duration, MP4 preview/download, visual retrieval/regeneration, audio decoding, captions, complete playback and downloaded-file playback are **not performed for this title**, because no script/video was authorized. Direct listening was unavailable; no pronunciation, naturalness, perceived clarity or listening-based synchronization approval is claimed.

Next session: read this report and TITLE_TO_SHORT_CHECKPOINT.md, inspect the saved review, obtain the missing evidence through legitimate retrieval or optional URLs, then retry. Only after evidence passes, review/edit script, regenerate a scene, render with a compatible configured English narrator and verify the complete media/download. Keep uploads and scheduling disabled.
