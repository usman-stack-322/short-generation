import shutil
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError, OperationalError

from app.core.config import settings
from app.core.security import current_context, new_id, require_admin, require_editor, require_owner
from app.database.session import get_db
from app.models import Asset, Channel, Personality, SEOData, Script, Topic, Video, VideoJob, VoiceGeneration, Thumbnail
from app.schemas import GenerateVideoInput, RegenerateInput, ScriptInput, RejectInput
from app.services.pipeline import serialize_job, run_job, ACTIVE_STATUSES


from app.youtube.permissions import approve, job_access, can_approve
from app.services.preferences import invalidate_approvals
from app.api.access import _accessible_channel_ids,personality_visible
from app.core.languages import language_info
router = APIRouter()
generated_dir = Path(settings.generated_dir).resolve()

@router.post("/api/videos/generate", status_code=status.HTTP_201_CREATED)
def generate_video(payload: GenerateVideoInput, background: BackgroundTasks, context=Depends(require_editor), db: Session = Depends(get_db)):
    _, membership = context
    channel = db.get(Channel, payload.channel_id)
    personality = db.get(Personality, payload.personality_id)
    visible_ids = _accessible_channel_ids(db, membership)
    if not channel or channel.workspace_id != membership.workspace_id or (visible_ids is not None and channel.id not in visible_ids):
        raise HTTPException(status_code=404, detail="Channel not found or not assigned to your account.")
    if not personality_visible(personality,membership,visible_ids) or not personality.enabled:
        raise HTTPException(status_code=404, detail="Enabled personality not found in this workspace.")
    if personality.channel_id and personality.channel_id != channel.id:
        raise HTTPException(status_code=400, detail="This personality is assigned to a different channel.")
    if payload.topic_mode == "manual" and not (payload.manual_topic or "").strip():
        raise HTTPException(status_code=422, detail="Enter a topic when using manual topic mode.")
    if not payload.collection_id and payload.content_mode=='hybrid':
        # Daily preparation and ordinary Hybrid requests use channel-assigned
        # collections too; local fallback must not depend on a browser picker.
        from app.models import MediaCollection,LibraryMedia
        from app.services.media_library import collection_access
        choices=db.query(MediaCollection).join(LibraryMedia).filter(
            MediaCollection.workspace_id==membership.workspace_id,MediaCollection.channel_id==channel.id,
            LibraryMedia.personality_id==personality.id,LibraryMedia.approved.is_(True),LibraryMedia.archived.is_(False),
            LibraryMedia.media_type.in_(['photo','clip'])).order_by(MediaCollection.created_at).all()
        for choice in choices:
            try:collection_access(db,choice.id,membership)
            except HTTPException:continue
            payload.collection_id=choice.id
            break
    if payload.collection_id:
        from app.services.media_library import collection_access
        collection=collection_access(db,payload.collection_id,membership)
        if collection.channel_id!=channel.id:raise HTTPException(422,'Assign this collection to the selected channel first')
    if payload.content_mode=='my_assets' and not payload.collection_id:
        raise HTTPException(422,'Choose a collection for My Assets mode')
    from app.services.generation_requests import identity,existing
    from app.models import GenerationRequest
    operation_key,fingerprint=identity(payload,channel,personality,db)
    is_auto = bool(payload.operation_id and payload.operation_id.startswith('auto:'))
    previous=existing(db,membership.workspace_id,operation_key,fingerprint,strict=not is_auto)
    if previous:return serialize_job(previous,db)
    language=language_info(payload.language or channel.default_language or 'en-US')
    narrator=payload.voice or channel.default_voice
    if not payload.voice and narrator.split('-')[0] != language.code.split('-')[0]:
        narrator=language.code
    job = VideoJob(
        content_mode=payload.content_mode,collection_id=payload.collection_id,avoid_recent_media=payload.avoid_recent_media,
        id=new_id(), workspace_id=membership.workspace_id, channel_id=channel.id,
        personality_id=personality.id, topic_title=(payload.manual_topic or "").strip() if payload.topic_mode == "manual" else "",
        topic_mode=payload.topic_mode, manual_topic=payload.manual_topic, duration=payload.duration if 'duration' in payload.model_fields_set else channel.generation_duration,
        voice=narrator, language=language.code, language_code=language.code, language_name=language.name, locale=language.locale,
        video_style=payload.video_style if 'video_style' in payload.model_fields_set else __import__('json').loads(channel.operational_defaults or '{}').get('template',payload.video_style), status="researching", current_step="researching",
        voice_style=payload.voice_style or (personality.default_voice_style if personality.default_voice_style!='auto' else channel.voice_style), tts_provider=payload.tts_provider or channel.tts_provider,
    )
    import json
    settings_dict = {
        'automatic_evergreen_fallback':channel.automatic_evergreen_fallback,'niche':channel.niche or personality.category,
        'evergreen_source_urls':channel.evergreen_source_urls,
        'language':job.language_code,'voice':job.voice,'voice_style':job.voice_style,
        'duration':job.duration,'tts_provider':job.tts_provider or channel.tts_provider,'video_style':job.video_style
    }
    trace_dict = {'generation_settings': settings_dict}
    if is_auto:
        trace_dict['generation_origin'] = 'daily_preparation'
        trace_dict['daily_operation'] = payload.operation_id
    job.research_trace=json.dumps(trace_dict)
    if payload.candidate_id:
        from app.models import ResearchCandidate
        from app.research.live import topic_from_candidate, similar
        candidate = db.get(ResearchCandidate,payload.candidate_id)
        from app.research.selection import configured_provider,demo_topic
        allowed_status='demo' if configured_provider(db,membership.workspace_id)=='demo' else 'verified'
        if not candidate or candidate.personality_id != personality.id or candidate.channel_id != channel.id or candidate.status != allowed_status:
            raise HTTPException(409,'Select a candidate from the active research provider for this channel/personality')
        if any(similar(candidate.title,t.title) for t in db.query(Topic).filter_by(channel_id=channel.id,personality_id=personality.id)):
            raise HTTPException(409,'This story was already generated for this channel/personality')
        try:
            topic = demo_topic(db,candidate) if allowed_status=='demo' else topic_from_candidate(db,candidate)
        except ValueError as exc:
            raise HTTPException(409,str(exc)) from None
        claimed=db.query(ResearchCandidate).filter_by(id=candidate.id,status=allowed_status).update({'status':'selected'})
        if claimed!=1:
            db.rollback()
            raise HTTPException(409,'This candidate was already selected by another request')
        job.topic_id,job.topic_title=topic.id,topic.title
        import json
        job.research_trace=json.dumps({**json.loads(job.research_trace),'provider':'demo' if allowed_status=='demo' else 'rss','candidate_ids':[candidate.id],'selected_candidate_id':candidate.id})
    if payload.music_id:
        from app.models import MusicTrack
        music=db.get(MusicTrack,payload.music_id)
        if not music or music.workspace_id != membership.workspace_id:
            raise HTTPException(400,'Workspace music track not found')
        job.music_id=music.id
    db.add(job)
    try:
        db.flush()
        db.add(GenerationRequest(workspace_id=membership.workspace_id,operation_key=operation_key,fingerprint=fingerprint,job_id=job.id))
        db.commit()
    except (IntegrityError, OperationalError):
        db.rollback()
        for attempt in range(5):
            previous=existing(db,membership.workspace_id,operation_key,fingerprint,strict=not is_auto)
            if previous:return serialize_job(previous,db)
            import time
            time.sleep(0.05)
        raise
    background.add_task(run_job, job.id, "all")
    return serialize_job(job, db)


