import json
from uuid import uuid4
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.ai.scripts import parse_script
from app.core.security import hash_password, verify_password
from app.database.session import SessionLocal
from app.models import Personality, Topic, VideoJob
from app.research.engine import Candidate, validate_candidate, research_topic
from app.services.pipeline import run_pipeline
from app.video.subtitles import subtitle_cues


def login(client,email='owner@example.com',password='DemoOwner123!'):
    response=client.post('/api/auth/login',json={'email':email,'password':password})
    assert response.status_code==200,response.text
    return {'Authorization':'Bearer '+response.json()['access_token']}


def test_password_hashing_and_invalid_tokens():
    encoded=hash_password('Secure-testing-123!')
    assert 'Secure-testing' not in encoded
    assert verify_password('Secure-testing-123!',encoded)
    assert not verify_password('wrong',encoded)
    with TestClient(app) as client:
        assert client.get('/api/channels').status_code==401
        for token in ('garbage','a.b','e30.invalid'):
            assert client.get('/api/channels',headers={'Authorization':'Bearer '+token}).status_code==401


def test_viewer_cannot_generate_or_regenerate_and_deactivation_revokes_access():
    with TestClient(app) as client:
        owner=login(client)
        email=f'viewer-{uuid4()}@example.com'
        assert client.post('/api/members',headers=owner,json={'name':'Read Only','email':email,'role':'VIEWER'}).status_code==422
        member=client.post('/api/members',headers=owner,json={'name':'Fresh Member','email':email,'role':'MEMBER'}).json()
        viewer=login(client,email,member['temporary_password'])
        assert client.get('/api/channels',headers=viewer).json()==[]
        assert client.post('/api/videos/generate',headers=viewer,json={'channel_id':'x','personality_id':'y'}).status_code in (403,404,422)
        assert client.post('/api/videos/unknown/regenerate',headers=viewer).status_code in (403,404,422)
        assert client.post('/api/channels',headers=viewer,json={'name':'Member own channel'}).status_code==201
        assert client.get('/api/members',headers=viewer).status_code==403
        client.patch('/api/members/'+member['id'],headers=owner,json={'active':False})
        assert client.get('/api/dashboard',headers=viewer).status_code==401


def test_workspace_and_assignment_isolation():
    with TestClient(app) as client:
        owner=login(client)
        editor=login(client,'editor@example.com','DemoEditor123!')
        channel=client.post('/api/channels',headers=owner,json={'name':'Owner Private'}).json()
        assert channel['id'] not in [c['id'] for c in client.get('/api/channels',headers=editor).json()]
        registration=client.post('/api/auth/register',json={'name':'Other Owner','email':f'{uuid4()}@example.com','password':'Another-password123!'}).json()
        other={'Authorization':'Bearer '+registration['access_token']}
        assert client.get('/api/channels',headers=other).json()==[]
        assert client.post('/api/personalities',headers=other,json={'name':'Invalid Assignment','channel_id':channel['id']}).status_code==400


def test_parser_rejects_invalid_responses_and_builds_consistent_full_script():
    for text in ('not json','[]','{}','{"hook":"hello"}'):
        with pytest.raises((ValueError,TypeError)):
            parse_script(text)
    values={k:k for k in ('hook','context','main_story','why_it_matters','ending')}
    result=parse_script('```json\n'+json.dumps(values)+'\n```')
    assert result['full_script']==' '.join(values.values())


def test_research_reliability_and_duplicate_rejection():
    with pytest.raises(ValueError,match='reliability'):
        validate_candidate(Candidate('Rumor','Unknown',reliability_score=.1))
    with TestClient(app),SessionLocal() as db:
        personality=db.query(Personality).first()
        title='Unique angle '+uuid4().hex
        topic=research_topic(db,personality,'manual',title)
        assert topic.source_url is None and topic.published_at is None
        db.commit()
        with pytest.raises(ValueError,match='unique'):
            research_topic(db,personality,'manual','  '+title.upper()+'  ')


def test_pipeline_failure_is_persisted(monkeypatch):
    with TestClient(app) as client:
        headers=login(client)
        channel=client.get('/api/channels',headers=headers).json()[0]
        persona=client.post('/api/personalities',headers=headers,json={'name':'Failure Test','channel_id':channel['id']}).json()
        def fail(*args,**kwargs):
            raise RuntimeError('Deliberate research provider outage')
        monkeypatch.setattr('app.services.pipeline.research_topic',fail)
        response=client.post('/api/videos/generate',headers=headers,json={'channel_id':channel['id'],'personality_id':persona['id']})
        assert response.status_code==201
        job=client.get('/api/videos/'+response.json()['id'],headers=headers).json()
        assert job['status']=='failed'
        assert 'research provider outage' in job['error_message']
        assert client.get('/api/health').status_code==200


