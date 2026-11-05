import calendar
import json
import re
from datetime import datetime, timezone, timedelta
from difflib import SequenceMatcher
from urllib.parse import urlparse, urlencode, parse_qsl, urlunparse
import feedparser
import httpx
from app.ai.reliability import safe_detail
from app.core.config import settings
from app.core.network import public_get
from app.core.security import new_id
from app.models import ResearchCandidate, Topic
from app.research.verification import source_metadata, verify_story

RUMOR = re.compile(r'\b(rumou?r|unconfirmed|speculation|reportedly|could join|may join|allegedly)\b', re.I)
STOP = {'the','and','for','with','from','that','this','after','about','into','says','said','his','her','has','have','will','was','are','but','not','cristiano','ronaldo','lionel','messi'}


def domain(url):
    host = urlparse(url or '').hostname or ''
    return host


def tokens(title):
    return {w for w in re.findall(r'\w+', title.casefold()) if len(w)>2 and w not in STOP}


def similar(left, right):
    a, b = tokens(left), tokens(right)
    return bool(a and b) and (len(a & b)/max(1,len(a | b)) >= .38 or SequenceMatcher(None,left.lower(),right.lower()).ratio() > .78)


class ResearchSearchError(ValueError):
    def __init__(self,message,candidate_ids=None):
        super().__init__(message)
        self.candidate_ids=candidate_ids or []


def candidate_age_hours(data):
    # Only server-persisted search metadata can extend a candidate's age limit.
    days=data.get('search_window_days')
    return days*24 if days in (3,7,14) else settings.research_max_age_hours


class RSSResearchProvider:
    def search_window(self,name,keywords,days,now):
        self.window_days,self.now=days,now
        return self.candidates(name,keywords)

    def candidates(self, name, keywords):
        urls = [url.strip() for url in settings.rss_feeds.split(',') if url.strip()]
        if not urls:
            raise ValueError('No RSS feeds configured')
        rows, errors = [], []
        now=getattr(self,'now',datetime.now(timezone.utc))
        days=getattr(self,'window_days',3)
        lower=now-timedelta(days=days)
        successful=0
        if days>3:
            urls=[url for url in urls if urlparse(url).hostname=='news.google.com' and urlparse(url).path=='/rss/search']
            if not urls:raise ValueError('Historical research needs a configured date-filtered Google News RSS search feed.')
        for url in urls[:8]:
            try:
                parsed_url=urlparse(url)
                if parsed_url.hostname=='news.google.com' and parsed_url.path=='/rss/search':
                    query=dict(parse_qsl(parsed_url.query))
                    subject=name.replace('"','').strip()
                    base=re.sub(r'\b(?:when:[^\s)]+|after:[^\s)]+|before:[^\s)]+)','',query.get('q','')).strip()
                    after=(lower-timedelta(days=1)).date().isoformat()
                    before=(now+timedelta(days=1)).date().isoformat()
                    query['q']=f'"{subject}" ({base}) after:{after} before:{before}' 
                    url=urlunparse(parsed_url._replace(query=urlencode(query)))
                body, _ = public_get(url)
                if b'<!DOCTYPE' in body.upper() or b'<!ENTITY' in body.upper():
                    raise ValueError('Unsafe feed XML')
                parsed = feedparser.parse(body)
                if parsed.bozo and not parsed.entries:
                    raise ValueError('RSS source returned invalid data')
                successful+=1
                for entry in parsed.entries[:100]:
                    link=entry.get('link',url)
                    if urlparse(link).scheme!='https' or urlparse(link).username or not urlparse(link).hostname:
                        continue
                    title = re.sub('<[^>]+>', '', entry.get('title',''))[:500]
                    summary = re.sub('<[^>]+>', '', entry.get('summary',''))[:1600]
                    terms = [name, *keywords]
                    matches = [term for term in terms if term and term.casefold() in (title+' '+summary).casefold()]
                    if not matches:
                        continue
                    source = entry.get('source', {})
                    source_url = source.get('href') or entry.get('link',url)
                    dt = entry.get('published_parsed') or entry.get('updated_parsed')
                    published = datetime.fromtimestamp(calendar.timegm(dt),timezone.utc) if dt else None
                    if published and not lower<=published<=now:continue
                    rows.append({'title':title,'summary':summary,'source_name':source.get('title') or parsed.feed.get('title',domain(url)),
                                 'source_url':link,'publisher_url':source_url,'source_domain':domain(source_url),
                                 'canonical_url':next((value['href'] for value in entry.get('links',[]) if value.get('rel')=='canonical'),link),
                                 'author':entry.get('author',''),
                                 'published_at':published.isoformat() if published else None,
                                 'personality_match':matches})
                    authority=source_metadata(rows[-1])
                    rows[-1].update(reliability_score=authority['reliability'],source_category=authority['category'])
            except Exception as exc:
                detail = f'HTTP {exc.response.status_code}' if isinstance(exc,httpx.HTTPStatusError) else safe_detail(exc)
                errors.append(f'{domain(url)}: {type(exc).__name__}: {detail}')
        if not successful:
            raise ValueError('Research provider failed. '+('; '.join(errors) or 'No successful feed response'))
        self.feed_errors=errors
        # Keep partial provider outages visible even when another feed returned rows.
        for row in rows:
            row['feed_errors']=errors
        return rows


