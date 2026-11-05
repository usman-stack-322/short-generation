"""Official Google OAuth flow, PKCE, one-time state, encrypted credentials."""
import hashlib
import json
import secrets
from datetime import datetime, timedelta, timezone
from google_auth_oauthlib.flow import Flow
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from google.auth.exceptions import RefreshError
from googleapiclient.discovery import build
from fastapi import HTTPException
from app.core.config import settings
from app.core.vault import encrypt, decrypt
from app.core.security import new_id
from app.models import OAuthState, ChannelAuthorization, Channel

BASE_SCOPES = ['https://www.googleapis.com/auth/youtube.readonly', 'https://www.googleapis.com/auth/youtube.upload']
ANALYTICS_SCOPE = 'https://www.googleapis.com/auth/yt-analytics.readonly'
SCOPES = BASE_SCOPES


def flow(state=None, verifier=None):
    if not settings.google_client_id or not settings.google_client_secret:
        raise HTTPException(503, 'Google OAuth is not configured. Set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET in backend/.env')
    config = {'web': {'client_id': settings.google_client_id, 'client_secret': settings.google_client_secret,
                     'auth_uri': 'https://accounts.google.com/o/oauth2/auth',
                     'token_uri': 'https://oauth2.googleapis.com/token', 'redirect_uris': [settings.google_redirect_uri]}}
    return Flow.from_client_config(config, SCOPES, state=state, redirect_uri=settings.google_redirect_uri,
                                   code_verifier=verifier)


def begin(db, member):
    state, browser, verifier = secrets.token_urlsafe(40), secrets.token_urlsafe(40), secrets.token_urlsafe(64)
    client = flow(state, verifier)
    url, _ = client.authorization_url(access_type='offline', prompt='consent', include_granted_scopes='true')
    db.add(OAuthState(id=hashlib.sha256(state.encode()).hexdigest(), member_id=member.id,
                     verifier=encrypt(verifier), browser_hash=hashlib.sha256(browser.encode()).hexdigest(),
                     expires_at=datetime.now(timezone.utc)+timedelta(minutes=10), consumed=False))
    db.commit()
    return url, browser, state


def consume_state(db, state, browser):
    key = hashlib.sha256(state.encode()).hexdigest()
    record = db.get(OAuthState, key)
    if not record or record.consumed or not browser or not secrets.compare_digest(record.browser_hash, hashlib.sha256(browser.encode()).hexdigest()):
        raise HTTPException(400, 'Invalid OAuth state or browser binding')
    if record.expires_at.replace(tzinfo=timezone.utc) < datetime.now(timezone.utc):
        raise HTTPException(400, 'OAuth state expired')
    # Atomic consume prevents callback replay in concurrent requests.
    count = db.query(OAuthState).filter_by(id=key, consumed=False).update({'consumed': True})
    db.commit()
    if count != 1:
        raise HTTPException(400, 'OAuth state already consumed')
    return record


def youtube(credentials):
    return build('youtube', 'v3', credentials=credentials, cache_discovery=False)


def save_credentials(db, channel, member_id, credentials):
    record = db.query(ChannelAuthorization).filter_by(channel_id=channel.id).first()
    if not record:
        record = ChannelAuthorization(id=new_id(), channel_id=channel.id, provider='google')
        db.add(record)
    if record.encrypted_tokens and not credentials.refresh_token:
        old = json.loads(decrypt(record.encrypted_tokens))
        payload = json.loads(credentials.to_json())
        payload['refresh_token'] = old.get('refresh_token')
        record.encrypted_tokens = encrypt(json.dumps(payload))
    else:
        record.encrypted_tokens = encrypt(credentials.to_json())
    record.authorized_member_id = member_id
    record.provider_account_id = channel.youtube_channel_id
    record.scopes = json.dumps(list(getattr(credentials, 'granted_scopes', None) or credentials.scopes or []))
    record.expires_at = credentials.expiry
    channel.status, channel.connection_error = 'connected', None


def credentials_for(db, channel, required_scopes=None):
    record = db.query(ChannelAuthorization).filter_by(channel_id=channel.id).first()
    if not record or not record.encrypted_tokens or channel.status == 'disconnected':
        raise RuntimeError('YouTube channel is disconnected. Reconnect this channel.')
    data = json.loads(decrypt(record.encrypted_tokens))
    credentials = Credentials.from_authorized_user_info(data, scopes=json.loads(record.scopes))
    if not set(required_scopes if required_scopes is not None else BASE_SCOPES).issubset(set(credentials.scopes or [])):
        channel.status = 'permission_missing'
        db.commit()
        raise RuntimeError('Required YouTube permissions missing. Reconnect and grant read/upload access.')
    if credentials.expired or not credentials.token:
        try:
            if not credentials.refresh_token:
                raise RefreshError('Refresh token missing')
            credentials.refresh(Request())
            save_credentials(db, channel, record.authorized_member_id, credentials)
            db.commit()
        except RefreshError:
            channel.status, channel.connection_error = 'token_expired', 'Google authorization expired or revoked. Reconnect.'
            from app.services.preferences import notify
            notify(db,channel.workspace_id,channel.id,'YouTube connection expired',channel.connection_error)
            db.commit()
            raise RuntimeError(channel.connection_error) from None
    return credentials
