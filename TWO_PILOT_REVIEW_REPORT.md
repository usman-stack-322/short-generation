# Narration and caption audit — 28 October 2026 (latest pass)

**Decision: retain Ronaldo r21 and Messi r20. No new video revision or speech synthesis was warranted by the available evidence.** Scripts, audio, captions, framing and transitions were not modified. All previous revisions remain preserved. Uploads are disabled and zero approvals remain recorded.

## Reference identity correction

The request associates original Henry r32 with Kokoro bm_george, but its own narration.words.json identifies ElevenLabs original character alignment / eleven_multilingual_v2; the earlier diagnosis identifies George (voice ID JBFqnCBsd6RMkjVDRZzb). Henry r32 is therefore displayed as the original requested reference, accurately labeled ElevenLabs George. It was not replaced or regenerated. Its SHA256 remains 621835aa62ddc68b3030509037c0243c9eb58d475ad7e3a7fc69122c41570449.

The separate Henry local review v2 is the verified **Kokoro bm_george** voice reference. Ronaldo r21 and Messi r20 already match its model hash and all engine controls exactly: Kokoro-82M v1.0 INT8, kokoro-onnx 0.6.1, speed 1.0, en-gb, sentence_pause 0.22, clause_pause 0.10, continuous true, is_phonemes true. No voice switch was made. Both Henry artifacts are preserved and linked on the review page; they are not conflated.

## Actual inspection and fresh verification

Direct listening is unavailable. Full perceptual audiovisual watching was not performed. Name pronunciation, unnatural-sounding pauses, perceived clarity, clipped phonemes and listening-based caption synchronization remain pending; no listening approval is claimed.

Fresh FFmpeg full-file decoding passed for both 1080×1920, 30 fps MP4s with AAC 48 kHz audio. Every caption midpoint (15 Ronaldo cues, 14 Messi cues), each scene beginning/middle/end, and every transition before/mid/after was extracted from actual video bytes and visually inspected. Captions are legible, outlined and box-free, at most two lines, and remain below faces/main ball action in inspected frames. Some captions split names across consecutive cues, but no truncation, duplicate overlay or unreadable line break was observed. No caption-layout edit was justified. Proportions are preserved; source-detail limits remain visible. One planned clean cut and one short dissolve per pilot were retained; sampled boundaries show no black flashes or awkward new crops. Full-file black-frame detection (0.05 s threshold) and freeze detection (0.7 s threshold) found no events. This is sampled editorial inspection plus full-file technical detection, not full perceptual visual approval.

| Check | Ronaldo r21 | Messi r20 |
|---|---|---|
| Duration | 30.766667 s | 29.400000 s |
| Integrated loudness | -15.10 LUFS | -15.10 LUFS |
| True peak | -1.48 dBTP | -1.49 dBTP |
| Decoded MP4 clipped PCM samples | 0 | 0 |
| Caption cues / minimum cue | 15 / 1.20 s | 14 / 1.05 s |
| Maximum cue-start difference from native first word | 0.005 s | 0.005 s |
| Native last word end / narration duration | 29.975 / 30.15 s | 28.625 / 28.80 s |

Caption words exactly match unchanged scripts, hashes validate, timestamps do not overlap, all cue intervals fall inside narration, and no duplicate intervals occur. Native G2P/phoneme timing is not independent ASR or listening-based sync verification. Render records have one narration WAV input and no music input/amix; music balance is not applicable. No quiet intervals met -42 dB / 0.25 s detection criteria; this does not establish natural pauses by ear. Complete final words have timing coverage and retained tails; pronunciation/phonetic clipping still need listening.

Installed Edge played complete Ronaldo and Messi videos with audio enabled, then downloaded each through the review page and played each exact downloaded file to ended. All sampled media errors were null and decoded audio byte counts increased. Both browser downloads hash-match the immutable renders and separately passed full FFmpeg decoding with empty error logs. Original Henry r32 also played to ended on the corrected page. Initial browser attempt failed because the review server was stopped; restarting the loopback-only server resolved it. This was server availability, not a rendered-file defect. No buffering-related rendered defect was established.

Authenticated normal-app downloads returned 200, matched hashes and fully decoded; Range returned 206, anonymous requests 401. API confirmed r21/r20, unchanged script hashes, bm_george, three distinct assets/scenes each, zero approvals, uploads_enabled=false. Original Henry r32 and separate Kokoro reference hashes also passed preservation checks. Scheduler was found enabled in backend/.env and changed to false; uploads were already false. The verification app started with both flags explicitly false. No upload, publish or deployment occurred.

Relevant regressions this pass: **43 passed** (selected Kokoro, quality revision, scene motion review, voice director) plus **3 passed** native alignment tests: **46 passed total**, zero failures. Existing Starlette/httpx deprecation warning remains. No frontend application source changed; no frontend build was run.

## Review and evidence

Review: http://127.0.0.1:8015/ . Main cards: original Henry r32, Ronaldo r21, Messi r20; separate Henry Kokoro v2 link and explicit provider names prevent the former reference ambiguity. The old page/manifest are backed up in the audit folder.

- MP4s remain the same links listed in the historical delivery below.
- Fresh evidence: generated/hybrid-review/narration-caption-audit-20261028/ . Includes per-subject results.json, all-captions-contact-sheet.jpg, motion/transition sheets, caption-audio-detail.json, voice-reference-check.json, browser-playback/results.json, exact-browser-download-decodes.json, selected-revision-verification.json, regression.xml and native-alignment-regression.xml.
- Original Henry playback: henry-r32-reference-playback/results.json in that audit folder.
- Exact current machine checkpoint: generated/hybrid-review/narration-caption-audit-20261028/checkpoint.json.

