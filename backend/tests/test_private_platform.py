"""Private workspace and upload regression checks. No external requests/uploads."""
import io,json
from pathlib import Path
from uuid import uuid4
import pytest
from PIL import Image
from fastapi.testclient import TestClient
from app.main import app
from app.database.session import SessionLocal
from app.core.config import settings
from app.core.security import create_token
from app.models import WorkspaceMember,User,Channel,VideoJob,UploadTask,Approval


@pytest.fixture
def client():
    with TestClient(app) as c:yield c


def login(c,email='owner@example.com',password='DemoOwner123!'):
    r=c.post('/api/auth/login',json=dict(email=email,password=password));assert r.status_code==200,r.text
    return {'Authorization':'Bearer '+r.json()['access_token']}


def register(c):
    r=c.post('/api/auth/register',json=dict(name='Private Member',email=uuid4().hex+'@example.com',password='Secure-pass-123!'))
    assert r.status_code==201,r.text
    assert r.json()['role']=='MEMBER'
    h={'Authorization':'Bearer '+r.json()['access_token']}
    return h,c.get('/api/auth/me',headers=h).json()


def test_multiple_admins_and_live_sessions(client):
    c=client;owner=login(c);a,ma=register(c);b,mb=register(c)
    members=c.get('/api/members',headers=owner).json();ids={m['user_id']:m['id'] for m in members}
    ai,bi=ids[ma['id']],ids[mb['id']]
    assert c.get('/api/members',headers=a).status_code==403
    for key in (ai,bi):assert c.patch('/api/members/'+key,headers=owner,json={'role':'ADMIN'}).status_code==200
    assert c.get('/api/members',headers=a).status_code==200
    assert c.patch('/api/members/'+bi,headers=a,json={'role':'MEMBER'}).status_code==403
    oid=next(m['id'] for m in members if m['role']=='OWNER')
    assert c.patch('/api/members/'+oid,headers=a,json={'active':False}).status_code==403
    assert c.patch('/api/members/'+oid,headers=owner,json={'role':'MEMBER'}).status_code==409
    assert c.patch('/api/members/'+ai,headers=owner,json={'can_manage_admins':True}).status_code==200
    assert c.patch('/api/members/'+bi,headers=a,json={'role':'MEMBER'}).status_code==200
    assert c.get('/api/members',headers=b).status_code==403
    assert c.patch('/api/members/'+bi,headers=owner,json={'active':False}).status_code==200
    assert c.get('/api/auth/me',headers=b).status_code==401
    events=c.get('/api/members/audit',headers=owner).json()
    assert any(e['target_id']==ai for e in events)
    assert 'password' not in json.dumps(events) and 'access_token' not in json.dumps(events)


def test_registration_cannot_set_role(client):
    r=client.post('/api/auth/register',json=dict(name='Escalate',email=uuid4().hex+'@example.com',password='Secure-pass-123!',role='OWNER'))
    assert r.status_code==422


def image_bytes():
    out=io.BytesIO();Image.new('RGB',(500,600),'blue').save(out,'JPEG');return out.getvalue()


def test_personal_media_and_channel_isolation(client,monkeypatch,tmp_path):
    c=client;a,ma=register(c);b,mb=register(c);owner=login(c)
    ch=c.post('/api/channels',headers=a,json={'name':'My private channel'});assert ch.status_code==201,ch.text
    channel=ch.json()['id']
    for headers in (b,owner):
        assert c.get('/api/channels/'+channel,headers=headers).status_code==404
        assert c.post('/api/youtube/disconnect',headers=headers,json={'channel_id':channel}).status_code==404
    collection=c.post('/api/library/collections',headers=a,json={'name':'Private photos'}).json()['id']
    body=image_bytes()
    r=c.post('/api/library/collections/'+collection+'/media',headers=a,files={'file':('image.jpg',body,'image/jpeg')},data={'name':'Campus','creator':'Member','rights_confirmed':'true'})
    assert r.status_code==201,r.text
    media=r.json();assert media['width']==500 and media['height']==600
    assert c.get(media['preview_url'],headers=a).status_code==200
    for headers in (b,owner):assert c.get(media['preview_url'],headers=headers).status_code==404
    duplicate=c.post('/api/library/collections/'+collection+'/media',headers=a,files={'file':('image.jpg',body,'image/jpeg')},data={'name':'Copy','creator':'Member','rights_confirmed':'true'})
    assert duplicate.json()['reused']
    bad=c.post('/api/library/collections/'+collection+'/media',headers=a,files={'file':('fake.jpg',b'not an image','image/jpeg')},data={'name':'Bad','creator':'Member','rights_confirmed':'true'})
    assert bad.status_code==422
    with SessionLocal() as db:
        member=db.query(WorkspaceMember).filter_by(user_id=ma['id']).one();member_id=member.id
    monkeypatch.setattr(settings,'local_media_roots',json.dumps({member_id:str(tmp_path)}))
    (tmp_path/'valid.jpg').write_bytes(body)
    url='/api/library/collections/'+collection+'/import-folder'
    assert c.post(url,headers=a,json={'relative_path':'../','rights_confirmed':True}).status_code==422
    r=c.post(url,headers=a,json={'rights_confirmed':True});assert r.status_code==200,r.text
    assert r.json()['files'][0]['media']['reused']


