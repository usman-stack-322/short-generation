"""Neutral discovery, readable evidence, provenance and primary-media limitations."""
import re,json,hashlib,html
from html.parser import HTMLParser
from urllib.parse import urlparse,urlencode,parse_qs,urljoin
from difflib import SequenceMatcher
import feedparser,httpx
from app.core.config import settings
from app.core.network import public_get
from app.research.evergreen import ArticleText
from app.research.verification import source_metadata

class ResearchFailure(ValueError):
    def __init__(self,code,message,sources=None,diagnostics=None):
        super().__init__(message);self.code=code;self.sources=sources or [];self.diagnostics=diagnostics or []

def norm(text):return ' '.join(re.findall(r'\w+',html.unescape(text).casefold()))

def lead_from_title(title,analysis=None):
    analysis=analysis or {}
    clean=re.sub(r'\b(?:GO OFF|GOES OFF|SLAMS?|DESTROYS?|DISSING|BLASTS?|EXPOSES?|ROASTS?)\b','|',title,flags=re.I)
    clean=re.sub(r'\b(?:On|For|After|Over|At|The|And)\b','|',clean)
    people=re.findall(r'\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,2}\b',clean)
    people+=re.findall(r'(?:&|\band\b)\s+([A-Z][a-z]+(?:\s+Da\s+[A-Z][a-z]+)?)',title)
    people+=[x for x in analysis.get('people',[]) if norm(x) in norm(title)]
    people=sorted(set(p.strip() for p in people if p.strip()),key=lambda p:norm(title).find(norm(p)))[:6]
    STOPWORDS={'Why','How','What','When','Where','Who','Which','Collapse','Collapsed','Dominating','America','Building','Built','Empire','History','Story','Complete','Secret'}
    people=[p for p in people if not any(w in STOPWORDS for w in p.split()) or any(norm(w) in norm(p) for w in analysis.get('people',[]))]
    if not analysis.get('people') and not re.search(r'&|go off|dissing|slams|respond|critic',title,re.I):people=[]
    quotes=re.findall(r'[“"]([^”"]{3,160})[”"]',title)
    return {'people':people,'alleged_claims':analysis.get('alleged_claims',[]),'unverified_quotes':list(dict.fromkeys(quotes)),'title_is_unverified_lead':True}

def neutral_queries(analysis,lead):
    names=lead.get('people',[]);queries=[]
    if len(names)>=3:
        queries.append(' '.join(names))
        # Search both the central debate and each participant; avoid a quoted,
        # overconstrained headline or accidental duplicate names.
        for i in range(min(len(names)-1,3)):
            subset=list(dict.fromkeys([names[i],names[-2],names[-1]]))
            queries.append(' '.join('"'+x+'"' for x in subset))
        queries+=[' '.join(names[-3:])+' original podcast response',
                  ' '.join(names[:3])+' original interview']
    queries+=analysis.get('search_queries',[])
    return list(dict.fromkeys(q[:400] for q in queries if q.strip()))[:6]

class Links(HTMLParser):
    def __init__(self):super().__init__();self.results=[];self.current=None;self.links=[];self.canonical=None;self.transcripts=[]
    def handle_starttag(self,tag,attrs):
        a=dict(attrs);url=a.get('href') or a.get('src')
        if url and tag in {'a','iframe'}:self.links.append(url)
        if tag=='link' and a.get('rel')=='canonical':self.canonical=a.get('href')
        if tag=='a' and 'result__a' in a.get('class',''):self.current={'url':a.get('href',''),'title':''}
        if tag=='podcast:transcript' and a.get('url'):self.transcripts.append(a['url'])
    def handle_data(self,text):
        if self.current:self.current['title']+=text
    def handle_endtag(self,tag):
        if tag=='a' and self.current:self.results.append(self.current);self.current=None

def unwrap(url):
    if url.startswith('//'):url='https:'+url
    p=urlparse(url)
    if p.hostname and p.hostname.endswith('duckduckgo.com'):return parse_qs(p.query).get('uddg',[url])[0]
    return url

