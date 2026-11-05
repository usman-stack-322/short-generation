import json
from datetime import datetime,timezone
from unittest.mock import Mock
from types import SimpleNamespace
from pathlib import Path
import pytest
from PIL import Image
from app.core.config import settings
from app.database.session import SessionLocal
from app.models import VideoJob,Channel,Personality,ResearchCandidate
from app.services import pipeline
from app.research.live import research_live,assess


def story(host='uefa.com',title='Ronaldo reaches goals milestone'):
    return {'title':title,'summary':'Ronaldo reaches a new goals milestone in an official match.',
            'source_name':host,'source_url':'https://'+host+'/sport/milestone',
            'published_at':datetime.now(timezone.utc).isoformat(),'personality_match':['Ronaldo']}


def prepare(p,monkeypatch,rows):
    monkeypatch.setattr(settings,'research_provider','rss')
    provider=Mock();provider.candidates.return_value=rows
    research=lambda db,personality,channel:research_live(db,personality,channel,provider)
    monkeypatch.setattr(pipeline,'research_live',research)
    monkeypatch.setattr('app.services.job_research.research_live',research)
    script=Mock(return_value=({k:'Fixture original narration.' for k in ('hook','context','main_story','why_it_matters','ending','full_script')},'Gemini fixture (no live call)'))
    monkeypatch.setattr(pipeline,'generate_script',script)
    with SessionLocal() as db:
        j=db.get(VideoJob,p['job_id']);j.script=None;j.video=None;j.voice_generation=None;j.topic=None
        j.status=j.current_step='researching';j.topic_title='';db.get(Personality,j.personality_id).name='Ronaldo';db.commit()
    def assets(*args,**kwargs):
        path=Path(settings.generated_dir)/'images'/p['job_id']/'fixture.png';path.parent.mkdir(parents=True,exist_ok=True)
        Image.new('RGB',(100,100),'navy').save(path)
        return [SimpleNamespace(source='Original test fixture',license='Original',attribution='Test',url=None,creator='Test',download_url=None,scene_number=1,local_path=path)]
    monkeypatch.setattr(pipeline,'collect_scene_assets',assets)
    def voice(text,voice,path,*args,**kwargs):path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(b'fixture');return 'Local narrator'
    monkeypatch.setattr(pipeline,'generate_narration',voice)
    def render(*args,**kwargs):
        root=Path(settings.generated_dir);path=root/'videos'/p['job_id']/'short.mp4';path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(b'test fixture, not real video')
        return path,root/'thumbnails'/p['job_id'],None
    monkeypatch.setattr(pipeline,'render_video',render)
    return script,provider


def run(p,scope='all'):
    with SessionLocal() as db:
        j=db.get(VideoJob,p['job_id'])
        return pipeline.run_pipeline(db,j,db.get(Personality,j.personality_id),db.get(Channel,j.channel_id),scope)


def test_verified_research_automatically_generates_and_persists(publishable,monkeypatch):
    p=publishable;script,_=prepare(p,monkeypatch,[story()]);result=run(p)
    assert result['status']=='ready_for_review' and result['script_state']=='saved'
    assert script.call_count==1 and result['research_trace']['selected_candidate_id']
    persisted=p['client'].get('/api/videos/'+p['job_id'],headers=p['owner']).json()
    assert persisted['script']==result['script']
    with SessionLocal() as db:assert db.get(ResearchCandidate,result['research_trace']['selected_candidate_id']).status=='selected'


def test_insufficient_evidence_holds_without_gemini_and_retry_continues(publishable,monkeypatch):
    p=publishable;script,provider=prepare(p,monkeypatch,[story('bbc.com')]);held=run(p)
    assert held['status']=='verification_required' and held['script_state']=='held' and not script.called
    assert held['error_message'].startswith('No verified story found in the past 14 days.') and held['sources'][0]['reason']
    first_ids=held['research_trace']['candidate_ids']
    provider.candidates.return_value=[story()]
    response=p['client'].post('/api/videos/'+p['job_id']+'/regenerate',headers=p['owner'],json={'scope':'retry'})
    assert response.status_code==200
    saved=p['client'].get('/api/videos/'+p['job_id'],headers=p['owner']).json()
    assert saved['status']=='research_ready' and not saved['script'] and script.call_count==0
    assert p['client'].post('/api/videos/'+p['job_id']+'/regenerate',headers=p['owner'],json={'scope':'all'}).status_code==200
    assert p['client'].get('/api/videos/'+p['job_id'],headers=p['owner']).json()['script'] and script.call_count==1
    assert saved['id']==p['job_id'] and saved['research_trace']['candidate_ids']!=first_ids


