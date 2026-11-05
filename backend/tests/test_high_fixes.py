from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timezone
from unittest.mock import Mock
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm.exc import StaleDataError
from app.database.session import SessionLocal
from app.models import VideoJob,Approval,WorkspaceMember,GenerationRequest
from app.research.live import assess
from app.research.verification import verify_story


def test_script_edit_cannot_be_cleared_by_partial_regeneration(publishable,monkeypatch):
    p=publishable;c=p['client'];url='/api/videos/'+p['job_id']
    worker=Mock();monkeypatch.setattr('app.api.videos.run_job',worker)
    assert c.post(url+'/approve',headers=p['owner'],json={'content_revision':1}).status_code==200
    edit={k:'Changed narration'for k in ('hook','context','main_story','why_it_matters','ending')}
    assert c.patch(url+'/script',headers=p['owner'],json=edit).status_code==200
    for scope in ['cover','seo']:
        assert c.post(url+'/regenerate',headers=p['owner'],json={'scope':scope}).status_code==409
    assert worker.call_count==0
    assert c.post(url+'/approve',headers=p['owner'],json={'content_revision':2}).status_code==409
    with SessionLocal() as db:
        job=db.get(VideoJob,p['job_id'])
        assert db.query(Approval).filter_by(job_id=job.id).count()==0
        job.status='ready_for_review';job.video.status='ready_for_review'
        job.video.media_revision=job.media_revision  # simulate successful current render
        db.commit()
    assert c.post(url+'/approve',headers=p['owner'],json={'content_revision':1}).status_code==409
    assert c.post(url+'/approve',headers=p['owner']).status_code==409
    assert c.post(url+'/approve',headers=p['owner'],json={'content_revision':2}).status_code==200


def test_concurrent_edit_cannot_restore_stale_approval(publishable):
    from app.youtube.permissions import approve
    p=publishable
    with SessionLocal() as stale:
        job=stale.get(VideoJob,p['job_id']);_ = job.video
        owner=stale.query(WorkspaceMember).filter_by(workspace_id=job.workspace_id,role='OWNER').one()
        edit={k:'Concurrent change'for k in ('hook','context','main_story','why_it_matters','ending')}
        assert p['client'].patch('/api/videos/'+job.id+'/script',headers=p['owner'],json=edit).status_code==200
        with pytest.raises(StaleDataError):approve(stale,job,owner,1)
        stale.rollback()
    with SessionLocal() as db:
        assert db.query(Approval).filter_by(job_id=p['job_id']).count()==0
        assert db.get(VideoJob,p['job_id']).status=='failed'


def test_concurrent_regeneration_claims_only_once(publishable,monkeypatch):
    from threading import Barrier
    from app.main import app
    from app.services.preferences import invalidate_approvals
    p=publishable;barrier=Barrier(2);worker=Mock()
    def invalidate(db,job):
        barrier.wait(timeout=10);invalidate_approvals(db,job)
    monkeypatch.setattr('app.api.videos.invalidate_approvals',invalidate)
    monkeypatch.setattr('app.api.videos.run_job',worker)
    def send(_):
        client=TestClient(app)
        try:return client.post('/api/videos/'+p['job_id']+'/regenerate',headers=p['owner'],json={'scope':'voice'}).status_code
        finally:client.close()
    with ThreadPoolExecutor(max_workers=2) as pool:codes=list(pool.map(send,range(2)))
    assert sorted(codes)==[200,409]
    assert worker.call_count==1


