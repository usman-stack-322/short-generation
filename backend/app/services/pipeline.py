"""Local, sequential job execution. Each committed stage is visible to polling clients."""
import json
import logging
import threading
import hashlib
from datetime import datetime,timezone
from pathlib import Path
from sqlalchemy.orm import Session
from app.core.config import settings
from app.core.security import new_id
from app.database.session import SessionLocal
from app.models import Asset, Channel, Personality, SEOData, Script, Video, VideoJob, VoiceGeneration, Thumbnail, Scene, UploadTask, MusicTrack, Approval
from app.ai.scripts import generate_script, generate_seo
from app.research.engine import research_topic
from app.tts.providers import generate_narration
from app.tts.director import direct_voice
from app.tts.delivery import provider_controls, prepare_delivery
from app.services.assets.providers import DemoAssetProvider, validate_local_image
from app.video.renderer import render_video, cover_image
from app.api.media import media_link
from app.services.preferences import preferences, notify
from app.services.scene_planner import save_scenes
from app.services.assets.licensed import collect_scene_assets
from app.video.cover import create_cover
from app.research.live import research_live, topic_from_candidate

logger=logging.getLogger(__name__)
worker_lock=threading.Lock()
ACTIVE_STATUSES={'researching','script_generation','collecting_assets','voice_generation','rendering','creating_cover'}
JOB_STATUSES=ACTIVE_STATUSES | {'research_ready','ready_for_review','approved','scheduled','uploading','uploaded','upload_failed','rejected','verification_required','failed'}
ALLOWED_TRANSITIONS={
    'researching': {'script_generation','failed'},
    'script_generation': {'collecting_assets','failed'},
    'collecting_assets': {'voice_generation','failed'},
    'voice_generation': {'rendering','failed'},
    'rendering': {'ready_for_review','failed'},
    'ready_for_review': {'approved','failed','researching'},
    'approved': {'scheduled','failed','researching'},
    'scheduled': {'uploaded','failed'}, 'uploaded': set(), 'failed': {'researching'},
}
# Reused checkpoints may skip earlier stages. Publishing never uses this transition helper.
for state in ACTIVE_STATUSES:
    ALLOWED_TRANSITIONS[state] = (ACTIVE_STATUSES - {'researching'}) | {'ready_for_review','verification_required','failed'}
ALLOWED_TRANSITIONS.update({'rejected':{'researching'},'verification_required':{'researching','rejected'},
                            'upload_failed':{'researching'}})


def _set_step(db,job,step):
    if step not in JOB_STATUSES:
        raise ValueError(f'Unsupported video job status: {step}')
    if step != job.status and step not in ALLOWED_TRANSITIONS.get(job.status,set()):
        raise ValueError(f'Invalid video job transition: {job.status} -> {step}')
    job.status=job.current_step=step
    db.commit()

def serialize_asset(asset):
    metadata=json.loads(asset.provenance or '{}')
    root=Path(settings.generated_dir).resolve()
    path=Path(asset.local_path).resolve()
    expected=root/'images'/asset.job_id
    preview=media_link(path.relative_to(root).as_posix()) if expected in path.parents and path.is_file() else None
    return {'id':asset.id,'scene_number':asset.scene_number,'source':asset.source,'url':asset.url,
        'creator':asset.creator,'license':asset.license,'attribution':metadata.get('required_credit',asset.attribution),
        'preview_url':preview,'kind':metadata.get('kind','legacy'),'label':metadata.get('label'),
        'license_url':metadata.get('license_url'),'modifications':metadata.get('modifications'),
        'media_type':'missing' if metadata.get('kind')=='missing' else 'clip' if path.suffix.lower()=='.mp4' else 'card' if metadata.get('kind')=='text_card' or asset.source in {'demo','Local text card','Original local illustration'} else 'photo',
        'focal_x':metadata.get('focal_x',.5),'focal_y':metadata.get('focal_y',.5),
        'note':metadata.get('reason') or metadata.get('authenticity_note')}


