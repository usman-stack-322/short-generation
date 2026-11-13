import json
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.orm import Session
from app.core.security import current_context,require_owner,require_admin,new_id
from app.core.config import settings
from app.database.session import get_db
from app.models import WorkspaceSettings,Notification,MusicTrack,Workspace
from app.schemas import SettingsInput
from app.services.preferences import preferences
from app.api.access import _accessible_channel_ids

router=APIRouter(tags=['Settings'])


@router.get('/api/languages')
def languages(context=Depends(current_context)):
    from app.core.languages import LANGUAGES
    return [language.public() for language in LANGUAGES.values()]


@router.get('/api/settings')
def get_settings(context=Depends(current_context),db:Session=Depends(get_db)):
    from app.ai.smart_router import get_ai_status, has_any_ai_configured
    owner=context[1].role=='OWNER'
    workspace=db.get(Workspace,context[1].workspace_id)
    ai_stat = get_ai_status()
    return {'workspace':{'id':workspace.id,'name':workspace.name},'preferences':preferences(db,context[1].workspace_id),
            'active_configuration':{'gemini_configured':bool(settings.gemini_api_key.strip()),
                                    'ai_configured':has_any_ai_configured(),
                                    'primary_model':settings.gemini_model,
                                    'fallback_model_configured':bool(settings.gemini_fallback_model.strip()),
                                    'research_provider':preferences(db,context[1].workspace_id)['research_provider'],
                                    'asset_provider':settings.asset_provider,
                                    'ai_status':ai_stat},
            'review_drafts_enabled':settings.review_drafts_enabled,
            'providers':{'gemini':bool(settings.gemini_api_key.strip()),
                         'groq':ai_stat['groq_configured'],
                         'openai_compat':ai_stat['openai_compat_configured'],
                         'ollama':bool(ai_stat['ollama_configured'] or ai_stat['ollama_detected_model']),
                         'google_oauth':bool(settings.google_client_id and settings.google_client_secret),
                         'google_tts':bool(settings.google_tts_api_key or settings.google_application_credentials),'elevenlabs':bool(settings.elevenlabs_api_key)},
            'uploads_enabled':settings.youtube_uploads_enabled,
            'thumbnail_note':'The vertical cover is saved locally. Shorts custom cover availability varies by account and surface. No thumbnail API success is assumed; apply the cover in YouTube Studio where available.',
            'thumbnail_help':'https://support.google.com/youtube/answer/72431?hl=en'}


@router.put('/api/settings/ai-providers')
def update_ai_providers(payload: dict, context=Depends(require_owner), db: Session = Depends(get_db)):
    from app.core.config import save_runtime_ai_overrides
    from app.ai.smart_router import clear_cooldowns, get_ai_status
    allowed_non_secret = (
        'gemini_model', 'gemini_fallback_model', 'gemini_fallback_models',
        'groq_model', 'openai_compat_base_url', 'openai_compat_model',
        'ollama_base_url', 'ollama_model', 'ai_auto_detect_ollama', 'title_short_ai_model',
    )
    allowed_secrets = ('gemini_api_key', 'gemini_api_keys', 'groq_api_key', 'openai_compat_api_key')
    updates = {}
    for k in allowed_non_secret:
        if k in payload and payload[k] is not None:
            updates[k] = payload[k] if isinstance(payload[k], bool) else str(payload[k]).strip()
    for k in allowed_secrets:
        val = str(payload.get(k, '') or '').strip()
        if val:
            updates[k] = val
    # Allow explicit clearing if requested
    for k in payload.get('clear_fields', []) or []:
        if k in (*allowed_secrets, 'title_short_ai_model', 'ollama_model', 'openai_compat_base_url', 'openai_compat_model'):
            updates[k] = ''
    save_runtime_ai_overrides(updates)
    clear_cooldowns()
    from app.api.members import audit
    audit(db, context[1], context[1], 'ai_providers_updated', {'fields': sorted(updates.keys())})
    db.commit()
    return {'ok': True, 'ai_status': get_ai_status()}


