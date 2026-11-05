import json
from pathlib import Path
from unittest.mock import Mock
import pytest
from app.core.config import settings, Settings, BACKEND_DIR


def test_env_path_independent_of_cwd(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    assert Path(Settings.model_config['env_file']) == BACKEND_DIR/'.env'
    config=Settings(database_url='sqlite:///./ai_shorts.db',generated_dir='../generated')
    assert config.generated_dir == BACKEND_DIR.parent/'generated'
    assert config.database_url == 'sqlite:///' + (BACKEND_DIR/'ai_shorts.db').as_posix()


def test_running_provider_status_hides_secrets(publishable, monkeypatch):
    monkeypatch.setattr(settings,'gemini_api_key','secret-not-for-ui')
    monkeypatch.setattr(settings,'gemini_fallback_model','fallback-model')
    monkeypatch.setattr(settings,'research_provider','rss')
    p=publishable
    result=p['client'].get('/api/settings',headers=p['owner']).json()
    assert result['providers']['gemini'] is True
    assert result['active_configuration']['gemini_configured'] is True
    assert result['active_configuration']['fallback_model_configured'] is True
    assert result['active_configuration']['research_provider']=='rss'
    assert result['preferences']['research_provider']=='rss'
    assert 'secret-not-for-ui' not in json.dumps(result)


def test_new_live_job_never_uses_demo_on_rss_failure(publishable,monkeypatch):
    from app.database.session import SessionLocal
    from app.models import VideoJob
    p=publishable
    with SessionLocal() as db:
        personality_id=db.get(VideoJob,p['job_id']).personality_id
    monkeypatch.setattr(settings,'research_provider','rss')
    live=Mock(side_effect=ValueError('RSS source unavailable: HTTP 503'))
    monkeypatch.setattr('app.services.pipeline.research_live',live)
    monkeypatch.setattr('app.services.pipeline.research_topic',Mock(side_effect=AssertionError('Demo forbidden')))
    response=p['client'].post('/api/videos/generate',headers=p['owner'],json={
        'channel_id':p['channel_id'],'personality_id':personality_id,'topic_mode':'current'})
    assert response.status_code==201
    job=p['client'].get('/api/videos/'+response.json()['id'],headers=p['owner']).json()
    assert live.call_count==1
    assert job['status']=='failed' and job['failed_step']=='researching' and job['retryable']
    assert job['error_message']=='RSS source unavailable: HTTP 503'
    assert job['sources']==[] and job['script'] is None


def test_interrupted_job_retains_script_and_resume_step(publishable, monkeypatch):
    from app.database.session import SessionLocal
    from app.models import VideoJob
    from app.services.recovery import recover_interrupted_jobs
    from app.services.pipeline import serialize_job
    p=publishable
    with SessionLocal() as db:
        job=db.get(VideoJob,p['job_id'])
        script_id=job.script.id
        job.status=job.current_step='voice_generation'
        db.commit()
        recover_interrupted_jobs(db)
        result=serialize_job(job,db)
        assert result['retryable'] and result['failed_step']=='voice_generation'
        assert result['current_step']=='interrupted'
        assert result['last_completed_step']=='collecting_assets'
        assert job.script.id==script_id and job.video is not None
        original=job.error_message
        recover_interrupted_jobs(db)
        assert job.error_message==original
    monkeypatch.setattr('app.api.videos.run_job',Mock())
    response=p['client'].post(f'/api/videos/{p["job_id"]}/regenerate',headers=p['owner'],json={'scope':'retry'})
    assert response.status_code==200
    assert response.json()['status']=='researching'


def test_retry_voice_reuses_research_and_script(publishable,monkeypatch):
    from app.database.session import SessionLocal
    from app.models import VideoJob,Channel,Personality
    from app.services.pipeline import run_pipeline
    p=publishable
    for name in ('research_live','research_topic','generate_script'):
        monkeypatch.setattr('app.services.pipeline.'+name,Mock(side_effect=AssertionError('Checkpoint must be reused')))
    monkeypatch.setattr('app.services.pipeline.collect_scene_assets',Mock(side_effect=RuntimeError('asset checkpoint check')))
    with SessionLocal() as db:
        job=db.get(VideoJob,p['job_id'])
        job.status='researching';job.failed_step='voice_generation'
        with pytest.raises(RuntimeError,match='asset checkpoint check'):
            run_pipeline(db,job,db.get(Personality,job.personality_id),db.get(Channel,job.channel_id),'retry')


def test_pending_live_sources_visible_without_claiming_verified(publishable):
    from app.database.session import SessionLocal
    from app.models import VideoJob,ResearchCandidate
    from app.core.security import new_id
    from app.services.pipeline import serialize_job
    p=publishable
    with SessionLocal() as db:
        job=db.get(VideoJob,p['job_id'])
        job.topic=None
        row={'title':'Current source headline','source_name':'BBC','source_url':'https://www.bbc.com/sport/test',
             'published_at':'2026-10-22T10:00:00+00:00','reliability_score':.93,'overall_score':.8}
        db.add(ResearchCandidate(id=new_id(),channel_id=job.channel_id,personality_id=job.personality_id,
                                title=row['title'],data=json.dumps(row),status='verification_required'))
        db.commit()
        job.status=job.current_step='verification_required';db.commit()
        result=serialize_job(job,db)
        assert result['verification_status']=='verification_required'
        assert result['sources'][0]['url']==row['source_url']
        assert result['sources'][0]['published_at']==row['published_at']
        assert result['sources'][0]['verification_required'] is True
        assert result['sources'][0]['name']=='BBC'
        assert result['topic']==row['title']
        assert job.topic is None


@pytest.fixture
def publishable(owner_publishable):
    # Channel access is per-member, so owner-driven flows use a channel owned by the OWNER membership.
    return owner_publishable
