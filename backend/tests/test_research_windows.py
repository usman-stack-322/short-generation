import json
from datetime import datetime,timedelta,timezone
from email.utils import format_datetime
from urllib.parse import urlparse,parse_qs
from unittest.mock import Mock
import pytest
from app.core.config import settings
from app.database.session import SessionLocal
from app.models import VideoJob,Personality,ResearchCandidate
from app.research.live import RSSResearchProvider,research_live,topic_from_candidate,assess


def story(days=0,host='uefa.com',suffix='one',title='Ronaldo goals milestone in Lisbon',now=None):
    now=now or datetime.now(timezone.utc)
    return {'title':title,'summary':'Ronaldo reaches a goals milestone in Lisbon.',
            'source_name':host,'source_url':f'https://{host}/sport/{suffix}',
            'published_at':(now-timedelta(days=days,seconds=1)).isoformat(),'personality_match':['Ronaldo']}


def setup_job(p):
    with SessionLocal() as db:
        j=db.get(VideoJob,p['job_id']);j.script=None;j.video=None;j.voice_generation=None;j.topic=None
        j.status=j.current_step='verification_required';j.error_message='Old combined rejection text'
        db.get(Personality,j.personality_id).name='Ronaldo';db.commit()


class Windows:
    def __init__(self,values):self.values=values;self.calls=[]
    def search_window(self,name,keywords,days,now):self.calls.append(days);return self.values.get(days,[])


@pytest.mark.parametrize('success,age,expected',[(3,1,[3]),(7,5,[3,7]),(14,10,[3,7,14])])
def test_progressive_search_stops_on_verified_window(publishable,success,age,expected):
    p=publishable;provider=Windows({success:[story(age)]})
    with SessionLocal() as db:
        j=db.get(VideoJob,p['job_id']);person=db.get(Personality,j.personality_id);person.name='Ronaldo'
        rows=research_live(db,person,j.channel_id,provider)
        assert provider.calls==expected and len(rows)==1 and rows[0].status=='verified'
        data=json.loads(rows[0].data);assert data['search_window_days']==success
        assert bool(data['period_label'])==(success>3)
        topic=topic_from_candidate(db,rows[0]);assert topic.verification_status=='verified'


def test_real_retrieval_changes_date_query_and_filters_exact_boundaries(monkeypatch):
    from app.research import live
    now=datetime(2026,10,23,12,tzinfo=timezone.utc)
    monkeypatch.setattr(settings,'rss_feeds','https://news.google.com/rss/search?q=football%20when%3A3d&hl=en-US')
    dates=[now-timedelta(days=7),now-timedelta(days=7,seconds=1),now+timedelta(seconds=1)]
    feed='<rss version="2.0"><channel><title>Fixture</title>'+''.join(f'<item><title>Ronaldo {i} goals milestone</title><link>https://www.uefa.com/{i}</link><pubDate>{format_datetime(dt)}</pubDate></item>' for i,dt in enumerate(dates))+'</channel></rss>'
    fetch=Mock(return_value=(feed.encode(),{}));monkeypatch.setattr(live,'public_get',fetch)
    provider=RSSResearchProvider()
    assert provider.search_window('Ronaldo',[],3,now)==[]
    rows=provider.search_window('Ronaldo',[],7,now)
    assert len(rows)==1 and rows[0]['source_url'].endswith('/0')
    provider.search_window('Ronaldo',[],14,now)
    queries=[parse_qs(urlparse(c.args[0]).query)['q'][0] for c in fetch.call_args_list]
    assert len(set(queries))==3 and all('after:' in q and 'before:' in q and 'when:' not in q for q in queries)
    assert 'after:2026-10-15' in queries[1] and 'after:2026-10-08' in queries[2]


def test_canonical_duplicates_across_windows_and_publishers_count_once(publishable):
    a=story(5,'bbc.com',title='Ronaldo 2028 contract update in Lisbon')
    a['summary']='Reuters: Ronaldo 2028 contract update in Lisbon.'
    b={**a,'title':'Lisbon 2028 contract update for Ronaldo','source_url':'https://espn.com/sport/other','source_name':'ESPN'}
    provider=Windows({3:[],7:[a,b,a],14:[a,b]})
    with SessionLocal() as db:
        j=db.get(VideoJob,publishable['job_id']);person=db.get(Personality,j.personality_id);person.name='Ronaldo'
        rows=research_live(db,person,j.channel_id,provider)
        assert len(rows)==1 and rows[0].status=='verification_required'
        data=json.loads(rows[0].data)
        assert data['verification']['independent_source_count']==1 and data['verification']['duplicate_signals']
        assert db.query(ResearchCandidate).filter_by(channel_id=j.channel_id).count()==1


def test_no_eligible_results_keeps_relevance_age_and_newest_selection(publishable):
    rows=[story(15),story(5,title='Harry Kane goals milestone in Lisbon')]
    provider=Windows({14:rows})
    with SessionLocal() as db:
        j=db.get(VideoJob,publishable['job_id']);person=db.get(Personality,j.personality_id);person.name='Ronaldo'
        results=research_live(db,person,j.channel_id,provider)
        assert all(r.status=='rejected' for r in results)
    ranked=assess([story(2,suffix='older'),story(1,suffix='newest')],'Ronaldo',[],[],max_age_hours=72)
    assert all(r['status']=='verified' for r in ranked)