def serialize_job(job,db):
    channel=db.get(Channel,job.channel_id)
    personality=db.get(Personality,job.personality_id)
    script=job.script
    narration_path=None
    if job.voice_generation and script and job.status not in ACTIVE_STATUSES and job.voice_generation.script_hash==hashlib.sha256(script.full_script.encode()).hexdigest():
        narration_path=Path(job.voice_generation.output_path)
        if job.video and job.video.media_revision==job.media_revision:
            finished=Path(job.video.output_path).parent/'narration.wav'
            if finished.is_file():narration_path=finished
    seo=script.seo if script else None
    task=db.query(UploadTask).filter_by(job_id=job.id).first()
    scenes=db.query(Scene).filter_by(job_id=job.id).order_by(Scene.scene_number).all()
    assets=db.query(Asset).filter_by(job_id=job.id).all()
    pending=[]
    verification=None
    trace=json.loads(job.research_trace or '{}')
    if not job.topic and (job.status=='verification_required' or job.failed_step=='researching'):
        from app.models import ResearchCandidate
        query=db.query(ResearchCandidate).filter(
            ResearchCandidate.channel_id==job.channel_id,ResearchCandidate.personality_id==job.personality_id,
        )
        if trace.get('candidate_ids') is not None:
            query=query.filter(ResearchCandidate.id.in_(trace['candidate_ids']))
        else:
            query=query.filter(ResearchCandidate.created_at>=job.created_at,ResearchCandidate.created_at<=job.updated_at)
        records=query.order_by(ResearchCandidate.created_at.desc()).all()
        pending=[{**json.loads(record.data),'id':record.id,'status':record.status,'rejection_reason':record.rejection_reason} for record in records]
    if job.topic:
        evidence=json.loads(job.topic.evidence or '[]')
        verification=next((row.get('verification') for row in evidence if row.get('verification')),None)
    elif pending:
        verification=pending[0].get('verification')
        if verification is None:
            from app.research.verification import verify_story
            verification=verify_story(pending[0],pending[0].get('evidence') or pending)
    return {
        'content_mode':job.content_mode,'collection_id':job.collection_id,
        'channel_defaults':json.loads(channel.operational_defaults or '{}') if channel else {},
        'content_type':trace.get('content_type') or ('historical' if job.topic and any(row.get('content_type')=='historical' for row in json.loads(job.topic.evidence or '[]')) else 'news' if job.topic else 'unselected'),
        'fallback_reason':trace.get('fallback_reason'),
        'review_drafts_enabled':settings.review_drafts_enabled,
        'draft_options':draft_options(pending,personality) if settings.review_drafts_enabled else [],
        'draft_review':next((row.get('draft_review') for row in json.loads(job.topic.evidence or '[]') if row.get('draft_review')),None) if job.topic else None,
        'research_trace':trace,
        'script_state': 'saved' if script else 'awaiting_generation' if job.status=='research_ready' else 'held' if job.status=='verification_required' else 'failed' if job.failed_step=='script_generation' and job.status=='failed' else 'running' if job.status=='script_generation' else 'queued' if job.topic and job.status in ACTIVE_STATUSES else 'not_started',
        'content_revision':job.content_revision,
        'verification':verification,
        'member_id':channel.member_id if channel else None,
        'member_name':channel.member.user.name if channel and channel.member else 'Workspace owner',
        'approval_policy':channel.approval_policy if channel else 'owner_only',
        'approval_count':db.query(Approval).filter_by(job_id=job.id,revision=job.content_revision).count(),
        'verification_status':job.topic.verification_status if job.topic else ('verification_required' if pending else None),
        'failed_step':job.failed_step,'rejection_note':job.rejection_note,
        'retryable':job.status=='verification_required' or job.status=='failed' and bool(job.error_message) and (
            job.error_message.startswith('Gemini is temporarily unavailable') or job.failed_step=='researching'
            or job.failed_step in {'script_generation','seo_generation'} or job.current_step=='interrupted' or 'invalid structured output' in job.error_message),
        'last_completed_step':{'script_generation':'researching','seo_generation':'script_generation','collecting_assets':'script_generation',
                               'voice_generation':'collecting_assets','rendering':'voice_generation',
                               'creating_cover':'rendering'}.get(job.failed_step) if job.status=='failed' else None,
        'script_provider':next((w.removeprefix('Script provider: ') for w in json.loads(job.warnings or '[]') if w.startswith('Script provider: ')),None),
        'upload':{'status':task.status,'progress':task.progress,'scheduled_at':task.scheduled_at.isoformat()+'Z' if task.scheduled_at else None,
                  'timezone':task.timezone,'youtube_video_id':task.youtube_video_id,'studio_url':('https://studio.youtube.com/video/'+task.youtube_video_id+'/edit') if task.youtube_video_id else None,'studio_fallback':('https://studio.youtube.com/channel/'+channel.youtube_channel_id+'/videos') if channel and channel.youtube_channel_id else None,'youtube_url':task.youtube_url,'error_message':task.error_message} if task else None,
        'scenes':[{k:getattr(scene,k) for k in ('scene_number','start_time','end_time','narration','visual_query','visual_type','caption','emphasis_word')} for scene in scenes],
        'assets':[serialize_asset(a) for a in assets],
        'visual_coverage': {
            'total_scenes': len(scenes),
            'media_scenes': sum(1 for a in assets if serialize_asset(a)['media_type'] in {'photo','clip'}),
            'card_scenes': len(scenes) - sum(1 for a in assets if serialize_asset(a)['media_type'] in {'photo','clip'}),
            'ratio': round(sum(1 for a in assets if serialize_asset(a)['media_type'] in {'photo','clip'}) / len(scenes), 2) if scenes else 0.0,
            'label': f"{sum(1 for a in assets if serialize_asset(a)['media_type'] in {'photo','clip'})} of {len(scenes)} scenes have photo/video media" if len(scenes) != 1 else f"{sum(1 for a in assets if serialize_asset(a)['media_type'] in {'photo','clip'})} of 1 scene has photo/video media",
            'is_low_coverage': bool(scenes and (sum(1 for a in assets if serialize_asset(a)['media_type'] in {'photo','clip'}) / len(scenes)) < 0.5),
            'warning': f"Low visual coverage: Only {sum(1 for a in assets if serialize_asset(a)['media_type'] in {'photo','clip'})} of {len(scenes)} scenes have photo/video media." if bool(scenes and (sum(1 for a in assets if serialize_asset(a)['media_type'] in {'photo','clip'}) / len(scenes)) < 0.5) else None,
            'options': [
                {'action': 'add_media', 'label': 'Add photo or clip from Media Library'},
                {'action': 'retry_retrieval', 'label': 'Retry automated media retrieval'},
                {'action': 'replace_media', 'label': 'Upload or replace genuine scene media'}
            ]
        },
        'evidence':json.loads(job.topic.evidence or '[]') if job.topic else pending,
        'id':job.id,'channel_id':job.channel_id,'youtube_channel_id':channel.youtube_channel_id if channel else None,'channel_name':channel.name if channel else 'Unknown',
        'personality_id':job.personality_id,'personality_name':personality.name if personality else 'Unknown',
        'topic':job.topic_title or (job.topic.title if job.topic else pending[0]['title'] if pending else ''),'duration':job.duration,'output_duration':job.video.duration if job.video else None,'voice':job.voice,'language':job.language_code,
        'language_code':job.language_code,'language_name':job.language_name,'locale':job.locale,
        'video_style':job.video_style,'status':job.status,'current_step':job.current_step,
        'error_message':job.error_message,'retry_count':job.retry_count,'warnings':json.loads(job.warnings or '[]'),
        'voice_provider':job.voice_generation.provider if job.voice_generation else None,
        'voice_style':job.voice_style,
        'voice_direction':json.loads(job.voice_generation.voice_profile) if job.voice_generation and job.voice_generation.voice_profile else None,
        'narrator_voice':job.voice_generation.voice if job.voice_generation else job.voice,
        'voice_delivery':json.loads(job.voice_generation.delivery) if job.voice_generation and job.voice_generation.delivery else None,
        'created_at':job.created_at.isoformat()+'Z' if job.created_at else None,
        'video_url':media_link(Path(job.video.output_path).resolve().relative_to(Path(settings.generated_dir).resolve()).as_posix()) + f'&revision={job.media_revision}&v={job.content_revision}' if job.video and job.video.media_revision==job.media_revision and job.video.status!='outdated' else None,
        'narration_url':media_link(narration_path.resolve().relative_to(Path(settings.generated_dir).resolve()).as_posix())+f'&revision={job.media_revision}' if narration_path and narration_path.is_file() else None,
        'thumbnail_url':media_link(f'thumbnails/{job.id}.png') + f'&v={job.updated_at.timestamp()}' if job.video else None,
        'script':{key:getattr(script,key) for key in ('hook','context','main_story','why_it_matters','ending','full_script')} if script else None,
        'seo':{'title':seo.title,'description':seo.description,'hashtags':json.loads(seo.hashtags),
               'keywords':json.loads(seo.keywords),'cover_text':seo.cover_text} if seo else None,
        'sources':[{'name':job.topic.source_name,'url':job.topic.source_url,
                    'event_date':next((row.get('event_date') for row in json.loads(job.topic.evidence or '[]') if row.get('event_date')),None),
                    'event_date_precision':next((row.get('event_date_precision') for row in json.loads(job.topic.evidence or '[]') if row.get('event_date')),None),
                    'published_at':job.topic.published_at.isoformat() if job.topic.published_at else None,
                    'period_label': 'Historical / evergreen' if trace.get('content_type')=='historical' else 'From the past 14 days' if job.topic.published_at and (datetime.now(timezone.utc)-job.topic.published_at.replace(tzinfo=timezone.utc)).total_seconds()>settings.research_max_age_hours*3600 else None,
                    **{k:getattr(job.topic,k) for k in ('freshness_score','relevance_score','viral_potential_score','reliability_score','overall_score')}}] if job.topic else [
                        {'name':row['source_name'],'headline':row['title'],'verification_required':True,
                         'supporting_sources':[{'name':s.get('source_name'),'url':s.get('source_url'),'published_at':s.get('published_at')} for s in row.get('evidence',[])],
                         'period_label':row.get('period_label'),'candidate_id':row['id'],'status':row['status'],'reason':row.get('rejection_reason'),'verification':row.get('verification'),
                         'url':row['source_url'],'published_at':row.get('published_at'),
                         **{key:row.get(key) for key in ('freshness_score','relevance_score','viral_potential_score','reliability_score','overall_score')}} for row in pending],
    }

