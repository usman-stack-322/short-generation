import os
import atexit
import shutil
import tempfile
from pathlib import Path
from uuid import uuid4

_test_root = Path(tempfile.gettempdir()) / f"ai-shorts-tests-{uuid4()}"
_test_root.mkdir()
atexit.register(lambda: shutil.rmtree(_test_root, ignore_errors=True))
os.environ["DATABASE_URL"] = f"sqlite:///{(_test_root / 'tests.db').as_posix()}"
os.environ["GENERATED_DIR"] = str(_test_root / "generated")
os.environ['SCHEDULER_ENABLED']='false'
os.environ['SEED_DEMO']='true'
os.environ['YOUTUBE_UPLOADS_ENABLED']='false'
os.environ['ASSET_PROVIDER']='demo'
os.environ['RESEARCH_PROVIDER']='demo'
os.environ['GEMINI_API_KEY']=''
os.environ['ELEVENLABS_API_KEY']=''
os.environ['GOOGLE_TTS_API_KEY']=''
os.environ['GOOGLE_APPLICATION_CREDENTIALS']=''

import pytest


def pytest_configure(config):
    if not getattr(config.option, 'basetemp', None):
        bt = _test_root / "pytest_tmp"
        bt.mkdir(parents=True, exist_ok=True)
        config.option.basetemp = str(bt)


@pytest.fixture
def publishable():
    yield from _build_publishable('editor')


@pytest.fixture
def owner_publishable():
    """Same data as `publishable`, but the channel belongs to the OWNER membership.

    Channel access is strictly per-member, so tests that act as the workspace owner on the
    fixture channel must use this fixture; 'editor' is then a non-owning member."""
    yield from _build_publishable('owner')


def _build_publishable(channel_user):
    from fastapi.testclient import TestClient
    from app.main import app
    from app.database.session import SessionLocal
    from app.models import (Channel, Personality, Topic, VideoJob, Script, SEOData, VoiceGeneration,
                            Video, ChannelAuthorization, WorkspaceMember, User)
    from app.core.config import settings
    from app.core.security import new_id
    with TestClient(app) as client:
        def login(email,password):
            result=client.post('/api/auth/login',json={'email':email,'password':password})
            assert result.status_code==200
            return {'Authorization':'Bearer '+result.json()['access_token']}
        owner=login('owner@example.com','DemoOwner123!')
        editor=login('editor@example.com','DemoEditor123!')
        with SessionLocal() as db:
            member=db.query(WorkspaceMember).join(User).filter(User.email==f'{channel_user}@example.com').one()
            channel=Channel(id=new_id(),workspace_id=member.workspace_id,member_id=member.id,name='Upload test',
                            youtube_channel_id='test-channel',status='connected',approval_policy='owner_only')
            db.add(channel);db.flush()
            persona=Personality(id=new_id(),workspace_id=member.workspace_id,channel_id=channel.id,name='Test Theme',category='Test')
            db.add(persona);db.flush()
            topic=Topic(id=new_id(),personality_id=persona.id,channel_id=channel.id,title='Verified test source',verification_status='verified')
            db.add(topic);db.flush()
            job=VideoJob(id=new_id(),workspace_id=member.workspace_id,channel_id=channel.id,personality_id=persona.id,
                         topic_id=topic.id,status='ready_for_review',current_step='ready_for_review',duration=30)
            db.add(job);db.flush()
            script=Script(id=new_id(),job_id=job.id,**{key:'Original test narration' for key in ('hook','context','main_story','why_it_matters','ending','full_script')})
            db.add(script);db.flush()
            db.add(SEOData(id=new_id(),script_id=script.id,title='Original test title',description='Source-grounded test description.',
                           hashtags='["#Shorts","#Stories","#Test"]',keywords='["test"]',cover_text='TEST STORY'))
            root=Path(settings.generated_dir).resolve()
            path=root/'videos'/job.id/'short.mp4'
            path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(b'unit-test-upload-payload')
            db.add(Video(id=new_id(),job_id=job.id,output_path=str(path),thumbnail_path='test.png',duration=30))
            db.add(VoiceGeneration(id=new_id(),job_id=job.id,provider='Local narrator',voice='en-US',output_path='test.wav'))
            db.add(ChannelAuthorization(id=new_id(),channel_id=channel.id,authorized_member_id=member.id,encrypted_tokens='test-encrypted-placeholder'))
            db.commit()
            try:
                yield {'client':client,'owner':owner,'editor':editor,'job_id':job.id,'channel_id':channel.id,'member_id':member.id}
            finally:
                with SessionLocal() as clean_db:
                    ch = clean_db.get(Channel, channel.id)
                    if ch and ch.automatic_generation_enabled:
                        ch.automatic_generation_enabled = False
                        clean_db.commit()


