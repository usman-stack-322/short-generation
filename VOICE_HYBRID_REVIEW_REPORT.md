# Voice and single-pilot continuation — 27 October 2026

One improved Henry review candidate and nine comparable free/local voice samples are delivered. The normal pilot records remain Ronaldo r20, Messi r19 and Henry r32. All earlier renders and failed attempts are retained. No other pilot was rebuilt, approved, deployed or published. YouTube uploads and scheduling are disabled.

## Narration diagnosis: actual tracks

Database output paths, audio hashes, stored delivery metadata, native timing and provider code were inspected; configured defaults were not used as proof of provenance. Ronaldo r20 and Messi r19 use Microsoft David through Windows SAPI at recorded speed 1.08 (167 configured words/minute), about 169 actual words/minute in the finished audio. Henry r32 uses an existing ElevenLabs George track, model eleven_multilingual_v2, speed 1, stability .5, similarity .75 and style .1, about 146 actual words/minute. Their hashes and full records are in current-diagnosis.json.

The local worker synthesizes a full script, not separate scenes. Its saved emotion/emphasis segments are not supported SAPI controls. ElevenLabs also received one full script and global voice_settings; its saved scene directions were not transmitted as per-scene emotions. Flat global controls and repetitive formal sentence construction are concrete limitations. Neither level normalization nor non-silence establishes naturalness. Direct listening is unavailable, so the precise perceived cause is not claimed proven. Henry's measured pace does not establish excessive speed.

## Free candidates and timing

Kokoro's model card identifies Apache-2.0 weights; the kokoro-onnx wrapper is MIT and supports CPU. Voices/languages are documented separately (American/British English, Japanese, Mandarin, Spanish, French, Hindi, Italian, Brazilian Portuguese), with language-specific limitations. This workflow actually validates English only. Dependencies retain their own licenses. References: [model](https://huggingface.co/hexgrad/Kokoro-82M), [voices](https://huggingface.co/hexgrad/Kokoro-82M/blob/main/VOICES.md), [runtime](https://github.com/thewh1teagle/kokoro-onnx).

This machine has an i7-10510U, eight logical CPUs, about 15.8 GiB RAM and Intel UHD graphics with 1 GiB reported graphics memory. A separate bundled Python 3.12 runtime and workspace-local packages avoid changing the application's Python 3.14 environment. Official release v1.1 INT8 weights are 114,119,327 bytes, verified against publisher SHA-256 ae315a79b623f244700e4afb9246c46a26066782e049ba174bf3ba433970ee9c. Model/voice/license evidence is in models/. The first full-model transfer was incomplete and rejected; the smaller ranged download passed the official digest.

The same hook, serious passage and achievement passage were generated with two Kokoro presets and installed Microsoft David. All final nine runs succeeded. Raw WAVs remain beside loudness-matched listening WAVs; no speech speed, pitch, emotion effect or pause edits were used for matching. Comparison MP3 reels concatenate hook → serious → achievement with half-second separators. Those separators are review organization, not narration edits.

| Voice | Passage | Audio seconds | Measured synthesis seconds | End-to-end wall seconds |
|---|---|---:|---:|---:|
| bm_george | hook | 8.225 | 146.71 | 152.61 |
| bm_george | serious | 8.475 | 149.76 | 155.69 |
| bm_george | achievement | 8.875 | 142.27 | 148.22 |
| bf_emma | hook | 7.455 | 120.99 | 127.47 |
| bf_emma | serious | 7.475 | 126.64 | 132.72 |
| bf_emma | achievement | 7.830 | 122.46 | 127.79 |
| sapi_david | hook | 7.695 | not separately instrumented | 2.82 |
| sapi_david | serious | 6.746 | not separately instrumented | 1.66 |
| sapi_david | achievement | 7.907 | not separately instrumented | 2.38 |

These measurements include CPU contention in this run; they are not best-case benchmarks. Kokoro is slow on this laptop. Provisional choice: bm_george, a generic British-English male model preset, used consistently for the pilot. It is a separate voice from the previous ElevenLabs George track. Emma is a viable technical alternative. No listening score or superiority claim is made.

The read-only account check found ElevenLabs free tier, 353/10,000 characters used, no overage extension; Google TTS is unconfigured. No new cloud speech request was made. The provider's [free-plan terms](https://elevenlabs.io/docs/help-center/legal/can-i-publish-the-content-i-generate-on-the-platform) exclude commercial use, so free quota was not treated as a suitable commercial production license. No paid selection, voice clone, purchase or upgrade occurred.

## New pilot and implemented behavior

[Henry local review v2 MP4](generated/hybrid-review/pilot/videos/henry-local-review/revision-2/short.mp4), 18.5 seconds. The new full script is 46 words, about 154 words/minute. Native model speed is 1.0; no time stretch or quiet-interval removal was applied. Synthesis took 249.73 seconds plus 4.91 seconds model loading; synthesis/render helper total 285.62 seconds. The failed earlier attempt stopped on acronym timing and produced no selected MP4.

