"""Independent, read-only historical research; never promotes a Review Draft.

Public search RSS supplies discovery URLs, not proof. Actual accessible article
excerpts must support a dated, focused claim under the normal source/risk policy.
"""
import calendar
import hashlib
import html
import json
import re
import time
import socket
import httpx
from datetime import datetime,timezone,timedelta
from html.parser import HTMLParser
from urllib.parse import urlencode
from urllib.parse import urlparse
import feedparser
from sqlalchemy.exc import IntegrityError
from app.core.config import settings
from app.core.network import public_get
from app.core.security import new_id
from app.models import Topic,ResearchCandidate
from app.research.verification import canonical_url,source_metadata,verify_story,normalize,origins
from app.research.claims import claim_match,signature,CLAIMS
from app.research.live import similar,RUMOR

NO_FALLBACK='No eligible verified news or historical story found. Review candidate reasons, retry research, or change the personality/theme or research sources.'


def hold_reason(trace):
    diagnostics=trace.get('historical_search',{})
    if not diagnostics:return NO_FALLBACK
    counts={}
    for row in diagnostics.get('outcomes',[]):
        status=row.get('status','unknown');counts[status]=counts.get(status,0)+1
    detail=', '.join(f'{key.replace("_"," ")}: {value}' for key,value in sorted(counts.items()))
    limit='Search budget reached; additional candidates remain.' if diagnostics.get('budget_exhausted') else 'Discovered candidates exhausted.'
    return (f'No verified topic after recent, 7-day, 14-day and historical research. '
            f'Historical articles: {diagnostics.get("accessible",0)} accessible / {diagnostics.get("attempted",0)} attempted. '
            f'{limit} {detail}. Configure direct public historical article URLs from credible independent publishers, then retry research.')


class ArticleText(HTMLParser):
    def __init__(self):
        super().__init__();self.parts=[];self.headings=[];self.h1=False;self.skip=0;self.metadata={};self.in_title=False;self.page_title=[];self.in_paragraph=False;self.paragraphs=[];self.article_start=None
    def handle_starttag(self,tag,attrs):
        attrs=dict(attrs)
        if tag in {'script','style','nav','footer'}:self.skip+=1
        if tag=='h1':
            self.h1=True
            if self.article_start is None:self.article_start=len(self.parts)
        if tag=='title':self.in_title=True
        if tag=='p':self.in_paragraph=True
        if tag=='time' and attrs.get('datetime'):self.metadata.setdefault('datePublished',attrs['datetime'])
        if tag=='meta':self.metadata[attrs.get('property') or attrs.get('name','')]=attrs.get('content','')
    def handle_endtag(self,tag):
        if tag in {'script','style','nav','footer'}:self.skip=max(0,self.skip-1)
        if tag=='h1':self.h1=False
        if tag=='title':self.in_title=False
        if tag=='p':self.in_paragraph=False;self.paragraphs.append('. ')
        if tag in {'p','h1','h2','div','li','section'}:self.parts.append('. ')
    def handle_data(self,data):
        if self.in_title:self.page_title.append(data)
        if not self.skip:
            self.parts.append(data+' ')
            if self.in_paragraph:self.paragraphs.append(data+' ')
            if self.h1:self.headings.append(data)
    def text(self):
        # Publisher menus can precede the article by thousands of characters.
        # Prefer readable paragraphs so the lead and claim budget see the article.
        parts=self.parts[self.article_start:] if self.article_start is not None else self.paragraphs if len(' '.join(self.paragraphs).strip(' .'))>=30 else self.parts
        return re.sub(r'\s+',' ',html.unescape(' '.join(parts)))


def aliases(personality):
    return [personality.name,*json.loads(personality.keywords or '[]')]


def focused(text,personality):
    value=normalize(text)
    # Exact configured names/aliases, not generic surnames or incidental matches.
    return any(normalize(alias) and re.search(r'(?<!\w)'+re.escape(normalize(alias))+r'(?!\w)',value) for alias in aliases(personality))


