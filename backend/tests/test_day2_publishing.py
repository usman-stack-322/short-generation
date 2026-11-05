from datetime import datetime,timedelta,timezone
import json
from types import SimpleNamespace
import pytest
from app.core.config import settings
from app.database.session import SessionLocal
from app.models import Channel,VideoJob,UploadTask,Approval,WorkspaceMember
from app.youtube.permissions import approval_satisfied
from app.youtube.upload import process_upload,upload_guard

PAYLOAD={'content_revision':1,'confirmed':True,'privacy_status':'private','made_for_kids':False}


@pytest.fixture
def publishable(owner_publishable,monkeypatch):
    # Channels are private to their authorized member, so these owner-driven flows use an owner-owned channel.
    monkeypatch.setattr(settings,'youtube_uploads_enabled',True)
    monkeypatch.setattr('app.api.publishing.run_requested_upload',lambda task_id:None)
    return owner_publishable


def test_upload_blocked_without_approval_or_confirmation(publishable):
    p=publishable;c=p['client'];url=f"/api/videos/{p['job_id']}/upload"
    assert c.post(url,headers=p['owner'],json=PAYLOAD).status_code==409
    assert c.post(url,headers=p['owner'],json={**PAYLOAD,'confirmed':False}).status_code==422
    assert c.post(f"/api/videos/{p['job_id']}/approve",headers=p['editor'],json={'content_revision':1}).status_code==404  # not the channel's member


def test_both_policy_requires_two_distinct_approvers(publishable):
    p=publishable;c=p['client'];url=f"/api/videos/{p['job_id']}"
    with SessionLocal() as db:
        db.get(Channel,p['channel_id']).approval_policy='both';db.commit()
    # The channel member is the owner here, so no distinct owner exists: 'both' can never be satisfied by one person.
    assert c.post(url+'/approve',headers=p['owner'],json={'content_revision':1}).json()['status']=='ready_for_review'
    assert c.post(url+'/upload',headers=p['owner'],json=PAYLOAD).status_code==409
    assert c.post(url+'/approve',headers=p['editor'],json={'content_revision':1}).status_code==404
    assert c.post(url+'/upload',headers=p['owner'],json=PAYLOAD).status_code==409


def test_scheduling_is_rejected_private_upload_only(publishable):
    # Product contract: upload privately now; publish/schedule manually in YouTube Studio.
    p=publishable;c=p['client'];url=f"/api/videos/{p['job_id']}"
    c.post(url+'/approve',headers=p['owner'],json={'content_revision':1})
    when=(datetime.now(timezone.utc)+timedelta(days=1)).isoformat()
    response=c.post(url+'/schedule',headers=p['owner'],json={**PAYLOAD,'scheduled_at':when,'timezone':'UTC'})
    assert response.status_code==422,response.text
    with SessionLocal() as db:
        assert not db.query(UploadTask).filter_by(job_id=p['job_id']).count()
        assert db.get(VideoJob,p['job_id']).status=='approved'


def test_invalid_schedule_and_scope_permissions(publishable):
    p=publishable;c=p['client'];url=f"/api/videos/{p['job_id']}"
    c.post(url+'/approve',headers=p['owner'],json={'content_revision':1})
    for when,zone in [('2000-01-01T12:00:00+00:00','UTC'),('2030-01-01T12:00:00','UTC'),('2030-01-01T12:00:00+00:00','Asia/Karachi')]:
        assert c.post(url+'/schedule',headers=p['owner'],json={**PAYLOAD,'scheduled_at':when,'timezone':zone}).status_code==422
    other=c.post('/api/auth/register',json={'name':'Other Owner','email':f'{p["job_id"]}@example.com','password':'Other-password123!'}).json()
    assert c.post(url+'/upload',headers={'Authorization':'Bearer '+other['access_token']},json=PAYLOAD).status_code==404


def test_regeneration_invalidates_approval(publishable,monkeypatch):
    p=publishable;c=p['client'];url=f"/api/videos/{p['job_id']}"
    c.post(url+'/approve',headers=p['owner'],json={'content_revision':1})
    monkeypatch.setattr('app.api.videos.run_job',lambda *args:None)
    assert c.post(url+'/regenerate',headers=p['owner'],json={'scope':'cover'}).status_code==200
    assert c.post(url+'/upload',headers=p['owner'],json=PAYLOAD).status_code==409
    with SessionLocal() as db:
        assert not db.query(Approval).filter_by(job_id=p['job_id']).count()


def test_official_upload_service_success_and_history(publishable,monkeypatch):
    p=publishable;c=p['client'];url=f"/api/videos/{p['job_id']}"
    c.post(url+'/approve',headers=p['owner'],json={'content_revision':1})
    assert c.post(url+'/upload',headers=p['owner'],json=PAYLOAD).status_code==200
    captured={}
    class Request:
        resumable_uri='https://upload.example.test/session'
        def next_chunk(self,**kwargs): return None,{'id':'unit-video','status':{'privacyStatus':'private'}}
    class Service:
        def channels(self): return self
        def list(self,**kwargs): return self
        def execute(self): return {'items':[{'id':'test-channel','snippet':{'channelId':'test-channel'},'status':{'privacyStatus':'private','uploadStatus':'processed'},'processingDetails':{'processingStatus':'succeeded'}}]}
        def videos(self): return self
        def insert(self,**kwargs): captured.update(kwargs);return Request()
    monkeypatch.setattr(settings,'youtube_uploads_enabled',True)
    monkeypatch.setattr('app.youtube.upload.credentials_for',lambda *args:object())
    monkeypatch.setattr('app.youtube.upload.youtube',lambda *args:Service())
    with SessionLocal() as db:
        task=db.query(UploadTask).filter_by(job_id=p['job_id']).one()
        process_upload(db,task)
        assert task.status=='uploaded' and task.progress==1,task.error_message
        assert task.youtube_url.endswith('unit-video')
        assert db.get(VideoJob,p['job_id']).status=='uploaded'
    assert captured['body']['status']['privacyStatus']=='private'
    assert captured['body']['status']['selfDeclaredMadeForKids'] is False
    assert captured['media_body'].resumable()


