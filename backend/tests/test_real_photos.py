import io
import json
from types import SimpleNamespace
from pathlib import Path
import pytest
from PIL import Image
from app.services.assets import licensed
from app.services.assets.policy import license_allowed, photo_supported, matches_subject, contextual


def photo(**kwargs):
    return {'source':'commons','url':'https://commons.wikimedia.org/wiki/File:Stadium.jpg',
        'download_url':'https://upload.wikimedia.org/stadium.jpg','creator':'Photographer',
        'license':'CC BY 4.0','license_url':'https://creativecommons.org/licenses/by/4.0/',
        'title':'Football stadium photograph','description':'Photograph of football stadium',
        'categories':'Photographs of football stadiums','sha1':'abc',**kwargs}


def jpeg():
    out=io.BytesIO();Image.new('RGB',(800,500),'#76ab68').save(out,'JPEG');return out.getvalue()


def scene(number=1):
    return SimpleNamespace(scene_number=number,visual_query='football stadium',caption='A documented story',narration='Supported narration')


@pytest.mark.parametrize('name,url,artist,allowed',[
 ('CC BY 4.0','https://creativecommons.org/licenses/by/4.0/','Author',True),
 ('CC BY-SA 4.0','https://creativecommons.org/licenses/by-sa/4.0/','Author',False),
 ('CC BY-NC 4.0','https://creativecommons.org/licenses/by-nc/4.0/','Author',False),
 ('CC BY 4.0','https://evil.test/licenses/by/4.0/','Author',False),
 ('CC BY 4.0','https://creativecommons.org/licenses/by/4.0/','',False),
 ('Public domain','','',True),('All rights reserved','','Author',False)])
def test_rights_gate(name,url,artist,allowed):
    assert license_allowed(name,url,artist)==allowed


def test_identity_requires_depicts_and_name():
    row=photo(title='LeBron James photograph',subject_entity='Q36159',depicts=['Q36159'])
    assert matches_subject(row,'LeBron James')
    assert not matches_subject(row,'LeBron Other')
    assert not matches_subject({**row,'depicts':['Q123']},'LeBron James')
    assert not matches_subject({**row,'subject_entity':None},'LeBron James')
    assert not contextual(photo(title='Generic player',description='Basketball player photograph',categories='Basketball court'),'basketball court photograph')


@pytest.mark.parametrize('description',['AI-generated photograph','Illustration of a stadium','Face swap photograph','Fabricated composite photograph','Painting of a stadium','Midjourney photograph','Stable Diffusion photograph','Computer-generated photograph','Deepfake photograph'])
def test_excludes_synthetic_artwork(description):
    assert not photo_supported(photo(description=description))


def test_unknown_photo_provenance_skipped():
    assert not photo_supported(photo(title='Stadium',description='Stadium',categories='Buildings'))


def test_missing_pexels_key_does_not_call_network(monkeypatch):
    monkeypatch.setattr(licensed.settings,'pexels_api_key','')
    monkeypatch.setattr(licensed.httpx,'get',lambda *a,**k:pytest.fail('Network forbidden'))
    assert licensed.PexelsAssetProvider().search('stadium')==[]


def test_download_safe_cached_padded_and_credited(tmp_path,monkeypatch):
    calls=[]
    monkeypatch.setattr(licensed,'fetch',lambda *a,**k:(calls.append(a[0]) or jpeg(),{}))
    root=tmp_path/'images'/'job'
    first=licensed.download_photo(photo(),scene(),root,'context')
    second=licensed.download_photo(photo(),scene(2),root,'context')
    assert len(calls)==1
    assert first.provenance['content_hash']==second.provenance['content_hash']
    assert first.provenance['label']=='Illustrative image'
    assert 'Photographer' in first.provenance['required_credit']
    assert 'creativecommons.org/licenses/by/4.0/' in first.provenance['required_credit']
    assert 'padded' in first.provenance['modifications']
    with Image.open(first.local_path) as image:
        assert image.size==(1080,1920)
        assert max(abs(a-b) for a,b in zip(image.getpixel((10,600)),(23,25,43)))<=2  # Safe border, not a stretched/cropped photograph.
    with pytest.raises(ValueError,match='Unapproved'):
        licensed.download_photo(photo(download_url='https://127.0.0.1/x'),scene(),root,'context')


