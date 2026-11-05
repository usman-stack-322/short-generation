import io,json
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from PIL import Image
from app.database.session import SessionLocal
from app.models import VideoJob,Personality,LibraryMedia,MediaUsage,Asset,Scene,Channel
from app.services.media_library import collect_saved,commit_usage
from app.core.config import settings


def image(color='navy'):
    buf=io.BytesIO();Image.new('RGB',(800,600),color).save(buf,'JPEG');return buf.getvalue()


def collection(p):
    r=p['client'].post('/api/library/collections',headers=p['editor'],json={'name':'Private photos','channel_id':p['channel_id']})
    assert r.status_code==201,r.text
    return r.json()['id']


def upload(p,c,body=None,**data):
    with SessionLocal() as db:person=db.get(VideoJob,p['job_id']).personality_id
    fields={'name':'Rights-cleared fixture','personality_id':person,'creator':'Fixture author','license':'Own work','rights_confirmed':'true','identity_confirmed':'true',**data}
    return p['client'].post(f'/api/library/collections/{c}/media',headers=p['editor'],data=fields,files={'file':('unsafe-path.jpg',(body or image())+c.encode(),'image/jpeg')})


def approve(p,row):
    r=p['client'].patch(f"/api/library/media/{row['id']}",headers=p['editor'],json={'name':row['name'],'tags':['test'],'credit':'Fixture credit','approved':True})
    assert r.status_code==200,r.text


def test_upload_duplicate_preview_and_archival(publishable):
    p=publishable;c=collection(p);r=upload(p,c);assert r.status_code==201,r.text
    row=r.json();assert not row['approved'];assert upload(p,c).json()['id']==row['id']
    assert Image.open(io.BytesIO(p['client'].get(row['preview_url'],headers=p['editor']).content)).size==(800,600)
    p['client'].cookies.clear()
    assert p['client'].get(row['preview_url']).status_code==401
    approve(p,row)
    assert p['client'].delete(f"/api/library/media/{row['id']}",headers=p['editor']).status_code==200
    assert p['client'].get(f'/api/library/collections/{c}/media',headers=p['editor']).json()==[]
    assert p['client'].get(row['preview_url'],headers=p['editor']).status_code==200


def test_corrupt_file_and_rights_rejected(publishable):
    p=publishable;c=collection(p)
    assert upload(p,c,b'not-an-image').status_code==422
    assert upload(p,c,rights_confirmed='false').status_code==422
    assert upload(p,c,identity_confirmed='false').status_code==422


def test_collection_workspace_isolation(publishable):
    p=publishable;c=collection(p);row=upload(p,c).json()
    outsider=p['client'].post('/api/auth/register',json={'name':'Other owner','email':'library-other@example.com','password':'StrongPassword123!','workspace_name':'Other'}).json()
    headers={'Authorization':'Bearer '+outsider['access_token']}
    assert p['client'].get(f'/api/library/collections/{c}/media',headers=headers).status_code==404
    assert p['client'].get(row['preview_url'],headers=headers).status_code==404
    assert p['client'].patch(f'/api/library/collections/{c}',headers=headers,json={'name':'Stolen'}).status_code==404


def test_concurrent_duplicate_upload(publishable):
    p=publishable;c=collection(p)
    with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(lambda _:upload(p,c),range(2)))
    assert all(r.status_code==201 for r in results),[r.text for r in results]
    assert results[0].json()['id']==results[1].json()['id']


def test_saved_selection_excludes_wrong_personality_and_unapproved(publishable):
    p=publishable;c=collection(p);one=upload(p,c).json();upload(p,c,image('red'));approve(p,one)
    with SessionLocal() as db:
        job=db.get(VideoJob,p['job_id']);job.collection_id=c
        scenes=[SimpleNamespace(scene_number=i) for i in (1,2)];root=Path(settings.generated_dir)/'images'/job.id
        selected=collect_saved(db,job,scenes,root)
        assert len(selected)==1 and selected[0].provenance['library_media_id']==one['id']
        assert db.query(MediaUsage).filter_by(job_id=job.id).count()==0
        other=Personality(id='wrong-'+job.id,workspace_id=job.workspace_id,name='Different person');db.add(other);db.flush()
        db.get(LibraryMedia,one['id']).personality_id=other.id;db.flush()
        assert collect_saved(db,job,scenes,root)==[]


def test_success_usage_and_recent_avoidance(publishable):
    p=publishable;c=collection(p);one=upload(p,c).json();two=upload(p,c,image('red')).json();approve(p,one);approve(p,two)
    with SessionLocal() as db:
        job=db.get(VideoJob,p['job_id']);job.collection_id=None;job.content_mode='hybrid'
        asset=SimpleNamespace(provenance=json.dumps({'library_media_id':one['id']}))
        commit_usage(db,job,[asset]);db.flush();commit_usage(db,job,[asset]);db.commit()
        assert db.query(MediaUsage).filter_by(media_id=one['id'],job_id=job.id).count()==1
        selected=collect_saved(db,job,[SimpleNamespace(scene_number=1)],Path(settings.generated_dir)/'images'/job.id)
        assert selected[0].provenance['library_media_id']==two['id']
        assert job.collection_id==c