def theme_matches(text,personality,niche=''):
    terms=re.findall(r'\w+',niche or personality.category or '')
    if not terms or normalize(niche or personality.category) in {'general','other'}:return True
    groups={'nba':['nba','basketball'],'football':['football','soccer'],'boxing':['boxing','boxer','heavyweight'],
            'business':['business','company','founded','corporation','revenue'],'sports':['sport','football','basketball','boxing','nba']}
    words={term.casefold() for term in terms if len(term)>2}
    expanded=set(words)
    for word in words:expanded.update(groups.get(word,[]))
    return any(re.search(r'\b'+re.escape(term)+r'\b',text,re.I) for term in expanded)


def event_identity(data):
    words,anchors=signature(data)
    kinds=sorted(key for key,pattern in CLAIMS.items() if re.search(pattern,data['title']+' '+data.get('summary',''),re.I))
    if len(kinds)>1 and 'result' in kinds:kinds.remove('result')
    years=sorted(anchors.get('date',[]))
    if not kinds or not years:return None
    subject=normalize(data.get('subject') or (data.get('personality_match') or [''])[0])
    if not subject:return None
    # Voting totals, wording, and the reporting location do not create a new
    # award/founding story. Keep event-defining anchors, not incidental figures.
    identity_anchors={key:sorted(values) for key,values in anchors.items() if key in {'date','award_name','competition','opponent'}}
    payload={'subject':subject,'kinds':kinds,'anchors':identity_anchors}
    return hashlib.sha256(json.dumps(payload,sort_keys=True).encode()).hexdigest()


def duplicate_story(db,data,channel_id):
    key=event_identity(data)
    for old in db.query(Topic).filter_by(channel_id=channel_id).filter(Topic.verification_status.in_(['verified','demo','limited_verification'])):
        if key and old.event_identity==key:return True
        if old.source_url and canonical_url(old.source_url)==canonical_url(data.get('source_url')):
            # A profile can document several different dated events. The URL
            # alone must not permanently consume every event in that profile.
            if data.get('content_type')!='historical' or not key or not old.event_identity:return True
        if (normalize(data['title'])==normalize(old.title) or
                data.get('content_type')!='historical' and similar(data['title'],old.title)):return True
        for source in json.loads(old.evidence or '[]'):
            # All queued/completed topic reservations count, not just uploaded videos.
            if source.get('title') and claim_match(data,source)=='supports':return True
    return False


def research_fetch(url, **kwargs):
    """At most two attempts; authentication/restricted pages are never retried."""
    for attempt in range(2):
        try:return public_get(url,timeout=10,**kwargs)
        except httpx.HTTPStatusError as exc:
            if attempt or exc.response.status_code not in {429,500,502,503,504}:raise
            delay=exc.response.headers.get('Retry-After','1')
            if not delay.isdigit() or int(delay)>2:raise
            time.sleep(int(delay))
        except (httpx.TimeoutException,httpx.NetworkError):
            if attempt:raise
            time.sleep(.5)


def source_failure(exc):
    if isinstance(exc,socket.gaierror):return 'network_failure','Source DNS lookup failed; retry when connectivity is restored'
    if isinstance(exc,(httpx.TimeoutException,httpx.NetworkError)):return 'network_failure','Source timeout/connection failure after bounded retries'
    if isinstance(exc,httpx.HTTPStatusError):return 'provider_failure',f'Source HTTP {exc.response.status_code}; restricted/error responses are not evidence'
    if isinstance(exc,ValueError) and 'incidental' in str(exc):return 'irrelevant_candidate',str(exc)
    if isinstance(exc,ValueError) and 'dated historical claim' in str(exc):return 'ineligible_claim',str(exc)
    return 'ineligible_source',str(exc) if isinstance(exc,ValueError) else 'Historical source unavailable'


class ResearchResults(list):
    """List-compatible candidates plus diagnostics even when no candidate exists."""
    pass