@router.get("/api/videos")
def list_videos(context=Depends(current_context), db: Session = Depends(get_db)):
    _, membership = context
    query = db.query(VideoJob).filter_by(workspace_id=membership.workspace_id)
    visible_ids = _accessible_channel_ids(db, membership)
    if visible_ids is not None:
        query = query.filter(VideoJob.channel_id.in_(visible_ids))
    jobs = query.order_by(VideoJob.created_at.desc()).all()
    return [serialize_job(job, db) for job in jobs]


@router.get("/api/videos/{job_id}")
def get_video(job_id: str, context=Depends(current_context), db: Session = Depends(get_db)):
    _, membership = context
    job = db.get(VideoJob, job_id)
    visible_ids = _accessible_channel_ids(db, membership)
    if not job or job.workspace_id != membership.workspace_id or (visible_ids is not None and job.channel_id not in visible_ids):
        raise HTTPException(status_code=404, detail="Video job not found.")
    return serialize_job(job, db)


@router.patch('/api/videos/{job_id}/classification')
def classify_video(job_id: str, payload: dict, context=Depends(require_editor), db: Session = Depends(get_db)):
    """Explicit operator label only; never infer test data from names or delete it."""
    import json
    if set(payload) != {'is_test'} or type(payload['is_test']) is not bool:
        raise HTTPException(422, 'Provide is_test as a boolean.')
    job = job_access(db, job_id, context[1], True)
    trace = json.loads(job.research_trace or '{}')
    trace['operator_is_test'] = payload['is_test']
    job.research_trace = json.dumps(trace)
    db.commit()
    return serialize_job(job, db)


