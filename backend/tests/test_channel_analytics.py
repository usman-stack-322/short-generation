import json
from datetime import datetime, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import Mock
import pytest
from fastapi import HTTPException
from googleapiclient.errors import HttpError
from httplib2 import Response
from app.youtube import channel_analytics as a, oauth
from app.database.session import SessionLocal
from app.models import Channel, ChannelAuthorization, ChannelAnalyticsCache


@pytest.fixture
def publishable(owner_publishable):
    # Channel access is per-member; the owner acts as the channel's authorized member here.
    return owner_publishable



def enabled(p):
    with SessionLocal() as db:
        record=db.query(ChannelAuthorization).filter_by(channel_id=p['channel_id']).one()
        record.scopes=json.dumps(a.READ_SCOPES);db.commit()


def test_mapping_uses_headers_and_watch_hours_not_video_average():
    response={'columnHeaders':[{'name':'averageViewDuration'},{'name':'estimatedMinutesWatched'},{'name':'views'}], 'rows':[[95,150,400]]}
    result=a.mapped(a.rows(response)[0])
    assert result=={'averageViewDuration':95,'views':400,'watch_hours':2.5}
    assert a.mapped({})['watch_hours'] is None
    assert a.rows({'columnHeaders':[]})==[]


@pytest.mark.parametrize('start,end',[('bad','2026-01-01'),('2026-02-01','2026-01-01'),('2020-01-01','2026-01-01'),('2099-01-01','2099-01-02')])
def test_invalid_dates(start,end):
    with pytest.raises(HTTPException): a.date_range(start,end)


def test_missing_scopes_demo_and_disconnect_cannot_read_cache(publishable,monkeypatch):
    p=publishable;url='/api/analytics/channels/'+p['channel_id']
    monkeypatch.setattr(a,'fetch_report',Mock(side_effect=AssertionError('No network allowed')))
    assert p['client'].get(url,headers=p['owner']).json()['state']=='missing_permission'
    enabled(p)
    p['client'].post('/api/youtube/disconnect',headers=p['owner'],json={'channel_id':p['channel_id']})
    assert p['client'].get(url,headers=p['owner']).json()['state']=='not_connected'
    assert p['client'].get(url).status_code==401


def test_cache_permissions_isolation_error_and_recovery(publishable,monkeypatch):
    p=publishable;enabled(p);calls=[]
    payload={'totals':{'views':50,'watch_hours':2,'averageViewDuration':37},'daily':[],'videos':[],'latest_reporting_date':None}
    def fetch(*args):calls.append(1);return payload
    monkeypatch.setattr(a,'fetch_report',fetch)
    url='/api/analytics/channels/'+p['channel_id']+'?start_date=2026-01-01&end_date=2026-01-28'
    first=p['client'].get(url,headers=p['owner']).json();assert first['data']==payload
    assert p['client'].get(url+'&refresh=true',headers=p['owner']).json()['data']==payload
    assert len(calls)==1
    # Channel permissions are checked even when the period is cached.
    other=p['client'].post('/api/members',headers=p['owner'],json={'name':'Analytics private','email':'analytics-'+p['channel_id']+'@example.com','role':'MEMBER'}).json()
    login=p['client'].post('/api/auth/login',json={'email':other['email'],'password':other['temporary_password']}).json()
    assert p['client'].get(url,headers={'Authorization':'Bearer '+login['access_token']}).status_code in (403,404)
    with SessionLocal() as db:
        cache=db.query(ChannelAnalyticsCache).filter_by(channel_id=p['channel_id']).one()
        cache.attempted_at=cache.synced_at=datetime.now(timezone.utc)-timedelta(hours=1);db.commit()
    monkeypatch.setattr(a,'fetch_report',Mock(side_effect=RuntimeError('YouTube reports are temporarily unavailable. Retry later.')))
    stale=p['client'].get(url,headers=p['owner']).json()
    assert stale['stale'] and stale['data']==payload and stale['error']
    with SessionLocal() as db:
        cache=db.query(ChannelAnalyticsCache).filter_by(channel_id=p['channel_id']).one();cache.attempted_at=None;db.commit()
    monkeypatch.setattr(a,'fetch_report',fetch)
    recovered=p['client'].get(url+'&refresh=true',headers=p['owner']).json()
    assert recovered['error'] is None and not recovered['stale']
    p['client'].get(url.replace('2026-01-01','2026-01-02'),headers=p['owner'])
    assert len(calls)==3


