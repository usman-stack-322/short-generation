import json
from pathlib import Path
from unittest.mock import Mock
import pytest
from fastapi import HTTPException
from app.core.config import settings
from app.core.languages import LANGUAGES,language_info,language_instruction
from app.ai.scripts import generate_script,generate_seo
from app.tts.capabilities import Narrator,NarrationUnavailable,resolve_narrator


@pytest.mark.parametrize('code',list(LANGUAGES))
def test_language_catalog_and_development_output(code):
    info=language_info(code)
    script,provider=generate_script('Career','Cristiano Ronaldo','Professional',30,code)
    seo=generate_seo('Career','Cristiano Ronaldo',script,code)
    assert all(script[key] for key in ('hook','context','main_story','why_it_matters','ending','full_script'))
    assert seo['cover_text'] and info.name in language_instruction(code)
    if code=='ur-PK': assert 'یہ' in script['context'] and 'خبر' in seo['cover_text']
    if code=='zh-CN': assert '这是' in script['context'] and '新闻' in seo['cover_text']
    if code=='it-IT': assert 'Questo' in script['context']
    if code=='es-ES': assert 'Este' in script['context']


def test_unsupported_language_is_400(publishable,monkeypatch):
    p=publishable
    response=p['client'].post('/api/videos/generate',headers=p['owner'],json={
        'channel_id':p['channel_id'],'personality_id':'ignored','language':'xx-XX'})
    assert response.status_code==400 and 'Unsupported language' in response.json()['detail']


def test_default_and_override_are_snapshotted(publishable,monkeypatch):
    from app.database.session import SessionLocal
    from app.models import VideoJob,Channel
    p=publishable
    monkeypatch.setattr('app.api.videos.run_job',lambda *args:None)
    with SessionLocal() as db:
        old=db.get(VideoJob,p['job_id']);personality=old.personality_id
        channel=db.get(Channel,p['channel_id']);channel.default_language='ur-PK';db.commit()
    base={'channel_id':p['channel_id'],'personality_id':personality,'topic_mode':'manual','manual_topic':'Career'}
    first=p['client'].post('/api/videos/generate',headers=p['owner'],json=base).json()
    assert (first['language_code'],first['language_name'],first['locale'])==('ur-PK','Urdu','ur-PK')
    assert first['voice']=='ur-PK'
    second=p['client'].post('/api/videos/generate',headers=p['owner'],json={**base,'language':'it-IT'}).json()
    assert second['language_code']=='it-IT'
    with SessionLocal() as db:
        db.get(Channel,p['channel_id']).default_language='en-US';db.commit()
    assert p['client'].get('/videos/'+first['id'],headers=p['owner']).status_code==404  # no unprefixed route
    assert p['client'].get('/api/videos/'+first['id'],headers=p['owner']).json()['language_code']=='ur-PK'


def test_language_change_invalidates_all_artifacts(publishable,monkeypatch):
    from app.database.session import SessionLocal
    from app.models import VideoJob,Approval
    p=publishable
    monkeypatch.setattr('app.api.videos.run_job',lambda *args:None)
    response=p['client'].post(f'/api/videos/{p["job_id"]}/regenerate',headers=p['owner'],json={'scope':'voice','language':'zh-CN'})
    assert response.status_code==200
    job=response.json()
    assert job['language_code']=='zh-CN' and job['language_name']=='Chinese'
    assert job['script'] is None and job['seo'] is None and job['video_url'] is None
    assert job['voice_direction'] is None and not job['scenes'] and not job['assets']
    with SessionLocal() as db:
        saved=db.get(VideoJob,p['job_id'])
        assert saved.voice_generation is None and saved.video is None
        assert not db.query(Approval).filter_by(job_id=saved.id).count()


def test_local_language_compatibility(monkeypatch):
    monkeypatch.setattr('app.tts.capabilities.local_voices',lambda:[{'id':'english-id','name':'English narrator','languages':['en-US']}])
    assert resolve_narrator('local','en-US').voice=='English narrator'
    with pytest.raises(NarrationUnavailable,match='Urdu'):resolve_narrator('local','ur-PK')
    with pytest.raises(NarrationUnavailable):resolve_narrator('local','en-US','es-ES')


def test_auto_provider_selects_compatible_cloud(monkeypatch,tmp_path):
    from app.tts.providers import generate_narration
    monkeypatch.setattr('app.tts.providers.configured',lambda name: name!='elevenlabs')
    def resolve(name,language,voice):
        if name=='local': raise NarrationUnavailable('Urdu not installed')
        return Narrator('google','ur-IN-Standard-A','ur-IN')
    monkeypatch.setattr('app.tts.providers.resolve_narrator',resolve)
    synth=Mock(return_value='Google TTS narrator')
    monkeypatch.setattr('app.tts.providers.GoogleTTSProvider.generate_voice',synth)
    metadata={}
    assert generate_narration('اردو','ur-PK',tmp_path/'voice.wav','auto',language='ur-PK',metadata=metadata)=='Google TTS narrator'
    assert metadata['locale']=='ur-IN' and metadata['provider']=='google'
    assert synth.call_args.args[1]=='ur-IN-Standard-A'