def assess(rows, name, keywords, history, now=None,max_age_hours=None):
    now = now or datetime.now(timezone.utc)
    output = []
    limit=max_age_hours if max_age_hours is not None else settings.research_max_age_hours
    for row in rows:
        item = dict(row)
        authority=source_metadata(item)
        item.update(reliability_score=authority["reliability"],source_category=authority["category"])
        try:
            published = datetime.fromisoformat(item['published_at']) if item.get('published_at') else None
            age = (now - published).total_seconds()/3600 if published else float('inf')
        except (ValueError,TypeError):
            age=float('inf')
        freshness = max(0,1-age/limit)
        text=(item['title']+' '+item.get('summary','')).lower()
        aliases=[name.lower(),name.lower().split()[-1]]
        relevance = 1 if name.lower() in text else .85 if any(alias in text for alias in aliases) else .4
        viral = min(1,.45 + .08*len(tokens(item['title'])))
        reason = None
        if age < 0 or age > limit:
            reason = 'Missing, future, or stale publication date'
        elif relevance<.7:
            reason = 'Insufficient personality relevance'
        elif not any(alias in item['title'].casefold() for alias in aliases) and (
                not any(alias in re.split(r'[.!?](?:\s|$)',item.get('summary','').casefold(),maxsplit=1)[0] for alias in aliases)
                or re.search(r'\b(?:era|archive|historic|historical|rivalry faded|remembered)\b',
                             re.split(r'[.!?](?:\s|$)',item.get('summary','').casefold(),maxsplit=1)[0])):
            reason = 'Personality is only incidentally mentioned; story is not focused on the requested theme'
        elif item['reliability_score'] < .7:
            reason = 'Source credibility below threshold'
        elif RUMOR.search(item['title']+' '+item.get('summary','')):
            reason = 'Rumor or unsupported speculation'
        elif any(similar(item['title'], old) for old in history):
            reason = 'Duplicate/recently generated story'
        peers = [r for r in rows if r is not row and similar(item['title'],r['title'])]
        evidence = [dict(item), *[dict(peer) for peer in peers]]
        decision=verify_story(item,evidence,now,max_age_hours=limit)
        status='rejected' if reason else 'verified' if decision['passed'] else 'verification_required'
        if status=='verification_required': reason=decision['reason']
        item['verification']=decision
        evidence[0]['verification']=decision
        item.update(freshness_score=freshness,relevance_score=relevance,viral_potential_score=viral,
                    overall_score=round(.3*freshness+.3*relevance+.25*item['reliability_score']+.15*viral,3),
                    status=status,rejection_reason=reason,evidence=evidence)
        output.append(item)
    return sorted(output,key=lambda row:row['overall_score'],reverse=True)


