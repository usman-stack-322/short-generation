import json
from datetime import datetime,timezone,timedelta
from types import SimpleNamespace
from unittest.mock import Mock
import pytest
from app.core.config import settings
from app.database.session import SessionLocal
from app.models import VideoJob,Personality,ResearchCandidate,Topic,UploadTask
from app.research.live import assess
from app.research.drafts import draft_decision,evergreen_offer


def row(title='Ronaldo football performance analysis in Lisbon'):
    return {'title':title,'summary':title+'.','source_name':'BBC Sport','source_url':'https://bbc.com/sport/football/one',
            'published_at':(datetime.now(timezone.utc)-timedelta(hours=2)).isoformat(),'personality_match':['Ronaldo']}


def persona():return SimpleNamespace(name='Ronaldo',category='Football',research_keywords='[]',keywords='[]')


def candidate(data=None):return assess([data or row()],'Ronaldo',[],[])[0]


def accessible(monkeypatch,data=None):
    d=data or row()
    fetch=Mock(return_value=(('<html><h1>'+d['title']+'</h1><p>'+d['summary']+'</p></html>').encode(),{}))
    monkeypatch.setattr('app.research.drafts.public_get',fetch)
    return fetch


def test_limited_score_and_accessible_claim(monkeypatch):
    data=candidate();accessible(monkeypatch)
    result=draft_decision(data,persona(),fetch=True)
    assert result['eligible'] and result['score']>=50
    assert not result['verification']['passed'] and result['sources'][0]['access_checked_at']
    assert 'not probability' in result['score_explanation']


@pytest.mark.parametrize('term',['arrest','abuse','death','medical diagnosis','injury','criminal allegation'])
def test_sensitive_never_unlocked_by_score(term,monkeypatch):
    data=candidate(row('Ronaldo football '+term+' in Lisbon'))
    fetch=accessible(monkeypatch)
    result=draft_decision(data,persona(),fetch=True)
    assert not result['eligible'] and 'Sensitive' in result['reason'] and not fetch.called


def test_conflict_missing_source_and_theme_block(monkeypatch):
    data=candidate();data['evidence'].append({**row(),'title':'Ronaldo football performance analysis in Porto','summary':'Ronaldo football performance analysis in Porto.'})
    assert not draft_decision(data,persona())['eligible']
    data=candidate();data['evidence']=[]
    assert not draft_decision(data,persona())['eligible']
    data=candidate();person=persona();person.category='Business'
    assert not draft_decision(data,person)['eligible']
    data=candidate();accessible(monkeypatch, row('Unrelated player football performance analysis in Paris'))
    assert not draft_decision(data,persona(),fetch=True)['eligible']
    accessible(monkeypatch,row('Ronaldo football performance analysis in Paris'))
    result=draft_decision(candidate(),persona(),fetch=True)
    assert not result['eligible'] and 'contradicts' in result['reason']


def test_verified_keeps_normal_path():
    data=row('Ronaldo football goals milestone in Lisbon');data['source_url']='https://uefa.com/sport/one'
    result=draft_decision(candidate(data),persona())
    assert not result['eligible'] and 'Fully verified' in result['reason']


def held(p):
    with SessionLocal() as db:
        j=db.get(VideoJob,p['job_id']);j.script=None;j.video=None;j.voice_generation=None;j.topic=None
        j.status=j.current_step='verification_required'
        person=db.get(Personality,j.personality_id);person.name='Ronaldo';person.category='Football'
        data=candidate();r=ResearchCandidate(id='draft-'+j.id,channel_id=j.channel_id,personality_id=j.personality_id,title=data['title'],data=json.dumps(data),status='verification_required')
        db.add(r);j.research_trace=json.dumps({'provider':'rss','candidate_ids':[r.id]});db.commit()
        return r.id


def test_explicit_draft_same_job_persist_and_duplicate_block(publishable,monkeypatch):
    p=publishable;cid=held(p);accessible(monkeypatch)
    worker=Mock();monkeypatch.setattr('app.api.videos.run_job',worker)
    url='/api/videos/'+p['job_id'];headers=p['owner']
    assert p['client'].post(url+'/review-draft/'+cid,headers=headers).status_code==409
    monkeypatch.setattr(settings,'review_drafts_enabled',True)
    initial=p['client'].get(url,headers=headers).json()
    assert initial['draft_options'][0]['eligible'] and not worker.called
    with SessionLocal() as db:count=db.query(VideoJob).count()
    response=p['client'].post(url+'/review-draft/'+cid,headers=headers)
    assert response.status_code==200,response.text
    saved=p['client'].get(url,headers=headers).json()
    assert saved['verification_status']=='limited_verification' and not saved['verification']['passed']
    assert saved['draft_review']['score']>=50 and worker.call_count==1
    assert p['client'].post(url+'/review-draft/'+cid,headers=headers).status_code==409
    with SessionLocal() as db:
        assert db.query(VideoJob).count()==count
        assert db.get(ResearchCandidate,cid).status=='verification_required'


