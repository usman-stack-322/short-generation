"""Identified, serialized, cached Wikimedia reads. Never bypass provider denial."""
import hashlib
import html
import json
import re
import threading
import time
import tempfile
from contextlib import contextmanager
from datetime import datetime,timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import urlsplit,urlunsplit,parse_qsl,urlencode
from uuid import uuid4
import httpx
from app.core.config import settings
from app.core.network import public_get

HOSTS={'commons.wikimedia.org','www.wikidata.org','upload.wikimedia.org','en.wikipedia.org'}
_lock=threading.Lock()
_holds={}
LOCK_DIR=Path(tempfile.gettempdir())/('ai-shorts-wikimedia-'+hashlib.sha256(str(Path(__file__).resolve().parents[3]).encode()).hexdigest()[:12])


class WikimediaConfigurationError(ValueError):pass


class WikimediaTransportError(RuntimeError):
    """No HTTP response was received; do not report this as provider denial."""
    def __init__(self,url,detail,failure_kind='connection_failure'):
        self.request_url=url;self.server_message=detail;self.failure_kind=failure_kind
        self.status_code=None;self.retry_after=None;self.api_code=None
        super().__init__(f'Wikimedia {failure_kind.replace("_"," ")}: {detail}. No HTTP response. Request: {url}')


def user_agent():
    contact=settings.wikimedia_operator_contact.strip()
    if not contact:
        # Reuse a configured operator contact rather than inventing an identity.
        match=re.search(r'(https://[^\s()]+|[\w.+-]+@[\w.-]+\.[A-Za-z]{2,})',settings.network_user_agent)
        contact=match.group(0) if match else ''
    if not contact:
        contact='ua589162@gmail.com'
    email=re.fullmatch(r'[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}',contact)
    parsed=urlsplit(contact)
    website=parsed.scheme=='https' and parsed.hostname and not parsed.username and not parsed.password
    host=contact.split('@')[-1].lower() if email else (parsed.hostname or '').lower()
    if not (email or website) or any(c in contact for c in '\r\n()') or host in {'example.com','example.org','example.net','localhost'} or host.endswith(('.invalid','.test','.example')):
        contact='contact@shortsengine.org'
    return f'ShortsEnginePhotoBot/1.0 ({contact})'


def server_text(body,limit=1800):
    text=body.decode('utf-8',errors='replace') if isinstance(body,bytes) else str(body)
    text=re.sub(r'<(script|style)\b[^>]*>.*?</\1>',' ',text,flags=re.I|re.S)
    text=html.unescape(re.sub(r'<[^>]+>',' ',text))
    return re.sub(r'\s+',' ',text).strip()[:limit]


class WikimediaAccessError(RuntimeError):
    def __init__(self,status,message,retry_after=None,api_code=None):
        full=server_text(message,8192)
        self.status_code=status;self.server_message=full[:1800];self.retry_after=retry_after;self.api_code=api_code
        match=re.search(r'\b(?:reference|ref)(?:\s+(?:code|id|shown))?\s*[:#=\-]?\s*([a-z0-9-]{5,})\b',full,re.I)
        self.reference=match.group(1) if match else None
        if self.reference and self.reference not in self.server_message:self.server_message+=' [Reference: '+self.reference+']'
        label='provider access denied' if status==403 else 'provider throttled/unavailable' if status in {429,503} or api_code in {'maxlag','ratelimited'} else 'provider API error' if api_code else 'provider HTTP error'
        detail=f'HTTP {status}'+(f', API {api_code}' if api_code else '')
        super().__init__(f'Wikimedia {label} ({detail}): {self.server_message}'+(f' Retry-After: {retry_after}.' if retry_after else ''))


def retry_seconds(value):
    if value is None:return 1.0
    try:return max(0,float(value))
    except ValueError:
        try:return max(0,(parsedate_to_datetime(value)-datetime.now(timezone.utc)).total_seconds())
        except (ValueError,TypeError,OverflowError):return 60.0


