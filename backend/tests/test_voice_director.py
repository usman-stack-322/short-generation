import json
from unittest.mock import Mock
import pytest
from pydantic import ValidationError
from app.tts.director import VoiceProfile, direct_voice, PRESETS
from app.tts.delivery import provider_controls, prepare_delivery, google_ssml


@pytest.mark.parametrize('topic,expected', [
    ('Cristiano Ronaldo tactical/career analysis', 'professional'),
    ('Breaking football news: club announcement', 'news'),
    ('Funny celebrity moment', 'funny'),
    ('Ronaldo major record achievement', 'sports_hype'),
    ('Emotional retirement/career retrospective', 'emotional'),
    ('How to understand football tactics: educational explanation', 'educational'),
    ('Business history', 'documentary'),
    ('Breaking news: serious injury', 'serious'),
])
def test_semantic_direction(topic, expected):
    profile = direct_voice(topic, {'hook': topic}, 'Cristiano Ronaldo', 'sports' if 'Business' not in topic else 'business', 'energetic')
    assert profile.style == expected
    assert profile.auto_selected


def test_manual_override_and_all_presets():
    for style in PRESETS:
        result = direct_voice('Funny story', {}, selection=style)
        assert result.style == style and not result.auto_selected


@pytest.mark.parametrize('field,value', [('pace', 4), ('energy', -1), ('pitch', 8), ('volume', 2),
                                       ('pause_strength', 2), ('emphasis_strength', -1), ('pace', float('nan'))])
def test_profile_validation(field, value):
    with pytest.raises(ValidationError):
        VoiceProfile(**{field: value})


def test_director_failure_is_neutral(monkeypatch):
    monkeypatch.setattr('app.tts.director.analyze', Mock(side_effect=RuntimeError('analysis failed')))
    profile = direct_voice('Story', {})
    assert (profile.style, profile.pace, profile.energy) == ('professional', 1, .5)


def test_scene_hints_and_script_priority():
    assert direct_voice('Story', {}, scenes=[{'caption':'Educational explanation'}]).style == 'educational'
    assert direct_voice('Tactical analysis', {'hook':'Detailed breakdown'}, tone='sports hype',
                        scenes=[{'caption':'Funny'}]).style == 'professional'


def test_provider_allowlists():
    profile = direct_voice('Ronaldo record achievement', {})
    local = provider_controls('local', profile)
    assert set(local) == {'rate','volume','speed'}
    google = provider_controls('google', profile, voice_name='en-US-Neural2-D')
    assert set(google) == {'speakingRate','pitch','volumeGainDb'}
    assert provider_controls('google', profile, voice_name='en-US-Chirp3-HD-Test') == {}
    eleven = provider_controls('elevenlabs', profile, speed=1.4)
    assert set(eleven) == {'stability','similarity_boost','style','speed'}
    assert eleven['speed'] == 1.2
    with pytest.raises(ValueError): provider_controls('unknown', profile)


def test_delivery_preserves_facts_and_escapes_markup():
    import xml.etree.ElementTree as ET
    text = 'Ronaldo set a record. A & B explain why. Here is the ending.'
    profile = direct_voice('Ronaldo record achievement', {})
    segments = prepare_delivery(text, profile, [{'emphasis_word':'record'}])
    assert ''.join(s['text'] for s in segments) == text
    xml = google_ssml(segments, profile)
    assert ''.join(ET.fromstring(xml).itertext()) == text
    assert '<emphasis' in xml and '&amp;' in xml
    assert [s['role'] for s in segments] == ['hook','context','ending']


def test_local_parameters_reach_worker(monkeypatch, tmp_path):
    import wave
    from app.tts.providers import LocalTTSProvider
    path = tmp_path/'voice.wav'
    def synth(command, **kwargs):
        assert float(command[-1]) == .8
        assert float(command[-2]) == .92
        assert kwargs['input'] == 'Original narration.'
        with wave.open(str(path),'wb') as audio:
            audio.setnchannels(1); audio.setsampwidth(2); audio.setframerate(22050)
            audio.writeframes(b'\x10\x01'*200)
    monkeypatch.setattr('app.tts.providers.subprocess.run', synth)
    monkeypatch.setattr('app.video.alignment.load_boundaries',lambda *a:{'fixture':True})
    profile = VoiceProfile(style='emotional', pace=.92, volume=.8)
    assert LocalTTSProvider().generate_voice('Original narration.', 'en-US', path, profile=profile).startswith('Local')


def test_cloud_failure_keeps_profile_for_local(monkeypatch, tmp_path):
    from app.tts.providers import generate_narration
    profile = VoiceProfile(style='educational')
    monkeypatch.setattr('app.tts.providers.GoogleTTSProvider.generate_voice', Mock(side_effect=RuntimeError('offline')))
    local = Mock(return_value='Local narrator')
    monkeypatch.setattr('app.tts.providers.LocalTTSProvider.generate_voice', local)
    assert 'local selected' in generate_narration('Text','en-US',tmp_path/'x.wav','google',1,profile)
    assert local.call_args.args[4] == profile


def test_voice_override_api_and_permissions(publishable, monkeypatch):
    from app.database.session import SessionLocal
    from app.models import VideoJob
    p = publishable
    monkeypatch.setattr('app.api.videos.run_job', lambda *args: None)
    route = f'/api/videos/{p["job_id"]}/regenerate'
    assert p['client'].post(route,headers=p['owner'],json={'scope':'voice','voice_style':'invalid'}).status_code == 422
    assert p['client'].post(route,json={'scope':'voice','voice_style':'funny'}).status_code == 401
    result = p['client'].post(route,headers=p['owner'],json={'scope':'voice','voice_style':'emotional'})
    assert result.status_code == 200 and result.json()['voice_style'] == 'emotional'
    with SessionLocal() as db:
        assert db.get(VideoJob,p['job_id']).voice_style == 'emotional'


