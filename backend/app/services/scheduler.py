"""Database-backed schedules; one local backend worker, no browser dependency."""
import logging
import threading
from datetime import datetime, timezone
from app.core.config import settings
from app.database.session import SessionLocal
from app.models import UploadTask, VideoJob
from app.youtube.upload import process_upload

logger = logging.getLogger(__name__)


def tick():
    from app.services.preparation import prepare_due
    prepare_due()
    if not settings.youtube_uploads_enabled:
        return
    with SessionLocal() as db:
        tasks = db.query(UploadTask).filter(UploadTask.status=='pending',UploadTask.scheduled_at.is_(None)).all()
        for task in tasks:
            if task.scheduled_at is None or task.scheduled_at.replace(tzinfo=timezone.utc) <= datetime.now(timezone.utc):
                process_upload(db, task)


def start_scheduler():
    stop = threading.Event()
    def run():
        while not stop.wait(5):
            try:
                tick()
            except Exception:
                logger.exception('Scheduler tick failed')
    thread = threading.Thread(target=run, name='shorts-scheduler', daemon=True)
    if settings.scheduler_enabled:
        thread.start()
    return stop, thread