def test_scene_layout_invalidates_approval_and_rejects_stale(publishable):
    p=publishable
    with SessionLocal() as db:
        job=db.get(VideoJob,p['job_id']);rev=job.content_revision
        db.get(Channel,p['channel_id']).approval_policy='member_only'
        db.add(Scene(id='scene-'+job.id,job_id=job.id,scene_number=1,start_time=0,end_time=30,narration='Text',visual_query='Test',visual_type='photo',caption='Text',emphasis_word='Text'))
        db.add(Asset(id='asset-'+job.id,job_id=job.id,scene_number=1,source='Fixture',license='Own work',attribution='Fixture',local_path='fixture.jpg'));db.commit()
    payload={'revision':rev,'scenes':[{'asset_id':'asset-'+p['job_id'],'duration':30,'focal_x':.2}]}
    r=p['client'].put(f"/api/videos/{p['job_id']}/scene-layout",headers=p['editor'],json=payload)
    assert r.status_code==200,r.text
    assert r.json()['status']=='failed' and r.json()['failed_step']=='rendering' and r.json()['content_revision']==rev+1
    assert p['client'].post(f"/api/videos/{p['job_id']}/approve",headers=p['editor'],json={'content_revision':rev}).status_code==409
    assert p['client'].put(f"/api/videos/{p['job_id']}/scene-layout",headers=p['editor'],json=payload).status_code==409


def test_defaults_cannot_apply_to_another_members_channel(publishable):
    p=publishable;defaults=p['client'].get('/api/channel-defaults',headers=p['owner']).json()['defaults']
    body={'channel_ids':[p['channel_id']],'defaults':defaults,'confirmed':True}
    assert p['client'].post('/api/channel-defaults/apply',headers=p['owner'],json=body).status_code==404


def test_library_preview_cookie_and_logout(publishable):
    p=publishable;c=collection(p);row=upload(p,c).json();client=p['client']
    client.post('/api/auth/media-session',headers=p['editor']).raise_for_status()
    assert client.get(row['preview_url']).status_code==200
    client.post('/api/auth/logout').raise_for_status()
    assert client.get(row['preview_url']).status_code==401


def test_private_collection_hidden_from_other_member(publishable):
    p=publishable;client=p['client']
    private=client.post('/api/library/collections',headers=p['owner'],json={'name':'Owner private assets'}).json()['id']
    assert client.get(f'/api/library/collections/{private}/media',headers=p['editor']).status_code==404
    assert not any(c['id']==private for c in client.get('/api/library/collections',headers=p['editor']).json())
    assert client.patch(f'/api/library/collections/{private}',headers=p['editor'],json={'name':'Taken'}).status_code==404


def test_defaults_survive_regular_settings_and_inherit(publishable):
    p=publishable;client=p['client'];defaults=client.get('/api/channel-defaults',headers=p['owner']).json()['defaults'];defaults['generation_duration']=60
    client.put('/api/channel-defaults',headers=p['owner'],json=defaults).raise_for_status()
    prefs=client.get('/api/settings',headers=p['owner']).json()['preferences'];assert 'channel_defaults' not in prefs
    client.put('/api/settings',headers=p['owner'],json=prefs).raise_for_status()
    assert client.get('/api/channel-defaults',headers=p['owner']).json()['defaults']['generation_duration']==60
    new=client.post('/api/channels',headers=p['owner'],json={'name':'Defaults inheritance'});new.raise_for_status()
    with SessionLocal() as db:assert db.get(Channel,new.json()['id']).generation_duration==60


def test_my_assets_does_not_bypass_held_generation(publishable,monkeypatch):
    p=publishable
    from app.services import pipeline
    monkeypatch.setattr(pipeline,'generate_script',lambda *a,**k:__import__('pytest').fail('Gemini must not be called'))
    with SessionLocal() as db:
        j=db.get(VideoJob,p['job_id']);j.status='verification_required';j.topic.verification_status='verification_required';j.content_mode='my_assets';db.commit()
    r=p['client'].post(f"/api/videos/{p['job_id']}/regenerate",headers=p['editor'],json={'scope':'script'})
    assert r.status_code==409