def test_upload_error_is_persisted_and_does_not_retry_ambiguous_upload(publishable,monkeypatch):
    from googleapiclient.errors import HttpError
    p=publishable;c=p['client'];url=f"/api/videos/{p['job_id']}"
    c.post(url+'/approve',headers=p['owner'],json={'content_revision':1});c.post(url+'/upload',headers=p['owner'],json=PAYLOAD)
    calls=[]
    class Request:
        resumable_uri=None
        def next_chunk(self,**kwargs):
            calls.append(1)
            raise HttpError(SimpleNamespace(status=500,reason='Server error'),b'{"error":"test"}')
    class Service:
        def channels(self): return self
        def list(self,**kwargs): return self
        def execute(self): return {'items':[{'id':'test-channel'}]}
        def videos(self): return self
        def insert(self,**kwargs): return Request()
    monkeypatch.setattr(settings,'youtube_uploads_enabled',True)
    monkeypatch.setattr('app.youtube.upload.credentials_for',lambda *args:object())
    monkeypatch.setattr('app.youtube.upload.youtube',lambda *args:Service())
    monkeypatch.setattr('app.youtube.upload.time.sleep',lambda *args:None)
    with SessionLocal() as db:
        task=db.query(UploadTask).filter_by(job_id=p['job_id']).one()
        process_upload(db,task)
        assert task.status=='upload_uncertain',task.error_message
        assert db.get(VideoJob,p['job_id']).status=='upload_failed'
        assert 'HTTP 500' in task.error_message
    assert len(calls)==4
    assert c.post(url+'/upload',headers=p['owner'],json=PAYLOAD).status_code==409


@pytest.mark.parametrize('status',['researching','rendering','ready_for_review','rejected','failed'])
def test_guard_blocks_nonapproved_jobs(publishable,status):
    with SessionLocal() as db:
        job=db.get(VideoJob,publishable['job_id']);job.status=status
        task=UploadTask(requested_by=publishable['member_id'],content_revision=1)
        with pytest.raises(RuntimeError,match='must be approved'): upload_guard(db,job,task)


def test_deactivated_approver_revokes_upload_eligibility(publishable):
    p=publishable;c=p['client'];url=f"/api/videos/{p['job_id']}"
    c.post(url+'/approve',headers=p['owner'],json={'content_revision':1})
    with SessionLocal() as db:
        approval=db.query(Approval).filter_by(job_id=p['job_id']).one()
        owner=db.get(WorkspaceMember,approval.member_id)
        owner.active=False;db.commit()
        assert not approval_satisfied(db,db.get(VideoJob,p['job_id']),db.get(Channel,p['channel_id']))
        owner.active=True;db.commit()


def test_scheduler_uses_persisted_due_tasks_only(publishable,monkeypatch):
    from app.services.scheduler import tick
    p=publishable;c=p['client'];url=f"/api/videos/{p['job_id']}"
    c.post(url+'/approve',headers=p['owner'],json={'content_revision':1})
    # Only pending immediate uploads are processed; a persisted scheduled task (legacy) is never run.
    assert c.post(url+'/upload',headers=p['owner'],json=PAYLOAD).status_code==200
    calls=[]
    monkeypatch.setattr('app.services.scheduler.process_upload',lambda db,task:calls.append(task.id))
    with SessionLocal() as db:
        task=db.query(UploadTask).filter_by(job_id=p['job_id']).one()
        task_id=task.id
        task.status='scheduled';task.timezone='UTC'
        task.scheduled_at=datetime.now(timezone.utc)-timedelta(seconds=1);db.commit()
    tick();assert task_id not in calls
    with SessionLocal() as db:
        task=db.get(UploadTask,task_id)
        task.status='pending';task.scheduled_at=None;db.commit()
    tick();assert calls.count(task_id)==1


def test_interrupted_upload_requires_manual_reconciliation(publishable):
    p=publishable;c=p['client'];url=f"/api/videos/{p['job_id']}"
    c.post(url+'/approve',headers=p['owner'],json={'content_revision':1});c.post(url+'/upload',headers=p['owner'],json=PAYLOAD)
    with SessionLocal() as db:
        task=db.query(UploadTask).filter_by(job_id=p['job_id']).one()
        task.status='upload_uncertain';db.get(VideoJob,p['job_id']).status='upload_failed';db.commit()
    assert c.post(url+'/reconcile-upload',headers=p['owner'],json={}).status_code==422
    assert c.post(url+'/reconcile-upload',headers=p['owner'],json={'confirmed_absent':True}).json()['status']=='upload_failed'
    assert c.post(url+'/upload',headers=p['owner'],json=PAYLOAD).status_code==200
