"""One durable job per operation, claimed by a database uniqueness constraint."""
import hashlib
import json
from fastapi import HTTPException
from app.models import GenerationRequest,VideoJob
from app.services.preferences import preferences


def identity(payload,channel,personality,db):
    from app.core.config import settings
    inputs=payload.model_dump(exclude={'operation_id'})
    inputs['operational_defaults']=channel.operational_defaults
    inputs['channel_defaults']={k:getattr(channel,k) for k in ('default_language','default_voice','voice_style','tts_provider','automatic_evergreen_fallback','niche','generation_duration','evergreen_source_urls')}
    inputs['personality_defaults']={k:getattr(personality,k) for k in ('name','tone','keywords','research_keywords','default_voice_style')}
    inputs['preferences']=preferences(db,channel.workspace_id)
    inputs['providers']={'live_ai':bool(settings.gemini_api_key),'model':settings.gemini_model,
                         'fallback_model':settings.gemini_fallback_model,'assets':settings.asset_provider}
    fingerprint=hashlib.sha256(json.dumps(inputs,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
    key=hashlib.sha256(('explicit:'+payload.operation_id).encode()).hexdigest() if payload.operation_id else fingerprint
    return key,fingerprint


def existing(db,workspace_id,key,fingerprint,strict=True):
    record=db.get(GenerationRequest,(workspace_id,key))
    if not record:return None
    if strict and record.fingerprint!=fingerprint:
        raise HTTPException(409,'Generation operation already exists with different inputs. Use a new operation_id.')
    return db.get(VideoJob,record.job_id)