def test_unavailable_source_no_generation(publishable,monkeypatch):
    p=publishable;cid=held(p);monkeypatch.setattr(settings,'review_drafts_enabled',True)
    monkeypatch.setattr('app.research.drafts.public_get',Mock(side_effect=ValueError('Unavailable')))
    worker=Mock();monkeypatch.setattr('app.api.videos.run_job',worker)
    result=p['client'].post('/api/videos/'+p['job_id']+'/review-draft/'+cid,headers=p['owner'])
    assert result.status_code==409 and 'accessible' in result.json()['detail'] and not worker.called


def test_no_source_evergreen_separate_read_only_offer(publishable,monkeypatch):
    p=publishable;held(p)
    response={'extract':'Ronaldo is a Portuguese football player.','content_urls':{'desktop':{'page':'https://en.wikipedia.org/wiki/Ronaldo'}}}
    monkeypatch.setattr('app.research.drafts.public_get',Mock(return_value=(json.dumps(response).encode(),{})))
    worker=Mock();monkeypatch.setattr('app.api.videos.run_job',worker)
    url='/api/videos/'+p['job_id']
    result=p['client'].post(url+'/evergreen',headers=p['owner'])
    assert result.status_code==200 and result.json()['verification_status']=='source_review_required'
    saved=p['client'].get(url,headers=p['owner']).json()
    assert saved['status']=='verification_required' and not saved['script'] and not worker.called


def test_draft_upload_rejected_even_if_approved(publishable):
    from app.youtube.upload import upload_guard
    p=publishable
    with SessionLocal() as db:
        j=db.get(VideoJob,p['job_id']);j.topic.verification_status='limited_verification';db.commit()
    c=p['client'];url='/api/videos/'+p['job_id']
    assert c.post(url+'/approve',headers=p['owner'],json={'content_revision':1}).status_code==200
    with SessionLocal() as db:
        j=db.get(VideoJob,p['job_id'])
        with pytest.raises(RuntimeError,match='verified topic'):
            upload_guard(db,j,SimpleNamespace(requested_by=p['member_id'],content_revision=j.content_revision))


def test_draft_no_mock_or_unattributed_script(monkeypatch):
    from app.ai.scripts import generate_script
    context=json.dumps({'verification':'limited_verification','sources':[row()],'publication_date':row()['published_at']})
    monkeypatch.setattr(settings,'gemini_api_key','')
    with pytest.raises(ValueError,match='fallback'):generate_script('topic','Ronaldo','natural',30,source_context=context)
    monkeypatch.setattr(settings,'gemini_api_key','non-secret-unit-test-placeholder')
    fake=Mock();fake.generate.return_value={'full_script':'Breaking today, something happened.'}
    monkeypatch.setattr('app.ai.scripts.GeminiProvider',lambda:fake)
    with pytest.raises(ValueError,match='attribution'):generate_script('topic','Ronaldo','natural',30,source_context=context)