class EvergreenSearchProvider:
    def discover(self,personality,channel):
        subject=personality.name.replace('"','')
        niche=channel.niche or personality.category
        keywords=' '.join(json.loads(personality.research_keywords or personality.keywords or '[]')[:3])
        query=f'"{subject}" {niche} {keywords} (career OR milestone OR award OR founded OR rivalry OR recovery)'
        configured=getattr(channel,'evergreen_source_urls','[]')
        configured=json.loads(configured) if isinstance(configured,str) else configured
        rows=[{'title':personality.name+' configured historical reference','source_url':url,'summary':'','published_at':None} for url in configured]
        # A separate dated discovery query: never recycle rejected current-news candidates.
        before=(datetime.now(timezone.utc)-timedelta(days=14)).date().isoformat()
        searches=[(settings.evergreen_search_url+'?'+urlencode({'q':query,'format':'rss','setlang':channel.default_language}),['www.bing.com','bing.com']),
                  ('https://news.google.com/rss/search?'+urlencode({'q':query+' before:'+before,'hl':'en-US','gl':'US','ceid':'US:en'}),['news.google.com'])]
        searches.insert(1,(settings.evergreen_search_url+'?'+urlencode({'q':f'"{subject}" {niche} historical award founded milestone','format':'rss','setlang':channel.default_language}),['www.bing.com','bing.com']))
        # Prefer direct publisher articles; aggregator landing pages are discovery,
        # never the article evidence. Keep this extra search bounded to one feed.
        searches.insert(2,(settings.evergreen_search_url+'?'+urlencode({'q':f'"{subject}" (site:theguardian.com/football OR site:skysports.com/football OR site:uefa.com) history award milestone','format':'rss','setlang':channel.default_language}),['www.bing.com','bing.com']))
        self.diagnostics={'searches':[],'source_budget':settings.evergreen_max_sources}
        successes=0
        for url,hosts in searches:
            try:
                body,_=research_fetch(url,hosts=hosts)
                if b'<!DOCTYPE' in body.upper() or b'<!ENTITY' in body.upper():raise ValueError('Unsafe search feed XML')
                parsed=feedparser.parse(body)
                if parsed.bozo and not parsed.entries:raise ValueError('Historical discovery returned invalid RSS')
                successes+=1
                self.diagnostics["searches"].append({"url":url,"status":"retrieved","entries":len(parsed.entries)})
                for item in parsed.entries[:100]:
                    title=html.unescape(re.sub('<[^>]+>',' ',item.get('title','')))
                    summary=html.unescape(re.sub('<[^>]+>',' ',item.get('summary','')))
                    # Search provider misrouting is not relevant evidence.
                    if not focused(title+' '+summary,personality):continue
                    source=item.get('source',{})
                    rows.append({'title':title,'summary':summary,'source_url':item.get('link',''),
                                 'publisher_url':source.get('href'),'source_name':source.get('title'),
                                 'published_at':datetime.fromtimestamp(calendar.timegm(item.published_parsed),timezone.utc).isoformat() if item.get('published_parsed') else None})
            except Exception as exc:
                kind,reason=source_failure(exc);self.diagnostics["searches"].append({"url":url,"status":kind,"reason":reason})
                continue
        if not successes and not rows:raise ValueError('Historical search providers unavailable; check connectivity or configure public reference URLs')
        # Do not spend the article-access budget on duplicate discovery rows.
        unique={}
        for row in rows:unique.setdefault(canonical_url(row.get('source_url')),row)
        return list(unique.values())[:min(80,settings.evergreen_max_sources*4)]


def load_article(row,personality):
    # A configured publisher identity is necessary but not sufficient evidence.
    authority=source_metadata(row)
    if authority['category']=='unknown' or authority['reliability']<.7:raise ValueError('Unrecognized or insufficiently credible publisher')
    body,_=research_fetch(row['source_url'],max_bytes=2*1024*1024)
    parser=ArticleText();parser.feed(body.decode('utf-8',errors='replace'))
    text=parser.text()
    if urlparse(row['source_url']).hostname=='news.google.com' and not focused(text,personality):
        raise ValueError('Discovery link returned a Google News landing page, not publisher article evidence. Configure a direct public article URL.')
    if re.search(r'access denied|subscribe to continue|captcha|enable javascript',text,re.I):raise ValueError('Article is restricted or unavailable')
    title=' '.join(parser.headings) or parser.metadata.get('og:title','')
    if not focused(title+' '+text[:1000],personality):raise ValueError('Personality is only incidental or absent in the accessible article')
    raw=body.decode('utf-8',errors='replace')
    structured=re.search(r'"datePublished"\s*:\s*"([^"\n]+)"',raw)
    published=parser.metadata.get('article:published_time') or parser.metadata.get('datePublished') or (structured[1] if structured else None) or row.get('published_at')
    if published:
        try:
            date=datetime.fromisoformat(published.replace('Z','+00:00'))
            if date.tzinfo is None:date=date.replace(tzinfo=timezone.utc)
            published=date.isoformat()
        except ValueError:published=None
    return {**row,'article_title':title,'article_excerpt':text[:30000],'published_at':published,
            'article_section':parser.metadata.get('article:section') or ' '.join(parser.page_title),
            'originating_sources':sorted(origins({'source_name':parser.metadata.get('author',''),'summary':' '.join(parser.parts)})),
            'source_name':parser.metadata.get('og:site_name') or authority['publisher_group'],
            'publisher_group':authority['publisher_group'],'access_checked_at':datetime.now(timezone.utc).isoformat()}


