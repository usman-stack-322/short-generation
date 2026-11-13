from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import current_context, new_id, require_admin
from app.database.session import get_db
from app.models import Channel, WorkspaceMember,ChannelAssignment
from app.schemas import ChannelInput
from app.schemas import InputModel
from app.tts.director import VoiceSelection
from app.core.languages import language_info
from pydantic import Field, field_validator


from app.api.access import _membership_for_workspace, _accessible_channel_ids
router = APIRouter()
generated_dir = Path(settings.generated_dir).resolve()


class ChannelSettings(InputModel):
    evergreen_source_urls: list[str] = Field(default_factory=list,max_length=20)
    @field_validator('evergreen_source_urls')
    @classmethod
    def historical_references(cls,value):
        from app.core.network import reference_urls
        return reference_urls(value)
    automatic_evergreen_fallback: bool = False
    automatic_generation_enabled: bool = False
    generation_duration: int = Field(default=45,ge=30,le=60)
    @field_validator('generation_duration')
    @classmethod
    def automatic_duration(cls,value):
        if value not in {30,45,60}:raise ValueError('Duration must be 30, 45 or 60 seconds')
        return value
    niche: str = Field(default='',max_length=160)
    member_id: str | None = None
    assigned_member_ids: list[str] | None = Field(default=None,max_length=100)
    default_language: str = 'en-US'
    @field_validator('default_language')
    @classmethod
    def language(cls,value):
        return language_info(value).code
    voice_style: VoiceSelection = 'auto'
    approval_policy: str = 'owner_only'
    daily_video_target: int = Field(default=1,ge=1,le=3)
    default_voice: str = Field(default='en-US',max_length=80)
    tts_provider: str = 'local'
    brand_color: str = Field(default='#61e8b6',pattern=r'^#[0-9a-fA-F]{6}$')

    @field_validator('approval_policy')
    @classmethod
    def policy(cls,v):
        if v not in {'owner_only','member_only','either','both'}: raise ValueError('Invalid approval policy')
        return v

    @field_validator('tts_provider')
    @classmethod
    def provider(cls,v):
        if v not in {'auto','local','google','elevenlabs'}: raise ValueError('Invalid narrator provider')
        return v


@router.patch('/api/channels/{channel_id}')
def configure_channel(channel_id:str,payload:ChannelSettings,context=Depends(require_admin),db:Session=Depends(get_db)):
    channel=db.get(Channel,channel_id)
    if not channel or channel.workspace_id!=context[1].workspace_id:
        raise HTTPException(404,'Workspace channel not found')
    from app.youtube.permissions import channel_access
    channel_access(channel,context[1],True)
    if payload.assigned_member_ids or payload.member_id not in {None,context[1].id}:
        raise HTTPException(403,'Channels cannot be shared or transferred to another member')
    if 'member_id' in payload.model_fields_set and payload.member_id!=context[1].id:
        raise HTTPException(403,'A channel must retain its owner')
    if payload.member_id: _membership_for_workspace(db,channel.workspace_id,payload.member_id)
    if payload.assigned_member_ids is not None:
        for key in payload.assigned_member_ids: _membership_for_workspace(db,channel.workspace_id,key)
        db.query(ChannelAssignment).filter_by(channel_id=channel.id).delete(synchronize_session=False)
        for key in set(payload.assigned_member_ids):db.add(ChannelAssignment(channel_id=channel.id,member_id=key))
    policy=payload.approval_policy if 'approval_policy' in payload.model_fields_set else channel.approval_policy
    target_member=payload.member_id if 'member_id' in payload.model_fields_set else channel.member_id
    if policy=='both' and not target_member:
        raise HTTPException(422,'Assign a member before requiring both approvers')
    import json
    for key,value in payload.model_dump(exclude_unset=True,exclude={'assigned_member_ids'}).items():
        setattr(channel,key,json.dumps(value) if key=='evergreen_source_urls' else value)
    channel.approval_required=True
    db.commit()
    return {'id':channel.id,'approval_policy':channel.approval_policy}