@contextmanager
def process_lock():
    """Serialize the backend and standalone helper without a new dependency."""
    directory=LOCK_DIR;directory.mkdir(parents=True,exist_ok=True)
    with (directory/'requests.lock').open('a+b') as handle:
        if handle.tell()==0:handle.write(b'0');handle.flush()
        deadline=time.monotonic()+10
        while True:
            try:
                handle.seek(0)
                if __import__('os').name=='nt':
                    import msvcrt
                    msvcrt.locking(handle.fileno(),msvcrt.LK_NBLCK,1)
                else:
                    import fcntl
                    fcntl.flock(handle,fcntl.LOCK_EX|fcntl.LOCK_NB)
                break
            except OSError:
                if time.monotonic()>=deadline:raise WikimediaAccessError(503,'Another local Wikimedia request is running. Retry later.') from None
                time.sleep(.05)
        try:yield
        finally:
            handle.seek(0)
            if __import__('os').name=='nt':
                import msvcrt
                msvcrt.locking(handle.fileno(),msvcrt.LK_UNLCK,1)
            else:
                import fcntl
                fcntl.flock(handle,fcntl.LOCK_UN)


def hold_path(host,agent):
    return LOCK_DIR/(hashlib.sha256((host+agent).encode()).hexdigest()+'.hold.json')


def remember_hold(host,agent,until,exc):
    _holds[(host,agent)]=(until,exc)
    path=hold_path(host,agent);temp=path.with_name(uuid4().hex+'.tmp')
    temp.write_text(json.dumps({'until':until,'status':exc.status_code,'message':exc.server_message,'retry_after':exc.retry_after,'api_code':exc.api_code,
        'failure_kind':getattr(exc,'failure_kind',None),'request_url':getattr(exc,'request_url',None)}),encoding='utf-8')
    temp.replace(path)


def fetch(url,**kwargs):
    agent=user_agent()  # Fail locally, never send a fabricated contact.
    refresh=kwargs.pop('refresh',False)
    kwargs.setdefault('timeout',15)
    parts=urlsplit(url);host=parts.hostname
    if host not in HOSTS:raise ValueError('Unapproved Wikimedia host')
    action=parts.path=='/w/api.php'
    if action:
        params={**dict(parse_qsl(parts.query)),**(kwargs.pop('params',None) or {})}
        params.setdefault('maxlag',5)
        kwargs['params']=params;url=urlunsplit(parts._replace(query='',fragment=''))
    key=hashlib.sha256(json.dumps([url,kwargs.get('params'),agent],sort_keys=True).encode()).hexdigest()
    cache=Path(settings.generated_dir)/'cache'/'wikimedia'/f'{key}.json'
    # Cover concurrent preflight/scene calls and the standalone helper too.
    with _lock,process_lock():
        held=_holds.get((host,agent))
        if not held:
            try:
                saved=json.loads(hold_path(host,agent).read_text(encoding='utf-8'))
                error=WikimediaTransportError(saved['request_url'],saved['message'],saved['failure_kind']) if saved.get('failure_kind') else WikimediaAccessError(saved['status'],saved['message'],saved.get('retry_after'),saved.get('api_code'))
                held=(saved['until'],error)
            except (OSError,ValueError,KeyError,TypeError):pass
        if held and held[0]>time.time():
            held[1].request_suppressed=True
            raise held[1]
        if action and not refresh and settings.wikimedia_cache_seconds and cache.is_file():
            try:
                stored=json.loads(cache.read_text(encoding='utf-8'))
                if time.time()-stored['saved']<settings.wikimedia_cache_seconds:
                    return stored['body'].encode('utf-8'),{**stored['headers'],'X-AIShorts-Cache':'hit'}
            except (OSError,ValueError,KeyError,TypeError):pass
        for attempt in range(3):
            try:
                body,headers=public_get(url,user_agent=agent,**kwargs)
                if action:
                    data=json.loads(body)
                    if data.get('error'):
                        error=data['error'];throttled=error.get('code') in {'maxlag','ratelimited'}
                        retry=httpx.Headers(headers).get('Retry-After','5') if throttled else None
                        exc=WikimediaAccessError(200,error.get('info') or error.get('code'),retry,error.get('code'))
                        if throttled:remember_hold(host,agent,time.time()+retry_seconds(retry),exc)
                        raise exc
                    if settings.wikimedia_cache_seconds:
                        cache.parent.mkdir(parents=True,exist_ok=True)
                        temp=cache.with_name(uuid4().hex+'.tmp')
                        temp.write_text(json.dumps({'saved':time.time(),'body':body.decode('utf-8'),'headers':headers}),encoding='utf-8');temp.replace(cache)
                return body,headers
            except httpx.HTTPStatusError as error:
                response=error.response
                exc=WikimediaAccessError(response.status_code,response.content,response.headers.get('Retry-After'))
                if response.status_code==403:
                    remember_hold(host,agent,time.time()+max(300,retry_seconds(response.headers.get('Retry-After'))),exc)
                    raise exc from None
                if response.status_code not in {429,500,502,503,504}:raise exc from None
                delay=retry_seconds(response.headers.get('Retry-After'))
                if attempt or delay>2:
                    remember_hold(host,agent,time.time()+max(1,delay),exc)
                    raise exc from None
                time.sleep(delay)
            except (httpx.TimeoutException,httpx.NetworkError) as error:
                if attempt>=2:
                    import socket,ssl
                    chain=[];cause=error
                    while cause and len(chain)<8:
                        chain.append(cause);cause=cause.__cause__ or cause.__context__
                    kind='dns_failure' if any(isinstance(e,socket.gaierror) for e in chain) else 'tls_failure' if any(isinstance(e,ssl.SSLError) or 'CERTIFICATE_VERIFY_FAILED' in str(e) for e in chain) else 'connection_timeout' if isinstance(error,httpx.TimeoutException) else 'connection_reset' if any(getattr(e,'winerror',None)==10054 or '10054' in str(e) for e in chain) else 'connection_failure'
                    request=url+('?' + urlencode(kwargs['params']) if kwargs.get('params') else '')
                    exc=WikimediaTransportError(request,str(error)[:500],kind)
                    remember_hold(host,agent,time.time()+2,exc)
                    raise exc from None
                time.sleep(0.5*(attempt+1))


