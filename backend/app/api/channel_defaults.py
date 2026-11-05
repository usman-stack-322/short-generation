"""Saved defaults are inherited by new channels; existing changes need preview + confirmation."""
import json
from zoneinfo import ZoneInfo,ZoneInfoNotFoundError
from fastapi import APIRouter,Depends,HTTPException
from pydantic import BaseModel,Field,field_validator,ConfigDict
from sqlalchemy.orm import Session
from app.database.session import get_db
from app.core.security import require_owner,current_context
from app.models import WorkspaceSettings,Channel
from app.core.languages import language_info
from app.tts.director import VoiceSelection
router=APIRouter(prefix='/api/channel-defaults')


class Defaults(BaseModel):
    model_config=ConfigDict(extra='forbid')
    default_language:str='en-US'
    default_voice:str=Field(default='en-US',min_length=1,max_length=80)
    voice_style:VoiceSelection='auto'
    generation_duration:int=45
    template:str='Documentary'
    timezone:str='UTC'
    posting_start:int=Field(default=0,ge=0,le=23)
    posting_end:int=Field(default=24,ge=1,le=24)
    minimum_gap_minutes:int=Field(default=60,ge=0,le=1440)
    visibility:str='private'
    approval_policy:str='owner_only'
    @field_validator('default_language')
    @classmethod
    def language(cls,v):return language_info(v).code
    @field_validator('generation_duration')
    @classmethod
    def duration(cls,v):
        if v not in {30,45,60}:raise ValueError('Choose 30, 45 or 60 seconds')
        return v
    @field_validator('template')
    @classmethod
    def template_valid(cls,v):
        if v not in {'Documentary','Energetic','Minimal'}:raise ValueError('Invalid template')
        return v
    @field_validator('timezone')
    @classmethod
    def zone(cls,v):
        try:ZoneInfo(v)
        except ZoneInfoNotFoundError:raise ValueError('Use an IANA timezone') from None
        return v
    @field_validator('visibility')
    @classmethod
    def visible(cls,v):
        if v not in {'private','unlisted','public'}:raise ValueError('Invalid visibility')
        return v
    @field_validator('approval_policy')
    @classmethod
    def approval(cls,v):
        if v not in {'owner_only','member_only','either','both'}:raise ValueError('Invalid approval mode')
        return v


PRESETS={'sports_news':Defaults(voice_style='energetic',template='Energetic').model_dump(),
    'sports_commentary':Defaults(template='Documentary').model_dump(),
    'business_storytelling':Defaults(template='Minimal').model_dump()}


def saved_defaults(db,workspace_id):
    row=db.get(WorkspaceSettings,workspace_id)
    return Defaults(**json.loads(row.data or '{}').get('channel_defaults',{})).model_dump() if row else Defaults().model_dump()


def apply_channel(channel,defaults,explicit=None):
    explicit=explicit or set()
    for key in ('default_language','default_voice','voice_style','generation_duration','approval_policy'):
        if key not in explicit:setattr(channel,key,defaults[key])
    channel.operational_defaults=json.dumps(defaults)


@router.get('')
def read(context=Depends(current_context),db:Session=Depends(get_db)):
    return {'defaults':saved_defaults(db,context[1].workspace_id),'presets':PRESETS}


@router.put('')
def save(payload:Defaults,context=Depends(require_owner),db:Session=Depends(get_db)):
    if payload.posting_start>=payload.posting_end:raise HTTPException(422,'Posting window start must precede end')
    row=db.get(WorkspaceSettings,context[1].workspace_id)
    if not row:row=WorkspaceSettings(workspace_id=context[1].workspace_id,data='{}');db.add(row)
    data=json.loads(row.data);data['channel_defaults']=payload.model_dump();row.data=json.dumps(data);db.commit()
    return read(context,db)


class Apply(BaseModel):
    channel_ids:list[str]=Field(min_length=1,max_length=100)
    defaults:Defaults
    confirmed:bool=False


@router.post('/apply')
def apply(payload:Apply,context=Depends(require_owner),db:Session=Depends(get_db)):
    rows=db.query(Channel).filter(Channel.workspace_id==context[1].workspace_id,Channel.member_id==context[1].id,Channel.id.in_(payload.channel_ids)).all()
    if len(rows)!=len(set(payload.channel_ids)):raise HTTPException(404,'Workspace channel not found')
    if payload.defaults.posting_start>=payload.defaults.posting_end:raise HTTPException(422,'Invalid posting window')
    if payload.defaults.approval_policy=='both' and any(not c.member_id for c in rows):raise HTTPException(422,'Assign members before requiring both approvers')
    proposed=payload.defaults.model_dump()
    changes=[{'channel_id':c.id,'channel':c.name,'before':{k:getattr(c,k) for k in ('default_language','default_voice','voice_style','generation_duration','approval_policy')},'after':proposed} for c in rows]
    if payload.confirmed:
        for c in rows:apply_channel(c,proposed)
        db.commit()
    return {'applied':payload.confirmed,'changes':changes}