def safe_failure(exc):
    if isinstance(exc,httpx.HTTPStatusError):return 'HTTP '+str(exc.response.status_code)+'; access restriction/quota respected'
    if isinstance(exc,httpx.DecodingError):return 'Content decoding failed'
    if isinstance(exc,(httpx.TimeoutException,TimeoutError)):return 'Network timeout'
    if isinstance(exc,(httpx.NetworkError,OSError)):return 'Network/DNS/connection failure'
    if isinstance(exc,ValueError):return re.sub(r'https?://\S+','[URL omitted]',str(exc))[:160]
    return type(exc).__name__

def relevant(text,people):
    if not people:return True
    return sum(norm(p) in norm(text) for p in people)>=min(2,len(people))

def discover(analysis,lead,diag):
    found=[];seen=set();queries=neutral_queries(analysis,lead)
    for query in queries:
        providers=['brave'] if settings.title_short_search_provider=='brave' else ['bing_rss','duckduckgo_html']
        for provider in providers:
            record={'stage':'discovery','provider':provider,'query':query}
            try:
                if provider=='brave':
                    if not settings.brave_search_api_key:raise ValueError('BRAVE_SEARCH_API_KEY is not configured; no paid subscription activated')
                    r=httpx.get('https://api.search.brave.com/res/v1/web/search',params={'q':query,'count':10},headers={'X-Subscription-Token':settings.brave_search_api_key},timeout=20,trust_env=False,follow_redirects=False);r.raise_for_status()
                    rows=[{'url':x['url'],'title':x.get('title',''),'summary':x.get('description','')} for x in r.json().get('web',{}).get('results',[])]
                else:
                    endpoint='https://www.bing.com/search' if provider=='bing_rss' else 'https://html.duckduckgo.com/html/'
                    params={'q':query,'format':'rss'} if provider=='bing_rss' else {'q':query}
                    body,_=public_get(endpoint+'?'+urlencode(params),hosts={'www.bing.com','bing.com'} if provider=='bing_rss' else {'duckduckgo.com'},max_bytes=1200000,timeout=15)
                    if b'anomaly-modal' in body.lower() or b'captcha' in body.lower():raise ValueError('Search challenge encountered; not bypassed')
                    if provider=='bing_rss':rows=[{'url':x.get('link',''),'title':x.get('title',''),'summary':x.get('summary','')} for x in feedparser.parse(body).entries[:10]]
                    else:
                        parser=Links();parser.feed(body.decode('utf8',errors='replace'));rows=parser.results
                eligible=0
                for row in rows:
                    row['url']=unwrap(row['url']);match=relevant(row.get('title','')+' '+row.get('summary','')+' '+row['url'],lead.get('people',[]))
                    diag.append({'stage':'candidate','provider':provider,'url':row['url'],'title':row.get('title',''),'result':'relevant_lead' if match else 'entity_mismatch'})
                    if match:
                        eligible+=1
                        if row['url'] not in seen:found.append(row);seen.add(row['url'])
                record.update(result='ok' if eligible else 'irrelevant_results',results=len(rows),relevant=eligible)
            except Exception as exc:record.update(result='search_failed',reason=safe_failure(exc))
            diag.append(record)
            if len(found)>=18:return found
    return found

def youtube_id(url):
    p=urlparse(url);host=(p.hostname or '').removeprefix('www.')
    id=(p.path.strip('/') if host=='youtu.be' else (p.path.split('/')[2] if p.path.startswith(('/embed/','/shorts/')) else parse_qs(p.query).get('v',[''])[0]) if host in {'youtube.com','youtube-nocookie.com'} else '')
    return id if re.fullmatch(r'[\w-]{11}',id) else None

def media_metadata(url):
    id=youtube_id(url)
    if not id:raise ValueError('Unsupported public media URL')
    body,_=public_get('https://www.youtube.com/oembed?'+urlencode({'url':'https://www.youtube.com/watch?v='+id,'format':'json'}),hosts={'youtube.com'},max_bytes=100000,timeout=15)
    meta=json.loads(body)
    return {'url':'https://www.youtube.com/watch?v='+id,'title':meta.get('title',''),'creator':meta.get('author_name',''),'creator_url':meta.get('author_url',''),
        'kind':'video_metadata','transcript_status':'unavailable: no owner-authorized captions or publisher transcript supplied','evidence_eligible':False,'excerpt':''}