The script uses a question, conversational context, peer recognition and a concise close. Facts remain Henry, 2004, English PFA Player of the Year, second consecutive season, and peer recognition, rechecked against [UEFA](https://www.uefa.com/news-media/news/019c-0f8e9d0ccd0c-19183188d315-1000--henry-honoured-by-peers/). No setback or injury was invented.

[HYBRID_SCENE_PLAN.md](HYBRID_SCENE_PLAN.md) gives each scene's text, purpose, emotion/intensity/pace targets, emphasis, pauses, pronunciation notes, visual choice and motion. Kokoro actually receives generic voice, English locale, native global speed, phonemes and supported punctuation pauses. It does not accept emotion instructions or per-word intensity. The arc therefore uses wording and punctuation; editorial emotion targets remain intent, not claimed engine controls. PFA is expanded to individual letters and Thierry/Henry use declared English-IPA approximations. Pronunciation remains pending listening approval.

The new optional renderer path accepts explicit scene motion and cut/dissolve choices. Scene text anchors to new narration timings rather than equal time slots. Four distinct genuine archival photos replace six scenes with two repeats. Camera choices are push-in 4.5%, pan right 8%, pull-out 5%, closing push-in 2.5%; two cuts and one .2-second dissolve. Fitted sharp foregrounds are capped to native source detail, with deliberate same-photo blurred backdrops. No recovered-detail claim, face animation, lip-sync or unvalidated segmentation/parallax is used. Captions stay box-free, with no decorative cards, corner labels or bottom panel.

The reusable workflow is tools/render_local_pilot.py --plan <plan.json> --voice <generic preset>. It creates independent revision folders and can consume other subjects' real plans without rebuilding them now. This is an opt-in local workflow; it does not silently replace normal provider defaults or add a new frontend voice selector.

## Hybrid visual blocker and functional import support

The delivered video contains four archival photo scenes, zero clips, zero AI-generated scenes. Current library inspection found zero approved Henry clips. No new asset was downloaded or invented. [Credits](generated/hybrid-review/pilot/videos/henry-local-review/revision-2/credits.txt) preserve photographer, source page, CC BY 2.0 license link, dates and modifications. These photos illustrate Henry and are not represented as images of the 2004 award event.

A practical free local image-generation runtime was not established on the integrated GPU/CPU setup. The built-in image tool is present, but its metering/free entitlement is not exposed; it was not invoked under the free-only constraint. No stock search is labeled AI generation. Proposed conceptual football illustrations in the scene plan are explicitly ungenerated. The actual AI portion of the requested hybrid remains blocked.

User-provided generated images can be imported through app/video/import_scene_plan.py and the --plan workflow: copy the real file inside the workspace, declare visual_type=ai_illustration, provider/model/prompt, rights_confirmed=true, rights_basis and disclosure=AI illustration. File decoding, size, root containment and hashes are checked. Real imported assets retain the existing license policy. Generated scenes receive readable top-centred disclosure only during their own time span. No invented documentary event, player injury/action or statement is accepted by the editorial plan. No generated file is present or claimed in this pilot.

## Verification actually performed

Final MP4: 1080×1920 H.264, 30 fps, AAC 48 kHz; full decoding exit 0; no detected black frames or freezes; four distinct assets and inspected start/middle/end frames for every scene plus before/mid/after samples for every transition. Audio: -15.09 LUFS, -1.49 dBTP, zero clipped final PCM samples; no quiet interval meeting -42 dB / .25s threshold. Caption text matches the script, cues do not overlap and remain within final speech, and hashes match final audio/script. Timing uses native model phoneme durations with G2P word-span matching, not ASR; overall phoneme match .9432. Five reduced function words use adjacent native phoneme bounds. Perceived synchronization remains unverified.

Installed Edge headless played the HTTP pilot to ended=true at 18.5s, readyState 4 throughout sampled states, 1080×1920 and decoded audio bytes, no media errors. Its actual Download MP4 action succeeded. The downloaded bytes match SHA-256 ce0bba1ab73a98caaeb4fc1fc2ebdb2ac6c8fda29425d9fd5e4b27ec2fbbc40f and fully decode. The exact downloaded file then played from start through ended=true in Edge with audio enabled. All nine sample controls reached readyState 4 with nonzero durations and no errors. No buffering failure was observed; native viewer sidebars are outside the encoded portrait frame. This is automated browser playback, not subjective listening or uninterrupted human editorial watching.

Final relevant tests: 51 passed, zero failures, one existing Starlette/httpx deprecation warning; 33.65s. Evidence: generated/hybrid-review/delivery-regression.xml. Covers real export/motion, source framing, explicit spoken-scene timing, license/import gates, generated disclosure, captions and narration failure safeguards. No full-suite run or frontend build is claimed; no frontend source was affected.

## Review and resume

Open [the local review page](http://127.0.0.1:8015/) for all nine samples and the pilot. Three playable reels are in comparison-v2/*-comparison.mp3. Evidence is in delivery-checkpoint.json, voice-review-results.json, verification/results.json, browser-playback.json, download-playback.json and download-decode.json. The local static server binds loopback port 8015 only; it is not a deployment. Restart with the bundled Python running generated/hybrid-review/serve_preview.py if needed.

Pending human judgment: naturalness, perceived emotion/intensity, name pronunciation, listening-based caption sync and overall visual pacing. The actual AI-visual blocker remains. Review one voice/pilot before regenerating Ronaldo or Messi. Their existing revisions and Henry's normal r32 are unchanged. Uploads remain disabled; no approval, publish or deployment action ran.
