from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from . import database
from .api import auth, celebrities, clips, projects
from .config import get_settings

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    database.init_db()
    try:
        yield
    finally:
        database.engine.dispose()


DEFAULT_CORS_ORIGINS = [
    "https://aishorts.space",
    "https://www.aishorts.space",
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]

settings = get_settings()
allowed_origins = list(dict.fromkeys([*DEFAULT_CORS_ORIGINS, *settings.cors_origin_list]))

app = FastAPI(title=settings.app_name, version="2.0.0-phase1", lifespan=lifespan)


@app.middleware("http")
async def catch_unhandled_exceptions(request: Request, call_next):
    """Catch unexpected errors inside CORSMiddleware so even 500 responses include CORS headers."""
    try:
        return await call_next(request)
    except Exception:
        logger.exception("Unhandled error processing %s %s", request.method, request.url.path)
        return JSONResponse(status_code=500, content={"detail": "Internal server error"})


app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_origin_regex=r"^https://([a-zA-Z0-9-]+\.)?(aishorts\.space|vercel\.app)$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(celebrities.router)
app.include_router(clips.router)
app.include_router(projects.router)


@app.get("/api/health")
def health_check():
    current = get_settings()
    return {
        "status": "ok",
        "version": "2.0.0-phase1",
        "storage_mode": current.storage_mode,
        "r2_configured": current.r2_configured,
    }