@pytest.mark.parametrize('visibility',['public','unlisted'])
def test_private_request_enforcement(client,visibility):
    h,_=register(client)
    r=client.post('/api/videos/missing/upload',headers=h,json={'content_revision':1,'confirmed':True,'made_for_kids':False,'privacy_status':visibility})
    assert r.status_code==422


def test_private_upload_worker_and_duplicates(publishable,monkeypatch):
    p=publishable;c=p['client'];h=p['editor'];base='/api/videos/'+p['job_id']
    with SessionLocal() as db:
        db.get(Channel,p['channel_id']).approval_policy='member_only';db.commit()
    assert c.post(base+'/approve',headers=h,json={'content_revision':1}).status_code==200
    monkeypatch.setattr(settings,'youtube_uploads_enabled',True)
    monkeypatch.setattr('app.api.publishing.run_requested_upload',lambda *a:None)
    payload={'content_revision':1,'confirmed':True,'made_for_kids':False}
    assert c.post(base+'/schedule',headers=h,json=payload).status_code==422
    assert c.post(base+'/upload',headers=h,json=payload).status_code==200
    assert c.post(base+'/upload',headers=h,json=payload).status_code==409
    captured={}
    class Request:
        resumable_uri='https://mock.invalid/session'
        def next_chunk(self,**kw):return None,{'id':'mockVideo01','status':{'privacyStatus':'private'}}
    class Service:
        mode=''
        def channels(self):self.mode='channels';return self
        def videos(self):self.mode='videos';return self
        def list(self,**kw):return self
        def execute(self):
            return {'items':[{'id':'test-channel'}]} if self.mode=='channels' else {'items':[{'snippet':{'channelId':'test-channel'},'status':{'privacyStatus':'private','uploadStatus':'processed'}}]}
        def insert(self,**kw):captured.update(kw);return Request()
    monkeypatch.setattr('app.youtube.upload.credentials_for',lambda *a:object())
    monkeypatch.setattr('app.youtube.upload.youtube',lambda *a:Service())
    from app.youtube.upload import process_upload
    with SessionLocal() as db:
        task=db.query(UploadTask).filter_by(job_id=p['job_id']).one();task.privacy_status='public';db.commit()
        process_upload(db,task);assert task.status=='uploaded',task.error_message
        process_upload(db,task)
    assert captured['body']['status']['privacyStatus']=='private'
    assert 'publishAt' not in captured['body']['status']
    assert captured['media_body'].resumable()


def test_disconnect_blocks_queued_upload(publishable,monkeypatch):
    p=publishable;c=p['client'];h=p['editor'];base='/api/videos/'+p['job_id']
    with SessionLocal() as db:db.get(Channel,p['channel_id']).approval_policy='member_only';db.commit()
    assert c.post(base+'/approve',headers=h,json={'content_revision':1}).status_code==200
    monkeypatch.setattr(settings,'youtube_uploads_enabled',True)
    monkeypatch.setattr('app.api.publishing.run_requested_upload',lambda *a:None)
    assert c.post(base+'/upload',headers=h,json={'content_revision':1,'confirmed':True,'made_for_kids':False}).status_code==200
    assert c.post('/api/youtube/disconnect',headers=h,json={'channel_id':p['channel_id']}).status_code==200
    from app.youtube.upload import process_upload
    with SessionLocal() as db:
        task=db.query(UploadTask).filter_by(job_id=p['job_id']).one();process_upload(db,task)
        assert task.status=='upload_failed' and 'connected' in task.error_message
        assert Path(db.get(VideoJob,p['job_id']).video.output_path).exists()


