"""Ordered full-verification selection for an explicit automatic generation job."""
import json
from sqlalchemy.exc import IntegrityError
from app.models import ResearchCandidate
from app.research.live import research_live,topic_from_candidate,ResearchSearchError
from app.research.evergreen import research_evergreen,load_article,duplicate_story,historical_topic,NO_FALLBACK
from app.research.verification import canonical_url
from app.core.config import settings
from app.research.claims import claim_match


def automatic_topic(db,job,personality,channel):
    trace=json.loads(job.research_trace or '{}')
    from types import SimpleNamespace
    snapshot=trace.get('generation_settings',{})
    channel=SimpleNamespace(id=channel.id,niche=snapshot.get('niche',channel.niche),default_language=job.language_code,
                            evergreen_source_urls=snapshot.get('evergreen_source_urls',channel.evergreen_source_urls))
    trace.update(provider='rss',candidate_ids=[],selected_candidate_id=None,fallback_reason=None)
    def progress(stage):
        job.current_step=stage;job.research_trace=json.dumps(trace);db.commit()
    def window(days):progress('research_latest' if days==3 else f'research_{days}_days')
    news_failure=None
    access_results={}
    def usable(data):
        key=canonical_url(data['source_url'])
        if key not in access_results:
            if len(access_results)>=settings.evergreen_max_sources:
                data['rejection_reason']='Source access budget exhausted. Retry research or configure focused reference sources.'
                return False
            ok=news_access(db,data,personality,channel)
            access_results[key]=(ok,data.get('rejection_reason'),data.get('access_checked_at'),data.get('evidence'),data.get('verification'))
        ok,reason,checked,evidence,verification=access_results[key]
        if reason:data['rejection_reason']=reason
        if checked:data['access_checked_at']=checked
        if ok:data['evidence']=evidence;data['verification']=verification
        return ok
    try:
        # Continue a search window when a nominally verified RSS item is inaccessible.
        candidates=research_live(db,personality,channel.id,on_window=window,eligible=usable)
        trace['candidate_ids']=[c.id for c in candidates]
    except ResearchSearchError as exc:
        news_failure=str(exc);trace['candidate_ids']=exc.candidate_ids
        trace['news_provider_error']=news_failure;candidates=[]
    selected=None;topic=None
    for candidate in candidates:
        if candidate.status!='verified':continue
        data=json.loads(candidate.data)
        if duplicate_story(db,data,channel.id):continue
        try:
            with db.begin_nested():topic=topic_from_candidate(db,candidate)
        except (ValueError,IntegrityError):continue
        selected=candidate;break
    if topic is None:
        trace['fallback_reason']='No usable fully verified news after latest, 7-day and 14-day research.' if not news_failure else 'News provider failed; separate historical research attempted.'
        progress('research_evergreen')
        try:
            evergreen=research_evergreen(db,personality,channel)
        except Exception as exc:
            trace['evergreen_provider_error']='Historical research provider unavailable: '+type(exc).__name__
            job.research_trace=json.dumps(trace);db.commit()
            raise ValueError('Historical research provider failed. Check network/research source configuration and retry research. '+('News provider also failed.' if news_failure else '')) from None
        trace['candidate_ids'].extend(c.id for c in evergreen)
        trace['historical_search']=getattr(evergreen,'diagnostics',json.loads(evergreen[0].data).get('research_diagnostics',{}) if evergreen else {})
        for candidate in evergreen:
            if candidate.status!='verified':continue
            try:
                with db.begin_nested():topic=historical_topic(db,candidate)
            except (ValueError,IntegrityError):continue
            selected=candidate;break
        trace['content_type']='historical' if selected else None
    else:trace['content_type']='news'
    if selected:
        job.current_step='selecting_topic'
        if db.query(ResearchCandidate).filter_by(id=selected.id,status='verified').update({'status':'selected'})!=1:
            raise ValueError('Selected research candidate already claimed. Retry research.')
        trace['selected_candidate_id']=selected.id
        job.topic=topic;job.topic_title=topic.title
    job.research_trace=json.dumps(trace);db.commit()
    return topic


def news_access(db,data,personality,channel):
    """Access failures cannot cause selection of an ungrounded RSS headline."""
    if duplicate_story(db,data,channel.id):
        data['rejection_reason']='Duplicate event already queued/generated for this channel'
        return False
    try:
        accessible=[];seen=set()
        for row in data.get('evidence',[data]):
            key=canonical_url(row['source_url'])
            if key in seen:continue
            if len(seen)>=3:break
            seen.add(key)
            try:article=load_article(row,personality)
            except Exception:continue
            if claim_match(data,{'title':article['article_title'],'summary':article['article_excerpt'][:1500]})!='supports':continue
            accessible.append({**row,'access_checked_at':article['access_checked_at'],'originating_sources':article.get('originating_sources',[])})
        from app.research.verification import verify_story
        from app.research.live import candidate_age_hours
        decision=verify_story(data,accessible,max_age_hours=candidate_age_hours(data))
        if not decision['passed']:
            data['rejection_reason']='Accessible sources do not independently support the specific news claim: '+decision['reason']
            return False
        data['evidence']=accessible;data['verification']=decision
        if accessible:accessible[0]['verification']=decision
        return True
    except Exception:
        data['rejection_reason']='News source inaccessible, restricted or not focused on the selected personality'
        return False