def historical_claims(article,personality,channel):
    claims=[]
    text=re.sub(r'\b([A-Z])\.(?=\s+[A-Z])',lambda m:m[1]+'\u2024',article['article_excerpt'])
    for sentence in re.split(r'(?<=[.!?])\s+',text):
        sentence=sentence.replace('\u2024','.')
        sentence=sentence.strip(' .')
        if re.match(r'Live\s+\d',sentence,re.I):continue  # related-news cards, not article claims
        if not 30<=len(sentence)<=280 or not focused(sentence,personality):continue
        # A mention after somebody else's award/result is supporting context,
        # not a historical claim about this configured subject.
        normalized=normalize(sentence)
        positions=[m.start() for alias in aliases(personality) if normalize(alias)
                   for m in re.finditer(r'(?<!\w)'+re.escape(normalize(alias))+r'(?!\w)',normalized)]
        prefix=normalized[:min(positions)] if positions else normalized
        if any(re.search(pattern,prefix,re.I) for pattern in CLAIMS.values()):continue
        years=re.findall(r'\b(?:19|20)\d{2}\b',sentence)
        supported=sentence
        date_basis='explicit_year'
        # A contemporaneous report explicitly saying "last night" can be
        # anchored to its publication year, except at the year boundary.
        if not years and re.search(r'\blast night\b',sentence,re.I) and article.get('published_at'):
            published=datetime.fromisoformat(article['published_at'])
            if (published.month,published.day)!=(1,1):
                years=[str(published.year)]
                supported=sentence+f' [Publication year: {published.year}]'
                sentence=f'In {published.year}, '+re.sub(r'\s+last night\b','',sentence,flags=re.I)
                date_basis='last_night_in_dated_report'
        if len(set(years))!=1:continue
        year=int(years[0])
        # A year-only event must be a completed year, never a supposed current fact.
        if year>=datetime.now(timezone.utc).year or year<1800:continue
        if not any(re.search(pattern,sentence,re.I) for pattern in CLAIMS.values()):continue
        if not theme_matches(article['article_title']+' '+article.get('article_section','')+' '+sentence,personality,channel.niche):continue
        if RUMOR.search(sentence):continue
        claims.append({**{key:value for key,value in article.items() if key!='article_excerpt'},
            'title':sentence,'summary':sentence,'supported_excerpt':supported,'event_date_basis':date_basis,
            'subject':personality.name,'personality_match':aliases(personality),'event_date':f'{year}-01-01',
            'event_date_precision':'year','content_type':'historical','period_label':'Historical / evergreen',
            'relevance_score':1.0,'freshness_score':0.0,'viral_potential_score':.5,
            'reliability_score':source_metadata(article)['reliability']})
    return claims[:4]