def draft_options(rows,personality):
    from app.research.drafts import draft_decision
    return [{'candidate_id':row['id'],**draft_decision(row,personality)} for row in rows if row['status']=='verification_required']


def update_seo(db,script,job,personality):
    evidence=json.loads(job.topic.evidence or '[]') if job.topic else []
    args=[job.topic_title,personality.name,{key:getattr(script,key) for key in ('hook','context','main_story','why_it_matters','ending','full_script')},job.language_code]
    if evidence and evidence[0].get('content_type')=='historical':args.append({'event_date':evidence[0]['event_date'],'event_date_precision':evidence[0].get('event_date_precision'),'content_type':'historical'})
    content=generate_seo(*args)
    seo=script.seo
    if not seo:
        seo=SEOData(id=new_id(),script_id=script.id)
        db.add(seo)
        script.seo=seo
    for key,value in content.items():
        setattr(seo,key,json.dumps(value) if isinstance(value,list) else value)
    db.flush()
    return content

def run_pipeline(db: Session,job,personality,channel,scope='all'):
    step='researching'
    try:
        if scope in {'cover','seo'} and job.video and job.video.media_revision!=job.media_revision:
            raise ValueError('Rendered media is outdated; partial metadata work cannot restore readiness.')
        if scope=='retry':
            scope={'researching':'all','script_generation':'script','collecting_assets':'assets',
                   'seo_generation':'seo','voice_generation':'voice','rendering':'video','creating_cover':'cover'}.get(job.failed_step,'all')
        warnings=json.loads(job.warnings or '[]') if scope!='all' else []
        prefs=preferences(db,job.workspace_id)
        root=Path(settings.generated_dir).resolve()
        if scope=='all' and job.topic and job.topic.verification_status not in {'verified','demo','limited_verification'}:
            job.topic=None
            job.topic_title=''
            db.commit()
        snapshot=json.loads(job.research_trace or '{}').get('generation_settings',{})
        fallback_enabled=snapshot.get('automatic_evergreen_fallback',channel.automatic_evergreen_fallback)
        if not job.topic and job.topic_mode=='current' and fallback_enabled:
            from app.research.selection import configured_provider
            if configured_provider(db,job.workspace_id)=='rss':
                from app.services.automatic_research import automatic_topic
                from app.research.evergreen import NO_FALLBACK
                topic=automatic_topic(db,job,personality,channel)
                if topic is None:
                    from app.research.evergreen import hold_reason
                    job.status=job.current_step='verification_required';job.error_message=hold_reason(json.loads(job.research_trace or '{}'))
                    notify(db,job.workspace_id,job.channel_id,'No verified topic found',job.error_message)
                    db.commit();return serialize_job(job,db)
                job.topic=topic;job.topic_title=topic.title;db.commit()
        if not job.topic:
            _set_step(db,job,step)
            from app.research.selection import configured_provider
            if configured_provider(db,job.workspace_id)=='rss':
                job.research_trace=json.dumps({'provider':'rss','candidate_ids':[],'selected_candidate_id':None})
                db.commit()
                if job.topic_mode=='manual':
                    job.status=job.current_step='verification_required'
                    job.error_message='Manual current-news claims need verified source evidence. Research and select a verified candidate.'
                    notify(db,job.workspace_id,job.channel_id,'Verification required',job.error_message)
                    db.commit()
                    return serialize_job(job,db)
                candidates=research_live(db,personality,channel.id)
                feed_errors=list(dict.fromkeys(error for c in candidates for error in json.loads(c.data).get('feed_errors',[])))
                job.research_trace=json.dumps({'provider':'rss','candidate_ids':[c.id for c in candidates],'selected_candidate_id':None,'feed_errors':feed_errors})
                db.commit()
                verified=next((c for c in candidates if c.status=='verified'),None)
                if not verified:
                    job.status=job.current_step='verification_required'
                    from app.services.job_research import NO_STORY
                    job.error_message=NO_STORY
                    notify(db,job.workspace_id,job.channel_id,'No verified topic found',job.error_message)
                    db.commit()
                    return serialize_job(job,db)
                topic=topic_from_candidate(db,verified)
                from app.models import ResearchCandidate
                if db.query(ResearchCandidate).filter_by(id=verified.id,status='verified').update({'status':'selected'})!=1:
                    raise ValueError('Research candidate was already selected. Retry research.')
                job.research_trace=json.dumps({'provider':'rss','candidate_ids':[c.id for c in candidates],'selected_candidate_id':verified.id,'feed_errors':feed_errors})
            else:
                topic=research_topic(db,personality,job.topic_mode,job.manual_topic)
                topic.channel_id=channel.id
            job.topic=topic
            job.topic_title=topic.title
            db.commit()
        if job.topic.verification_status not in {'verified','demo','limited_verification'}:
            job.status=job.current_step='verification_required'
            job.error_message='Selected topic has insufficient verified evidence. Retry research to obtain a verified current topic.'
            db.commit()
            return serialize_job(job,db)
        if job.topic.verification_status=='demo':
            warnings=list(dict.fromkeys(warnings+['Development research: not a verified current news story.']))
        if job.topic.verification_status=='limited_verification':
            from app.research.drafts import LABEL,draft_decision
            evidence=json.loads(job.topic.evidence or '[]')
            if not settings.review_drafts_enabled or not evidence or not draft_decision(evidence[0],personality)['eligible']:
                raise ValueError('Review draft evidence no longer qualifies. Retry research.')
            warnings=list(dict.fromkeys(warnings+[LABEL]))
            if not settings.gemini_api_key.strip():
                raise ValueError('Review drafts require configured Gemini; development fallback is not permitted.')
        script=job.script
        if script is None or scope in {'all','script'}:
            step='script_generation'; _set_step(db,job,step)
            logger.info('Job %s research mode %s; starting script generation (candidate %s)',job.id,job.topic.verification_status,json.loads(job.research_trace or '{}').get('selected_candidate_id'))
            evidence=json.loads(job.topic.evidence or '[]')
            historical=bool(evidence and evidence[0].get('content_type')=='historical')
            if historical:
                from app.research.verification import verify_story
                if not verify_story(evidence[0],evidence,historical=True)['passed']:
                    raise ValueError('Historical sources no longer meet verification policy. Retry research.')
                if not settings.gemini_api_key.strip():
                    raise ValueError('Verified historical generation requires configured Gemini; demo fallback is not allowed.')
            content,provider=generate_script(job.topic_title,personality.name,personality.tone,job.duration,job.language_code,
                json.dumps({'verification':job.topic.verification_status,'sources':evidence,'summary':job.topic.summary,
                    'content_type':'historical' if historical else 'news','event_date':evidence[0].get('event_date') if historical else None,
                    'event_date_precision':evidence[0].get('event_date_precision') if historical else None,
                    'publication_date':job.topic.published_at.isoformat() if job.topic.published_at else None,
                    'older_story':bool(job.topic.published_at and (datetime.now(timezone.utc)-job.topic.published_at.replace(tzinfo=timezone.utc)).total_seconds()>settings.research_max_age_hours*3600)}))
            suggestions=content.pop('scene_suggestions',None)
            content.pop('visual_keywords',None)
            warnings=[w for w in warnings if 'Script provider:' not in w]
            if 'fallback' in provider:
                warnings.append(f'Script provider: {provider}. Development copy is not publishable.')
            else:
                warnings.append(f'Script provider: {provider}')
            job.warnings=json.dumps(warnings)
            if not script:
                script=Script(id=new_id(),job_id=job.id,**content)
                job.script=script
                db.add(script)
            else:
                for key,value in content.items(): setattr(script,key,value)
            db.flush()
            save_scenes(db,job,suggestions)
            # Preserve script before the separate, potentially billable SEO request.
            db.commit()
            step='seo_generation'
            job.current_step=step
            db.commit()
            update_seo(db,script,job,personality)
            db.commit()
        elif not db.query(Scene).filter_by(job_id=job.id).first():
            save_scenes(db,job)
            db.commit()
        if scope=='seo':
            step='seo_generation'; _set_step(db,job,'script_generation')
            job.current_step=step;db.commit()
            update_seo(db,script,job,personality)
            db.commit()
        seo=script.seo
        if not seo:
            step='seo_generation'
            update_seo(db,script,job,personality);db.commit();seo=script.seo
        scenes=db.query(Scene).filter_by(job_id=job.id).order_by(Scene.scene_number).all()
        assets=db.query(Asset).filter_by(job_id=job.id).order_by(Asset.scene_number).all()
        if not assets or scope in {'all','assets','script'}:
            step='collecting_assets';_set_step(db,job,step)
            from app.services.media_library import collect_saved
            saved=collect_saved(db,job,scenes,root/'images'/job.id) if job.content_mode!='auto' else []
            filled={a.scene_number for a in saved}
            remaining=[s for s in scenes if s.scene_number not in filled]
            provider=settings.asset_provider if job.topic.verification_status in {'verified','limited_verification'} and job.content_mode!='my_assets' else 'demo'
            collected=saved+(collect_scene_assets(remaining,job.topic_title,personality.name,script.full_script,root/'images'/job.id,
                    provider,language=job.language_code,subject_category=personality.category) if remaining else [])
            collected.sort(key=lambda a:a.scene_number)
            db.query(Asset).filter_by(job_id=job.id).delete(synchronize_session=False)
            assets=[]
            for asset in collected:
                from app.services.media_library import validate_job_media
                validate_job_media(asset.local_path,root)
                record=Asset(id=new_id(),job_id=job.id,source=asset.source,license=asset.license,
                    attribution=asset.attribution[:500],url=asset.url,creator=asset.creator,
                    download_url=asset.download_url,scene_number=asset.scene_number,local_path=str(asset.local_path),
                    provenance=json.dumps(getattr(asset,"provenance",{})))
                db.add(record);assets.append(record)
            db.commit()
        held=[a.scene_number for a in assets if json.loads(a.provenance or '{}').get('kind') in {'text_card','missing'} or a.source in {'demo','Local text card','Original local illustration','Missing scene media'}]
        if held:
            raise ValueError('Missing genuine media for scenes '+', '.join(map(str,held))+'. Upload or replace licensed relevant photos/clips; standalone text cards are disabled.')
        legacy=[]
        for asset in assets:
            path=Path(asset.local_path);meta=json.loads(asset.provenance or '{}')
            if path.suffix.lower()!='.mp4' and meta.get('label') and not path.with_name(path.stem+'-source.jpg').is_file():
                from PIL import Image
                with Image.open(path) as preview:
                    if preview.size==(1080,1920):legacy.append(asset.scene_number)
        if legacy:
            raise ValueError('Retained original photos are missing for scenes '+', '.join(map(str,legacy))+'. Re-upload the licensed originals; legacy baked labels/panels cannot be rendered.')
        from app.services.assets.credits import sync_credits
        sync_credits(db,job);db.commit()
        audio=root/'audio'/f'{job.id}.wav'
        voice=job.voice_generation
        script_hash=hashlib.sha256(script.full_script.encode()).hexdigest()
        if scope in {'all','script','voice'} or not voice or not audio.is_file() or voice.script_hash!=script_hash:
            step='voice_generation';_set_step(db,job,step)
            scene_hints=[{'caption':s.caption,'emphasis_word':s.emphasis_word,'narration':s.narration} for s in scenes]
            profile=direct_voice(job.topic_title,{key:getattr(script,key) for key in ('hook','context','main_story','why_it_matters','ending','full_script')},
                                 personality.name,personality.category,personality.tone,scene_hints,job.voice_style,job.video_style,job.language_code)
            segments=prepare_delivery(script.full_script,profile,scene_hints,script.hook)
            requested_provider=job.tts_provider or channel.tts_provider or prefs['default_provider']
            narration_metadata={}
            provider=generate_narration(script.full_script,job.voice,audio,requested_provider,prefs['voice_speed'],profile,segments,
                                        language=job.language_code,metadata=narration_metadata)
            if not voice:
                voice=VoiceGeneration(id=new_id(),job_id=job.id)
                job.voice_generation=voice
                db.add(voice)
            voice.provider,voice.output_path,voice.voice=provider,str(audio),job.voice
            actual_provider='kokoro_onnx' if provider=='Kokoro local narrator' else 'google' if provider=='Google TTS narrator' else 'elevenlabs' if provider=='ElevenLabs allowed narrator' else 'local'
            if actual_provider=='google': voice.voice=job.voice if job.voice.count('-')>=3 else (settings.google_tts_voice if settings.google_tts_voice.startswith(job.voice) else job.voice)
            if actual_provider=='elevenlabs': voice.voice=job.voice if job.voice in [v.strip() for v in settings.elevenlabs_allowed_voice_ids.split(',')] else settings.elevenlabs_voice_id
            voice.voice=narration_metadata.get('voice',voice.voice)
            controls=provider_controls(actual_provider,profile,prefs['voice_speed'],voice.voice)
            voice.voice_profile=profile.model_dump_json()
            voice.delivery=json.dumps({'provider':actual_provider,'voice':voice.voice,'locale':narration_metadata.get('locale',job.locale),
                                       'model':'Kokoro-82M v1.0 INT8' if actual_provider=='kokoro_onnx' else 'eleven_multilingual_v2' if actual_provider=='elevenlabs' else None,
                                       'selection_reason':narration_metadata.get('reason',''),'controls':controls,'segments':segments,
                                       'audio_available':'fallback (silent' not in provider})
            voice.language=job.language
            voice.script_hash=script_hash
            voice.speed=controls.get('speed',controls.get('speakingRate',1))
            warnings=[w for w in warnings if 'Narration unavailable' not in w]
            if 'fallback' in provider:
                warnings.append('Narration unavailable: development silence is not publishable.')
            db.commit()
        slides=[Path(a.local_path) for a in assets]
        if scope not in {'cover','seo'} or not job.video:
            step='rendering';_set_step(db,job,step)
            music=db.get(MusicTrack,job.music_id or prefs.get('background_music_id')) if (job.music_id or prefs.get('background_music_id')) else None
            if music and music.workspace_id!=job.workspace_id: raise ValueError('Workspace music permission denied')
            if music: job.music_id=music.id
            output,cover,_=render_video(job.id,job.topic_title,personality.name,script.full_script,audio,job.duration,root,
                slides,seo.cover_text,job.video_style,Path(music.local_path) if music else None,
                scenes=scenes,subtitle_preset={**prefs,'language':job.language_code},voice_speed=voice.speed,
                focal_positions=[(json.loads(a.provenance or '{}').get('focal_x',.5),json.loads(a.provenance or '{}').get('focal_y',.5)) for a in assets],
                slide_kinds=[json.loads(a.provenance or '{}').get('kind','text_card' if a.source=='Local text card' else 'photo') for a in assets],
                media_labels=[('ARCHIVE '+str(json.loads(a.provenance or '{}').get('date') or '')[:4]+' - NOT THE AWARD EVENT') if json.loads(a.provenance or '{}').get('date') else 'ILLUSTRATIVE ARCHIVE' for a in assets],
                revision=job.content_revision,manual_timing=json.loads(job.research_trace or '{}').get('manual_scene_timing',False),
                scene_plan=json.loads(job.research_trace or '{}').get('accepted_henry_scene_plan'))
            video=job.video
            if not video:
                video=Video(id=new_id(),job_id=job.id);job.video=video;db.add(video)
            video.output_path,video.thumbnail_path,video.duration,video.status=str(output),str(cover),job.duration,'ready_for_review'
            render_metadata=Path(output).parent/'subtitle-timing.json'
            if render_metadata.is_file():
                video.duration=json.loads(render_metadata.read_text(encoding='utf8')).get('output_duration',job.duration)
            timeline_path=Path(output).parent/'render-timeline.json'
            if timeline_path.is_file():
                timeline=json.loads(timeline_path.read_text(encoding='utf8'))
                video.duration=timeline['duration']
                for scene,span in zip(scenes,timeline['scenes']):
                    scene.start_time,scene.end_time=span['start'],span['end']
                    if span.get('narration'):
                        scene.narration=span['narration']
                        scene.caption=' '.join(span['narration'].split()[:5])
            video.media_revision=job.media_revision
            db.commit()
        step='creating_cover';_set_step(db,job,step)
        poster=Path(job.video.output_path).parent/'poster.jpg' if job.video else None
        if poster and poster.is_file():
            from PIL import Image
            cover=root/'thumbnails'/f'{job.id}.png'
            Image.open(poster).save(cover)
        else:
            cover=create_cover(cover_image(slides[0],root/'videos'/job.id),seo.cover_text,root/'thumbnails'/f'{job.id}.png',channel.brand_color,job.language_code)
        thumbnail=db.query(Thumbnail).filter_by(job_id=job.id).first()
        if not thumbnail:
            thumbnail=Thumbnail(id=new_id(),job_id=job.id);db.add(thumbnail)
        thumbnail.local_path,thumbnail.headline=str(cover),seo.cover_text
        if not job.video or job.video.media_revision!=job.media_revision:
            raise ValueError('Rendered video does not match current media revision. Regenerate narration/video.')
        job.video.status='ready_for_review'
        from app.services.media_library import commit_usage
        commit_usage(db,job,assets)
        job.warnings=json.dumps(warnings)
        job.error_message,job.failed_step=None,None
        _set_step(db,job,'ready_for_review')
        notify(db,job.workspace_id,job.channel_id,'Video ready for approval',job.topic_title)
        db.commit()
        return serialize_job(job,db)
    except Exception as exc:
        db.rollback()
        from sqlalchemy.orm.exc import StaleDataError
        if isinstance(exc,StaleDataError):
            logger.warning('Superseded worker result discarded for %s',job.id)
            return serialize_job(db.get(VideoJob,job.id),db)
        job=db.get(VideoJob,job.id)
        job.status=job.current_step='failed'
        job.failed_step=step
        job.error_message=str(exc)[:2000]
        notify(db,job.workspace_id,job.channel_id,'Generation failed',f'{step}: {job.error_message}')
        db.commit()
        logger.exception('Video pipeline failed for %s at %s',job.id,step)
        raise

def run_job(job_id,scope='all'):
    # One local renderer at a time keeps Windows SAPI and memory use predictable.
    with worker_lock, SessionLocal() as db:
        job=db.get(VideoJob,job_id)
        if not job:
            return
        if job.status not in ACTIVE_STATUSES:
            return
        try:
            run_pipeline(db,job,db.get(Personality,job.personality_id),db.get(Channel,job.channel_id),scope)
        except Exception:
            pass  # The exception is logged and stored by run_pipeline; the API stays available.

