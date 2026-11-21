from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import database
from .api import celebrities, clips, projects
from .config import get_settings


@asynccontextmanager
async def lifespan(_app: FastAPI):
    database.init_db()
    try:
        yield
    finally:
        database.engine.dispose()


settings = get_settings()
app = FastAPI(title=settings.app_name, version="2.0.0-phase1", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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
