# 100% Free Deployment Guide (Render + Vercel + Cloudflare Tunnel)

This guide explains how to deploy the **AI Shorts Automation Platform** for **$0/month** using either:
- **Option A: Render (Free Docker Backend) + Vercel (Free React Frontend)**
- **Option B: Vercel (Free Frontend) + Local Backend via Free Cloudflare Tunnel** (great if you want to use your local CPU/GPU and local Kokoro TTS with zero cloud memory limits)

---

## Option A: Cloud Deployment (Render Free Docker + Vercel Free)

### Step 1: Push Your Repository to GitHub
1. Create a new private or public repository on GitHub.
2. Push this project root (containing `backend/`, `frontend/`, and `render.yaml`) to your GitHub repository:
   ```bash
   git init
   git add .
   git commit -m "Prepare for free Render and Vercel deployment"
   git branch -M main
   git remote add origin https://github.com/<your-username>/<your-repo>.git
   git push -u origin main
   ```

### Step 2: Deploy the Backend on Render (`plan: free`)
1. Go to [https://dashboard.render.com](https://dashboard.render.com) and sign in with GitHub.
2. Click **New +** → **Blueprint** (or **Web Service**).
3. Select your GitHub repository:
   - If using **Blueprint**, Render automatically reads [`render.yaml`](render.yaml) and configures the Docker service using [`backend/Dockerfile`](backend/Dockerfile).
   - If creating a **Web Service** manually:
     - **Runtime**: `Docker`
     - **Root Directory**: `backend`
     - **Dockerfile Path**: `./Dockerfile`
     - **Instance Type**: `Free`
4. In the Render **Environment** tab, set:
   - `GEMINI_API_KEY`: Your free Google AI Studio Gemini key
   - `CORS_ORIGINS`: Your Vercel frontend URL (e.g., `https://your-app.vercel.app`)
   - `APP_SECRET_KEY`: Any random 32+ character secret string
   - `TOKEN_ENCRYPTION_KEY`: Any random 32+ character secret string
5. Once deployed, copy your Render backend URL (for example: `https://ai-shorts-backend.onrender.com`) and verify `https://ai-shorts-backend.onrender.com/api/health` returns `{"status":"ok"}`.

### Step 3: Deploy the Frontend on Vercel (Free Tier)
1. Go to [https://vercel.com/new](https://vercel.com/new) and import the same GitHub repository.
2. Configure the Vercel project settings:
   - **Framework Preset**: `Vite`
   - **Root Directory**: `frontend`
   - **Build Command**: `npm run build`
   - **Output Directory**: `dist`
3. Under **Environment Variables**, add:
   - `VITE_API_BASE_URL` = `https://ai-shorts-backend.onrender.com` (your Render URL, with no trailing slash)
   - `VITE_API_URL` = `https://ai-shorts-backend.onrender.com`
4. Click **Deploy**. [`frontend/vercel.json`](frontend/vercel.json) is already configured to rewrite SPA routes (`/(.*) -> /index.html`).

---

## Option B: Hybrid Zero-Cost Setup (Vercel Frontend + Local Backend via Cloudflare Tunnel)

If you want fast local FFmpeg rendering, persistent SQLite storage on your disk, and local **Kokoro ONNX** narration while still sharing a public web UI:

1. Start your local backend as usual:
   ```powershell
   .\start-backend.ps1
   ```
2. Expose port `8000` over HTTPS for free using **Cloudflare Quick Tunnels** (no account required):
   ```powershell
   cloudflared tunnel --url http://127.0.0.1:8000
   ```
3. Copy the generated `https://<random-words>.trycloudflare.com` URL.
4. Set `VITE_API_BASE_URL` in Vercel (or `frontend/.env.local`) to that `.trycloudflare.com` URL.
   - Note: `backend/app/main.py` automatically permits `*.vercel.app` and `*.trycloudflare.com` origins via CORS regex, or you can explicitly list origins in `CORS_ORIGINS`.

---

## Zero-Key Online Visual Sourcing

When generating visuals for a Title-to-Short draft without local media, the backend automatically retrieves 9:16 scene visuals using **100% free, zero-API-key** providers before falling back to local documentary cards:
1. **Openverse API** (`https://api.openverse.org/v1/images/`) — Creative Commons / Public Domain photography.
2. **Lexica API** (`https://lexica.art/api/v1/search`) — High-resolution vertical scene illustrations.
3. **Pollinations 9:16 AI Generator** (`https://image.pollinations.ai/prompt/...`) — Direct `1080x1920` vertical visual generation.
4. **YouTube Multi-Frame Thumbnails** (`maxresdefault.jpg`, `hq1.jpg`, `hq2.jpg`, `hq3.jpg`) — When a YouTube reference URL is attached to the draft.
5. **Local Documentary Card** — Offline fallback if all internet sources are unreachable.