def research_live(db, personality, channel_id, provider=None,on_window=None,eligible=None):
    keywords = json.loads(personality.research_keywords or personality.keywords or '[]')
    from app.research.verification import canonical_url,duplicate_signals
    provider=provider or RSSResearchProvider()
    now=datetime.now(timezone.utc)
    history=[t.title for t in db.query(Topic).filter_by(personality_id=personality.id,channel_id=channel_id)]
    windows=(3,7,14) if callable(getattr(type(provider),'search_window',None)) else (3,)
    gathered={}
    records={}
    for days in windows:
        if on_window:on_window(days)
        try:
            incoming=provider.search_window(personality.name,keywords,days,now) if len(windows)>1 else provider.candidates(personality.name,keywords)
        except ValueError as exc:
            raise ResearchSearchError(str(exc),[r.id for r in records.values()]) from None
        for row in incoming:
            # Never relabel a feed timestamp or reuse a 3-day query as a 14-day search.
            data=dict(row)
            data['search_window_days']=days
            data['search_retrieved_at']=now.isoformat()
            try:older=(now-datetime.fromisoformat(data['published_at'])).total_seconds()>settings.research_max_age_hours*3600
            except (KeyError,ValueError,TypeError):older=False
            data['period_label']='From the past 14 days' if older else None
            key=canonical_url(data.get('canonical_url') or data['source_url'])
            gathered.setdefault(key,data)
        ranked=assess(list(gathered.values()),personality.name,keywords,history,now,max_age_hours=days*24)
        for data in ranked:
            data['search_window_days']=days
            if data['status']=='verified' and eligible and not eligible(data):
                data['status']='rejected'
                data['rejection_reason']=data.get('rejection_reason') or 'Candidate cannot be used for automatic generation'
        # Publisher copies remain evidence but cannot become duplicate story cards.
        cards=[]
        from app.research.claims import claim_match
        for data in sorted(ranked,key=lambda r:(r['status']=='verified',r.get('published_at') or ''),reverse=True):
            if any(similar(data['title'],old['title']) and (claim_match(data,old)=='supports' or canonical_url(data['source_url'])==canonical_url(old['source_url'])) for old in cards):continue
            cards.append(data)
        for data in cards:
            key=canonical_url(data.get('canonical_url') or data['source_url'])
            data['search_window_days']=days
            record=records.get(key)
            if record is None:
                record=ResearchCandidate(id=new_id(),personality_id=personality.id,channel_id=channel_id,title=data['title'])
                db.add(record);records[key]=record
            record.data=json.dumps(data);record.status=data['status'];record.rejection_reason=data['rejection_reason']
        active={canonical_url(d.get('canonical_url') or d['source_url']) for d in cards}
        for key,record in records.items():
            if key not in active:
                record.status='rejected';record.rejection_reason='Duplicate coverage grouped with another candidate'
        db.commit()
        if any(r.status=='verified' for r in records.values()):break
    return sorted((records[key] for key in active),key=lambda r:(r.status=='verified',json.loads(r.data).get('published_at') or '',json.loads(r.data).get('overall_score',0)),reverse=True)



def topic_from_candidate(db, record):
    if json.loads(record.data).get('content_type')=='historical':
        from app.research.evergreen import historical_topic
        return historical_topic(db,record)
    if record.status != 'verified':
        raise ValueError('Topic verification is required before factual script generation')
    data=json.loads(record.data)
    decision=verify_story(data,data.get('evidence',[]),max_age_hours=candidate_age_hours(data))
    if not decision['passed']:
        raise ValueError('Topic no longer meets verification policy: '+decision['reason'])
    if data.get('evidence'):
        data['evidence'][0]['verification']=decision
        if data.get('search_window_days'):data['evidence'][0]['search_window_days']=data['search_window_days']
    if not data.get('published_at') or (datetime.now(timezone.utc)-datetime.fromisoformat(data['published_at'])).total_seconds()>candidate_age_hours(data)*3600:
        raise ValueError('Research candidate expired. Research current sources again.')
    topic=Topic(id=new_id(),personality_id=record.personality_id,channel_id=record.channel_id,title=record.title,
                source_name=data['source_name'],source_url=data['source_url'],summary=data['summary'],
                published_at=datetime.fromisoformat(data['published_at']),verification_status='verified',
                evidence=json.dumps(data['evidence']),**{k:data[k] for k in ('freshness_score','relevance_score','reliability_score','viral_potential_score','overall_score')})
    from app.research.evergreen import event_identity
    topic.event_identity=event_identity(data)
    db.add(topic)
    db.flush()
    return topic