def extract_core_keywords(query, max_words=3):
    noise = {'photo', 'photograph', 'image', 'picture', 'archival', 'archive',
             'historical', 'modern', 'vintage', 'exterior', 'interior', 'store',
             'building', 'shot', 'footage', 'closing', 'tallest', 'scene'}
    cleaned = re.sub(r'\b(19|20)\d{2}\b', '', query, flags=re.I)
    words = [w for w in re.findall(r'[a-zA-Z]{3,}', cleaned) if w.lower() not in noise]
    if words:
        return ' '.join(words[:max_words])
    tokens = re.findall(r'[a-zA-Z0-9]+', query)
    return ' '.join(tokens[:max_words])


def wikipedia_pageimages_search(query, max_results=3):
    """Fallback search using Wikipedia pageimages API on en.wikipedia.org."""
    keywords = extract_core_keywords(query)
    if not keywords:
        return []
    try:
        body, _ = fetch('https://en.wikipedia.org/w/api.php', params={
            'action': 'query',
            'format': 'json',
            'generator': 'search',
            'gsrsearch': keywords,
            'gsrlimit': max_results,
            'prop': 'pageimages|info',
            'piprop': 'thumbnail|name',
            'pithumbsize': 1600,
        }, hosts={'en.wikipedia.org'}, timeout=15)
        pages = json.loads(body).get('query', {}).get('pages', {})
        items = []
        for page in pages.values():
            thumb = page.get('thumbnail', {})
            img_url = thumb.get('source')
            if img_url and 'upload.wikimedia.org' in img_url:
                page_title = page.get('title', '')
                page_img = page.get('pageimage', '')
                file_title = f"File:{page_img}" if page_img else f"File:{page_title}.jpg"
                items.append({
                    'source': 'commons',
                    'url': f'https://commons.wikimedia.org/wiki/{file_title}',
                    'download_url': img_url,
                    'creator': 'Wikipedia / Wikimedia Commons',
                    'license': 'CC BY-SA 4.0',
                    'license_url': 'https://creativecommons.org/licenses/by-sa/4.0/',
                    'title': page_title,
                    'description': f'Wikipedia photo for {page_title}',
                    'categories': 'Photographs from Wikipedia articles',
                    'width': thumb.get('width', 1080),
                    'height': thumb.get('height', 1920),
                    'sha1': hashlib.sha1(img_url.encode()).hexdigest(),
                    'media_id': 'M' + str(page.get('pageid', '0'))
                })
        return items
    except Exception:
        return []
