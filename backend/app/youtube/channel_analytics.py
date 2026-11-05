"""Read-only channel reports. No app-video filter, publishing, or synthetic data."""
import json
import random
import time
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from fastapi import HTTPException
from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError
from app.core.config import settings
from app.models import ChannelAuthorization, ChannelAnalyticsCache, Channel
from app.youtube import oauth

READ_SCOPES = [oauth.BASE_SCOPES[0], oauth.ANALYTICS_SCOPE]
METRICS = 'views,engagedViews,estimatedMinutesWatched,averageViewDuration,subscribersGained,subscribersLost'


def date_range(start=None, end=None):
    yesterday = datetime.now(ZoneInfo('America/Los_Angeles')).date() - timedelta(days=1)
    try:
        end = date.fromisoformat(end) if end else yesterday
        start = date.fromisoformat(start) if start else end - timedelta(days=27)
    except ValueError:
        raise HTTPException(422, 'Use dates in YYYY-MM-DD format') from None
    if start > end or end > yesterday or start < date(2009, 1, 1) or (end-start).days > 365:
        raise HTTPException(422, 'Select an ordered range of at most 366 days ending before today (Pacific time).')
    return start.isoformat(), end.isoformat()


def connection(db, channel):
    auth = db.query(ChannelAuthorization).filter_by(channel_id=channel.id).first()
    if not auth or not auth.encrypted_tokens or channel.status == 'disconnected':
        return 'not_connected'
    if channel.status == 'token_expired':
        return 'reconnect'
    if not set(READ_SCOPES).issubset(set(json.loads(auth.scopes or '[]'))):
        return 'missing_permission'
    return 'connected'


def rows(report):
    names = [header['name'] for header in report.get('columnHeaders', [])]
    return [dict(zip(names, row)) for row in report.get('rows', [])]


def mapped(row):
    result = dict(row)
    minutes = result.pop('estimatedMinutesWatched', None)
    result['watch_hours'] = float(minutes) / 60 if minutes is not None else None
    return result


def execute(request):
    for attempt in range(3):
        try:
            if hasattr(request, 'http'):
                transport = getattr(request.http, 'http', request.http)
                transport.timeout = 25
            return request.execute(num_retries=0)
        except HttpError as exc:
            status = exc.resp.status
            if status in {429, 500, 502, 503, 504} and attempt < 2:
                time.sleep((1, 3)[attempt] + random.uniform(0, .25))
                continue
            if status == 401:
                raise RuntimeError('YouTube authorization expired. Reconnect this channel.') from None
            if status == 403:
                raise RuntimeError('YouTube denied the report. Check Analytics API enablement, consent, and quota; reconnect if permission is missing.') from None
            if status == 429:
                raise RuntimeError('YouTube report quota is temporarily exhausted. Wait before refreshing.') from None
            raise RuntimeError('YouTube reports are temporarily unavailable. Retry later.') from None


def fetch_report(db, channel, start, end):
    credentials = oauth.credentials_for(db, channel, required_scopes=READ_SCOPES)
    data = oauth.youtube(credentials)
    identity = execute(data.channels().list(part='id', mine=True))
    if channel.youtube_channel_id not in {item['id'] for item in identity.get('items', [])}:
        raise RuntimeError('Connected Google identity does not match this channel. Reconnect the correct account.')
    reports = build('youtubeAnalytics', 'v2', credentials=credentials, cache_discovery=False).reports()
    base = dict(ids='channel==' + channel.youtube_channel_id, startDate=start, endDate=end)
    totals = rows(execute(reports.query(**base, metrics=METRICS)))
    daily = rows(execute(reports.query(**base, metrics=METRICS, dimensions='day', sort='day', maxResults=366, startIndex=1)))
    top = rows(execute(reports.query(**base, metrics='views,estimatedMinutesWatched,averageViewDuration', dimensions='video', sort='-views', maxResults=10, startIndex=1)))
    metadata = {}
    if top:
        metadata = {item['id']: item['snippet'] for item in execute(data.videos().list(part='snippet', id=','.join(row['video'] for row in top))).get('items', [])}
    videos = []
    for row in top:
        snippet = metadata.get(row['video'], {})
        videos.append({**mapped(row), 'title': snippet.get('title', 'Video metadata unavailable'),
                       'thumbnail': snippet.get('thumbnails', {}).get('medium', {}).get('url')})
    return {'totals': mapped(totals[0]) if totals else None,
            'daily': [mapped(row) for row in daily], 'videos': videos,
            'latest_reporting_date': max((r['day'] for r in daily), default=None),
            'activity': 'reported' if totals else 'no_reported_data', 'source': 'YouTube Analytics API'}


