import json
import hashlib
import wave
from pathlib import Path
from unittest.mock import Mock
import pytest

from app.database.session import SessionLocal
from app.models import VideoJob


def test_legacy_illustration_is_never_reported_as_a_photo(tmp_path):
    from types import SimpleNamespace
    from app.services.pipeline import serialize_asset
    asset = SimpleNamespace(id='asset',job_id='job',scene_number=1,source='Original local illustration',
        local_path=str(tmp_path/'card.png'),provenance='{}',url='',creator='',license='Original',attribution='')
    assert serialize_asset(asset)['media_type'] == 'card'
    asset.source='commons'
    asset.provenance=json.dumps({'kind':'archive','label':'Archive photo'})
    assert serialize_asset(asset)['media_type'] == 'photo'


def test_explicit_test_label_is_reversible_and_preserves_output(publishable):
    p = publishable
    client, headers = p['client'], p['owner']
    url = f"/api/videos/{p['job_id']}"
    before = client.get(url, headers=headers).json()
    for value in (True, False):
        result = client.patch(url+'/classification', headers=headers, json={'is_test': value})
        assert result.status_code == 200
        data = result.json()
        assert data['research_trace']['operator_is_test'] is value
        assert data['content_revision'] == before['content_revision']
        assert data['status'] == before['status']
    assert client.patch(url+'/classification', headers=headers, json={'is_test': 'false'}).status_code == 422


def test_dashboard_processing_uses_current_accessible_jobs(publishable):
    p = publishable
    with SessionLocal() as db:
        job = db.get(VideoJob, p['job_id'])
        job.status = 'rendering'
        db.commit()
    response = p['client'].get('/api/dashboard', headers=p['owner'])
    assert response.status_code == 200
    assert response.json()['processing'] >= 1


@pytest.mark.parametrize('failed_step', ['collecting_assets', 'creating_cover'])
def test_saved_media_retry_reaches_ready_without_rebuying_script_or_voice(publishable, monkeypatch, failed_step):
    from app.core.config import settings
    p = publishable
    from app.services.assets.providers import SafeAsset
    from PIL import Image
    def fixture_media(scenes,*args,**kwargs):
        folder=Path(args[3]);folder.mkdir(parents=True,exist_ok=True)
        photo=folder/'offline-fixture.jpg';Image.new('RGB',(500,800),'green').save(photo)
        return [SafeAsset(photo,'Offline media fixture','Own photograph','Test fixture',scene_number=scene.scene_number,provenance={'kind':'archive'}) for scene in scenes]
    monkeypatch.setattr('app.services.pipeline.collect_scene_assets',fixture_media)
    script_provider = Mock(side_effect=AssertionError('Unchanged script must be reused'))
    voice_provider = Mock(side_effect=AssertionError('Unchanged narration must be reused'))
    monkeypatch.setattr('app.services.pipeline.generate_script', script_provider)
    monkeypatch.setattr('app.services.pipeline.generate_narration', voice_provider)
    with SessionLocal() as db:
        job = db.get(VideoJob, p['job_id'])
        job.topic.verification_status = 'demo'
        job.status, job.failed_step = 'failed', failed_step
        saved_script = job.script.full_script
        audio = Path(settings.generated_dir)/'audio'/f'{job.id}.wav'
        audio.parent.mkdir(parents=True, exist_ok=True)
        with wave.open(str(audio), 'wb') as wav:
            wav.setparams((1, 2, 22050, 0, 'NONE', 'not compressed'))
            wav.writeframes(b'\0\0'*22050)
        job.voice_generation.output_path = str(audio)
        job.voice_generation.script_hash = hashlib.sha256(saved_script.encode()).hexdigest()
        video = Path(job.video.output_path)
        before_audio = audio.read_bytes()
        db.commit()
    monkeypatch.setattr('app.services.pipeline.render_video', lambda *a, **kw: (video, video.with_suffix('.png'), None))
    response = p['client'].post(f"/api/videos/{p['job_id']}/regenerate", headers=p['owner'], json={'scope':'retry'})
    assert response.status_code == 200
    final = p['client'].get(f"/api/videos/{p['job_id']}", headers=p['owner']).json()
    assert final['status'] == 'ready_for_review', final.get('error_message')
    assert final['script']['full_script'] == saved_script
    assert audio.read_bytes() == before_audio
    script_provider.assert_not_called()
    voice_provider.assert_not_called()


@pytest.fixture
def publishable(owner_publishable):
    # Channel access is per-member, so owner-driven flows use a channel owned by the OWNER membership.
    return owner_publishable