def _extract_json_value(text,marker):
    idx=text.find(marker)
    if idx==-1:return None
    pos=idx+len(marker)
    while pos<len(text) and text[pos].isspace():pos+=1
    if pos>=len(text):return None
    try:
        val,_=json.JSONDecoder().raw_decode(text[pos:])
        return val
    except Exception:return None

def _parse_caption_payload(body):
    if not body:return ''
    stripped=body.lstrip()
    if stripped.startswith('{'):
        try:
            payload=json.loads(stripped)
            parts=[]
            for ev in payload.get('events') or []:
                for seg in ev.get('segs') or []:
                    u=seg.get('utf8') or ''
                    if u and u!='\n':parts.append(html.unescape(u))
            return re.sub(r'\s+',' ',' '.join(parts)).strip()
        except Exception:return ''
    try:
        import xml.etree.ElementTree as ET
        root=ET.fromstring(body)
        lines=[html.unescape(''.join(el.itertext())) for el in list(root.iter('text'))+list(root.iter('p'))]
        return re.sub(r'\s+',' ',' '.join(l for l in lines if l and l.strip())).strip()
    except Exception:return ''

def _fetch_caption_tracks(tracks,headers,cookies=None):
    if not isinstance(tracks,list):return ''
    def _rank(t):
        lang=(t.get('languageCode') or '').lower()
        is_en=0 if lang.startswith('en') else 1
        is_asr=1 if t.get('kind')=='asr' else 0
        return (is_en,is_asr)
    best_text=''
    for t in sorted(tracks,key=_rank):
        b_url=t.get('baseUrl')
        if not b_url:continue
        candidates=[b_url+('&fmt=json3' if 'fmt=' not in b_url else ''),b_url]
        for cu in dict.fromkeys(candidates):
            try:
                sub=httpx.get(cu,headers=headers,cookies=cookies,timeout=12,follow_redirects=True)
                if sub.status_code==200:
                    text=_parse_caption_payload(sub.text)
                    if len(text.split())>len(best_text.split()):best_text=text
                    if len(best_text.split())>=40:return best_text
            except Exception:pass
    return best_text

def _clean_youtube_desc(desc):
    lines=[]
    for raw in (desc or '').splitlines():
        line=raw.strip()
        if not line:continue
        low=line.lower()
        if any(p in low for p in ('http://','https://','subscribe','follow us','follow me','use code','promo code','cashapp','venmo','patreon','merch','business inquiries')):continue
        lines.append(re.sub(r'https?://\S+','',line).strip())
    return re.sub(r'\s+',' ',' '.join(lines)).strip()