Remaining issues: direct listening review is required for pronunciation, perceived clarity/naturalness and perceptual sync; existing AI-visual/clip unavailability remains unchanged. No unsupported audio/caption fixes were applied. Final user review precedes a separately supervised upload; uploads remain disabled.

---

# Previous delivery report (historical)

# Ronaldo r21 and Messi r20 review delivery — 28 October 2026

Review page: http://127.0.0.1:8015/ . It shows accepted Henry local review v2, Ronaldo r21, Messi r20 and the exact narrator on every card. Original Henry r32 remains preserved and linked separately. These are review candidates; no editorial approval or upload has been recorded.

## Delivered changes

Ronaldo r20 → r21 (30.766667 s), Messi r19 → r20 (29.400000 s). Both export H.264 1080×1920 at 30 fps with AAC 48 kHz audio. Original scripts and factual claims are byte-for-byte unchanged. Each uses three distinct relevant licensed archival photographs across three narrated scenes, with source/license credits retained. These are animated photographs, not video clips. Removed repeated scene photos, corner/debug/decorative text and caption background panels. Restrained push-in, horizontal pan and pull-out visibly vary the motion; clean cuts and a short dissolve join scenes. Proportions and native-detail foreground fitting are retained over a same-photo blurred backdrop. Limited original photo resolution remains visible; no restored-detail claim is made.

Exact accepted Henry narrator verified against its generation record: **Kokoro bm_george**, generic British English male, **Kokoro-82M v1.0 INT8**, kokoro-onnx 0.6.1; speed 1.0, en-gb, sentence pause 0.22 s, clause pause 0.10 s, continuous phoneme input. Model SHA256 ae315a79b623f244700e4afb9246c46a26066782e049ba174bf3ba433970ee9c. This is not ElevenLabs George. Both new narrations use that same local model and controls. Explicit Kokoro configuration now fails visibly rather than silently substituting another provider. No paid voice or cloud synthesis was used.

Narration determines final duration, with the complete last sentence retained. Captions are generated once from the final narration timings, without a large box. No placeholder or silent narration was substituted. Ronaldo's first normalization attempt timed out; the successful retry reused its hash-verified source audio/timings without resynthesis. Failed/intermediate revisions remain preserved.

## Checks actually performed

- Both full-file decodes passed; audio streams present, no clipped PCM samples, no detected black/frozen intervals or qualifying quiet gaps. Final loudness: Ronaldo -15.10 LUFS / -1.48 dBTP; Messi -15.10 LUFS / -1.49 dBTP.
- Caption words match unchanged scripts; intervals do not overlap and remain within final audio. Native phoneme/word mapping passed integrity checks. This is not an independent speech-recognition or perceptual sync approval.
- Inspected beginning/middle/end scene contact sheets and before/mid/after transition sheets for both videos: relevant subjects, proportional framing, readable box-free captions, varied motion, no drawn corner text/panel. No direct full audiovisual viewing/listening is claimed.
- Installed Edge played all three page videos to ended with audio enabled and no sampled media errors. Ronaldo/Messi were downloaded through the page and those exact downloads played to ended; hashes match the selected renders. Authenticated normal-app downloads also matched and fully decoded. Range requests returned 206; anonymous access returned 401. These checks show complete playable files, without establishing perceived audio clarity or pronunciation. No evidence of a rendered-file defect was found; buffering and subjective pacing were not independently assessed by direct viewing.
- Relevant regression groups: 54 passed and 55 passed (109 total, zero final failures). An initial run caught the missing explicit no-fallback branch; it was fixed and rerun successfully. Existing Starlette/httpx warning remains. Not a full-suite claim. No frontend application source changed; frontend build was not run. The static review page was checked through complete browser playback.
- Old Ronaldo r20, Messi r19, original Henry r32 and accepted Henry local review v2 hashes/preservation verified. New normal revisions selected with three distinct asset records each, script hashes matching and zero approvals.

## Remaining review issues

Direct listening is unavailable in this session. Naturalness, perceived clarity, correct pronunciation of names, and perceptual caption synchronization require the user's listening review; they are not marked passed. Automated audio-level and timing checks do not replace that review. AI visuals and relevant licensed clips were unavailable under the verified-free constraints; zero AI visuals or clips were generated or claimed. Current outputs use recorded licensed photographs only. Local CPU speech synthesis was slow but completed.

Uploads and scheduling remain disabled. No upload, deployment, publication or new approval occurred. After final video review, one separately supervised upload is the intended next step.

## Artifacts and evidence

- Ronaldo: [r21 MP4](generated/videos/230904a6-bfc0-4182-b240-c4d498cd99fe/revision-21/short.mp4)
- Messi: [r20 MP4](generated/videos/7f51b5de-a19d-4faf-9318-43dc15ba2b06/revision-20/short.mp4)
- Henry accepted reference: [local review v2](generated/hybrid-review/pilot/videos/henry-local-review/revision-2/short.mp4)
- Representative visual evidence: generated/hybrid-review/verification/ronaldo/motion-contact-sheet.jpg and generated/hybrid-review/verification/messi/motion-contact-sheet.jpg; transition-contact-sheet.jpg in each directory.
- Selection and preservation: generated/hybrid-review/selected-revisions.json; normal-before/ snapshots.
- Technical checks: generated/hybrid-review/verification/{ronaldo,messi}/results.json.
- Normal API/download checks: generated/hybrid-review/selected-revision-verification.json.
- Complete page/download playback: generated/hybrid-review/three-pilot-playback/results.json.
- Tests: generated/hybrid-review/two-pilot-final-regression.xml and two-pilot-voice-regression.xml.
- Accepted voice proof: generated/hybrid-review/pilot-henry-revision-2/source-narration.generation.json.