def test_concurrent_requests_one_provider_fetch(publishable,monkeypatch):
    import time
    p=publishable;enabled(p);calls=[]
    def fetch(*args):calls.append(1);time.sleep(.2);return {'totals':None,'daily':[],'videos':[]}
    monkeypatch.setattr(a,'fetch_report',fetch)
    def load(_):
        with SessionLocal() as db:
            return a.report(db,db.get(Channel,p['channel_id']),'2026-01-01','2026-01-28')
    with ThreadPoolExecutor(max_workers=4) as pool: results=list(pool.map(load,range(4)))
    assert len(calls)==1
    assert any(result['data'] is not None for result in results)


@pytest.mark.parametrize('status,expected',[(403,1),(401,1),(429,3),(503,3)])
def test_provider_errors_bounded_and_secret_safe(monkeypatch,status,expected):
    request=Mock();request.execute.side_effect=HttpError(Response({'status':str(status)}),b'{"error":{"message":"SECRET must not escape"}}')
    monkeypatch.setattr(a.time,'sleep',lambda *_:None)
    with pytest.raises(RuntimeError) as exc:a.execute(request)
    assert request.execute.call_count==expected and 'SECRET' not in str(exc.value)


def test_old_connections_keep_publishing_scopes_and_analytics_requires_consent(publishable,monkeypatch):
    from app.core.vault import encrypt
    p=publishable
    credentials=Mock(scopes=oauth.BASE_SCOPES,expired=False,token='test-only')
    monkeypatch.setattr(oauth.Credentials,'from_authorized_user_info',lambda *args,**kwargs:credentials)
    with SessionLocal() as db:
        c=db.get(Channel,p['channel_id']);record=db.query(ChannelAuthorization).filter_by(channel_id=c.id).one()
        record.scopes=json.dumps(oauth.BASE_SCOPES);record.encrypted_tokens=encrypt('{}');db.commit()
        assert oauth.credentials_for(db,c) is credentials
        with pytest.raises(RuntimeError):oauth.credentials_for(db,c,required_scopes=a.READ_SCOPES)


def test_report_queries_channel_identity_and_external_video_metadata(publishable,monkeypatch):
    p=publishable;data=Mock();data.channels.return_value.list.return_value.execute.return_value={'items':[{'id':'test-channel'}]}
    data.videos.return_value.list.return_value.execute.return_value={'items':[{'id':'outside-app','snippet':{'title':'Outside this application','thumbnails':{}}}]}
    report=Mock();queries=[]
    def query(**kwargs):
        queries.append(kwargs)
        row={'video':'outside-app','views':10,'estimatedMinutesWatched':120,'averageViewDuration':42} if kwargs.get('dimensions')=='video' else {'day':'2026-01-25','views':10,'engagedViews':8,'estimatedMinutesWatched':120,'averageViewDuration':42,'subscribersGained':2,'subscribersLost':1}
        return Mock(execute=Mock(return_value={'columnHeaders':[{'name':k} for k in row],'rows':[list(row.values())]}))
    report.query.side_effect=query
    monkeypatch.setattr(a,'build',lambda *args,**kwargs:Mock(reports=Mock(return_value=report)))
    monkeypatch.setattr(oauth,'youtube',lambda *_:data)
    monkeypatch.setattr(oauth,'credentials_for',lambda *args,**kwargs:object())
    with SessionLocal() as db:
        c=db.get(Channel,p['channel_id']);result=a.fetch_report(db,c,'2026-01-01','2026-01-28')
        assert result['totals']['watch_hours']==2 and result['totals']['averageViewDuration']==42
        assert result['videos'][0]['title']=='Outside this application'
        assert result['latest_reporting_date']=='2026-01-25'
        assert all('filters' not in q and q['ids']=='channel==test-channel' for q in queries)
        data.channels.return_value.list.return_value.execute.return_value={'items':[{'id':'wrong'}]}
        with pytest.raises(RuntimeError,match='does not match'):a.fetch_report(db,c,'2026-01-01','2026-01-28')