@router.post('/api/settings/ai-test')
def run_ai_provider_test(context=Depends(require_owner)):
    from app.ai.smart_router import clear_cooldowns, test_ai_providers
    clear_cooldowns()
    return test_ai_providers()


@router.put('/api/settings')
def save_settings(payload:SettingsInput,context=Depends(require_admin),db:Session=Depends(get_db)):
    if payload.background_music_id:
        music=db.get(MusicTrack,payload.background_music_id)
        if not music or music.workspace_id!=context[1].workspace_id:
            raise HTTPException(400,'Music track not found in workspace')
    record=db.get(WorkspaceSettings,context[1].workspace_id)
    if not record:
        record=WorkspaceSettings(workspace_id=context[1].workspace_id)
        db.add(record)
    record.data=json.dumps({**json.loads(record.data or '{}'),**payload.model_dump()})
    from app.api.members import audit
    audit(db,context[1],context[1],'settings_updated',{'fields':sorted(payload.model_fields_set)})
    db.commit()
    return {'preferences':preferences(db,context[1].workspace_id)}


@router.get('/api/notifications')
def notifications(context=Depends(current_context),db:Session=Depends(get_db)):
    member=context[1]
    query=db.query(Notification).filter_by(workspace_id=member.workspace_id)
    visible=_accessible_channel_ids(db,member)
    if visible is not None:
        query=query.filter(Notification.channel_id.in_(visible))
    return [{'id':r.id,'title':r.title,'message':r.message,'read':member.id in json.loads(r.read_by),
             'created_at':r.created_at.isoformat()+'Z'} for r in query.order_by(Notification.created_at.desc()).limit(40)]


@router.post('/api/notifications/{notification_id}/read')
def mark_read(notification_id:str,context=Depends(current_context),db:Session=Depends(get_db)):
    row=db.get(Notification,notification_id)
    visible=_accessible_channel_ids(db,context[1])
    if not row or row.workspace_id!=context[1].workspace_id or (visible is not None and row.channel_id not in visible):
        raise HTTPException(404,'Notification not found')
    row.read_by=json.dumps(list(set(json.loads(row.read_by)+[context[1].id])))
    db.commit()
    return {'read':True}


@router.get('/api/music')
def music(context=Depends(current_context),db:Session=Depends(get_db)):
    return [{'id':r.id,'name':r.name,'source':r.source,'license':r.license,'attribution':r.attribution}
            for r in db.query(MusicTrack).filter_by(workspace_id=context[1].workspace_id)]


@router.post('/api/music')
def add_music(file:UploadFile=File(...),source:str=Form(...),license:str=Form(...),attribution:str=Form(...),
              context=Depends(require_admin),db:Session=Depends(get_db)):
    from app.video.renderer import validate_music
    suffix=Path(file.filename or '').suffix.lower()
    if suffix not in {'.mp3','.wav','.m4a','.ogg'} or not license.strip() or len(license)>500 or len(attribution)>500 or len(source)>1000:
        raise HTTPException(422,'Supported audio file, source and usage license are required')
    key=new_id()
    root=Path(settings.generated_dir).resolve()/'music'
    root.mkdir(parents=True,exist_ok=True)
    target=root/(key+suffix)
    try:
        total=0
        with target.open('wb') as stream:
            while data:=file.file.read(1024*1024):
                total+=len(data)
                if total>30*1024*1024:
                    raise ValueError('Music exceeds 30 MB')
                stream.write(data)
        if not 1<=validate_music(target)<=1800:
            raise ValueError('Audio duration must be 1–1800 seconds')
    except Exception:
        target.unlink(missing_ok=True)
        raise HTTPException(422,'Audio is invalid, oversized, or unsupported by FFmpeg') from None
    row=MusicTrack(id=key,workspace_id=context[1].workspace_id,name=Path(file.filename).name[:120],
                   local_path=str(target),source=source,license=license,attribution=attribution)
    db.add(row)
    db.commit()
    return {'id':key,'name':row.name}
