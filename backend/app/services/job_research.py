"""Research-only checkpoints. Never invokes script, SEO, voice or rendering."""
import json
import logging
from app.database.session import SessionLocal
from app.models import VideoJob,Personality,ResearchCandidate
from app.research.live import research_live,topic_from_candidate
from app.services.preferences import invalidate_approvals

NO_STORY='No verified story found in the past 14 days. Retry research or change the personality/theme.'


def research_job(db,job):
    from app.research.selection import configured_provider
    from app.models import Channel
    channel=db.get(Channel,job.channel_id)
    if configured_provider(db,job.workspace_id)=='rss' and job.topic_mode=='current' and channel.automatic_evergreen_fallback:
        from app.services.automatic_research import automatic_topic
        from app.research.evergreen import NO_FALLBACK
        topic=automatic_topic(db,job,db.get(Personality,job.personality_id),channel)
        invalidate_approvals(db,job)
        job.status=job.current_step='research_ready' if topic else 'verification_required'
        from app.research.evergreen import hold_reason
        job.error_message=None if topic else hold_reason(json.loads(job.research_trace or '{}'));job.failed_step=None
        db.commit();return
    if configured_provider(db,job.workspace_id)=='demo':
        from app.research.engine import research_topic
        topic=research_topic(db,db.get(Personality,job.personality_id),job.topic_mode,job.manual_topic)
        topic.channel_id=job.channel_id
        invalidate_approvals(db,job)
        job.topic=topic;job.topic_title=topic.title
        job.research_trace=json.dumps({'provider':'demo','candidate_ids':[],'selected_candidate_id':None})
        job.status=job.current_step='research_ready';job.error_message=None;job.failed_step=None
        db.commit()
        return
    candidates=research_live(db,db.get(Personality,job.personality_id),job.channel_id)
    job.research_trace=json.dumps({'provider':'rss','candidate_ids':[c.id for c in candidates],
        'selected_candidate_id':None,'feed_errors':list(dict.fromkeys(e for c in candidates for e in json.loads(c.data).get('feed_errors',[])))})
    selected=next((c for c in candidates if c.status=='verified'),None)
    if selected:
        topic=topic_from_candidate(db,selected)
        if db.query(ResearchCandidate).filter_by(id=selected.id,status='verified').update({'status':'selected'})!=1:
            raise ValueError('Candidate already selected. Retry research.')
        invalidate_approvals(db,job)
        job.topic=topic;job.topic_title=topic.title
        trace=json.loads(job.research_trace);trace['selected_candidate_id']=selected.id;job.research_trace=json.dumps(trace)
        job.status=job.current_step='research_ready'
        job.error_message=None
    else:
        job.status=job.current_step='verification_required'
        job.error_message=NO_STORY
    job.failed_step=None
    db.commit()


def run_research_job(job_id):
    from app.services.pipeline import worker_lock
    with worker_lock,SessionLocal() as db:
        job=db.get(VideoJob,job_id)
        if not job or job.status!='researching' or job.current_step!='research_only':return
        try:
            research_job(db,job)
        except Exception as exc:
            db.rollback()
            from sqlalchemy.orm.exc import StaleDataError
            if isinstance(exc,StaleDataError):return
            job=db.get(VideoJob,job_id)
            job.status=job.current_step='failed';job.failed_step='researching'
            message=str(exc)[:1200]
            job.error_message=message if message.startswith('Research provider failed.') else 'Research provider failed. '+message
            job.research_trace=json.dumps({'provider':'rss','candidate_ids':getattr(exc,'candidate_ids',[]),'selected_candidate_id':None})
            db.commit()
            logging.getLogger(__name__).warning('Research-only job %s failed (%s)',job_id,type(exc).__name__)
