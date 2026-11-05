# Claim-level scope review — 29 October 2026

**Implementation and live script review succeeded. No video was rendered.** Saved draft 83aed818-f7ff-489f-80fc-4573f844d628, revision 10, status script_review. [Open review](http://127.0.0.1:5173/title-to-short/83aed818-f7ff-489f-80fc-4573f844d628). Scope acceptance is false; the live checkbox is unchecked, the acceptance button is disabled until it is checked, and rendering remains disabled. Neither acceptance nor render was clicked on the real draft.

## Original and proposed scope

Original input, preserved unchanged: Ryan Clark & Gillie GO OFF On Cam Newton For Dissing Jalen Hurts: “YOU NEVER WON!”

Proposed video title: **Ryan Clark Responds to Cam Newton's Comments Questioning Jalen Hurts' Standing Among NFL Quarterbacks**

Focused angle: Analysis of Ryan Clark's defense of Jalen Hurts in response to Cam Newton's public criticism of the quarterback's ranking.

Gillie's participation/response and the exact phrase YOU NEVER WON! are omitted because their evidence is insufficient under the existing policy. Missing transcript access does not block independently supported reporting paraphrases. Exact spoken quotations require original recording/transcript evidence as well as the existing independent-origin requirements; this draft uses none.

## Supported saved script

Scene 1: July 2025 reporting described Cam Newton questioning Jalen Hurts' place among the NFL's top quarterbacks.

Scene 2: Ryan Clark defended Hurts on ESPN's Get Up. He also turned part of his response toward Newton's own playing career.

Scene 3: The reports cover both parts of the exchange: Newton's assessment of Hurts, followed by Clark's defense and his criticism directed back at Newton.

58 spoken words, English, 30-second target. Scene times in the UI are estimates until narration exists. No actual duration, narrator invocation, audio, caption alignment or MP4 is claimed.

## Evidence mapping inspected from the actual retrieved bodies

| Proposed assertion | Actual supporting passages | Origins and decision |
|---|---|---|
| July 2025 reporting context | S1 passage 1/publication metadata; S2 passage 1/byline and publication metadata | Both reports date to July 2025. This dates the reporting, rather than inventing the precise event date. |
| Newton questioned Hurts' standing among leading NFL quarterbacks | S1 passage 2 describes Newton questioning top-ten placement; S2 passage 5 discusses Newton's view of Hurts' standing/production | Pro Football Network G1 and Awful Announcing G2; retained as a paraphrase. No extra roster-quality rationale is included. |
| Clark defended Hurts on Get Up and directed part of his response toward Newton's playing career | S1 passage 3 names Get Up, Hurts' defense and comparison with Newton's resume; S2 passage 2 describes Clark's defense and the reference to Newton's Super Bowl play | G1 and G2; retained. S1 passage 4 additionally supplies the Super Bowl/fumble detail in the full body, but the final narration stays with the narrower career reference. |
| Ending restates Newton's assessment and Clark's defense/criticism | The preceding two mapped assertions and their passages | A summary of those supported assertions; no additional statistic, motive or outcome. |
| Gillie response/Super Bowl comparison | S3 VIBE reports it, including a social repost | Penske Media G3 only among retrieved qualifying evidence; omitted. |
| YOU NEVER WON! as exact spoken dialogue | Sensational video metadata/title, with no qualifying original transcript/recording evidence | Omitted, with no speaker attribution asserted. |

Sources:

- S1: [Pro Football Network](https://www.profootballnetwork.com/cam-newton-jalen-hurts-criticism/), Ishika Dadhwal, 24 July 2025, publisher group pro_football_network, G1.
- S2: [Awful Announcing](https://awfulannouncing.com/nfl/cam-newton-ryan-clark-dan-orlovsky-afraid-criticize-jalen-hurts.html), Brendon Kleen, 23 July byline / 24 July UTC metadata, publisher group comeback_media, G2.
- S3: [VIBE](https://www.vibe.com/news/entertainment/gillie-roasts-cam-newton-jalen-hurts-take-1235089357/), Amber Corrine, 25 July 2025, publisher group penske_media, G3.

Origin grouping still checks publisher identity/ownership, canonical and syndication origins, duplicate bodies and shared original episode/post references. S1/S2 have distinct publisher groups, authors, bodies and canonicals under those checks. Host count alone is insufficient. All three source links and retrieved text remain visible in review. Stored passage IDs and original fetched-body hashes remain attached to the claims.

## Implementation

- title_evidence.py retains each qualifying claim with actual server-owned passages from at least two independent origin groups. An unsupported person or unverified headline quote no longer vetoes other qualifying claims. No qualifying claims still produces a precise evidence error.
- New title_scope.py proposes an accurate narrower title/focus and records omissions while retaining the original input title. Scoped narration is paraphrase-only and cannot reintroduce omitted people or quote text.
- Script generation uses the selected claims/scope, rather than the unsupported original headline. A bounded repair handles invalid-length or failed-audit candidates without truncating speech or authorizing unsupported output. Rejected candidates are retained separately.
- The final factual audit judges the revised title/focus/script and mapped passages; the original full-headline failure and pending user consent are not factual failures. Only selected evidence is supplied for narrowed-script auditing, with an explicit two-origin requirement for every added fact. A generated supporting-cast rationale was removed during review because it exceeded the selected claim mapping. The final saved script passed the configured audit after that edit.
- POST /api/title-shorts/{id}/scope/accept requires an authenticated editor, current revision and a verified script_review state. Acceptance binds a fingerprint of the proposed scope, current saved plan and sources. Content/source changes require acceptance again. Derived narration timing does not invalidate consent by itself.
- Both the render API and worker reject an unaccepted current scope. The renderer uses the proposed title only after acceptance. Rendering remains a separate action; no automatic render follows acceptance.
- The UI displays original input, revised title/focus, omissions, complete editable script and source support before the consent control. Unsaved edits block acceptance. Saved script history, prior research/scope/evidence snapshots, render history, existing idempotent creation and stale/concurrent-action protection are preserved. No schema migration or paid service was added.

## Checks actually performed

- Real UI action rechecked the saved PFN/AA/VIBE bodies without manual source injection, ran the configured AI, generated a three-scene draft and reached script_review. Initial over-length/audit failures were diagnosed and repaired; their stages are not counted as success.
- The final narration was edited and saved through the actual UI, then reloaded. All three edits persisted. The original title remained unchanged. Final draft revision 10, zero browser page errors. Scope checkbox remained unchecked, acceptance button and render button remained disabled. Actual acceptance/render were not exercised on this user draft.
- The exact saved revision/script passed the real configured passage-only factual audit: generated/claim-scope-review/final-script-audit.json. This audit did not render or accept scope.
- Combined relevant regressions: **86 passed**, one warning. Feature rerun after subsequent audit/history changes: **55 passed**, one warning. Final scope/evidence suite after the passage restriction and added length-repair test: **20 passed**, one warning. Isolated tests cover the accepted path, stale/cross-user acceptance, edit invalidation, render rejection, two-origin grouping, absent transcripts for paraphrases, exact-quote primary evidence, idempotency, history preservation and bounded script repair. Isolated test acceptance is not the user's real scope acceptance.
- Final frontend build passed (1,617 modules). Scope/script screenshots were inspected; the consent checkbox alignment was corrected and rebuilt.
- Pilot revision/SHA256 checks passed: Ronaldo r21, Messi r20, original Henry r32 unchanged. Uploads and scheduling are disabled. No upload, schedule, publication or deployment occurred.

## Remaining work and checkpoint

The narrowed research/script flow is ready for user review. **User acceptance of the revised scope/current script is required before rendering.** The missing Gillie/quote evidence does not block this narrower paraphrase, but those elements remain omitted. Licensed visual retrieval/regeneration, voiceover, final caption timing, rendering, complete playback/decoding and download checks remain future work after acceptance. No narrator was used and no direct listening approval is claimed.

Evidence: [scope screenshot](generated/claim-scope-review/scope-review.png), [script screenshot](generated/claim-scope-review/script-review.png), [final UI state](generated/claim-scope-review/final-ui.json), [machine checkpoint](generated/claim-scope-review/checkpoint.json). Previous automatic-research reports and rendered pilots remain preserved. Do not treat this successful script-review implementation as a completed Short.