def research_evergreen(db,personality,channel,provider=None,progress=None):
    provider=provider or EvergreenSearchProvider()
    discovered=provider.discover(personality,channel)
    seen=set();claims=[];rejected=[];accessible=0;attempted=0
    started=time.monotonic();budget_exhausted=False
    diagnostics={'discovered':len(discovered),'attempted':0,'accessible':0,'source_budget':settings.evergreen_max_sources,
        'discovery':getattr(provider,'diagnostics',{}) if isinstance(getattr(provider,'diagnostics',{}),dict) else {},'outcomes':[]}
    # Round-robin publishers so repeated excerpts from one publisher cannot consume every slot.
    groups={}
    for row in discovered:groups.setdefault(source_metadata(row)['publisher_group'],[]).append(row)
    ordered=[]
    while any(groups.values()):
        for values in groups.values():
            if values:ordered.append(values.pop(0))
    for row in ordered:
        url=canonical_url(row.get('source_url'))
        if url in seen:continue
        seen.add(url)
        try:
            authority=source_metadata(row)
            if authority['category']=='unknown' or authority['reliability']<.7:raise ValueError('Unrecognized or insufficiently credible publisher')
            if attempted>=settings.evergreen_max_sources or time.monotonic()-started>=150:
                budget_exhausted=True;break
            attempted+=1
            article=load_article(row,personality);accessible+=1
            values=historical_claims(article,personality,channel)
            if not values:raise ValueError('No focused, theme-matching dated historical claim in accessible source')
            claims.extend(values)
            diagnostics['outcomes'].append({'url':url,'status':'claims_found','claims':len(values)})
        except Exception as exc:
            # Persist actionable source-level outcomes, without raw provider exceptions/secrets.
            failure,reason=source_failure(exc)
            diagnostics['outcomes'].append({'url':url,'status':failure,'reason':reason})
            rejected.append({**row,'status':'rejected','rejection_reason':reason,
                             'source_name':source_metadata(row)['publisher_group'],'content_type':'historical','subject':personality.name})
    ranked=[]
    for claim in claims:
        kinds={key for key,pattern in CLAIMS.items() if re.search(pattern,claim['summary'],re.I)}
        repeatable=bool(kinds) and kinds<={'award','statistics','result','fixture'}
        evidence=[other for other in claims if (not repeatable or other['event_date']==claim['event_date']) and
                  (canonical_url(other['source_url'])==canonical_url(claim['source_url']) or claim_match(claim,other) in {'supports','conflict'})]
        decision=verify_story(claim,evidence,historical=True)
        duplicate=duplicate_story(db,claim,channel.id)
        reason='Duplicate historical event already queued/generated for this channel' if duplicate else None if decision['passed'] else decision['reason']
        ranked.append({**claim,'verification':decision,'evidence':evidence,'event_identity':event_identity(claim),
                       'overall_score':round(.6*claim['reliability_score']+.3*claim['relevance_score']+.1*claim['viral_potential_score'],3),
                       'status':'verified' if decision['passed'] and not duplicate else 'rejected' if duplicate else 'verification_required','rejection_reason':reason})
    diagnostics.update(attempted=attempted,accessible=accessible,budget_exhausted=budget_exhausted,remaining_unattempted=max(0,len(ordered)-len(seen)+(1 if budget_exhausted else 0)),
        outcome='budget_exhausted' if budget_exhausted else 'candidates_exhausted')
    records=ResearchResults();records.diagnostics=diagnostics;event_seen=set()
    for data in sorted(ranked,key=lambda d:(d['status']=='verified',d['overall_score'],d.get('event_date','')),reverse=True)+rejected:
        key=data.get('event_identity')
        if key and key in event_seen:continue
        if key:event_seen.add(key)
        data['research_diagnostics']=diagnostics
        record=ResearchCandidate(id=new_id(),channel_id=channel.id,personality_id=personality.id,title=data['title'][:500],
                                 status=data['status'],rejection_reason=data['rejection_reason'],data=json.dumps(data))
        db.add(record);records.append(record)
    db.commit()
    return records


def historical_topic(db,record):
    data=json.loads(record.data)
    decision=verify_story(data,data.get('evidence',[]),historical=True)
    if record.status!='verified' or not decision['passed']:raise ValueError('Historical candidate does not meet full verification policy')
    if duplicate_story(db,data,record.channel_id):raise ValueError('Duplicate historical event')
    evidence=data.get('evidence',[])
    if evidence:evidence[0]={**evidence[0],'verification':decision,'content_type':'historical','event_identity':data.get('event_identity')}
    topic=Topic(id=new_id(),channel_id=record.channel_id,personality_id=record.personality_id,title='Historical: '+data['title'],
                event_identity=data.get('event_identity'),source_name=data['source_name'],source_url=data['source_url'],summary=data['summary'],
                published_at=datetime.fromisoformat(data['published_at']) if data.get('published_at') else None,
                verification_status='verified',evidence=json.dumps(evidence),
                **{key:data[key] for key in ('freshness_score','relevance_score','reliability_score','viral_potential_score','overall_score')})
    db.add(topic);db.flush()
    return topic