def test_download_rejects_inaccessible_and_invalid_bytes(tmp_path,monkeypatch):
    monkeypatch.setattr(licensed,'fetch',lambda *a,**k:(b'<html>not a photo</html>',{}))
    with pytest.raises(Exception):licensed.download_photo(photo(),scene(),tmp_path/'images'/'job','context')
    assert not list((tmp_path/'cache'/'photos').glob('*.bin'))


def test_collection_deduplicates_identified_photos_and_holds_missing_scene(tmp_path,monkeypatch):
    monkeypatch.setattr(licensed.CommonsAssetProvider,'subject',lambda *a:None)
    monkeypatch.setattr(licensed.CommonsAssetProvider,'search',lambda *a:[photo(title='Cristiano Ronaldo photograph',subject_entity='Q11571',depicts=['Q11571']),photo(title='Cristiano Ronaldo photograph',subject_entity='Q11571',depicts=['Q11571'],download_url='https://upload.wikimedia.org/copy.jpg')])
    monkeypatch.setattr(licensed.CommonsAssetProvider,'identify',lambda *a:None)
    monkeypatch.setattr(licensed.settings,'pexels_api_key','')
    monkeypatch.setattr(licensed,'fetch',lambda *a,**k:(jpeg(),{}))
    rows=licensed.collect_scene_assets([scene(),scene(2)],'Football story','Cristiano Ronaldo','Football',tmp_path/'images'/'job')
    assert [row.source for row in rows]==['commons','Missing scene media']
    assert rows[1].provenance['kind']=='missing'


def test_provider_failure_has_explicit_neutral_reason(tmp_path,monkeypatch):
    def fail(*a,**k):raise TimeoutError('Provider inaccessible')
    monkeypatch.setattr(licensed.CommonsAssetProvider,'subject',fail)
    monkeypatch.setattr(licensed.CommonsAssetProvider,'search',fail)
    monkeypatch.setattr(licensed.settings,'pexels_api_key','')
    rows=licensed.collect_scene_assets([scene()],'Football','Ronaldo','Football',tmp_path/'images'/'job')
    assert rows[0].source=='Missing scene media'
    assert 'timed out' in rows[0].provenance['reason']


def add_scene_asset(p):
    from app.database.session import SessionLocal
    from app.models import Asset,Scene
    from app.core.security import new_id
    with SessionLocal() as db:
        s=Scene(id=new_id(),job_id=p['job_id'],scene_number=1,start_time=0,end_time=30,narration='Test',visual_query='football stadium',visual_type='photo',caption='Test',emphasis_word='Test')
        a=Asset(id=new_id(),job_id=p['job_id'],scene_number=1,source='Fixture',license='Original',attribution='Fixture credit',local_path='not-real.jpg')
        db.add_all([s,a]);db.commit();return a.id


def test_remove_invalidates_approval_and_stale_edits(publishable):
    p=publishable;c=p['client'];asset=add_scene_asset(p)
    job=c.get('/api/videos/'+p['job_id'],headers=p['owner']).json();revision=job['content_revision']
    assert c.post('/api/videos/'+p['job_id']+'/approve',headers=p['owner'],json={'content_revision':revision}).status_code==200
    url=f"/api/videos/{p['job_id']}/assets/{asset}/remove"
    result=c.post(url,headers=p['owner'],json={'revision':revision})
    assert result.status_code==200,result.text
    updated=result.json()
    assert updated['content_revision']==revision+1 and updated['status']=='failed'
    assert updated['assets'][0]['kind']=='missing'
    assert c.post(url,headers=p['owner'],json={'revision':revision}).status_code==409
    assert c.post('/api/videos/'+p['job_id']+'/approve',headers=p['owner'],json={'content_revision':revision}).status_code==409
    assert c.get(updated['assets'][0]['preview_url'],headers=p['owner']).status_code==200
    c.cookies.clear()
    assert c.get(updated['assets'][0]['preview_url']).status_code==401


