"""Recover in-process workers at startup, retaining committed stage artifacts."""
from app.models import VideoJob

STEPS = {'researching', 'script_generation', 'seo_generation', 'collecting_assets', 'voice_generation', 'rendering', 'creating_cover'}


def recover_interrupted_jobs(db):
    for job in db.query(VideoJob).filter(VideoJob.status.in_(STEPS)):
        job.failed_step = job.current_step if job.current_step in STEPS else job.status
        job.status = 'failed'
        job.current_step = 'interrupted'
        job.error_message = 'Local worker interrupted. Retry the failed step to resume from saved checkpoints.'
    db.commit()