@router.get("/api/channels")
def list_channels(context=Depends(require_admin), db: Session = Depends(get_db)):
    _, membership = context
    query = db.query(Channel).filter_by(workspace_id=membership.workspace_id)
    visible_ids = _accessible_channel_ids(db, membership)
    if visible_ids is not None:
        query = query.filter(Channel.id.in_(visible_ids))
    channels = query.order_by(Channel.created_at.desc()).all()
    member_names = {m.id: m.user.name for m in db.query(WorkspaceMember).filter_by(workspace_id=membership.workspace_id).all()}
    return [{
        "id": c.id, "name": c.name, "youtube_channel_id": c.youtube_channel_id,
        **({'assigned_member_ids':[r.member_id for r in db.query(ChannelAssignment).filter_by(channel_id=c.id)]} if membership.role in {'OWNER','ADMIN'} else {}),
        "profile_image_url": c.profile_image_url, "status": c.status, "member_id": c.member_id,
        "member_name": member_names.get(c.member_id) if c.member_id else None,
        "default_language": c.default_language, "default_voice": c.default_voice, "voice_style": c.voice_style,
        "daily_video_target": c.daily_video_target, "approval_required": True,
        "automatic_evergreen_fallback":c.automatic_evergreen_fallback,"automatic_generation_enabled":c.automatic_generation_enabled,
        "generation_duration":c.generation_duration,"niche":c.niche,
        "operational_defaults":__import__('json').loads(c.operational_defaults or '{}'),
        "evergreen_source_urls":__import__('json').loads(c.evergreen_source_urls or '[]'),
        "approval_policy":c.approval_policy,"subscriber_count":c.subscriber_count,"video_count":c.video_count,
        "channel_url":c.channel_url,"connection_error":c.connection_error,"tts_provider":c.tts_provider,"brand_color":c.brand_color,
        "connected_at": c.connected_at.isoformat() if c.connected_at else None,
        "created_at": c.created_at.isoformat(),
    } for c in channels]


@router.get('/api/channels/{channel_id}')
def read_channel(channel_id:str,context=Depends(require_admin),db:Session=Depends(get_db)):
    from app.youtube.permissions import channel_access
    channel_access(db.get(Channel,channel_id),context[1])
    return next(row for row in list_channels(context,db) if row['id']==channel_id)


@router.post("/api/channels", status_code=status.HTTP_201_CREATED)
def create_channel(payload: ChannelInput, context=Depends(require_admin), db: Session = Depends(get_db)):
    _, membership = context
    if payload.member_id not in {None,membership.id}:
        raise HTTPException(403,'Create channels only in your own workspace')
    payload.member_id=membership.id
    payload.approval_policy='member_only'
    if payload.member_id:
        _membership_for_workspace(db, membership.workspace_id, payload.member_id)
    channel = Channel(id=new_id(), workspace_id=membership.workspace_id, member_id=payload.member_id, name=payload.name.strip(), youtube_channel_id=payload.youtube_channel_id, profile_image_url=payload.profile_image_url, status="demo", default_language=payload.default_language, default_voice=payload.default_voice, daily_video_target=payload.daily_video_target, approval_required=True, approval_policy=payload.approval_policy)
    db.add(channel)
    channel.voice_style, channel.tts_provider = payload.voice_style, payload.tts_provider
    channel.automatic_evergreen_fallback=payload.automatic_evergreen_fallback
    channel.automatic_generation_enabled=payload.automatic_generation_enabled
    channel.generation_duration=payload.generation_duration;channel.niche=payload.niche
    import json
    channel.evergreen_source_urls=json.dumps(payload.evergreen_source_urls)
    from app.api.channel_defaults import saved_defaults,apply_channel
    apply_channel(channel,saved_defaults(db,membership.workspace_id),payload.model_fields_set)
    channel.approval_policy='member_only'
    db.commit()
    return {"id": channel.id, "name": channel.name, "status": channel.status, "member_id": channel.member_id}