def read_youtube(url,is_user=False):
    yid=youtube_id(url)
    if not yid:return None,None
    watch_url=f'https://www.youtube.com/watch?v={yid}'
    meta={}
    try:
        body,_=public_get('https://www.youtube.com/oembed?'+urlencode({'url':watch_url,'format':'json'}),hosts={'youtube.com'},max_bytes=100000,timeout=12)
        meta=json.loads(body)
    except Exception:pass
    title=meta.get('title') or ''
    creator=meta.get('author_name') or ''
    creator_url=meta.get('author_url') or ''
    transcript=''
    desc=''
    headers={'User-Agent':'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36','Accept-Language':'en-US,en;q=0.9'}
    cookies={'CONSENT':'YES+cb.20210328-17-p0.en+FX+999','SOCS':'CAI'}
    try:
        res=httpx.get(watch_url,headers=headers,cookies=cookies,timeout=15,follow_redirects=True)
        if res.status_code==200:
            page_text=res.text
            if not title:
                t_m=re.search(r'<title>(.*?)</title>',page_text)
                if t_m:title=html.unescape(t_m.group(1).removesuffix(' - YouTube'))
            tracks=_extract_json_value(page_text,'"captionTracks":')
            if isinstance(tracks,list):transcript=_fetch_caption_tracks(tracks,headers,cookies)
            raw_d=_extract_json_value(page_text,'"shortDescription":')
            if isinstance(raw_d,str):desc=raw_d
    except Exception:pass
    if len(transcript.split())<40:
        try:
            inn=httpx.post(
                'https://www.youtube.com/youtubei/v1/player?prettyPrint=false',
                json={'context':{'client':{'clientName':'ANDROID','clientVersion':'20.10.38','hl':'en','gl':'US'}},'videoId':yid},
                headers={'Content-Type':'application/json','User-Agent':'com.google.android.youtube/20.10.38 (Linux; U; Android 14)'},
                timeout=12,
            )
            if inn.status_code==200:
                pdata=inn.json()
                vd=pdata.get('videoDetails') or {}
                if not title and vd.get('title'):title=vd['title']
                if not creator and vd.get('author'):creator=vd['author']
                if not desc and vd.get('shortDescription'):desc=vd['shortDescription']
                tracks=((pdata.get('captions') or {}).get('playerCaptionsTracklistRenderer') or {}).get('captionTracks')
                if isinstance(tracks,list):
                    cand=_fetch_caption_tracks(tracks,headers,cookies)
                    if len(cand.split())>len(transcript.split()):transcript=cand
        except Exception:pass
    clean_desc=_clean_youtube_desc(desc)
    excerpt=transcript if len(transcript.split())>=20 else ('\n\n'.join(p for p in (title,clean_desc) if p) if len(clean_desc.split())>=20 else '')
    if not excerpt or len(excerpt.split())<20:
        item={'url':watch_url,'title':title or 'YouTube Video','creator':creator,'creator_url':creator_url,
              'kind':'video_metadata','transcript_status':'unavailable: no owner-authorized captions or publisher transcript supplied','evidence_eligible':False,'excerpt':''}
        return None,item
    has_transcript=bool(transcript and len(transcript.split())>=20)
    source={
        'url':watch_url,'title':title or 'YouTube Video','excerpt':excerpt[:18000],
        'retrieved_sha256':hashlib.sha256(excerpt.encode('utf8')).hexdigest(),
        'kind':'publisher_transcript' if has_transcript else 'article','evidence_eligible':True,
        'transcript_status':'captions extracted' if has_transcript else 'description and video content extracted',
        'published_at':None,'primary_links':[],
        'publisher_group':'youtube_'+(re.sub(r'\W+','_',creator.lower()).strip('_') or yid),
        'origin':'user_url' if is_user else 'automatic'
    }
    media_item={
        'url':watch_url,'title':title or 'YouTube Video','creator':creator,'creator_url':creator_url,
        'kind':'video_metadata','transcript_status':source['transcript_status'],'evidence_eligible':True,'excerpt':excerpt[:500]
    }
    return source,media_item

def fetch_wikipedia_sources(topic,lead):
    queries=[topic]
    if lead.get('people'):
        queries.extend([p for p in lead['people'] if len(p.split())<=3][:2])
    results=[];seen=set()
    for q in queries:
        if not q or len(q.strip())<3:continue
        clean_q=re.sub(r'^(Why|How|What|When|Where)\s+','',q,flags=re.I).strip()
        ua='AIShortsPlatform/0.2 (local user-operated research; contact: dev@example.com)'
        try:
            r=httpx.get('https://en.wikipedia.org/w/api.php',params={
                'action':'query','list':'search','srsearch':clean_q or q,'format':'json','utf8':1
            },headers={'User-Agent':ua},timeout=10)
            if r.status_code==200:
                hits=r.json().get('query',{}).get('search',[])
                for hit in hits[:2]:
                    title=hit.get('title')
                    if not title or title in seen:continue
                    seen.add(title)
                    er=httpx.get('https://en.wikipedia.org/w/api.php',params={
                        'action':'query','prop':'extracts','explaintext':1,'exsentences':15,'titles':title,'format':'json'
                    },headers={'User-Agent':ua},timeout=10)
                    if er.status_code==200:
                        pages=er.json().get('query',{}).get('pages',{})
                        for p in pages.values():
                            extract=p.get('extract','').strip()
                            if len(extract.split())>=40:
                                page_url=f"https://en.wikipedia.org/wiki/{title.replace(' ','_')}"
                                results.append({
                                    'url':page_url,'title':f"{title} - Wikipedia",'excerpt':extract[:18000],
                                    'retrieved_sha256':hashlib.sha256(extract.encode('utf8')).hexdigest(),
                                    'kind':'article','evidence_eligible':True,'published_at':None,
                                    'primary_links':[],'publisher_group':'wikipedia','origin':'automatic'
                                })
                    if len(results)>=2:break
        except Exception:pass
        if len(results)>=2:break
    return results

