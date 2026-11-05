from concurrent.futures import ThreadPoolExecutor
import json
import math
import struct
import subprocess
import wave
from pathlib import Path
from unittest.mock import Mock
import pytest
from fastapi.testclient import TestClient
from app.core.config import settings
from app.database.session import SessionLocal
from app.models import VideoJob,Personality,Workspace


def test_subtitle_parents_are_independent(tmp_path):
    from app.video.subtitles import write_subtitles
    ass=tmp_path/'one'/'nested'/'captions.ass';srt=tmp_path/'two'/'nested'/'captions.srt'
    write_subtitles('An original offline test.',3,ass,srt)
    assert ass.is_file() and srt.is_file()


def test_real_render_into_empty_root(tmp_path):
    from PIL import Image
    from app.video.renderer import render_video
    root=tmp_path/'empty-output';root.mkdir();assert not list(root.iterdir())
    inputs=tmp_path/'inputs';inputs.mkdir()
    slides=[]
    for i in range(6):
        path=inputs/f'{i}.png';Image.new('RGB',(1080,1920),(35+i*10,45,100)).save(path);slides.append(path)
    audio=inputs/'original-test-tone.wav'
    with wave.open(str(audio),'wb') as wav:
        wav.setnchannels(1);wav.setsampwidth(2);wav.setframerate(22050)
        wav.writeframes(b''.join(struct.pack('<h',int(500*math.sin(2*math.pi*220*i/22050)))for i in range(22050*3)))
    output,cover,_=render_video('empty-root-test','Offline test','Test theme',
        'This original offline fixture checks clean output directories and readable subtitles.',audio,30,root,slides,'OFFLINE TEST')
    assert output.is_file() and cover.is_file()
    assert (root/'subtitles'/'empty-root-test.srt').is_file()
    assert (root/'videos'/'empty-root-test'/'captions.ass').is_file()
    result=subprocess.run([settings.ffprobe_path,'-v','error','-show_streams','-show_format','-of','json',str(output)],capture_output=True,text=True,check=True)
    data=json.loads(result.stdout);video=next(s for s in data['streams']if s['codec_type']=='video')
    assert (video['width'],video['height'],video['codec_name'])==(1080,1920,'h264')
    assert any(s['codec_name']=='aac'for s in data['streams'])
    assert abs(float(data['format']['duration'])-3.12)<.1


def test_attachment_keeps_authorization_and_ranges(publishable):
    p=publishable;c=p['client'];url=c.get('/api/videos/'+p['job_id'],headers=p['owner']).json()['video_url']+'&download=true'
    response=c.get(url,headers=p['owner'])
    assert response.status_code==200
    assert response.headers['content-disposition'].startswith('attachment;')
    assert 'ai-shorts-'+p['job_id']+'.mp4' in response.headers['content-disposition']
    partial=c.get(url,headers={**p['owner'],'Range':'bytes=0-3'})
    assert partial.status_code==206 and partial.content==response.content[:4]
    c.cookies.clear();assert c.get(url).status_code==401
    other=c.post('/api/auth/register',json={'name':'Other owner','email':p['job_id']+'@example.com','password':'Audit-test-password123!'}).json()
    assert c.get(url,headers={'Authorization':'Bearer '+other['access_token']}).status_code==404
    assert c.get(url.replace('signature=','signature=bad'),headers=p['owner']).status_code==403


def test_demo_picker_and_worker_never_use_network(publishable,monkeypatch):
    p=publishable;monkeypatch.setattr(settings,'research_provider','demo');monkeypatch.setattr(settings,'gemini_api_key','')
    def forbidden(*args,**kwargs):raise AssertionError('Network forbidden in demo mode')
    monkeypatch.setattr('socket.create_connection',forbidden)
    monkeypatch.setattr('app.api.research.research_live',forbidden)
    monkeypatch.setattr('app.services.pipeline.research_live',forbidden)
    monkeypatch.setattr('app.api.videos.run_job',lambda *args:None)
    with SessionLocal() as db:persona=db.get(VideoJob,p['job_id']).personality_id
    rows=p['client'].post('/api/research/candidates',headers=p['owner'],json={'channel_id':p['channel_id'],'personality_id':persona}).json()
    assert rows and all(row['status']=='demo' and row['provider']=='demo'for row in rows)
    created=p['client'].post('/api/videos/generate',headers=p['owner'],json={'channel_id':p['channel_id'],'personality_id':persona,'candidate_id':rows[0]['id']})
    assert created.status_code==201 and created.json()['verification_status']=='demo'
    # Run the actual worker up to the script boundary without calling a renderer/TTS.
    generator=Mock(side_effect=RuntimeError('Reached offline script stage'))
    monkeypatch.setattr('app.services.pipeline.generate_script',generator)
    from app.services.pipeline import run_job
    run_job(created.json()['id'])
    assert generator.call_count==1
    automatic=p['client'].post('/api/videos/generate',headers=p['owner'],json={'channel_id':p['channel_id'],'personality_id':persona})
    assert automatic.status_code==201
    run_job(automatic.json()['id'])
    assert generator.call_count==2
    detail=p['client'].get('/api/videos/'+automatic.json()['id'],headers=p['owner']).json()
    assert detail['verification_status']=='demo' and 'demo research' in detail['sources'][0]['name']
    monkeypatch.setattr(settings,'research_provider','rss')
    result=p['client'].post('/api/videos/generate',headers=p['owner'],json={'channel_id':p['channel_id'],'personality_id':persona,'candidate_id':rows[1]['id']})
    assert result.status_code==409  # demo candidate cannot enter the live pipeline