def test_subtitles_cover_all_words_without_overrun():
    script=' '.join('word'+str(i) for i in range(91))
    cues=subtitle_cues(script,29.4)
    assert cues[0][0]==0
    assert abs(cues[-1][1]-29.4)<.001
    assert ' '.join(c[2] for c in cues)==script


def test_generate_input_validation():
    with TestClient(app) as client:
        headers=login(client)
        assert client.post('/api/videos/generate',headers=headers,json={'channel_id':'x','personality_id':'y','duration':31}).status_code==422
        assert client.post('/api/videos/generate',headers=headers,json={'channel_id':'x','personality_id':'y','topic_mode':'rumor'}).status_code==422

def test_edit_invalidation_regeneration_and_deletion(monkeypatch):
    from pathlib import Path
    from app.core.config import settings
    from app.models import Script, SEOData, Video, Thumbnail, VoiceGeneration, Asset
    with TestClient(app) as client:
        headers=login(client)
        channel=client.get('/api/channels',headers=headers).json()[0]
        persona=client.post('/api/personalities',headers=headers,json={'name':'Editable Story','channel_id':channel['id']}).json()
        monkeypatch.setattr('app.api.videos.run_job',lambda *args: None)
        result=client.post('/api/videos/generate',headers=headers,json={'channel_id':channel['id'],'personality_id':persona['id'],'topic_mode':'manual','manual_topic':'An educational test'})
        job_id=result.json()['id']
        with SessionLocal() as db:
            job=db.get(VideoJob,job_id)
            topic=research_topic(db,db.get(Personality,persona['id']),'manual','An educational test')
            job.topic_id=topic.id
            job.status='ready_for_review'
            script=Script(id=str(uuid4()),job_id=job_id,**{k:'Test '+k for k in ('hook','context','main_story','why_it_matters','ending','full_script')})
            db.add(script)
            db.flush()
            db.add(SEOData(id=str(uuid4()),script_id=script.id,title='Test title',description='Test context',cover_text='TEST STORY'))
            db.add(Video(id=str(uuid4()),job_id=job_id,output_path='test',thumbnail_path='test',duration=30))
            db.add(Thumbnail(id=str(uuid4()),job_id=job_id,local_path='test',headline='TEST STORY'))
            db.add(VoiceGeneration(id=str(uuid4()),job_id=job_id,provider='test',voice='en-US',output_path='test'))
            db.add(Asset(id=str(uuid4()),job_id=job_id,source='local',license='original',attribution='test',local_path='test'))
            db.commit()
        edited=client.patch(f'/api/videos/{job_id}/script',headers=headers,json={k:'Edited '+k for k in ('hook','context','main_story','why_it_matters','ending')})
        assert edited.status_code==200
        assert edited.json()['current_step']=='script_edited'
        assert client.post(f'/api/videos/{job_id}/approve',headers=headers).status_code==409
        regenerated=client.post(f'/api/videos/{job_id}/regenerate',headers=headers,json={'scope':'voice'})
        assert regenerated.status_code==200
        assert regenerated.json()['retry_count']==1
        assert client.delete(f'/api/videos/{job_id}',headers=headers).status_code==409
        with SessionLocal() as db:
            db.get(VideoJob,job_id).status='failed'
            db.commit()
        assert client.delete(f'/api/videos/{job_id}',headers=headers).status_code==200
        assert client.get(f'/api/videos/{job_id}',headers=headers).status_code==404


def test_signed_media_and_path_restrictions(publishable):
    from pathlib import Path
    from app.api.media import media_link
    from app.core.config import settings
    with TestClient(app) as client:
        root=Path(settings.generated_dir)
        (root/'thumbnails').mkdir(exist_ok=True,parents=True)
        (root/'thumbnails'/'test.png').write_bytes(b'test-image')
        assert client.get(media_link('thumbnails/test.png')).status_code==401
        key=publishable['job_id']
        (root/'thumbnails'/f'{key}.png').write_bytes(b'test-image')
        assert client.get(media_link(f'thumbnails/{key}.png'),headers=publishable['owner']).status_code==200
        assert client.get('/generated/thumbnails/test.png?expires=1&signature=invalid').status_code==403
        assert client.get(media_link('../.env')).status_code==404


@pytest.fixture
def publishable(owner_publishable):
    # Channel access is per-member, so owner-driven flows use a channel owned by the OWNER membership.
    return owner_publishable