def publisher_group(source):
    known=source_metadata({'source_url':source['url']});host=(urlparse(source['url']).hostname or '').removeprefix('www.')
    return known.get('publisher_group') if known.get('verified_identity') else '.'.join(host.split('.')[-3:] if host.endswith('.ac.uk') else host.split('.')[-2:])

def group_sources(sources):
    parents=list(range(len(sources)))
    def root(i):
        while parents[i]!=i:i=parents[i]
        return i
    for i,a in enumerate(sources):
        for j,b in enumerate(sources[:i]):
            reason=None
            def original_refs(s):return {('youtube:'+youtube_id(u)) if youtube_id(u) else u.split('?')[0].replace('twitter.com','x.com') for u in s.get('primary_links',[]) if youtube_id(u) or re.search(r'(?:twitter|x)\.com/[^/]+/status/\d+',u)}
            if a['publisher_group']==b['publisher_group']:reason='same publisher/original syndication group'
            elif a.get('canonical_url')==b.get('canonical_url') and a.get('canonical_url'):reason='same canonical original'
            elif a.get('origin_url') and a.get('origin_url')==b.get('origin_url'):reason='same originating report'
            elif original_refs(a)&original_refs(b):reason='shared original episode/post; repeat reporting is not independent corroboration'
            elif min(len(a['excerpt'].split()),len(b['excerpt'].split()))>=80 and SequenceMatcher(None,norm(a['excerpt']),norm(b['excerpt'])).ratio()>=.80:reason='near-duplicate article text'
            if reason:parents[root(i)]=root(j);a.setdefault('independence_notes',[]).append(reason)
    for i,s in enumerate(sources):s['independence_group']='G'+str(root(i)+1)
    return len({s['independence_group'] for s in sources})

def read_source(url,trusted):
    if not trusted(url):raise ValueError('Publisher not in reviewed trusted-source policy')
    body,headers=public_get(url,hosts={(urlparse(url).hostname or '').removeprefix('www.')},max_bytes=1800000,timeout=18)
    if any(x in headers.get('content-type','').lower() for x in ['rss','xml']):return read_podcast(url,body,trusted)
    if 'html' not in headers.get('content-type','').lower():raise ValueError('Unsupported source format: readable HTML or publisher podcast RSS required')
    text=body.decode('utf8',errors='replace');page=ArticleText();page.feed(text);content=page.text();links=Links();links.feed(text)
    if len(content.split())<80:raise ValueError('Insufficient readable article text')
    if any(x in content[:1500].lower() for x in ['just a moment...','verify you are human','access denied']):raise ValueError('Publisher access challenge; not bypassed')
    source={'url':url,'title':''.join(page.page_title)[:250] or urlparse(url).hostname,'excerpt':content[:18000],'retrieved_sha256':hashlib.sha256(body).hexdigest(),
        'kind':'article','evidence_eligible':True,'canonical_url':urljoin(url,links.canonical) if links.canonical else url,'published_at':page.metadata.get('article:published_time') or page.metadata.get('datePublished'),
        'primary_links':list(dict.fromkeys(urljoin(url,x) for x in links.links if any(h in x for h in ['youtube.com/watch','youtube.com/embed/','youtube-nocookie.com/embed/','youtu.be/','instagram.com/p/','twitter.com/','x.com/','podcasts.apple.com/'])))[:8]}
    source['publisher_group']=publisher_group(source)
    # Canonical partner pages/syndication cannot manufacture a second publisher.
    canonical_host=(urlparse(source['canonical_url']).hostname or '').removeprefix('www.')
    if canonical_host and canonical_host!=(urlparse(url).hostname or '').removeprefix('www.') and trusted(source['canonical_url']):
        source['origin_url']=source['canonical_url'];source['publisher_group']=publisher_group({'url':source['canonical_url']})
    if 'yahoo.com' in url:
        for label,group in [('panthers wire','usa_today'),('vibe','penske_media'),('sporting news','sporting_news'),("men’s journal",'arena_group'),("men\'s journal",'arena_group')]:
            if label in content[:1800].lower():source['publisher_group']=group;source['syndication_note']='Yahoo distribution of '+label;break
        else:source['publisher_group']='yahoo_unknown_origin';source['evidence_eligible']=False;source['syndication_note']='Original publisher unresolved; not independent evidence'
    for label,group in [('the associated press','associated_press'),('associated press contributed','associated_press'),('by reuters','reuters')]:
        if label in content[:1800].lower():source['publisher_group']=group;source['syndication_note']='Origin attribution: '+label;break
    return source