def test_provider_failure_is_research_failure_not_verification(publishable,monkeypatch):
    p=publishable;script,provider=prepare(p,monkeypatch,[]);provider.candidates.side_effect=ValueError('RSS unavailable: HTTP 503')
    with pytest.raises(ValueError):run(p)
    result=p['client'].get('/api/videos/'+p['job_id'],headers=p['owner']).json()
    assert result['status']=='failed' and result['failed_step']=='researching' and result['script_state']=='not_started'
    assert result['error_message']=='RSS unavailable: HTTP 503' and not script.called


def test_gemini_failure_and_retry_reuse_verified_topic(publishable,monkeypatch):
    p=publishable;script,provider=prepare(p,monkeypatch,[story()]);script.side_effect=RuntimeError('Gemini is temporarily unavailable because of high demand. Please retry generation.')
    with pytest.raises(RuntimeError):run(p)
    failed=p['client'].get('/api/videos/'+p['job_id'],headers=p['owner']).json()
    assert failed['failed_step']=='script_generation' and failed['script_state']=='failed' and failed['retryable']
    assert failed['verification_status']=='verified'
    script.side_effect=None
    assert p['client'].post('/api/videos/'+p['job_id']+'/regenerate',headers=p['owner'],json={'scope':'retry'}).status_code==200
    assert provider.candidates.call_count==1 and script.call_count==2
    assert p['client'].get('/api/videos/'+p['job_id'],headers=p['owner']).json()['script']


def test_explicit_verified_candidate_passes_to_worker(publishable,monkeypatch):
    p=publishable;script,_=prepare(p,monkeypatch,[story()])
    with SessionLocal() as db:
        j=db.get(VideoJob,p['job_id']);pid=j.personality_id
        candidate=research_live(db,db.get(Personality,pid),p['channel_id'],Mock(candidates=Mock(return_value=[story()])))[0].id
    result=p['client'].post('/api/videos/generate',headers=p['owner'],json={'channel_id':p['channel_id'],'personality_id':pid,'candidate_id':candidate,'duration':30}).json()
    saved=p['client'].get('/api/videos/'+result['id'],headers=p['owner']).json()
    assert saved['script'] and saved['research_trace']['selected_candidate_id']==candidate
    assert script.call_count==1


def test_incidental_personality_mentions_are_rejected():
    row=story('bbc.com',title='Barcelona prepares for Real Madrid')
    row['summary']='Barcelona prepares for a match. The historic Ronaldo era is remembered.'
    assert 'incidentally' in assess([row],'Ronaldo',[],[])[0]['rejection_reason']


def test_seo_failure_keeps_script_and_retries_only_seo(publishable,monkeypatch):
    p=publishable;script,provider=prepare(p,monkeypatch,[story()])
    original=pipeline.generate_seo
    seo=Mock(side_effect=RuntimeError('SEO provider unavailable'))
    monkeypatch.setattr(pipeline,'generate_seo',seo)
    with pytest.raises(RuntimeError):run(p)
    failed=p['client'].get('/api/videos/'+p['job_id'],headers=p['owner']).json()
    assert failed['failed_step']=='seo_generation' and failed['script'] and failed['script_state']=='saved'
    seo.side_effect=original
    assert p['client'].post('/api/videos/'+p['job_id']+'/regenerate',headers=p['owner'],json={'scope':'retry'}).status_code==200
    ready=p['client'].get('/api/videos/'+p['job_id'],headers=p['owner']).json()
    assert ready['status']=='ready_for_review' and ready['seo'] and script.call_count==1 and provider.candidates.call_count==1


def test_retry_replaces_unverified_attached_topic_without_deleting_history(publishable,monkeypatch):
    from app.models import Topic
    p=publishable;script,_=prepare(p,monkeypatch,[story()])
    with SessionLocal() as db:
        j=db.get(VideoJob,p['job_id']);old=Topic(id='held-'+j.id,personality_id=j.personality_id,channel_id=j.channel_id,title='Old unsupported claim',verification_status='verification_required')
        db.add(old);j.topic=old;j.status=j.current_step='verification_required';db.commit();old_id=old.id
    assert p['client'].post('/api/videos/'+p['job_id']+'/regenerate',headers=p['owner'],json={'scope':'retry'}).status_code==200
    with SessionLocal() as db:
        j=db.get(VideoJob,p['job_id']);assert j.topic_id!=old_id and j.topic and not j.script and db.get(Topic,old_id)
    assert script.call_count==0


@pytest.fixture
def publishable(owner_publishable):
    # Channel access is per-member, so owner-driven flows use a channel owned by the OWNER membership.
    return owner_publishable