@router.post("/api/videos/{job_id}/approve")
def approve_video(job_id: str, payload: dict | None = None, context=Depends(require_admin), db: Session = Depends(get_db)):
    job=job_access(db,job_id,context[1],True)
    approve(db,job,context[1],(payload or {}).get('content_revision'))
    return serialize_job(job,db)


@router.post("/api/videos/{job_id}/reject")
def reject_video(job_id: str, payload: RejectInput = RejectInput(), context=Depends(require_admin), db: Session = Depends(get_db)):
    job=job_access(db,job_id,context[1],True)
    if not can_approve(db.get(Channel,job.channel_id),context[1]):
        raise HTTPException(403,'Channel policy does not allow your rejection')
    if job.status not in {'ready_for_review','approved','scheduled','verification_required'}:
        raise HTTPException(409,'This video cannot be rejected in its current state')
    invalidate_approvals(db,job)
    job.status=job.current_step='rejected'
    job.rejection_note=payload.note
    job.error_message='Rejected: '+(payload.note or 'No note provided')
    if job.video: job.video.status='rejected'
    db.commit()
    return serialize_job(job,db)


@router.post("/api/videos/{job_id}/regenerate")
def regenerate_video(job_id: str, background: BackgroundTasks, payload: RegenerateInput = RegenerateInput(), context=Depends(require_editor), db: Session = Depends(get_db)):
    _, membership = context
    job = db.get(VideoJob, job_id)
    visible_ids = _accessible_channel_ids(db, membership)
    if not job or job.workspace_id != membership.workspace_id or (visible_ids is not None and job.channel_id not in visible_ids):
        raise HTTPException(status_code=404, detail="Video job not found.")
    if job.status in ACTIVE_STATUSES or job.status in {"uploading","uploaded","scheduled"}:
        raise HTTPException(status_code=409, detail="Cancel a schedule first; uploaded/running jobs cannot be regenerated.")
    if job.status=='verification_required' and payload.scope not in {'all','retry'}:
        raise HTTPException(409,'Source verification must pass before regenerating content')
    if job.status=='verification_required' or (payload.scope=='retry' and job.failed_step=='researching'):
        return retry_research(job_id,background,context,db)
    if job.status=='research_ready' or job.topic and job.topic.verification_status=='limited_verification':
        import json
        from app.research.verification import verify_story
        from app.research.live import candidate_age_hours
        evidence=json.loads(job.topic.evidence or '[]') if job.topic else []
        from app.research.selection import configured_provider
        development=job.topic and job.topic.verification_status=='demo' and configured_provider(db,job.workspace_id)=='demo'
        limited=job.topic and job.topic.verification_status=='limited_verification'
        if limited:
            from app.research.drafts import draft_decision
            if not settings.review_drafts_enabled or not evidence or not draft_decision(evidence[0],db.get(Personality,job.personality_id),fetch=True)['eligible']:
                raise HTTPException(409,'Review draft evidence no longer qualifies. Retry research.')
        historical=bool(evidence and evidence[0].get('content_type')=='historical')
        if not limited and not development and (not evidence or not verify_story(evidence[0],evidence,max_age_hours=candidate_age_hours(evidence[0]),historical=historical)['passed']):
            from app.services.job_research import NO_STORY
            job.status=job.current_step='verification_required';job.error_message=NO_STORY
            db.commit()
            raise HTTPException(409,'Selected evidence expired or no longer verifies. Retry research before generation.')
    if payload.scope=='retry' and (job.status=='verification_required' or job.failed_step=='researching'):
        payload.scope='all'
    if payload.scope=='retry':
        payload.scope={'script_generation':'script','collecting_assets':'assets','voice_generation':'voice',
                       'seo_generation':'seo','rendering':'video','creating_cover':'cover'}.get(job.failed_step,'all')
        if not job.script:payload.scope='all'
    if not job.script and payload.scope != "all" and payload.language is None:
        raise HTTPException(status_code=409, detail="Generate a script first using full regeneration.")
    if job.status=='verification_required' and payload.scope not in {'all','retry'}:
        raise HTTPException(409,'Source verification must pass before regenerating content')
    if job.status=='verification_required':
        payload.scope='all'
    if payload.scope in {'cover','seo'} and job.video and job.video.media_revision!=job.media_revision:
        raise HTTPException(409,'Narration/video is outdated. Regenerate voice or video before cover/SEO-only work.')
    invalidate_approvals(db,job)
    if payload.scope not in {'cover','seo'}:
        job.media_revision+=1
        if job.video:job.video.status='outdated'
    job.error_message = None
    if payload.language is not None and payload.language != job.language_code:
        language=language_info(payload.language)
        job.language=job.language_code=language.code
        job.language_name,job.locale=language.name,language.locale
        job.voice=language.code
        # Remove all language-dependent DB artifacts before acknowledging the change.
        # Historical files remain on disk, but are no longer served as this job's output.
        for attribute in ('script','voice_generation','video'):
            record=getattr(job,attribute)
            if record: db.delete(record)
            setattr(job,attribute,None)
        from app.models import Scene
        for model in (Asset,Thumbnail,Scene):
            db.query(model).filter_by(job_id=job.id).delete(synchronize_session=False)
        payload.scope='script'
        job.warnings='[]'
    if payload.voice_style is not None:
        if payload.scope not in {'voice','script','all'}:
            raise HTTPException(422,'A voice style change requires voice regeneration')
        job.voice_style = payload.voice_style
    job.status = "researching"
    job.current_step = "researching"
    job.retry_count += 1
    db.commit()
    background.add_task(run_job, job.id, payload.scope)
    return serialize_job(job, db)