def read_podcast(url,body,trusted):
    import xml.etree.ElementTree as ET
    # Only publisher-provided podcast:transcript links; never undocumented caption endpoints.
    tree=ET.fromstring(body);items=tree.findall('.//item')[:10]
    for item in items:
        transcript=item.find('{https://podcastindex.org/namespace/1.0}transcript')
        if transcript is None:continue
        target=urljoin(url,transcript.attrib.get('url',''));kind=transcript.attrib.get('type','')
        if not trusted(target) or kind not in {'text/plain','text/vtt'}:continue
        raw,headers=public_get(target,hosts={(urlparse(target).hostname or '').removeprefix('www.')},max_bytes=800000,timeout=18)
        if not any(x in headers.get('content-type','') for x in ['text/plain','text/vtt']):continue
        text=raw.decode('utf8',errors='replace')
        if len(text.split())<80:continue
        source={'url':url,'title':item.findtext('title') or 'Publisher podcast transcript','excerpt':text[:18000],'retrieved_sha256':hashlib.sha256(raw).hexdigest(),'kind':'publisher_transcript','transcript_url':target,'transcript_status':'publisher public transcript retrieved','evidence_eligible':True,'published_at':item.findtext('pubDate'),'primary_links':[]}
        source['publisher_group']=publisher_group(source);return source
    raise ValueError('Podcast metadata accessible, but no readable trusted publisher transcript is available; speech unverified')

def fetch_user_urls(source_urls,diag=None):
    """Pre-read user-supplied URLs (e.g. YouTube transcript or trusted articles) before Analysis."""
    diag=diag if diag is not None else []
    sources=[];media=[];seen=set()
    for url in (source_urls or []):
        if url in seen:continue
        seen.add(url)
        try:
            if youtube_id(url):
                yt_source,yt_media=read_youtube(url,is_user=True)
                if yt_media:media.append(yt_media)
                if yt_source:
                    yt_source['id']='S'+str(len(sources)+1)
                    sources.append(yt_source)
                    diag.append({'stage':'primary_media','url':url,'result':'readable','words':len(yt_source['excerpt'].split()),'publisher_group':yt_source['publisher_group']})
                else:
                    item=yt_media or media_metadata(url)
                    if not yt_media:media.append(item)
                    diag.append({'stage':'primary_media','url':url,'result':'metadata_only','reason':item['transcript_status']})
                continue
            source=read_source(url,lambda u:True)
            source['id']='S'+str(len(sources)+1);source['origin']='user_url';sources.append(source)
            diag.append({'stage':'article','url':url,'result':'readable','words':len(source['excerpt'].split()),'publisher_group':source['publisher_group']})
        except Exception as exc:
            diag.append({'stage':'article','url':url,'result':'fetch_failed','reason':safe_failure(exc)})
    return sources,media,diag


