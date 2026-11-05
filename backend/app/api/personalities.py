import json
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status,Response
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import current_context, new_id, require_owner, require_editor
from app.database.session import get_db
from app.models import Channel, Personality
from app.schemas import PersonalityInput,InputModel


from app.api.access import _accessible_channel_ids,personality_visible
router = APIRouter()
generated_dir = Path(settings.generated_dir).resolve()

@router.get("/api/personalities")
def list_personalities(context=Depends(current_context), db: Session = Depends(get_db)):
    _, membership = context
    rows = db.query(Personality).filter_by(workspace_id=membership.workspace_id).order_by(Personality.created_at.desc()).all()
    visible_ids = _accessible_channel_ids(db, membership)
    if visible_ids is not None:
        rows = [p for p in rows if personality_visible(p,membership,visible_ids)]
    return [{
        "id": p.id, "name": p.name, "category": p.category, "description": p.description,
        "keywords": json.loads(p.keywords), "preferred_language": p.preferred_language,
        "tone": p.tone, "default_duration": p.default_duration, "default_voice": p.default_voice,
        "enabled": p.enabled, "channel_id": p.channel_id, "research_keywords": json.loads(p.research_keywords),
        "visibility":p.visibility,"default_voice_style":p.default_voice_style,
    } for p in rows]


@router.post("/api/personalities", status_code=status.HTTP_201_CREATED)
def create_personality(payload: PersonalityInput, response:Response, context=Depends(require_editor), db: Session = Depends(get_db)):
    _, membership = context
    visibility=payload.visibility or ('workspace' if membership.role=='OWNER' else 'personal')
    if visibility not in {'workspace','personal'}: raise HTTPException(422,'Invalid visibility')
    if membership.role!='OWNER' and visibility!='personal': raise HTTPException(403,'Only owners can share workspace personalities')
    if payload.channel_id:
        channel = db.get(Channel, payload.channel_id)
        if not channel or channel.workspace_id != membership.workspace_id:
            raise HTTPException(status_code=400, detail="Select a channel in this workspace.")
        from app.youtube.permissions import channel_access
        channel_access(channel,membership,True)
    from app.services.personality_identity import find_equivalent
    existing=find_equivalent(db,membership,payload.name,payload.channel_id,visibility)
    if existing:
        if not existing.enabled:raise HTTPException(409,'An equivalent personality in this scope is disabled. Ask the owner to review it.')
        response.status_code=200
        result={'id':existing.id,'name':existing.name,'category':existing.category,'channel_id':existing.channel_id,'reused':True}
        db.commit()
        return result
    personality = Personality(
        id=new_id(), workspace_id=membership.workspace_id, channel_id=payload.channel_id,
        creator_member_id=membership.id,visibility=visibility,default_voice_style=payload.default_voice_style,
        name=payload.name.strip(), category=payload.category.strip(), description=payload.description,
        keywords=json.dumps(payload.keywords), preferred_language=payload.preferred_language,
        tone=payload.tone, default_duration=payload.default_duration, default_voice=payload.default_voice,
        enabled=payload.enabled, research_keywords=json.dumps(payload.research_keywords),
    )
    db.add(personality)
    db.commit()
    return {"id": personality.id, "name": personality.name, "category": personality.category, "channel_id": personality.channel_id,"reused":False}


class ShareInput(InputModel):
    channel_id:str


@router.get('/api/personalities/{personality_id}')
def read_personality(personality_id:str,context=Depends(current_context),db:Session=Depends(get_db)):
    matches=[row for row in list_personalities(context,db) if row['id']==personality_id]
    if not matches:raise HTTPException(404,'Personality not found')
    return matches[0]


@router.patch('/api/personalities/{personality_id}/share')
def share_personality(personality_id:str,payload:ShareInput,context=Depends(require_owner),db:Session=Depends(get_db)):
    personality=db.get(Personality,personality_id)
    if not personality or personality.workspace_id!=context[1].workspace_id:raise HTTPException(404,'Personality not found')
    if personality.creator_member_id!=context[1].id:raise HTTPException(404,'Personality not found')
    channel=db.get(Channel,payload.channel_id)
    if not channel or channel.workspace_id!=context[1].workspace_id:raise HTTPException(422,'Select a workspace channel for sharing')
    personality.visibility,personality.channel_id='workspace',channel.id
    db.commit()
    return {'id':personality.id,'visibility':personality.visibility,'channel_id':channel.id}