def test_wrong_channel_prevents_external_mutation(publishable,monkeypatch):
    from app.youtube.upload import process_upload
    from app.core.security import new_id
    p=publishable
    with SessionLocal() as db:
        job=db.get(VideoJob,p['job_id']);job.status='approved'
        db.get(Channel,p['channel_id']).approval_policy='member_only'
        db.add(Approval(id=new_id(),job_id=job.id,member_id=p['member_id'],revision=1))
        task=UploadTask(id=new_id(),job_id=job.id,requested_by=p['member_id'],content_revision=1,status='pending')
        db.add(task);db.commit()
        class WrongChannel:
            def channels(self):return self
            def list(self,**kw):return self
            def execute(self):return {'items':[{'id':'someone-elses-channel'}]}
            def videos(self):pytest.fail('Wrong-channel upload must never start')
        monkeypatch.setattr(settings,'youtube_uploads_enabled',True)
        monkeypatch.setattr('app.youtube.upload.credentials_for',lambda *a:object())
        monkeypatch.setattr('app.youtube.upload.youtube',lambda *a:WrongChannel())
        process_upload(db,task)
        assert task.status=='upload_failed' and 'mismatch' in task.error_message


def test_title_local_selection_export_and_private_download(client):
    import hashlib
    from app.models import TitleShortDraft
    from app.core.security import new_id
    from app.services.title_shorts import directory
    c=client;headers,me=register(c);other,_=register(c)
    channel=c.post('/api/channels',headers=headers,json={'name':'Member export channel'}).json()['id']
    collection=c.post('/api/library/collections',headers=headers,json={'name':'Export images'}).json()['id']
    uploaded=c.post('/api/library/collections/'+collection+'/media',headers=headers,files={'file':('campus.jpg',image_bytes(),'image/jpeg')},data={'name':'Campus','creator':'Member','rights_confirmed':'true'}).json()
    c.patch('/api/library/media/'+uploaded['id'],headers=headers,json={'name':'Campus','tags':['Dartmouth'],'description':'Campus archive image','approved':True}).raise_for_status()
    with SessionLocal() as db:
        member=db.query(WorkspaceMember).filter_by(user_id=me['id']).one()
        draft=TitleShortDraft(id=new_id(),workspace_id=member.workspace_id,creator_id=member.user_id,title='Reviewed research title',duration=30,language='English',style='educational',status='script_review')
        scenes=[dict(number=i+1,start=i*10,end=(i+1)*10,narration='Reviewed source supported narration.',visual_description='Campus archive image',image_query='Dartmouth campus',on_screen_text='Campus',motion='push_in',transition='dissolve',ai_image_prompt='A campus photograph') for i in range(3)]
        data={'research_state':'verified','analysis':{'topic':'Research proposal','people':[]},'sources':[{'id':'S1','url':'https://example.edu','excerpt':'Fixture evidence'}],
            'plan':{'scenes':scenes,'claims':[]},'assets':[None]*3,'collection_id':collection,'media_mode':'local'}
        draft.data=json.dumps(data);db.add(draft);db.commit();key=draft.id
    for number in range(1,4):
        row=c.get('/api/title-shorts/'+key,headers=headers).json()
        r=c.put(f'/api/title-shorts/{key}/scenes/{number}/local-image',headers=headers,json={'revision':row['revision'],'media_id':uploaded['id']})
        assert r.status_code==200,r.text
    with SessionLocal() as db:
        draft=db.get(TitleShortDraft,key);data=json.loads(draft.data)
        path=directory(draft)/'render-fixture'/'short.mp4';path.parent.mkdir();path.write_bytes(b'mocked-render-for-export-test')
        data['video']={'path':str(path),'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'duration':30,'revision':draft.revision}
        data['renders']=[data['video']];draft.data=json.dumps(data);draft.status='ready';db.commit();revision=draft.revision
        audio=directory(draft)/('render-'+str(revision))/'source.wav'
        audio.parent.mkdir(exist_ok=True);audio.write_bytes(b'preserved-narration-fixture')
    body={'revision':revision,'channel_id':channel,'title':'Reviewed title','description':'Source supported description'}
    r=c.post('/api/title-shorts/'+key+'/finalize',headers=headers,json=body);assert r.status_code==200,r.text
    job_id=r.json()['job_id']
    assert c.post('/api/title-shorts/'+key+'/finalize',headers=headers,json=body).json()['job_id']==job_id
    job=c.get('/api/videos/'+job_id,headers=headers).json();assert len(job['scenes'])==3
    with SessionLocal() as db:
        exported=db.get(VideoJob,job_id)
        assert Path(exported.voice_generation.output_path).read_bytes()==b'preserved-narration-fixture'
    assert c.get(job['video_url'],headers=headers).status_code==200
    assert c.get(job['video_url'],headers=other).status_code==404
    assert c.get('/api/title-shorts/'+key,headers=other).status_code==404
    assert c.post('/api/videos/'+job_id+'/approve',headers=headers,json={'content_revision':1}).status_code==200


def test_local_match_requires_confirmed_person_tags(client):
    from types import SimpleNamespace
    from app.services.title_library import match_local
    c=client;headers,me=register(c)
    collection=c.post('/api/library/collections',headers=headers,json={'name':'Identity matching'}).json()['id']
    row=c.post('/api/library/collections/'+collection+'/media',headers=headers,files={'file':('person.jpg',image_bytes(),'image/jpeg')},data={'name':'Person','creator':'Member','rights_confirmed':'true'}).json()
    c.patch('/api/library/media/'+row['id'],headers=headers,json={'name':'Person','tags':['Bob','football'],'description':'football photograph','approved':True}).raise_for_status()
    draft=SimpleNamespace(id=uuid4().hex,workspace_id=me['workspace_id'],creator_id=me['id'],data=json.dumps({'collection_id':collection,'analysis':{'people':['Alice']}}))
    assert match_local(draft,{'visual_description':'Alice playing football','image_query':'Alice football'},[]) is None


def test_settings_audit_records_field_names_only(client):
    from app.models import AdminAudit
    c=client;owner=login(c)
    prefs=c.get('/api/settings',headers=owner).json()['preferences']
    response=c.put('/api/settings',headers=owner,json=prefs)
    assert response.status_code==200,response.text
    with SessionLocal() as db:
        event=db.query(AdminAudit).filter_by(action='settings_updated').order_by(AdminAudit.created_at.desc()).first()
        assert event and set(json.loads(event.details))=={'fields'}
        assert set(json.loads(event.details)['fields'])==set(prefs)


def test_reconciliation_verifies_processing_before_success(publishable,monkeypatch):
    from app.core.security import new_id
    p=publishable
    with SessionLocal() as db:
        job=db.get(VideoJob,p['job_id']);job.status='upload_failed'
        db.add(UploadTask(id=new_id(),job_id=job.id,requested_by=p['member_id'],content_revision=1,status='upload_uncertain'))
        title=job.script.seo.title;db.commit()
    calls=[]
    class Service:
        def videos(self):return self
        def list(self,**kwargs):calls.append(kwargs);return self
        def execute(self):return {'items':[{'snippet':{'channelId':'test-channel','title':title},'status':{'privacyStatus':'private','uploadStatus':'uploaded'},'processingDetails':{'processingStatus':'processing'}}]}
    monkeypatch.setattr('app.youtube.oauth.credentials_for',lambda *a:object())
    monkeypatch.setattr('app.youtube.oauth.youtube',lambda *a:Service())
    monkeypatch.setattr('app.youtube.upload.credentials_for',lambda *a:object())
    monkeypatch.setattr('app.youtube.upload.youtube',lambda *a:Service())
    response=p['client'].post('/api/videos/'+p['job_id']+'/reconcile-upload',headers=p['editor'],json={'youtube_video_id':'testvideo01'})
    assert response.status_code==200,response.text
    assert response.json()['status']=='processing'
    assert any('processingDetails' in c['part'] for c in calls)
