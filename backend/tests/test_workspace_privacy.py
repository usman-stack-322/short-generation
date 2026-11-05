import json
from pathlib import Path
import pytest
from app.core.security import new_id


@pytest.fixture
def isolated(publishable,monkeypatch):
    from app.database.session import SessionLocal
    from app.models import VideoJob,Video
    p=publishable;c=p['client']
    monkeypatch.setattr('app.api.videos.run_job',lambda *args:None)
    email=f'{new_id()}@example.com'
    response=c.post('/api/members',headers=p['owner'],json={'name':'Member B','email':email,'role':'MEMBER'})
    member=response.json()
    auth=c.post('/api/auth/login',json={'email':email,'password':member['temporary_password']}).json()
    other={'Authorization':'Bearer '+auth['access_token']}
    channel=c.post('/api/channels',headers=other,json={'name':'Channel B'}).json()
    persona=c.post('/api/personalities',headers=other,json={'name':'Private Member B','channel_id':channel['id']}).json()
    job=c.post('/api/videos/generate',headers=other,json={'channel_id':channel['id'],'personality_id':persona['id']}).json()
    with SessionLocal() as db:
        saved=db.get(VideoJob,job['id']);saved.status=saved.current_step='ready_for_review'
        db.commit()
    yield {**p,'b':other,'b_id':member['id'],'b_channel':channel['id'],'b_personality':persona['id'],'b_job':job['id']}


def test_team_and_dashboard_privacy(isolated):
    p=isolated;c=p['client']
    for member in ('editor','b'):
        assert c.get('/api/members',headers=p[member]).status_code==403
        data=c.get('/api/dashboard',headers=p[member]).json()
        assert 'team_activity' not in data and 'total_members' not in data
        assert all(v['channel_id']!=(p['b_channel'] if member=='editor' else p['channel_id']) for v in data['recent_videos'])
    data=c.get('/api/dashboard',headers=p['owner']).json()
    assert 'team_activity' in data and data['total_members']>=2
    # Administration does not grant access to members' private channels or videos.
    assert not {p['channel_id'],p['b_channel']}&{r['id'] for r in data['channels']}
    assert c.get('/api/videos/'+p['job_id'],headers=p['owner']).status_code==404


def test_cross_member_channel_video_and_action_access(isolated):
    p=isolated;c=p['client']
    for headers,channel,job in [(p['editor'],p['b_channel'],p['b_job']),(p['b'],p['channel_id'],p['job_id'])]:
        assert c.get('/api/channels/'+channel,headers=headers).status_code==404
        assert c.get('/api/videos/'+job,headers=headers).status_code==404
        assert c.get('/api/videos/'+job+'/logs',headers=headers).status_code==404
        assert c.post('/api/videos/'+job+'/regenerate',headers=headers,json={'scope':'all'}).status_code==404
        assert c.post('/api/videos/'+job+'/analytics/sync',headers=headers).status_code==404
        assert c.post('/api/videos/'+job+'/approve',headers=headers).status_code==404
    assert c.get('/api/videos/'+p['b_job'],headers=p['owner']).status_code==404
    assert c.get('/api/videos/'+p['b_job']+'/logs',headers=p['owner']).status_code==404


def test_private_personalities_and_owner_sharing(isolated):
    p=isolated;c=p['client']
    assert c.get('/api/personalities/'+p['b_personality'],headers=p['editor']).status_code==404
    assert c.get('/api/personalities/'+p['b_personality'],headers=p['owner']).status_code==404
    assert c.post('/api/personalities',headers=p['editor'],json={'name':'Forbidden share','visibility':'workspace'}).status_code==403
    assert c.post('/api/videos/generate',headers=p['editor'],json={'channel_id':p['channel_id'],'personality_id':p['b_personality']}).status_code==404
    assert c.patch('/api/personalities/'+p['b_personality']+'/share',headers=p['editor'],json={'channel_id':p['channel_id']}).status_code==403
    assert c.patch('/api/personalities/'+p['b_personality']+'/share',headers=p['owner'],json={'channel_id':p['channel_id']}).status_code in (403,404)
    assert c.get('/api/personalities/'+p['b_personality'],headers=p['editor']).status_code==404


def test_signed_asset_links_still_require_channel_access(isolated):
    from app.core.config import settings
    from app.api.media import media_link
    p=isolated;c=p['client'];key=p['b_job']
    target=Path(settings.generated_dir)/'images'/key/'source.jpg';target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(b'test image')
    url=media_link(f'images/{key}/source.jpg')
    assert c.get(url).status_code==401
    assert c.get(url,headers=p['editor']).status_code==404
    assert c.get(url,headers=p['b']).status_code==200
    assert c.get(url,headers=p['owner']).status_code==404
    assert c.post('/api/auth/media-session',headers=p['b']).status_code==200
    assert c.get(url).status_code==200
    assert c.get(url,headers=p['editor']).status_code==404  # Bearer identity wins over another session cookie.
    c.post('/api/auth/logout')
    assert c.get(url).status_code==401


def test_explicit_assignment_and_viewer_read_only(isolated):
    p=isolated;c=p['client']
    # Owners cannot assign or read another member's private channel; nothing is shared implicitly.
    assert c.patch('/api/channels/'+p['b_channel'],headers=p['owner'],json={'assigned_member_ids':[p['member_id']]}).status_code in (403,404)
    assert c.get('/api/channels/'+p['b_channel'],headers=p['editor']).status_code==404
    assert c.get('/api/videos/'+p['b_job'],headers=p['editor']).status_code==404
    assert c.get('/api/personalities/'+p['b_personality'],headers=p['editor']).status_code==404
    email=new_id()+'@example.com'
    # VIEWER is no longer an assignable role.
    assert c.post('/api/members',headers=p['owner'],json={'name':'Read only','email':email,'role':'VIEWER'}).status_code==422
    member=c.post('/api/members',headers=p['owner'],json={'name':'Fresh member','email':email,'role':'MEMBER'}).json()
    token=c.post('/api/auth/login',json={'email':email,'password':member['temporary_password']}).json()['access_token']
    fresh={'Authorization':'Bearer '+token}
    assert c.post('/api/videos/'+p['job_id']+'/regenerate',headers=fresh,json={'scope':'all'}).status_code==404


def test_research_retry_and_invalid_regeneration(isolated):
    from app.database.session import SessionLocal
    from app.models import VideoJob
    p=isolated;c=p['client']
    with SessionLocal() as db:
        job=db.get(VideoJob,p['b_job']);job.status=job.current_step='verification_required';db.commit()
    assert c.post('/api/videos/'+p['b_job']+'/regenerate',headers=p['b'],json={'scope':'voice'}).status_code==409
    assert c.post('/api/videos/'+p['b_job']+'/regenerate',headers=p['b'],json={'scope':'retry'}).status_code==200