def collect(analysis,source_urls,diag,trusted,lead,progress=None,style='educational',prefetched_user=None):
    sources=[];media=[];seen=set();attempts=0
    if prefetched_user is not None:
        u_sources,u_media,u_diag=prefetched_user
        for s in u_sources:
            if s['url'] not in seen:
                seen.add(s['url']);sc=dict(s);sc['id']='S'+str(len(sources)+1);sources.append(sc)
        for m in u_media:
            if not any(x.get('url')==m.get('url') for x in media):media.append(m)
        diag.extend(u_diag)
        if progress and sources:progress(sources,media)
    elif source_urls:
        u_sources,u_media,u_diag=fetch_user_urls(source_urls,diag=diag)
        for s in u_sources:
            seen.add(s['url']);s['id']='S'+str(len(sources)+1);sources.append(s)
        media.extend(u_media)
        if progress and sources:progress(sources,media)

    user_eligible=[s for s in sources if s.get('evidence_eligible')]
    user_rich=[s for s in user_eligible if len((s.get('excerpt') or '').split())>=50]
    if source_urls and user_rich and group_sources(user_eligible)>=1:
        return sources,media

    for u in source_urls:seen.add(u)
    rows=discover(analysis,lead,diag)
    for row in rows:
        url=row['url']
        if url in seen:continue
        seen.add(url)
        is_user_url = url in source_urls
        try:
            if youtube_id(url):
                yt_source,yt_media=read_youtube(url,is_user=is_user_url)
                if yt_media:media.append(yt_media)
                if yt_source:
                    yt_source['id']='S'+str(len(sources)+1)
                    sources.append(yt_source)
                    diag.append({'stage':'primary_media','url':url,'result':'readable','words':len(yt_source['excerpt'].split()),'publisher_group':yt_source['publisher_group']})
                    if progress:progress(sources,media)
                    continue
                else:
                    item=media_metadata(url);media.append(item);diag.append({'stage':'primary_media','url':url,'result':'metadata_only','reason':item['transcript_status']});continue
            if not is_user_url and not trusted(url):diag.append({'stage':'article','url':url,'result':'publisher_unreviewed'});continue
            attempts+=1
            if attempts>12:break
            source=read_source(url,lambda u:True if is_user_url else trusted(u))
            if not is_user_url and lead.get('people') and not relevant(source['title']+' '+source['excerpt'],lead.get('people',[])):
                topic_words=[w for w in norm(analysis.get('topic','')+' '+analysis.get('angle','')).split() if len(w)>3]
                if not any(w in norm(source['title']+' '+source['excerpt']) for w in topic_words):
                    raise ValueError('Readable source does not match the extracted people')
            source['id']='S'+str(len(sources)+1);source['origin']='user_url' if is_user_url else 'automatic';sources.append(source)
            diag.append({'stage':'article','url':url,'result':'readable','words':len(source['excerpt'].split()),'publisher_group':source['publisher_group']})
            if progress:progress(sources,media)
        except Exception as exc:diag.append({'stage':'article','url':url,'result':'fetch_failed','reason':safe_failure(exc)})
        if len(sources)>=6:break
    # If sources are sparse for evergreen / storytelling topics, fetch Wikipedia references
    is_evergreen = bool(source_urls) or style in {'storytelling','documentary','evergreen'}
    if len(sources)<2 and is_evergreen:
        topic_str=analysis.get('topic') or analysis.get('angle') or (media[0].get('title') if media else '') or ' '.join(lead.get('people',[]))
        if topic_str:
            wiki_sources=fetch_wikipedia_sources(topic_str,lead)
            for ws in wiki_sources:
                if ws['url'] not in seen:
                    seen.add(ws['url'])
                    ws['id']='S'+str(len(sources)+1)
                    sources.append(ws)
                    diag.append({'stage':'article','url':ws['url'],'result':'readable','words':len(ws['excerpt'].split()),'publisher_group':ws['publisher_group']})
                    if progress:progress(sources,media)
                if len(sources)>=4:break
    # Follow a bounded set of original video references legitimately via oEmbed.
    for url in list(dict.fromkeys(u for s in sources for u in s.get('primary_links',[]) if youtube_id(u)))[:3]:
        if any(x['url']==url for x in media):continue
        try:media.append(media_metadata(url))
        except Exception as exc:diag.append({'stage':'primary_media','url':url,'result':'metadata_unavailable','reason':safe_failure(exc)})
    eligible=[s for s in sources if s.get('evidence_eligible')];groups=group_sources(eligible)
    search_ok=any(x.get('stage')=='discovery' and x.get('result') in {'ok','irrelevant_results'} for x in diag)
    min_groups=1 if (is_evergreen and (len(source_urls)>0 or len(eligible)>=1)) else 2
    if groups<min_groups:
        code='evidence_insufficient' if search_ok or sources or source_urls else 'search_failed'
        raise ResearchFailure(code,('Evidence insufficient: ' if code=='evidence_insufficient' else 'Search failed: ')+str(len(eligible))+' readable trusted reports in '+str(groups)+' independent origin groups. Original transcripts/attributed reporting or genuinely independent corroboration are still needed. Search snippets and metadata do not verify speech.',sources,diag)
    return sources,media
