# AI Shorts Studio v2 — Phase 1 (Smart Hybrid Foundation)

Yeh **AI Shorts v2** ka clean, modular Phase 1 foundation hai jo aapke **100 GB Celebrity Clips Vault**, **Cloud Database (PostgreSQL)**, **Cloudflare R2 Storage**, aur **Option B Local PC Worker** ke liye design kiya gaya hai—aur Phase 2 mein bina rewrite kiye **SaaS** mein scale ho sakta hai.

## Folder Structure
- `backend/app/` — FastAPI v2 API, SQLAlchemy 2.0 SaaS-ready models (`User`, `Celebrity`, `MediaClip`, `VideoProject`, `RenderJob`), Cloudflare R2 presigned/multipart service, aur smart `clip_matcher.py`.
- `scripts/bulk_sync_r2.py` — Resumable **100 GB Bulk Uploader & Auto-Indexer** (fast SHA-256 fingerprint + `ffprobe` metadata + `--dry-run` preview).
- `backend/tests/` — Automated QA suite (`test_clip_matcher.py`, `test_bulk_sync_scanner.py`, `test_api_contract.py`).

## Quick Setup (Windows / Local PC)

1. **Extract & Virtual Environment:**
   ```bash
   cd "c:/Users/ua589/short generation"
   python -m venv .venv
   .venv\Scripts\activate
   pip install -r backend/requirements.txt
   ```

2. **Environment File:**
   - `.env.example` ko `.env` mein copy karein.
   - **Cloud Database:** [Neon.tech](https://neon.tech) par free PostgreSQL database bana kar `DATABASE_URL` paste karein (testing ke liye default SQLite bhi chalega).
   - **100 GB Storage:** Cloudflare Dashboard → R2 → bucket banayein (`ai-shorts-vault`) aur API token keys `.env` mein daalein.

3. **Backend Start Karein:**
   ```bash
   uvicorn backend.app.main:app --reload --port 8000
   ```
   Open `http://127.0.0.1:8000/docs` to see all v2 APIs.

4. **Apne 100 GB Clips Folder ko Dry-Run Test Karein (Upload se pehle):**
   Make sure folder structure aisa ho: `D:\CelebrityClips\LeBron James\clip1.mp4`
   ```bash
   python scripts/bulk_sync_r2.py --folder "D:\CelebrityClips" --dry-run
   ```
   Jab dry-run sahi lage, to `--dry-run` hata kar run karein—agar internet disconnect ho jaye to dobara chalane par wahin se resume hoga!

5. **QA Tests Run Karein:**
   ```bash
   pytest backend/tests -v
   ```

## Next Phase (Phase 2)
Phase 1 setup confirm hone ke baad hum **Phase 2** build karenge:
- Local PC Worker (`worker/run_worker.py`) with **`edge-tts`** (free neural voiceover + word timestamps), **Gemini script generator**, **`yt-dlp` real original clip fetcher**, aur **FFmpeg `9:16` Shorts + bold captions renderer**.
