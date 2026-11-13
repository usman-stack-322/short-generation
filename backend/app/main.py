"""Application composition; route logic lives in app/api/."""
import logging
from app.core.logging import RedactAccessQuery
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.database.seed import seed_demo_data
from app.database.session import Base, engine, SessionLocal
from app.models import VideoJob
from app.api import auth, channels, dashboard, members, personalities, videos
from app.api import media, assets
from app.api import library
from app.api import title_shorts, studio
from app.api import scene_layout
from app.api import channel_defaults
from app.database.migrate import migrate_database
from app.services.scheduler import start_scheduler
from app.services.recovery import recover_interrupted_jobs
from app.api import youtube, publishing, research, analytics
from app.api import settings as settings_api

logging.basicConfig(level=logging.INFO)

@asynccontextmanager
async def lifespan(app):
    migrate_database()
    if settings.seed_demo:
        seed_demo_data()
    # The local worker is in-process. Interrupted jobs remain visible and retryable.
    with SessionLocal() as db:
        recover_interrupted_jobs(db)
        from app.models import TitleShortDraft
        from app.services.title_shorts import ACTIVE as TITLE_ACTIVE
        for draft in db.query(TitleShortDraft).filter(TitleShortDraft.status.in_(TITLE_ACTIVE)):
            draft.status="failed"
            draft.error_message="Generation interrupted by server restart. Review saved progress and retry."
        db.commit()
    with SessionLocal() as db:
        from app.models import UploadTask
        for task in db.query(UploadTask).filter_by(status='uploading'):
            task.status = 'upload_uncertain'
            task.error_message = 'Backend interrupted during upload. Reconcile in YouTube Studio before retrying.'
            job = db.get(VideoJob, task.job_id)
            job.status = 'upload_failed'
            job.error_message = task.error_message
        db.commit()
    stop, scheduler = start_scheduler()
    yield
    stop.set()
    if scheduler.is_alive():
        scheduler.join(timeout=2)

app = FastAPI(title="AI Shorts Automation Platform", version="0.2.0", lifespan=lifespan)
from sqlalchemy.orm.exc import StaleDataError
from sqlalchemy.exc import IntegrityError
from fastapi.responses import JSONResponse

@app.exception_handler(StaleDataError)
async def stale_update(request,exc):
    return JSONResponse(status_code=409,content={'detail':'Content changed concurrently. Refresh and retry.'})

@app.exception_handler(IntegrityError)
async def duplicate_update(request,exc):
    return JSONResponse(status_code=409,content={'detail':'This operation already exists or conflicts with a concurrent change. Refresh before retrying.'})
_extra_origins = [o.strip().rstrip("/") for o in getattr(settings, "cors_origins", "").split(",") if o.strip()]
_allowed_origins = list({settings.frontend_origin.rstrip("/"), "http://127.0.0.1:5173", "http://localhost:5173", *_extra_origins})
app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_origin_regex=r"^https://[a-zA-Z0-9-]+\.(vercel\.app|trycloudflare\.com)$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
for router_module in (auth, channels, dashboard, members, personalities, videos, youtube, publishing, research, settings_api, analytics, assets, library):
    app.include_router(router_module.router)

# Media links are signed and expire; the development server binds to loopback.
generated_dir = Path(settings.generated_dir).resolve()
generated_dir.mkdir(parents=True, exist_ok=True)
app.include_router(media.router)
app.include_router(scene_layout.router)
app.include_router(title_shorts.router)
app.include_router(studio.router)
app.include_router(channel_defaults.router)

@app.get("/api/health")
def health():
    return {"status": "ok", "service": "AI Shorts Automation Platform"}