def test_unavailable_language_cannot_become_silence(monkeypatch,tmp_path):
    from app.tts.providers import generate_narration
    monkeypatch.setattr('app.tts.providers.configured',lambda name:name=='local')
    monkeypatch.setattr('app.tts.providers.resolve_narrator',Mock(side_effect=NarrationUnavailable('Unsupported')))
    with pytest.raises(NarrationUnavailable,match='Urdu'):
        generate_narration('اردو','ur-PK',tmp_path/'voice.wav','auto',language='ur-PK')
    assert not (tmp_path/'voice.wav').exists()


def test_google_uses_metadata_locales(monkeypatch):
    monkeypatch.setattr(settings,'google_tts_api_key','fake-key')
    voice={'name':'cmn-CN-Standard-A','languageCodes':['cmn-CN']}
    monkeypatch.setattr('app.tts.capabilities.httpx.get',Mock(return_value=Mock(json=lambda:{'voices':[voice]})))
    result=resolve_narrator('google','zh-CN')
    assert result.locale=='cmn-CN'
    with pytest.raises(NarrationUnavailable):resolve_narrator('google','ur-PK')


def test_gemini_script_and_seo_prompts_include_locale(monkeypatch):
    monkeypatch.setattr(settings,'gemini_api_key','fake-key')
    prompts=[]
    def generation(self,prompt):
        prompts.append(prompt)
        return {'hook':'Test'}
    monkeypatch.setattr('app.ai.scripts.GeminiProvider.generate',generation)
    generate_script('Career','Cristiano Ronaldo','Professional',30,'ur-PK',source_context='English source: 5 awards in 2016')
    assert 'Urdu (ur-PK)' in prompts[0] and '5 awards in 2016' in prompts[0]
    def execute(self,request,prompt):
        prompts.append(prompt)
        return {'title':'ٹیسٹ'}
    monkeypatch.setattr('app.ai.scripts.GeminiRetryPolicy.execute',execute)
    generate_seo('Career','Cristiano Ronaldo',{'full_script':'اصل متن'},'ur-PK')
    assert 'Urdu (ur-PK)' in prompts[1] and 'Preserve factual values' in prompts[1]


@pytest.mark.parametrize('code,text',[('ur-PK','یہ ایک مثال ہے۔'),('ar-SA','هذا مثال للنص العربي.'),('zh-CN','这是中文测试。保持原文字幕。'),('hi-IN','यह एक उदाहरण है।')])
def test_subtitles_use_final_text_and_language_font(tmp_path,code,text):
    from app.video.subtitles import write_subtitles
    ass,srt=tmp_path/'captions.ass',tmp_path/'captions.srt'
    write_subtitles(text,30,ass,srt,{'language':code})
    content=ass.read_text(encoding='utf-8')
    assert all(char in content for char in text if not char.isspace())
    if LANGUAGES[code].rtl: assert '\u202b' in content
    assert ' --> ' in srt.read_text(encoding='utf-8')


def test_missing_font_is_actionable(monkeypatch):
    from app.video.fonts import resolve_font
    monkeypatch.setattr(Path,'is_file',lambda path:False)
    with pytest.raises(RuntimeError,match='Missing Urdu-compatible font'):resolve_font('ur-PK','اردو')


def test_chinese_scenes_cover_text():
    from app.services.scene_planner import plan_scenes
    text='这是中文场景规划测试。每一个场景都应该保留原始事实和完整的旁白内容。'
    scenes=plan_scenes(text,30,'Cristiano Ronaldo',language='zh-CN')
    assert len(scenes)==6 and ''.join(s['narration'] for s in scenes)==text


def test_elevenlabs_model_language_capability(monkeypatch):
    monkeypatch.setattr(settings,'elevenlabs_api_key','fake-key')
    monkeypatch.setattr(settings,'elevenlabs_allowed_voice_ids','generic-narrator')
    monkeypatch.setattr(settings,'elevenlabs_voice_id','generic-narrator')
    metadata=[{'model_id':'eleven_multilingual_v2','can_do_text_to_speech':True,'languages':[{'language_id':'es'}]}]
    monkeypatch.setattr('app.tts.capabilities.httpx.get',Mock(return_value=Mock(json=lambda:metadata)))
    assert resolve_narrator('elevenlabs','es-ES').voice=='generic-narrator'
    with pytest.raises(NarrationUnavailable,match='Urdu'):resolve_narrator('elevenlabs','ur-PK')


def test_rtl_requires_real_shaping(monkeypatch):
    from app.video.fonts import resolve_font
    monkeypatch.setattr('app.video.fonts.features.check_feature',lambda *args:False)
    with pytest.raises(RuntimeError,match='libraqm'):resolve_font('ar-SA','العربية')


def test_catalog_api_is_shared(publishable):
    p=publishable
    response=p['client'].get('/api/languages',headers=p['owner'])
    assert response.status_code==200
    catalog={item['code']:item for item in response.json()}
    assert set(catalog)==set(LANGUAGES)
    assert catalog['ar-SA']['rtl'] and catalog['ur-PK']['rtl']
    assert not catalog['zh-CN']['rtl']


@pytest.fixture
def publishable(owner_publishable):
    # Channel access is per-member, so owner-driven flows use a channel owned by the OWNER membership.
    return owner_publishable