def test_real_saved_clip_render(tmp_path):
    import subprocess,wave,math,struct
    from app.video.renderer import render_video
    clip=tmp_path/'fixture.mp4';audio=tmp_path/'narration.wav'
    subprocess.run([settings.ffmpeg_path,'-y','-v','error','-f','lavfi','-i','color=c=navy:s=640x480:r=24','-t','4','-c:v','libx264',str(clip)],capture_output=True,check=True)
    with wave.open(str(audio),'wb') as w:w.setnchannels(1);w.setsampwidth(2);w.setframerate(16000);w.writeframes(b''.join(struct.pack('<h',int(1200*math.sin(i*2*math.pi*220/16000))) for i in range(16000)))
    output,cover,_=render_video('clip-test','OFFLINE FIXTURE','Test','Offline fixture clip test.',audio,3,tmp_path/'empty',[clip],focal_positions=[(.2,.7)])
    result=json.loads(subprocess.check_output([settings.ffprobe_path,'-v','error','-show_streams','-of','json',str(output)]))
    assert any(s.get('codec_name')=='h264' and s.get('width')==1080 for s in result['streams'])
    assert cover.is_file()


def test_hybrid_resolves_channel_collection_without_browser(publishable,monkeypatch):
    p=publishable;c=collection(p);row=upload(p,c).json();approve(p,row)
    from app.api import videos
    calls=[];monkeypatch.setattr(videos,'run_job',lambda *args:calls.append(args))
    with SessionLocal() as db:person=db.get(VideoJob,p['job_id']).personality_id
    payload={'channel_id':p['channel_id'],'personality_id':person,'duration':30,'operation_id':'hybrid-'+p['job_id']}
    r=p['client'].post('/api/videos/generate',headers=p['editor'],json=payload)
    assert r.status_code==201,r.text
    assert r.json()['collection_id']==c
    again=p['client'].post('/api/videos/generate',headers=p['editor'],json=payload)
    assert again.json()['id']==r.json()['id'] and len(calls)==1
    auto=p['client'].post('/api/videos/generate',headers=p['editor'],json={**payload,'operation_id':'auto-'+p['job_id'],'content_mode':'auto'})
    assert auto.status_code==201 and auto.json()['collection_id'] is None


def test_scheduling_is_disabled_for_private_release(publishable,monkeypatch):
    p=publishable
    with SessionLocal() as db:
        db.get(Channel,p['channel_id']).approval_policy='member_only';db.commit()
    client=p['client'];url=f"/api/videos/{p['job_id']}"
    assert client.post(url+'/approve',headers=p['editor'],json={'content_revision':1}).status_code==200
    monkeypatch.setattr(settings,'youtube_uploads_enabled',True)
    assert client.post(url+'/schedule',headers=p['editor'],json={'content_revision':1,'confirmed':True,'made_for_kids':False}).status_code==422


def test_failed_render_does_not_record_usage_or_restart_script(publishable,monkeypatch):
    import hashlib,wave
    from app.services import pipeline
    p=publishable;c=collection(p);row=upload(p,c).json();approve(p,row)
    monkeypatch.setattr(pipeline,'generate_script',lambda *a,**k:__import__('pytest').fail('Successful script must be preserved'))
    monkeypatch.setattr(pipeline,'render_video',lambda *a,**k:(_ for _ in ()).throw(RuntimeError('Isolated renderer failure')))
    with SessionLocal() as db:
        job=db.get(VideoJob,p['job_id']);job.collection_id=c
        audio=Path(settings.generated_dir)/'audio'/f'{job.id}.wav';audio.parent.mkdir(exist_ok=True,parents=True)
        with wave.open(str(audio),'wb') as w:w.setnchannels(1);w.setsampwidth(2);w.setframerate(16000);w.writeframes(b'\x10\x01'*16000)
        job.voice_generation.output_path=str(audio);job.voice_generation.script_hash=hashlib.sha256(job.script.full_script.encode()).hexdigest()
        path=Path(settings.generated_dir)/'images'/job.id/'saved.jpg';path.parent.mkdir(parents=True);path.write_bytes(image())
        db.add(Scene(id='fail-scene-'+job.id,job_id=job.id,scene_number=1,start_time=0,end_time=30,narration='Text',visual_query='Test',visual_type='photo',caption='Text',emphasis_word='Text'))
        db.add(Asset(id='fail-asset-'+job.id,job_id=job.id,scene_number=1,source='Saved collection',license='Own work',attribution='Fixture',local_path=str(path),provenance=json.dumps({'library_media_id':row['id']})))
        before=job.script.full_script;db.commit()
    p['client'].post(f"/api/videos/{p['job_id']}/regenerate",headers=p['editor'],json={'scope':'video'}).raise_for_status()
    final=p['client'].get(f"/api/videos/{p['job_id']}",headers=p['editor']).json()
    assert final['status']=='failed' and final['failed_step']=='rendering' and final['error_message']=='Isolated renderer failure'
    with SessionLocal() as db:
        assert db.query(MediaUsage).filter_by(job_id=p['job_id']).count()==0
        assert db.get(VideoJob,p['job_id']).script.full_script==before