@router.post('/api/videos/{job_id}/research')
def retry_research(job_id: str, background: BackgroundTasks, context=Depends(require_editor), db: Session=Depends(get_db)):
    job=job_access(db,job_id,context[1],True)
    if job.status=='research_ready' or (job.status=='researching' and job.current_step=='research_only'):
        return serialize_job(job,db)
    if job.script or job.video or not (job.status=='verification_required' or job.status=='failed' and job.failed_step=='researching'):
        raise HTTPException(409,'Research retry requires a held or failed research job without generated content.')
    from app.services.job_research import run_research_job
    import json
    channel=db.get(Channel,job.channel_id)
    trace=json.loads(job.research_trace or '{}')
    snapshot=trace.get('generation_settings',{})
    snapshot.update(automatic_evergreen_fallback=channel.automatic_evergreen_fallback,
                    evergreen_source_urls=channel.evergreen_source_urls,
                    niche=channel.niche or db.get(Personality,job.personality_id).category)
    trace['generation_settings']=snapshot
    trace['selected_candidate_id']=None;trace['content_type']=None;trace['fallback_reason']=None
    job.research_trace=json.dumps(trace)
    job.topic=None;job.topic_title='';job.error_message=None
    job.status='researching';job.current_step='research_only';job.retry_count+=1
    db.commit()
    background.add_task(run_research_job,job.id)
    return serialize_job(job,db)


@router.post('/api/videos/{job_id}/review-draft/{candidate_id}')
def generate_review_draft(job_id:str,candidate_id:str,background:BackgroundTasks,context=Depends(require_editor),db:Session=Depends(get_db)):
    import json
    from datetime import datetime
    from app.models import ResearchCandidate
    from app.research.drafts import draft_decision,LABEL
    if not settings.review_drafts_enabled:raise HTTPException(409,'Review Draft mode is disabled by the server configuration.')
    job=job_access(db,job_id,context[1],True)
    if job.status!='verification_required' or job.script or job.video:
        raise HTTPException(409,'Only a held research job without generated content can start a review draft.')
    record=db.get(ResearchCandidate,candidate_id)
    trace=json.loads(job.research_trace or '{}')
    if not record or candidate_id not in trace.get('candidate_ids',[]) or record.channel_id!=job.channel_id or record.personality_id!=job.personality_id:
        raise HTTPException(404,'Research candidate not found for this job')
    if record.status!='verification_required':raise HTTPException(409,'Rejected or fully verified candidates cannot use this path.')
    data=json.loads(record.data)
    history=[t.title for t in db.query(Topic).filter_by(channel_id=job.channel_id,personality_id=job.personality_id)]
    decision=draft_decision(data,db.get(Personality,job.personality_id),history,fetch=True)
    if not decision['eligible']:raise HTTPException(409,decision['reason'])
    # Save only source-supported material, separately from verified topics.
    grounded={**data,'evidence':decision['sources'],'draft_review':decision,'verification':decision['verification']}
    topic=Topic(id=new_id(),personality_id=job.personality_id,channel_id=job.channel_id,title=record.title,
                source_name=data['source_name'],source_url=data['source_url'],summary=data['summary'],
                published_at=datetime.fromisoformat(data['published_at']),verification_status='limited_verification',
                evidence=json.dumps([grounded]),**{key:data[key] for key in ('freshness_score','relevance_score','reliability_score','viral_potential_score','overall_score')})
    db.add(topic);job.topic=topic;job.topic_title=topic.title
    trace['selected_candidate_id']=record.id;trace['mode']='review_draft';job.research_trace=json.dumps(trace)
    invalidate_approvals(db,job)
    job.status=job.current_step='researching';job.error_message=None;job.failed_step=None
    job.warnings=json.dumps([LABEL]);job.retry_count+=1
    db.commit()
    background.add_task(run_job,job.id,'all')
    return serialize_job(job,db)


