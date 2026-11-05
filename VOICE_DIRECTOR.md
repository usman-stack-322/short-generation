# Automatic Voice Style Director

Voice Style defaults to Auto. A deterministic local director examines the topic,
spoken script (including the hook), category, theme tone, video style and scene
hints. Explicit script/topic cues take priority over personality defaults.
Sensitive stories use calm delivery; analysis takes priority over achievement
hype. No extra AI request or paid dependency is introduced.

Supported styles: professional, news, documentary, energetic, funny, emotional,
motivational, educational, dramatic, luxury, conversational, sports_hype, serious.
Manual selection overrides automatic classification. Failed classification logs
the problem and uses professional delivery at pace 1.0, energy 0.5.

Channel Configure stores provider, generic narrator and default style. Create
Short can override these. Review shows the saved direction, provider, narrator,
pace, energy and reason. Change style and Regenerate Voice updates narration and
video, invalidating prior approvals. Uploading stays disabled.

## Provider controls

- Local pyttsx3: operating-system voice selection, rate and volume only. It
  receives original text, never spoken style instructions or SSML. Pitch,
  emotion, emphasis and explicit pause controls are unsupported. Missing local
  speech still produces the existing clearly marked development silence.
- Google: Standard, Wavenet and Neural2 voice families receive speakingRate,
  pitch and volumeGainDb, plus escaped SSML sentence pauses and modest prosody.
  Scene emphasis words can receive moderate emphasis. Unknown voice families
  receive plain text and no optional prosody controls, preventing unsupported
  parameter requests. This deliberately conservative allowlist can be extended
  after checking a new voice family's capabilities.
- ElevenLabs: the existing eleven_multilingual_v2 model receives speed,
  stability, similarity_boost and style. No pitch, energy, SSML or emotion tags
  are sent. Expression is an approximation using documented settings. Only
  administrator-allowlisted generic narrator IDs are accepted. Administrators
  must keep cloned/impersonation voices out of that allowlist.
- Cloud failures retain the selected direction while using the existing local
  fallback. The saved delivery record reports the actual provider and controls.

All narration uses one narrator identity. Google SSML makes small sentence-level
changes without rewriting words. Local and ElevenLabs retain original spoken
text. Profile pace is bounded to 0.85–1.15, energy/emphasis/pause strength to 0–1,
pitch to -0.2–0.2, and volume to 0.1–1.0; nonfinite values are rejected. Final
provider rates are bounded separately. Fixed video duration constrains slow
narration; the renderer retains the complete script and aligns subtitles to
the fitted narration duration.

References: [Google SSML](https://docs.cloud.google.com/text-to-speech/docs/ssml),
[ElevenLabs settings](https://elevenlabs.io/docs/api-reference/voices/settings/get).

## Persistence and verification

Migration `0003_voice_director` adds channel/job style defaults, optional job
provider override, and nullable profile/delivery JSON on existing narration
records. Existing narrations remain valid; direction appears after regeneration.
The migration runner backs up existing SQLite data before upgrading.

From `backend`:

```powershell
..\.venv\Scripts\python.exe -m app.database.migrate
..\.venv\Scripts\python.exe -m pytest -q
```

From `frontend`:

```powershell
npm.cmd run build
```

`backend/verify_voice_director.py` checks the four requested semantic examples and
performs a real local TTS/FFmpeg render using the cached live Gemini script from
`generated/gemini-fallback-verification.json`. It makes no cloud requests, marks
the acceptance job as development research, and never publishes it. Run it after
finishing code edits so the development autoreloader cannot interrupt its job.
Evidence is saved in `generated/voice-director-acceptance.json`.

Cloud mappings are covered with mocked API requests; they do not establish live
Google/ElevenLabs synthesis availability without those providers' credentials.