def test_concurrent_generation_is_one_durable_operation(publishable,monkeypatch):
    from app.main import app
    p=publishable;worker=Mock();monkeypatch.setattr('app.api.videos.run_job',worker)
    body={'channel_id':p['channel_id'],'personality_id':None,'topic_mode':'manual','manual_topic':'Synthetic concurrency fixture'}
    with SessionLocal() as db:body['personality_id']=db.get(VideoJob,p['job_id']).personality_id
    def send():
        c=TestClient(app)
        try:return c.post('/api/videos/generate',headers=p['owner'],json=body)
        finally:c.close()
    with ThreadPoolExecutor(max_workers=6) as pool:responses=list(pool.map(lambda _:send(),range(6)))
    assert all(r.status_code==201 for r in responses),[(r.status_code,r.text)for r in responses]
    key=responses[0].json()['id']
    assert {r.json()['id']for r in responses}=={key}
    assert worker.call_count==1
    with SessionLocal() as db:
        assert db.query(GenerationRequest).filter_by(job_id=key).count()==1
        job=db.get(VideoJob,key);job.status='failed';job.failed_step='researching';db.commit()
    assert send().json()['id']==key
    assert p['client'].post('/api/videos/'+key+'/regenerate',headers=p['owner'],json={'scope':'retry'}).status_code==200
    changed={**body,'manual_topic':'A changed operation'}
    assert p['client'].post('/api/videos/generate',headers=p['owner'],json=changed).json()['id']!=key
    explicit={**body,'operation_id':'explicit-new-attempt-1'}
    first=p['client'].post('/api/videos/generate',headers=p['owner'],json=explicit).json()['id']
    assert first!=key
    assert p['client'].post('/api/videos/generate',headers=p['owner'],json=explicit).json()['id']==first
    assert p['client'].post('/api/videos/generate',headers=p['owner'],json={**explicit,'manual_topic':'Changed'}).status_code==409


def report(title,host,summary=''):
    return {'title':title,'summary':summary,'source_url':'https://'+host+'/sport/fixture','source_name':host,'published_at':datetime.now(timezone.utc).isoformat()}


def test_different_events_do_not_corroborate():
    rows=[report('Cristiano Ronaldo wins award at Portugal ceremony','bbc.com','A recognition event took place in Lisbon.'),
          report('Cristiano Ronaldo wins award at Madrid ceremony','theguardian.com','A different recognition event in Spain.')]
    assert all(r['status']=='verification_required'for r in assess(rows,'Cristiano Ronaldo',[],[]))
    assert not verify_story(rows[0],rows)['passed']


def test_name_and_topic_are_not_evidence_but_specific_claim_is():
    a=report('Ronaldo contract update','bbc.com')
    b=report('Contract update for Ronaldo','espn.com')
    assert not verify_story(a,[a,b])['passed']
    a=report('Ronaldo contract extension through 2028 at Al Nassr','bbc.com')
    b=report('Al Nassr confirms Ronaldo contract extension through 2028','espn.com')
    assert verify_story(a,[a,b])['passed']
    b['title']=b['title'].replace('2028','2029')
    assert not verify_story(a,[a,b])['passed']


def test_specific_claim_does_not_override_syndication():
    a=report('Ronaldo contract extension through 2028','bbc.com','Reuters reports the extension.')
    b=report('Contract extended through 2028 for Ronaldo','espn.com','Reuters confirmed the deal.')
    assert not verify_story(a,[a,b])['passed']


def test_shared_year_or_subject_does_not_override_different_claims():
    a=report('Ronaldo wins award in 2028','bbc.com')
    b=report('Ronaldo arrest confirmed in 2028','espn.com')
    assert not verify_story(a,[a,b])['passed']
    a=report('Ronaldo contract extension through 2028','bbc.com')
    b=report('Ronaldo contract termination through 2028','espn.com')
    assert not verify_story(a,[a,b])['passed']
    a=report('Ronaldo wins Golden Boot award in 2028','bbc.com')
    b=report("Ronaldo wins Ballon d'Or award in 2028",'espn.com')
    assert not verify_story(a,[a,b])['passed']


def test_retry_cover_preserves_render_revision(publishable,monkeypatch):
    p=publishable;worker=Mock();monkeypatch.setattr('app.api.videos.run_job',worker)
    with SessionLocal() as db:
        job=db.get(VideoJob,p['job_id']);job.status='failed';job.failed_step='creating_cover';db.commit()
    result=p['client'].post('/api/videos/'+p['job_id']+'/regenerate',headers=p['owner'],json={'scope':'retry'})
    assert result.status_code==200
    assert worker.call_args.args[1]=='cover'
    with SessionLocal() as db:
        job=db.get(VideoJob,p['job_id']);assert job.media_revision==job.video.media_revision


@pytest.fixture
def publishable(owner_publishable):
    # Channel access is per-member, so owner-driven flows use a channel owned by the OWNER membership.
    return owner_publishable