def test_concurrent_draft_submissions_only_queue_once(publishable,monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    from fastapi.testclient import TestClient
    from app.main import app
    from app.services.preferences import invalidate_approvals
    p=publishable;cid=held(p);accessible(monkeypatch)
    monkeypatch.setattr(settings,'review_drafts_enabled',True)
    barrier=Barrier(2);worker=Mock()
    def invalidate(db,job):
        barrier.wait(timeout=15);invalidate_approvals(db,job)
    monkeypatch.setattr('app.api.videos.invalidate_approvals',invalidate)
    monkeypatch.setattr('app.api.videos.run_job',worker)
    def send(_):
        client=TestClient(app)
        try:return client.post('/api/videos/'+p['job_id']+'/review-draft/'+cid,headers=p['owner']).status_code
        finally:client.close()
    with ThreadPoolExecutor(max_workers=2) as pool:codes=list(pool.map(send,range(2)))
    assert sorted(codes)==[200,409] and worker.call_count==1


def test_draft_pipeline_saves_script_without_promoting_verification(publishable,monkeypatch):
    from test_research_continuation import prepare
    from app.services import pipeline
    p=publishable
    script,_=prepare(p,monkeypatch,[])
    cid=held(p);accessible(monkeypatch)
    monkeypatch.setattr(settings,'review_drafts_enabled',True)
    monkeypatch.setattr(settings,'gemini_api_key','unit-test-placeholder')
    monkeypatch.setattr(pipeline,'generate_seo',lambda *a,**k:{'title':'Fixture','description':'Source-grounded fixture','hashtags':['#Test'],'keywords':['test'],'cover_text':'TEST DRAFT'})
    response=p['client'].post('/api/videos/'+p['job_id']+'/review-draft/'+cid,headers=p['owner'])
    assert response.status_code==200,response.text
    saved=p['client'].get('/api/videos/'+p['job_id'],headers=p['owner']).json()
    assert saved['status']=='ready_for_review',saved.get('error_message')
    assert saved['script'] and script.call_count==1 and saved['verification_status']=='limited_verification'
    assert not saved['verification']['passed']
    context=json.loads(script.call_args.args[-1]);assert context['verification']=='limited_verification'


def test_draft_permissions_and_foreign_candidate(publishable,monkeypatch):
    from app.core.security import new_id
    p=publishable;cid=held(p);monkeypatch.setattr(settings,'review_drafts_enabled',True)
    worker=Mock();monkeypatch.setattr('app.api.videos.run_job',worker)
    url='/api/videos/'+p['job_id']
    assert p['client'].post(url+'/review-draft/'+cid).status_code==401
    assert p['client'].post(url+'/review-draft/'+new_id(),headers=p['owner']).status_code==404
    with SessionLocal() as db:
        from app.models import Channel
        job=db.get(VideoJob,p['job_id'])
        other=Channel(id=new_id(),workspace_id=job.workspace_id,member_id=p['member_id'],name='Other isolated channel')
        db.add(other);db.flush()
        record=db.get(ResearchCandidate,cid);record.channel_id=other.id;db.commit()
    assert p['client'].post(url+'/review-draft/'+cid,headers=p['owner']).status_code==404
    assert not worker.called


def test_draft_date_and_source_attribution_validation(monkeypatch):
    from app.ai.scripts import generate_script
    date=datetime.now(timezone.utc).date().isoformat()
    context=json.dumps({'verification':'limited_verification','sources':[row()],'publication_date':date})
    monkeypatch.setattr(settings,'gemini_api_key','unit-test-placeholder')
    provider=Mock();provider.retry_policy.model_used='test fixture'
    monkeypatch.setattr('app.ai.scripts.GeminiProvider',lambda:provider)
    provider.generate.return_value={'full_script':'According to BBC Sport, Ronaldo had a football performance analysis in Lisbon.'}
    with pytest.raises(ValueError,match='publication date'):generate_script('topic','Ronaldo','natural',30,source_context=context)
    provider.generate.return_value={'full_script':f'According to BBC Sport on {date}, Ronaldo had a football performance analysis in Lisbon. Independent corroboration is missing.'}
    result,source=generate_script('topic','Ronaldo','natural',30,source_context=context)
    assert date in result['full_script'] and source=='Gemini (test fixture)'
    assert 'LIMITED_VERIFICATION_DRAFT' in provider.generate.call_args.args[0]


def test_below_fifty_ranking_is_not_unlocked(monkeypatch):
    # A nearly 14-day-old alias-only story from a minimally credible specialist.
    authority=lambda row:{'category':'specialist_news','publisher_group':'fixture','verified_identity':True,'reliability':.7,'primary_scope':False,'authoritative_for':[]}
    for path in ['app.research.live.source_metadata','app.research.verification.source_metadata','app.research.drafts.source_metadata']:
        monkeypatch.setattr(path,authority)
    source=row('Ronaldo');source.update(summary='Football milestone in Lisbon, Ronaldo.',search_window_days=14,
        published_at=(datetime.now(timezone.utc)-timedelta(days=14)+timedelta(seconds=10)).isoformat())
    person=persona();person.name='Cristiano Ronaldo'
    data=assess([source],person.name,[],[],max_age_hours=14*24)[0]
    fetch=accessible(monkeypatch,source)
    result=draft_decision(data,person,fetch=True)
    assert result['score']<50 and 'below 50' in result['reason'] and not result['eligible'] and not fetch.called


@pytest.fixture
def publishable(owner_publishable):
    # Channel access is per-member, so owner-driven flows use a channel owned by the OWNER membership.
    return owner_publishable
