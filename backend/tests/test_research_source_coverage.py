import pytest
import json
from datetime import datetime,timezone,timedelta
from email.utils import format_datetime
from urllib.parse import urlparse,parse_qs
from unittest.mock import Mock
from app.core.config import settings
from app.core.security import new_id
from app.database.session import SessionLocal
from app.models import VideoJob,ResearchCandidate
from app.research.live import RSSResearchProvider,assess


def test_google_news_feed_targets_personality_preserves_filters(monkeypatch):
    from app.research import live
    monkeypatch.setattr(settings,'rss_feeds','https://news.google.com/rss/search?q=football%20when%3A3d&hl=en-US&gl=US')
    feed=f'<rss version="2.0"><channel><title>Test</title><item><title>Cristiano Ronaldo goals milestone</title><link>https://www.uefa.com/test</link><pubDate>{format_datetime(datetime.now(timezone.utc))}</pubDate></item></channel></rss>'.encode()
    fetch=Mock(return_value=(feed,{}));monkeypatch.setattr(live,'public_get',fetch)
    assert RSSResearchProvider().candidates('Cristiano Ronaldo',['Ronaldo'])
    query=parse_qs(urlparse(fetch.call_args.args[0]).query)
    assert '"Cristiano Ronaldo"' in query['q'][0] and 'after:' in query['q'][0] and 'before:' in query['q'][0] and 'when:' not in query['q'][0]
    assert query['hl']==['en-US'] and query['gl']==['US']


def test_saved_review_survives_picker_refresh_but_not_expiry_or_provider_failure(publishable,monkeypatch):
    p=publishable;monkeypatch.setattr(settings,'research_provider','rss')
    with SessionLocal() as db:
        job=db.get(VideoJob,p['job_id']);pid=job.personality_id
        row={'title':'Ronaldo goals milestone','summary':'Ronaldo reaches an official goals milestone.',
             'source_name':'UEFA','source_url':'https://www.uefa.com/test-saved',
             'published_at':datetime.now(timezone.utc).isoformat(),'personality_match':['Ronaldo']}
        data=assess([row],'Ronaldo',[],[])[0];assert data['status']=='verified'
        candidate=ResearchCandidate(id=new_id(),channel_id=p['channel_id'],personality_id=pid,title=data['title'],status='verified',data=json.dumps(data))
        db.add(candidate);db.commit();cid=candidate.id
    monkeypatch.setattr('app.api.research.research_live',lambda *args:[])
    body={'channel_id':p['channel_id'],'personality_id':pid}
    result=p['client'].post('/api/research/candidates',headers=p['owner'],json=body)
    assert result.status_code==200 and any(r['id']==cid for r in result.json())
    monkeypatch.setattr('app.api.research.research_live',Mock(side_effect=ValueError('RSS provider unavailable')))
    assert p['client'].post('/api/research/candidates',headers=p['owner'],json=body).status_code==422
    monkeypatch.setattr('app.api.research.research_live',lambda *args:[])
    with SessionLocal() as db:
        record=db.get(ResearchCandidate,cid);data=json.loads(record.data)
        expired=(datetime.now(timezone.utc)-timedelta(days=5)).isoformat()
        data['published_at']=expired
        for evidence in data['evidence']:evidence['published_at']=expired
        record.data=json.dumps(data);db.commit()
    assert not any(r['id']==cid for r in p['client'].post('/api/research/candidates',headers=p['owner'],json=body).json())


@pytest.fixture
def publishable(owner_publishable):
    # Channel access is per-member, so owner-driven flows use a channel owned by the OWNER membership.
    return owner_publishable