@router.post('/api/videos/{job_id}/evergreen')
def offer_evergreen(job_id:str,context=Depends(require_editor),db:Session=Depends(get_db)):
    from app.research.drafts import evergreen_offer
    job=job_access(db,job_id,context[1],True)
    if job.status!='verification_required':raise HTTPException(409,'Evergreen suggestions are available for held research.')
    try:return evergreen_offer(db.get(Personality,job.personality_id))
    except Exception:
        raise HTTPException(422,'Evergreen biography source unavailable. Retry later or choose another personality; no current event or script was invented.') from None


@router.get('/api/videos/{job_id}/logs')
def job_logs(job_id:str,context=Depends(current_context),db:Session=Depends(get_db)):
    job=job_access(db,job_id,context[1])
    from app.ai.reliability import safe_detail
    folder=Path(settings.generated_dir)/'videos'/job.id
    path=folder/f'revision-{job.content_revision}'/'render.log'
    if not path.is_file() and job.video:path=Path(job.video.output_path).parent/'render.log'
    if not path.is_file():path=folder/'render.log'
    return {'step':job.current_step,'failed_step':job.failed_step,'retry_count':job.retry_count,
            'error':job.error_message,'render_log':safe_detail(path.read_text(encoding='utf-8')[-6000:]) if path.is_file() else None}


@router.patch("/api/videos/{job_id}/script")
def edit_script(job_id: str, payload: ScriptInput, context=Depends(require_editor), db: Session = Depends(get_db)):
    _, membership = context
    job = db.get(VideoJob, job_id)
    visible = _accessible_channel_ids(db, membership)
    if not job or job.workspace_id != membership.workspace_id or (visible is not None and job.channel_id not in visible):
        raise HTTPException(status_code=404, detail="Video job not found")
    if job.status in ACTIVE_STATUSES or not job.script:
        raise HTTPException(status_code=409, detail="A completed script is required")
    if job.status in {"scheduled","uploading","uploaded"}:
        raise HTTPException(409,"Cancel schedule first; uploaded videos cannot be edited.")
    invalidate_approvals(db,job)
    job.media_revision+=1
    for key, value in payload.model_dump().items():
        setattr(job.script, key, value.strip())
    job.script.full_script = " ".join(payload.model_dump().values())
    job.status = "failed"
    job.current_step = "script_edited"
    job.error_message = "Script edited. Regenerate voice and video before approval."
    if job.video:
        job.video.status = "outdated"
    db.commit()
    return serialize_job(job, db)


@router.delete("/api/videos/{job_id}")
def delete_video(job_id: str, context=Depends(require_admin), db: Session = Depends(get_db)):
    _, membership = context
    job = db.get(VideoJob, job_id)
    if not job or job.workspace_id != membership.workspace_id:
        raise HTTPException(status_code=404, detail="Video job not found.")
    job_access(db,job_id,membership,True)
    if job.status in ACTIVE_STATUSES or job.status in {"scheduled","uploading","uploaded"}:
        raise HTTPException(status_code=409, detail="Cannot delete running, scheduled or uploaded records.")
    output_root = generated_dir.resolve()
    target_dirs = [(output_root / "videos" / job.id).resolve(), (output_root / "images" / job.id).resolve()]
    for target in target_dirs:
        if output_root not in target.parents:
            raise HTTPException(status_code=400, detail="Invalid generated media path.")
    topic_id = job.topic_id
    db.query(Thumbnail).filter_by(job_id=job.id).delete(synchronize_session=False)
    db.query(Asset).filter_by(job_id=job.id).delete(synchronize_session=False)
    db.delete(job)
    db.flush()
    if topic_id:
        db.query(Topic).filter_by(id=topic_id).delete(synchronize_session=False)
    db.commit()
    for target in target_dirs:
        if target.exists():
            shutil.rmtree(target)
    for relative_path in (Path("audio") / f"{job_id}.wav", Path("thumbnails") / f"{job_id}.png", Path("thumbnails") / f"{job_id}.checks.json", Path("subtitles") / f"{job_id}.srt"):
        media_path = (output_root / relative_path).resolve()
        if output_root in media_path.parents and media_path.exists():
            media_path.unlink()
    return {"deleted": True}