def report(db, channel, start, end, force=False):
    state = connection(db, channel)
    if state != 'connected':
        return {'state': state, 'data': None, 'message': 'Connect or reconnect this channel with analytics read permission.'}
    key = (channel.workspace_id, channel.id, f'v1:{start}:{end}:top10')
    now = datetime.now(timezone.utc)
    # Data API video titles/avatars must not persist indefinitely in old reports.
    db.query(ChannelAnalyticsCache).filter(
        ChannelAnalyticsCache.workspace_id == channel.workspace_id,
        ChannelAnalyticsCache.synced_at < now-timedelta(days=30)).delete(synchronize_session=False)
    db.commit()
    cache = db.get(ChannelAnalyticsCache, key)
    if not cache:
        db.add(ChannelAnalyticsCache(workspace_id=key[0], channel_id=key[1], report_key=key[2]))
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
        cache = db.get(ChannelAnalyticsCache, key)
    def age(value):
        return (now-value.replace(tzinfo=timezone.utc)).total_seconds() if value else float('inf')
    def response(refreshing=False):
        # Recheck saved connection even when using cached reports.
        db.refresh(channel)
        current = connection(db, channel)
        if current != 'connected':
            return {'state': current, 'data': None, 'message': 'Reconnect this channel for analytics.'}
        return {'state': 'ready' if cache.payload else ('loading' if refreshing else 'error'),
                'data': json.loads(cache.payload) if cache.payload else None,
                'synced_at': cache.synced_at.isoformat() + 'Z' if cache.synced_at and cache.synced_at.tzinfo is None else cache.synced_at.isoformat() if cache.synced_at else None,
                'stale': bool(cache.error) or age(cache.synced_at) >= settings.analytics_cache_seconds,
                'error': cache.error, 'refreshing': refreshing, 'start_date': start, 'end_date': end}
    if cache.payload and age(cache.synced_at) < settings.analytics_cache_seconds and not force:
        return response()
    # A persisted lease deduplicates concurrent callers across backend processes.
    if age(cache.attempted_at) < max(1, settings.analytics_refresh_seconds):
        return response(bool(cache.lease_until and cache.lease_until.replace(tzinfo=timezone.utc) > now))
    claimed = db.query(ChannelAnalyticsCache).filter_by(workspace_id=key[0], channel_id=key[1], report_key=key[2]).filter(
        or_(ChannelAnalyticsCache.lease_until.is_(None), ChannelAnalyticsCache.lease_until < now),
        or_(ChannelAnalyticsCache.attempted_at.is_(None), ChannelAnalyticsCache.attempted_at < now-timedelta(seconds=max(1, settings.analytics_refresh_seconds))))
    if claimed.update({'lease_until': now+timedelta(minutes=5), 'attempted_at': now}, synchronize_session=False) != 1:
        db.rollback(); db.refresh(cache)
        return response(True)
    db.commit()
    try:
        payload = fetch_report(db, channel, start, end)
        db.refresh(channel)
        if connection(db, channel) != 'connected':
            raise RuntimeError('Channel disconnected during refresh. Reconnect for analytics.')
        cache.payload = json.dumps(payload)
        cache.synced_at = datetime.now(timezone.utc)
        cache.error = None
    except Exception as exc:
        # Only controlled provider messages leave this service. Never log credentials.
        cache.error = str(exc) if type(exc) is RuntimeError else 'Analytics refresh failed. Check the connection and retry later.'
    cache.lease_until = None
    db.commit()
    return response()