def test_channel_defaults_inherited(publishable, monkeypatch):
    from app.database.session import SessionLocal
    from app.models import VideoJob
    p = publishable
    monkeypatch.setattr('app.api.videos.run_job', lambda *args: None)
    with SessionLocal() as db:
        existing = db.get(VideoJob,p['job_id'])
        personality_id = existing.personality_id
    response = p['client'].patch(f'/api/channels/{p["channel_id"]}',headers=p['owner'],json={
        'default_voice':'en-GB', 'tts_provider':'google', 'voice_style':'documentary'})
    assert response.status_code == 200
    result = p['client'].post('/api/videos/generate',headers=p['owner'],json={
        'channel_id':p['channel_id'],'personality_id':personality_id,
        'topic_mode':'manual','manual_topic':'Historical career analysis'})
    assert result.status_code == 201
    assert result.json()['voice'] == 'en-GB'
    assert result.json()['voice_style'] == 'documentary'


def test_google_unsupported_voice_omits_ssml_and_prosody(monkeypatch, tmp_path):
    import base64
    from app.core.config import settings
    from app.tts.providers import GoogleTTSProvider
    monkeypatch.setattr(settings,'google_tts_api_key','fake-key')
    post = Mock(return_value=Mock(json=lambda: {'audioContent':base64.b64encode(b'test audio').decode()}))
    monkeypatch.setattr('app.tts.providers.httpx.post',post)
    GoogleTTSProvider().generate_voice('Original words.', 'en-US-Chirp3-HD-Test', tmp_path/'x.wav', profile=VoiceProfile())
    payload = post.call_args.kwargs['json']
    assert payload['input'] == {'text':'Original words.'}
    assert payload['audioConfig'] == {'audioEncoding':'LINEAR16'}


def test_elevenlabs_request_uses_v2_allowlist_controls(monkeypatch, tmp_path):
    from app.core.config import settings
    from app.tts.providers import ElevenLabsProvider
    monkeypatch.setattr(settings,'elevenlabs_api_key','fake-key')
    monkeypatch.setattr(settings,'elevenlabs_allowed_voice_ids',' generic-narrator ')
    monkeypatch.setattr(settings,'elevenlabs_voice_id','')
    post = Mock(return_value=Mock(json=lambda:{'audio_base64':'bXAzIGF1ZGlv','alignment':{}}))
    monkeypatch.setattr('app.tts.providers.httpx.post',post)
    monkeypatch.setattr('app.tts.providers.subprocess.run',Mock())
    monkeypatch.setattr('app.video.alignment.write_character_boundaries',Mock())
    ElevenLabsProvider().generate_voice('Original text.', 'generic-narrator', tmp_path/'x.wav',profile=VoiceProfile())
    payload = post.call_args.kwargs['json']
    assert payload['model_id'] == 'eleven_multilingual_v2'
    assert payload['text'] == 'Original text.'
    assert set(payload['voice_settings']) == {'speed','stability','similarity_boost','style','use_speaker_boost'}


def test_pipeline_persists_direction_and_delivery(publishable, monkeypatch):
    from pathlib import Path
    from app.database.session import SessionLocal
    from app.models import VideoJob, Channel, Personality
    from app.services.pipeline import run_pipeline
    from app.services.assets.providers import SafeAsset
    from PIL import Image
    def fixture_media(scenes,*args,**kwargs):
        folder=Path(args[3]);folder.mkdir(parents=True,exist_ok=True)
        photo=folder/'offline-fixture.jpg';Image.new('RGB',(500,800),'green').save(photo)
        return [SafeAsset(photo,'Offline media fixture','Own photograph','Test fixture',scene_number=scene.scene_number,provenance={'kind':'archive'}) for scene in scenes]
    monkeypatch.setattr('app.services.pipeline.collect_scene_assets',fixture_media)
    def narrate(text, voice, path, provider, speed, profile, segments, **kwargs):
        assert profile.style == 'sports_hype'
        assert ''.join(s['text'] for s in segments) == text
        path.parent.mkdir(parents=True,exist_ok=True)
        path.write_bytes(b'test narration')
        return 'Local narrator (pyttsx3)'
    monkeypatch.setattr('app.services.pipeline.generate_narration', narrate)
    def render(*args, **kwargs):
        output = Path(args[6])/'videos'/args[0]/'short.mp4'
        output.parent.mkdir(parents=True,exist_ok=True)
        output.write_bytes(b'test render')
        return output, output.with_suffix('.png'), args[7]
    monkeypatch.setattr('app.services.pipeline.render_video',render)
    with SessionLocal() as db:
        job = db.get(VideoJob,publishable['job_id'])
        job.status=job.current_step='researching'
        job.topic_title='Ronaldo major record achievement'
        result = run_pipeline(db,job,db.get(Personality,job.personality_id),db.get(Channel,job.channel_id),'voice')
        assert result['status'] == 'ready_for_review'
        assert result['voice_direction']['style'] == 'sports_hype'
        assert result['voice_delivery']['provider'] == 'local'
        assert result['voice_direction']['auto_selected']
        assert result['voice_delivery']['controls']['speed'] == 1.08


@pytest.fixture
def publishable(owner_publishable):
    # Channel access is per-member, so owner-driven flows use a channel owned by the OWNER membership.
    return owner_publishable
