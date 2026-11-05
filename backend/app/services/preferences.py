import json
from app.models import WorkspaceSettings, Notification
from app.core.security import new_id
from app.core.config import settings

DEFAULTS = {'default_provider': 'local', 'default_voice': 'en-US', 'default_duration': 45,
            'subtitle_mode': 'sentence', 'font_size': 58, 'caption_position': 'bottom',
            'max_words': 6, 'highlight_color': '#61e8b6', 'transitions': True,
            'research_provider': 'demo', 'background_music_id': None, 'voice_speed': 1.0}


def preferences(db, workspace_id):
    record = db.get(WorkspaceSettings, workspace_id)
    result = {**DEFAULTS, **(json.loads(record.data) if record else {})}
    result.pop('channel_defaults',None)
    # A server configured for live research cannot be downgraded by old demo preferences.
    result['research_provider'] = 'rss' if settings.research_provider == 'rss' else result['research_provider']
    return result


def notify(db, workspace_id, channel_id, title, message):
    db.add(Notification(id=new_id(), workspace_id=workspace_id, channel_id=channel_id,
                        title=title, message=message[:2000]))


def invalidate_approvals(db, job):
    from app.models import Approval, UploadTask
    job.content_revision += 1
    db.query(Approval).filter_by(job_id=job.id).delete(synchronize_session=False)
    task = db.query(UploadTask).filter_by(job_id=job.id).first()
    if task and task.status not in {'uploaded', 'uploading'}:
        task.status = 'cancelled'