def test_retry_updates_same_job_persists_and_requires_explicit_generation(owner_publishable,monkeypatch):
    p=owner_publishable;setup_job(p);monkeypatch.setattr(settings,'research_provider','rss')
    provider=Windows({7:[story(5)]})
    monkeypatch.setattr('app.services.job_research.research_live',lambda db,person,channel:research_live(db,person,channel,provider))
    gemini=Mock(side_effect=AssertionError('Research must never generate'))
    monkeypatch.setattr('app.services.pipeline.generate_script',gemini)
    monkeypatch.setattr('app.services.pipeline.generate_seo',gemini)
    with SessionLocal() as db:count=db.query(VideoJob).count()
    url='/api/videos/'+p['job_id']
    assert p['client'].post(url+'/research',headers=p['owner']).status_code==200
    ready=p['client'].get(url,headers=p['owner']).json()
    assert ready['status']=='research_ready' and ready['script'] is None and ready['verification']['passed']
    selected=ready['research_trace']['selected_candidate_id'];assert selected and ready['sources'][0]['period_label']
    assert p['client'].post(url+'/research',headers=p['owner']).json()['research_trace']['selected_candidate_id']==selected
    assert provider.calls==[3,7] and not gemini.called
    with SessionLocal() as db:assert db.query(VideoJob).count()==count
    worker=Mock();monkeypatch.setattr('app.api.videos.run_job',worker)
    assert p['client'].post(url+'/regenerate',headers=p['owner'],json={'scope':'all'}).status_code==200
    assert worker.call_count==1


@pytest.mark.parametrize('failed',[False,True])
def test_no_match_is_not_a_provider_failure(publishable,monkeypatch,failed):
    p=publishable;setup_job(p);monkeypatch.setattr(settings,'research_provider','rss')
    def search(*args):
        if failed:raise ValueError('RSS HTTP 503')
        return []
    monkeypatch.setattr('app.services.job_research.research_live',search)
    gemini=Mock(side_effect=AssertionError('No generation'))
    monkeypatch.setattr('app.services.pipeline.generate_script',gemini)
    p['client'].post('/api/videos/'+p['job_id']+'/research',headers=p['owner'])
    result=p['client'].get('/api/videos/'+p['job_id'],headers=p['owner']).json()
    assert result['status']==('failed' if failed else 'verification_required')
    if failed:assert result['failed_step']=='researching' and '503' in result['error_message']
    else:assert result['error_message']=='No verified story found in the past 14 days. Retry research or change the personality/theme.'
    assert not gemini.called


def test_old_story_script_rejects_today_and_breaking(monkeypatch):
    from app.ai.scripts import GeminiProvider
    payload={k:'Today this is breaking news.' for k in ('hook','context','main_story','why_it_matters','ending','full_script')}
    payload.update(visual_keywords=['football'],scenes=[{'visual_query':'stadium'}]*6)
    response=Mock();response.json.return_value={'candidates':[{'content':{'parts':[{'text':json.dumps(payload)}]}}]}
    monkeypatch.setattr('app.ai.scripts.httpx.post',lambda *args,**kwargs:response)
    with pytest.raises(ValueError,match='Older story'):GeminiProvider()._request('OLDER_STORY_DATE_GUARD')


def test_concurrent_research_retry_queues_once(publishable,monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    p=publishable;setup_job(p);monkeypatch.setattr(settings,'research_provider','rss')
    worker=Mock();monkeypatch.setattr('app.services.job_research.run_research_job',worker)
    def request(_):return p['client'].post('/api/videos/'+p['job_id']+'/research',headers=p['owner']).status_code
    with ThreadPoolExecutor(max_workers=4) as pool:codes=list(pool.map(request,range(4)))
    assert all(c in (200,409) for c in codes) and worker.call_count==1


def test_newest_verified_story_is_preferred(publishable):
    p=publishable
    provider=Windows({3:[story(2,suffix='older'),story(1,suffix='newest')]})
    with SessionLocal() as db:
        j=db.get(VideoJob,p['job_id']);person=db.get(Personality,j.personality_id);person.name='Ronaldo'
        rows=research_live(db,person,j.channel_id,provider)
        assert len(rows)==1 and json.loads(rows[0].data)['source_url'].endswith('/newest')


def test_generation_rechecks_expired_selected_evidence(publishable,monkeypatch):
    p=publishable;setup_job(p);monkeypatch.setattr(settings,'research_provider','rss')
    provider=Windows({7:[story(5)]})
    monkeypatch.setattr('app.services.job_research.research_live',lambda db,person,channel:research_live(db,person,channel,provider))
    url='/api/videos/'+p['job_id'];p['client'].post(url+'/research',headers=p['owner'])
    with SessionLocal() as db:
        j=db.get(VideoJob,p['job_id']);evidence=json.loads(j.topic.evidence)
        for row in evidence:row['published_at']=(datetime.now(timezone.utc)-timedelta(days=15)).isoformat()
        j.topic.evidence=json.dumps(evidence);db.commit()
    worker=Mock();monkeypatch.setattr('app.api.videos.run_job',worker)
    assert p['client'].post(url+'/regenerate',headers=p['owner'],json={'scope':'all'}).status_code==409
    assert not worker.called


@pytest.fixture
def publishable(owner_publishable):
    # Channel access is per-member, so owner-driven flows use a channel owned by the OWNER membership.
    return owner_publishable