def test_upload_validation_and_credits(publishable):
    p=publishable;c=p['client'];asset=add_scene_asset(p)
    revision=c.get('/api/videos/'+p['job_id'],headers=p['owner']).json()['content_revision']
    url=f"/api/videos/{p['job_id']}/assets/{asset}/upload"
    data={'revision':revision,'creator':'Test photographer','license':'CC BY 4.0','source_url':'https://example.org/photo','rights_confirmed':'true','real_photo_confirmed':'true'}
    assert c.post(url,headers=p['owner'],data=data,files={'file':('x.svg',b'<svg/>','image/svg+xml')}).status_code==422
    response=c.post(url,headers=p['owner'],data=data,files={'file':('../../escape.jpg',jpeg(),'image/jpeg')})
    assert response.status_code==200,response.text
    value=response.json();credit=value['assets'][0]['attribution']
    assert credit in value['seo']['description']
    assert 'CC BY 4.0' in credit and 'Test photographer' in credit
    assert value['status']=='failed' and value['failed_step']=='rendering'
    assert c.post(f"/api/videos/{p['job_id']}/assets/other-id/remove",headers=p['owner'],json={'revision':value['content_revision']}).status_code==404


def test_licensed_archive_upload_retains_actual_date_without_claiming_event(publishable):
    p=publishable;c=p['client'];asset=add_scene_asset(p)
    revision=c.get('/api/videos/'+p['job_id'],headers=p['owner']).json()['content_revision']
    data={'revision':revision,'creator':'Archive photographer','license':'CC BY 2.0','source_url':'https://commons.wikimedia.org/wiki/File:Photo.jpg','rights_confirmed':'true','real_photo_confirmed':'true','capture_date':'2015-01-15','source_title':'Later illustrative portrait'}
    url=f"/api/videos/{p['job_id']}/assets/{asset}/upload"
    bad=c.post(url,headers=p['owner'],data={**data,'capture_date':'not-a-date'},files={'file':('photo.jpg',jpeg(),'image/jpeg')})
    assert bad.status_code==422
    response=c.post(url,headers=p['owner'],data=data,files={'file':('photo.jpg',jpeg(),'image/jpeg')})
    assert response.status_code==200,response.text
    job=response.json();assert job['assets'][0]['label']=='Illustrative archive - 2015'
    assert 'not the historical award event' in job['seo']['description'] and 'CC BY 2.0' in job['seo']['description']
    assert job['content_revision']>revision and job['approval_count']==0


def test_photo_changes_cannot_clear_verification_hold(publishable):
    from app.database.session import SessionLocal
    from app.models import VideoJob
    p=publishable;asset=add_scene_asset(p)
    with SessionLocal() as db:
        job=db.get(VideoJob,p['job_id']);job.status='verification_required';db.commit();revision=job.content_revision
    result=p['client'].post(f"/api/videos/{p['job_id']}/assets/{asset}/remove",headers=p['owner'],json={'revision':revision})
    assert result.status_code==409
    with SessionLocal() as db:assert db.get(VideoJob,p['job_id']).status=='verification_required'


def test_photo_edit_and_preview_are_workspace_isolated(publishable):
    from app.core.security import new_id
    p=publishable;c=p['client'];asset=add_scene_asset(p)
    own=c.get('/api/videos/'+p['job_id'],headers=p['owner']).json()
    url=f"/api/videos/{p['job_id']}/assets/{asset}/remove"
    new=c.post('/api/auth/register',json={'name':'Other isolated owner','workspace_name':'Other private workspace','email':new_id()+'@example.org','password':'TestOnly123!'}).json()
    other={'Authorization':'Bearer '+new['access_token']}
    assert c.post(url,headers=other,json={'revision':own['content_revision']}).status_code==404
    response=c.post(url,headers=p['owner'],json={'revision':own['content_revision']}).json()
    assert c.get(response['assets'][0]['preview_url'],headers=other).status_code==404


