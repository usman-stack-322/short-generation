"""Opt-in daily preparation, keyed durably by channel/timezone local day/target slot.

This schedules generation only. Publishing always uses the existing approvals.
"""
import hashlib
import json
import logging
from datetime import datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from fastapi import BackgroundTasks
from app.database.session import SessionLocal
from app.models import Channel, Personality, WorkspaceMember, GenerationRequest
from app.api.access import personality_visible, _accessible_channel_ids
from app.schemas import GenerateVideoInput

logger = logging.getLogger(__name__)


def prepare_due(now=None):
    from app.api.videos import generate_video
    now = now or datetime.now(timezone.utc)
    with SessionLocal() as db:
        channel_ids = [c.id for c in db.query(Channel.id).filter_by(automatic_generation_enabled=True).all()]

    for channel_id in channel_ids:
        try:
            with SessionLocal() as db:
                channel = db.get(Channel, channel_id)
                if not channel or not channel.automatic_generation_enabled:
                    continue
                actor = db.get(WorkspaceMember, channel.member_id) if channel.member_id else db.query(WorkspaceMember).filter_by(workspace_id=channel.workspace_id, role='OWNER', active=True).first()
                if not actor or not actor.active or actor.role == 'VIEWER':
                    continue
                visible = _accessible_channel_ids(db, actor)
                themes = [p for p in db.query(Personality).filter_by(workspace_id=channel.workspace_id, channel_id=channel.id, enabled=True).order_by(Personality.created_at)
                          if personality_visible(p, actor, visible)]
                if not themes:
                    continue

                defaults = json.loads(channel.operational_defaults or '{}')
                tz_name = defaults.get('timezone', 'UTC')
                try:
                    zone = ZoneInfo(tz_name)
                except (ZoneInfoNotFoundError, ValueError, TypeError):
                    zone = timezone.utc
                local_date = now.astimezone(zone).date()

                for slot in range(channel.daily_video_target):
                    operation = f'auto:{channel.id}:{local_date}:{slot}'
                    key = hashlib.sha256(('explicit:' + operation).encode()).hexdigest()
                    # Completed, failed and interrupted requests all retain their durable identity.
                    # Failed jobs use the existing explicit stage retry, never a new daily job.
                    if db.get(GenerationRequest, (channel.workspace_id, key)):
                        continue
                    theme = themes[slot % len(themes)]
                    payload = GenerateVideoInput(
                        operation_id=operation,
                        channel_id=channel.id,
                        personality_id=theme.id,
                        duration=channel.generation_duration,
                        voice=channel.default_voice,
                        language=channel.default_language,
                        tts_provider=channel.tts_provider,
                        voice_style=theme.default_voice_style if theme.default_voice_style != 'auto' else channel.voice_style
                    )
                    background = BackgroundTasks()
                    try:
                        result = generate_video(payload, background, (actor.user, actor), db)
                        # Only run background tasks if this invocation actually created the job (not claimed concurrently)
                        for task in background.tasks:
                            task.func(*task.args, **task.kwargs)
                    except Exception as exc:
                        db.rollback()
                        logger.warning('Daily preparation slot failed channel=%s slot=%s type=%s: %s', channel.id, slot, type(exc).__name__, exc)
        except Exception as exc:
            logger.warning('Daily preparation channel failed channel=%s type=%s: %s', channel_id, type(exc).__name__, exc)

