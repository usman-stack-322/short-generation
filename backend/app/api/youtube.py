import json
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from app.core.config import settings
from app.core.security import require_admin, new_id
from app.core.vault import decrypt
from app.database.session import get_db
from app.models import Channel, ChannelAuthorization, WorkspaceMember
from app.schemas import InputModel
from app.youtube import oauth
from app.youtube.permissions import channel_access

router = APIRouter(prefix='/api/youtube', tags=['YouTube'])


@router.get('/connect')
def connect(response: Response, context=Depends(require_admin), db: Session=Depends(get_db)):
    url, browser, _ = oauth.begin(db, context[1])
    response.set_cookie('youtube_oauth_browser', browser, max_age=600, httponly=True,
                        secure=settings.google_redirect_uri.startswith('https://'), samesite='lax', path='/api/youtube')
    return {'authorization_url': url}


@router.get('/callback')
def callback(request: Request, state: str, code: str | None=None, error: str | None=None, db: Session=Depends(get_db)):
    record = oauth.consume_state(db, state, request.cookies.get('youtube_oauth_browser'))
    member = db.get(WorkspaceMember, record.member_id)
    if not member or not member.active or member.role not in {'OWNER', 'ADMIN'}:
        raise HTTPException(403, 'Active owner/admin membership required')
    if error or not code:
        raise HTTPException(400, 'Google authorization was declined or incomplete')
    client = oauth.flow(state, decrypt(record.verifier))
    try:
        client.fetch_token(code=code)
        credentials = client.credentials
        if not set(oauth.SCOPES).issubset(set(credentials.granted_scopes or credentials.scopes or [])):
            raise HTTPException(403, 'Required read/upload scopes were not granted')
        channels = oauth.youtube(credentials).channels().list(part='id,snippet,statistics', mine=True).execute().get('items', [])
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(502, 'Google authorization/channel discovery failed. Reconnect and check server configuration.') from None
    if not channels:
        raise HTTPException(400, 'No YouTube channel returned. Create or select a YouTube channel in Google first.')
    # Serialize claims in the supported single SQLite backend before global lookup.
    from sqlalchemy import text
    if db.bind.dialect.name=='sqlite':
        db.execute(text('UPDATE workspaces SET name=name WHERE id=:id'),{'id':member.workspace_id})
    for item in channels:
        matches=db.query(Channel).filter_by(youtube_channel_id=item['id']).all()
        if len(matches)>1:raise HTTPException(409,'Legacy duplicate channel records require operator reconciliation; no credentials were shared')
        channel=matches[0] if matches else None
        if channel and (channel.workspace_id!=member.workspace_id or channel.member_id != member.id):
            raise HTTPException(409, 'This channel is assigned to another workspace member; ownership cannot be replaced by reconnecting.')
        if not channel:
            channel = Channel(id=new_id(), workspace_id=member.workspace_id, member_id=member.id,
                              youtube_channel_id=item['id'],name=item['snippet']['title'],approval_policy='member_only')
            db.add(channel)
            from app.api.channel_defaults import saved_defaults,apply_channel
            apply_channel(channel,saved_defaults(db,member.workspace_id))
            channel.approval_policy='member_only'
            db.flush()
        snippet, stats = item['snippet'], item.get('statistics', {})
        channel.name = snippet['title']
        channel.member_id = member.id
        channel.profile_image_url = snippet.get('thumbnails', {}).get('default', {}).get('url')
        channel.subscriber_count = int(stats['subscriberCount']) if 'subscriberCount' in stats else None
        channel.video_count = int(stats['videoCount']) if 'videoCount' in stats else None
        channel.channel_url = 'https://www.youtube.com/channel/' + item['id']
        channel.connected_at = datetime.now(timezone.utc)
        oauth.save_credentials(db, channel, member.id, credentials)
    db.commit()
    response = RedirectResponse(settings.frontend_origin + '/channels?connected=1', status_code=303)
    response.delete_cookie('youtube_oauth_browser', path='/api/youtube')
    return response


class ChannelRequest(InputModel):
    channel_id: str


@router.post('/disconnect')
def disconnect(payload: ChannelRequest, context=Depends(require_admin), db: Session=Depends(get_db)):
    channel = db.get(Channel, payload.channel_id)
    channel_access(channel, context[1], True)
    record = db.query(ChannelAuthorization).filter_by(channel_id=channel.id).first()
    if record:
        record.encrypted_tokens = None
    channel.status = 'disconnected'
    db.commit()
    return {'status': 'disconnected', 'message': 'Local credentials removed. Google account access can also be revoked in your Google Account permissions.'}


@router.post('/health')
def health(payload: ChannelRequest, context=Depends(require_admin), db: Session=Depends(get_db)):
    channel = db.get(Channel, payload.channel_id)
    channel_access(channel, context[1], True)
    try:
        data = oauth.youtube(oauth.credentials_for(db, channel)).channels().list(part='id', mine=True).execute()
        if channel.youtube_channel_id not in [item['id'] for item in data.get('items', [])]:
            raise RuntimeError('Authenticated account does not own the selected YouTube channel')
        channel.status, channel.connection_error = 'connected', None
    except Exception:
        if channel.status == 'connected':
            channel.status, channel.connection_error = 'permission_missing', 'Connection check failed. Reconnect this account.'
    db.commit()
    return {'status': channel.status, 'error': channel.connection_error}