def test_stale_approval_session_cannot_undo_photo_change(publishable):
    from app.database.session import SessionLocal
    from app.models import VideoJob,WorkspaceMember,Approval
    from app.youtube.permissions import approve
    from sqlalchemy.orm.exc import StaleDataError
    p=publishable;asset=add_scene_asset(p)
    with SessionLocal() as stale:
        job=stale.get(VideoJob,p['job_id']);_ = job.video
        owner=stale.query(WorkspaceMember).filter_by(workspace_id=job.workspace_id,role='OWNER').one()
        response=p['client'].post(f"/api/videos/{job.id}/assets/{asset}/remove",headers=p['owner'],json={'revision':job.content_revision})
        assert response.status_code==200
        with pytest.raises(StaleDataError):approve(stale,job,owner,job.content_revision)
        stale.rollback()
    with SessionLocal() as db:assert db.query(Approval).filter_by(job_id=p['job_id']).count()==0


def test_bounded_retry_only_on_transient_http_errors(monkeypatch,tmp_path):
    import httpx
    from app.services.assets import wikimedia
    monkeypatch.setattr(wikimedia,'LOCK_DIR',tmp_path/'locks')
    monkeypatch.setattr(wikimedia,"user_agent",lambda:"OFFLINE TEST USER AGENT")
    wikimedia._holds.clear()
    calls=[]
    def failed(*a,**k):
        calls.append(1)
        response=httpx.Response(503,request=httpx.Request('GET','https://commons.wikimedia.org/w/api.php'))
        raise httpx.HTTPStatusError('temporary',request=response.request,response=response)
    monkeypatch.setattr(wikimedia,'public_get',failed);monkeypatch.setattr(licensed.time,'sleep',lambda _:None)
    with pytest.raises(wikimedia.WikimediaAccessError):licensed.fetch('https://commons.wikimedia.org/w/api.php')
    assert len(calls)==2
    calls.clear();wikimedia._holds.clear()
    monkeypatch.setattr(wikimedia,'user_agent',lambda:'OFFLINE TEST USER AGENT 401')
    def denied(*a,**k):
        calls.append(1)
        response=httpx.Response(401,request=httpx.Request('GET','https://commons.wikimedia.org/w/api.php'))
        raise httpx.HTTPStatusError('denied',request=response.request,response=response)
    monkeypatch.setattr(wikimedia,'public_get',denied)
    with pytest.raises(wikimedia.WikimediaAccessError):licensed.fetch('https://commons.wikimedia.org/w/api.php')
    assert len(calls)==1


def test_replacement_excludes_existing_content_hash_even_with_other_url(tmp_path,monkeypatch):
    import hashlib
    monkeypatch.setattr(licensed.CommonsAssetProvider,'subject',lambda *a:None)
    monkeypatch.setattr(licensed.CommonsAssetProvider,'search',lambda *a:[photo(download_url='https://upload.wikimedia.org/same-photo-other-name.jpg')])
    monkeypatch.setattr(licensed.CommonsAssetProvider,'identify',lambda *a:None)
    monkeypatch.setattr(licensed.settings,'pexels_api_key','')
    monkeypatch.setattr(licensed,'fetch',lambda *a,**k:(jpeg(),{}))
    rows=licensed.collect_scene_assets([scene()],'Football','Cristiano Ronaldo','Football',tmp_path/'images'/'job',exclude_hashes=[hashlib.sha256(jpeg()).hexdigest()])
    assert rows[0].source=='Missing scene media'


def test_pexels_long_rate_limit_is_respected_without_retry(monkeypatch):
    import httpx
    monkeypatch.setattr(licensed.settings,'pexels_api_key','fixture-key-never-log')
    calls=[]
    def get(url,**kwargs):
        calls.append(url)
        return httpx.Response(429,headers={'Retry-After':'60'},request=httpx.Request('GET',url))
    monkeypatch.setattr(licensed.httpx,'get',get)
    with pytest.raises(httpx.HTTPStatusError):licensed.PexelsAssetProvider().search('football stadium')
    assert len(calls)==1


@pytest.fixture
def publishable(owner_publishable):
    # Channel access is per-member, so owner-driven flows use a channel owned by the OWNER membership.
    return owner_publishable