def test_live_picker_failure_is_actionable(publishable,monkeypatch):
    p=publishable;monkeypatch.setattr(settings,'research_provider','rss')
    monkeypatch.setattr('app.api.research.research_live',Mock(side_effect=ValueError('RSS feed unavailable. Retry research or check configured feeds.')))
    with SessionLocal() as db:persona=db.get(VideoJob,p['job_id']).personality_id
    response=p['client'].post('/api/research/candidates',headers=p['owner'],json={'channel_id':p['channel_id'],'personality_id':persona})
    assert response.status_code==422 and 'Retry research' in response.json()['detail']


def test_scoped_personality_duplicates_concurrent(owner_publishable):
    from app.main import app
    p=owner_publishable;body={'name':'  Lionel   MESSI  ','channel_id':p['channel_id']}
    def send(_):
        c=TestClient(app)
        try:return c.post('/api/personalities',headers=p['owner'],json=body)
        finally:c.close()
    with ThreadPoolExecutor(max_workers=5) as pool:responses=list(pool.map(send,range(5)))
    assert sorted(r.status_code for r in responses)==[200,200,200,200,201]
    key=responses[0].json()['id'];assert {r.json()['id']for r in responses}=={key}
    c=p['client'];equivalent=c.post('/api/personalities',headers=p['owner'],json={**body,'name':'lionel messi'})
    assert equivalent.status_code==200 and equivalent.json()['id']==key and equivalent.json()['reused']
    unicode_equivalent=c.post('/api/personalities',headers=p['owner'],json={**body,'name':'Ｌｉｏｎｅｌ Ｍｅｓｓｉ'})
    assert unicode_equivalent.json()['id']==key
    from app.core.security import new_id
    with SessionLocal() as db:
        original=db.get(Personality,key)
        historical=Personality(id=new_id(),workspace_id=original.workspace_id,creator_member_id=original.creator_member_id,
            name='LIONEL MESSI',channel_id=original.channel_id,visibility='workspace',category='Historical')
        db.add(historical);db.flush();historical_id=historical.id
        linked=VideoJob(id=new_id(),workspace_id=original.workspace_id,channel_id=original.channel_id,
            personality_id=historical_id,status='failed');db.add(linked);db.commit();linked_id=linked.id
    assert c.post('/api/personalities',headers=p['owner'],json=body).json()['id']==key
    with SessionLocal() as db:
        assert db.get(Personality,historical_id) is not None
        assert db.get(VideoJob,linked_id).personality_id==historical_id
        db.get(Personality,key).enabled=False;db.commit()
    assert c.post('/api/personalities',headers=p['owner'],json=body).json()['id']==historical_id
    editor_body={'name':'Lionel Messi'}
    private=c.post('/api/personalities',headers=p['editor'],json=editor_body)
    assert private.status_code==201 and private.json()['id']!=key
    owner_private=c.post('/api/personalities',headers=p['owner'],json={**body,'name':'Lionel Messi','visibility':'personal'})
    assert owner_private.status_code==201 and owner_private.json()['id']!=private.json()['id']
    assert c.get('/api/personalities/'+owner_private.json()['id'],headers=p['editor']).status_code==404
    assert c.post('/api/personalities',headers=p['editor'],json={'name':'LIONEL MESSI'}).json()['id']==private.json()['id']
    channel=c.post('/api/channels',headers=p['owner'],json={'name':'Different scope'}).json()['id']
    assert c.post('/api/personalities',headers=p['owner'],json={**body,'channel_id':channel}).status_code==201


def test_workspace_identity_is_persisted_and_scoped(publishable):
    p=publishable
    with SessionLocal() as db:
        workspace=db.get(Workspace,db.get(VideoJob,p['job_id']).workspace_id);workspace.name='Local acceptance studio';db.commit()
    for role in ('owner','editor'):
        assert p['client'].get('/api/settings',headers=p[role]).json()['workspace']['name']=='Local acceptance studio'


@pytest.fixture
def publishable(owner_publishable):
    # Channel access is per-member, so owner-driven flows use a channel owned by the OWNER membership.
    return owner_publishable
