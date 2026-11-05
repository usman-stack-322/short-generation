# Multi-language generation

The shared catalog is `backend/app/core/languages.py`. The authenticated
`GET /api/languages` endpoint supplies the same definitions to all UI selectors.

| Language | Output locale |
| --- | --- |
| English | en-US |
| Urdu | ur-PK |
| Spanish | es-ES |
| Italian | it-IT |
| Chinese | zh-CN |
| Arabic | ar-SA |
| French | fr-FR |
| German | de-DE |
| Hindi | hi-IN |
| Portuguese | pt-BR |

Create Short initially selects the channel's language and can override it. API
requests with no language inherit the channel default, then en-US. Legacy short
codes en/es/fr remain accepted. Unsupported codes return HTTP 400. Research
remains independent of output language and all existing fact-verification gates
remain in place.

Gemini script and SEO prompts request original native phrasing and preservation
of names, dates, values, scores and quotations. Localized development copy is
explicitly marked as development; a live provider failure never uses it.

## Narration

Voice Provider Auto checks installed local voices first, then configured Google
and ElevenLabs providers. Manual provider selection retains priority, with a
compatible configured alternative used if necessary. The saved narration record
contains the provider, actual narrator and provider locale, alongside the Voice
Director profile and output locale. No celebrity cloning is added.

- Local voice availability is read from pyttsx3/SAPI. An English system voice
  cannot be used for Urdu/Chinese narration. Normal pipeline jobs cannot use the
  legacy silent development audio fallback as successful narration.
- Google voices.list must advertise a compatible language. Mandarin can map
  zh-CN output to a cmn-CN voice. Urdu can map ur-PK output to an advertised ur-IN
  Urdu voice. The actual provider locale is shown in review. Unsupported Google
  voice families receive no SSML/pitch/rate controls.
- ElevenLabs checks language support on the existing eleven_multilingual_v2
  model using API metadata. A newer model's language coverage is never assumed
  for this model. Generic narrator IDs still require the existing allowlist.

If no compatible provider is available, the job fails at voice_generation with
instructions to install a matching system voice or configure a compatible cloud
narrator. This environment currently has English local voices only; no compatible
cloud narrators are configured for the other tested languages.

## Unicode rendering

Subtitles come directly from final narration. Chinese uses character-sized timing
units rather than assuming whitespace-delimited words; scene planning also covers
the complete Chinese script. Urdu and Arabic stay in logical Unicode order, with
RTL UI direction and bidi-aware libass rendering. Pillow cover rendering uses
libraqm shaping. Letters are never manually reversed.

Font coverage is checked with fontTools before rendering. Windows Arial, Tahoma,
Microsoft YaHei and Nirmala UI provided the tested glyph coverage. Alternatively,
place the catalog's compatible Noto fonts in `backend/fonts/`. Missing glyphs or
missing RTL shaping produce a clear configuration error instead of broken squares.
The selected font is supplied to libass for each render. Covers preserve localized
headlines, without adding an English filler headline on overflow.

## Language changes and persistence

Changing language from review invalidates approvals and removes the old script,
SEO, narration, scenes, asset records, cover record and video record. The response
no longer exposes the old render as the current video. Regeneration starts at
script generation, keeps the previously researched facts, and rebuilds every
dependent stage. Existing media files may remain on disk as historical artifacts;
they are never reused as the new-language narration/render.

Migration `0004_languages` adds immutable language_code/language_name/locale
snapshots to existing video jobs and normalizes known channel defaults. Existing
content is retained and SQLite is backed up by the migration runner.

## Setup and verification

From the project root:

```powershell
.\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
cd backend
..\.venv\Scripts\python.exe -m app.database.migrate
..\.venv\Scripts\python.exe -m pytest -q
..\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

From frontend: `npm.cmd run build` or `npm.cmd run dev`.

Five live script/SEO samples and local cover/subtitle checks are recorded in
`generated/language-acceptance/report.json`. English used the normal configured
retry/fallback flow. After the primary model hit HTTP 429, the four remaining
diagnostic samples explicitly targeted the already configured fallback model,
without changing .env or the application's retry policy. All five passed native
script/SEO generation, subtitle/cover generation and checks for numeric values
5/2016 (with the permitted historical reference year 2017). This is a practical
content check, not a substitute for final human translation/fact review.

The existing real local English pipeline again produced a 30-second 1080x1920
H.264/AAC MP4. Non-English narration remains unavailable on this machine until a
compatible narrator is installed/configured; it is not reported as successful.
YouTube uploads remain disabled.

Final validation: 126 backend tests passed, zero failed (one existing dependency
deprecation warning); frontend production build passed. A real Urdu libass
subtitle frame was visually inspected for connected letters and RTL order.
The running backend serves all ten language definitions after restart.
