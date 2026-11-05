from datetime import datetime,timedelta,timezone
from urllib.parse import urlparse,parse_qs
import pytest
from fastapi.testclient import TestClient
from fastapi import HTTPException
from app.main import app
from app.core.config import settings
from app.core.vault import encrypt,decrypt
from app.database.session import SessionLocal
from app.models import WorkspaceMember,User,Channel,ChannelAuthorization
from app.youtube import oauth


def test_oauth_state_pkce_browser_binding_and_replay(monkeypatch):
    monkeypatch.setattr(settings,'google_client_id','unit-test-client')
    monkeypatch.setattr(settings,'google_client_secret','unit-test-secret')
    with TestClient(app),SessionLocal() as db:
        member=db.query(WorkspaceMember).join(User).filter(User.email=='owner@example.com').one()
        url,browser,state=oauth.begin(db,member)
        query=parse_qs(urlparse(url).query)
        assert query['access_type']==['offline']
        assert query['code_challenge_method']==['S256']
        assert set(query['scope'][0].split())==set(oauth.SCOPES)
        with pytest.raises(HTTPException): oauth.consume_state(db,state,'wrong-browser')
        record=oauth.consume_state(db,state,browser)
        assert record.member_id==member.id
        assert decrypt(record.verifier)
        with pytest.raises(HTTPException): oauth.consume_state(db,state,browser)
        _,browser,state=oauth.begin(db,member)
        import hashlib
        from app.models import OAuthState
        db.get(OAuthState,hashlib.sha256(state.encode()).hexdigest()).expires_at=datetime.now(timezone.utc)-timedelta(seconds=1)
        db.commit()
        with pytest.raises(HTTPException): oauth.consume_state(db,state,browser)


def test_encryption_authentication():
    token='sensitive-refresh-token'
    encoded=encrypt(token)
    assert token not in encoded
    assert decrypt(encoded)==token
    with pytest.raises(Exception): decrypt(encoded[:-5]+'wrong')


def test_refresh_and_revocation_handling(publishable,monkeypatch):
    import json
    from google.auth.exceptions import RefreshError
    class Credentials:
        scopes=oauth.SCOPES
        expired=True
        token='old'
        refresh_token='refresh'
        expiry=datetime.now(timezone.utc)
        def refresh(self,request): self.token='new'
        def to_json(self): return json.dumps({'token':self.token,'refresh_token':self.refresh_token})
    fake=Credentials()
    monkeypatch.setattr(oauth.Credentials,'from_authorized_user_info',lambda *args,**kwargs:fake)
    with SessionLocal() as db:
        channel=db.get(Channel,publishable['channel_id'])
        record=db.query(ChannelAuthorization).filter_by(channel_id=channel.id).one()
        record.scopes=json.dumps(oauth.SCOPES);record.encrypted_tokens=encrypt('{}');db.commit()
        assert oauth.credentials_for(db,channel).token=='new'
        assert 'new' in decrypt(record.encrypted_tokens)
        def revoked(request): raise RefreshError('revoked')
        fake.refresh=revoked
        with pytest.raises(RuntimeError,match='expired or revoked'): oauth.credentials_for(db,channel)
        assert channel.status=='token_expired'


def test_oauth_routes_do_not_expose_credentials(publishable,monkeypatch):
    client=publishable['client']
    monkeypatch.setattr(settings,'google_client_id','')
    assert client.get('/api/youtube/connect',headers=publishable['owner']).status_code==503
    assert client.get('/api/youtube/callback?state=forged&code=fake').status_code==400
    channels=client.get('/api/channels',headers=publishable['owner']).text
    assert 'encrypted_tokens' not in channels and 'refresh_token' not in channels
    assert client.post('/api/youtube/disconnect',headers=publishable['editor'],json={'channel_id':publishable['channel_id']}).status_code==200


def test_callback_discovers_channel_with_encrypted_credentials(publishable,monkeypatch):
    import json
    from types import SimpleNamespace
    p=publishable;c=p['client']
    monkeypatch.setattr(settings,'google_client_id','fake-client')
    monkeypatch.setattr(settings,'google_client_secret','fake-secret')
    with SessionLocal() as db:
        member=db.get(WorkspaceMember,p['member_id'])
        _,browser,state=oauth.begin(db,member)
    class Credential:
        granted_scopes=scopes=oauth.SCOPES
        refresh_token='test-refresh-secret'
        expiry=datetime.now(timezone.utc)
        def to_json(self):return json.dumps({'token':'test-access-secret','refresh_token':self.refresh_token})
    class Flow:
        credentials=Credential()
        def fetch_token(self,**kwargs):assert kwargs['code']=='fake-code'
    class YouTube:
        def channels(self):return self
        def list(self,**kwargs):assert kwargs['mine'];return self
        def execute(self):return {'items':[{'id':'discovered-channel','snippet':{'title':'Discovered Sports','thumbnails':{'default':{'url':'https://example.com/avatar.jpg'}}},'statistics':{'subscriberCount':'42','videoCount':'12'}}]}
    monkeypatch.setattr(oauth,'flow',lambda *args,**kwargs:Flow())
    monkeypatch.setattr(oauth,'youtube',lambda *args:YouTube())
    c.cookies.set('youtube_oauth_browser',browser)
    result=c.get('/api/youtube/callback',params={'state':state,'code':'fake-code'},follow_redirects=False)
    assert result.status_code==303,result.text
    channels=c.get('/api/channels',headers=p['editor']).json()
    found=next(row for row in channels if row['youtube_channel_id']=='discovered-channel')
    assert found['name']=='Discovered Sports' and found['subscriber_count']==42
    assert found['member_id']==p['member_id']
    assert 'test-refresh-secret' not in json.dumps(channels)
    with SessionLocal() as db:
        record=db.query(ChannelAuthorization).filter_by(channel_id=found['id']).one()
        assert 'test-refresh-secret' not in record.encrypted_tokens
        assert 'test-refresh-secret' in decrypt(record.encrypted_tokens)
