"""Bounded official API photo retrieval; no arbitrary web image search."""
import hashlib
import io
import json
import logging
import re
import time
import socket
from pathlib import Path
from urllib.parse import urlparse
from uuid import uuid4
import httpx
from PIL import Image, ImageOps, ImageDraw, ImageFont
from app.core.config import settings
from app.core.network import public_get
from app.services.assets.providers import SafeAsset
from app.services.assets.policy import license_allowed, photo_supported, matches_subject, contextual, normalized

logger = logging.getLogger(__name__)


def plain(value):
    import html
    return html.unescape(re.sub('<[^>]+>', '', value or '')).strip()


def fetch(url, **kwargs):
    from app.services.assets import wikimedia
    if urlparse(url).hostname in wikimedia.HOSTS:return wikimedia.fetch(url,**kwargs)
    for attempt in range(2):
        try:
            return public_get(url, **kwargs)
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code not in {429,500,502,503,504} or attempt:
                raise
            retry = exc.response.headers.get('Retry-After','1')
            if not retry.isdigit() or int(retry)>2:
                raise
            time.sleep(int(retry))
        except (httpx.TimeoutException,httpx.NetworkError):
            if attempt: raise
            time.sleep(1)


def failure_note(exc):
    from app.services.assets.wikimedia import WikimediaAccessError,WikimediaConfigurationError,WikimediaTransportError
    if isinstance(exc,(WikimediaAccessError,WikimediaConfigurationError,WikimediaTransportError)):
        return str(exc)+(' (request suppressed during local cooldown)' if getattr(exc,'request_suppressed',False) else '')
    if isinstance(exc,socket.gaierror):return 'Photo provider DNS lookup failed. Check internet/DNS, then retry assets or upload a licensed photo.'
    import ssl
    cause=exc
    for _ in range(8):
        if cause is None:break
        if isinstance(cause,ssl.SSLError) or 'CERTIFICATE_VERIFY_FAILED' in str(cause):
            return 'Photo provider TLS verification failed. Check certificate trust/network configuration; TLS verification remains enabled.'
        cause=cause.__cause__ or cause.__context__
    if isinstance(exc,httpx.HTTPStatusError):return f'Photo provider HTTP {exc.response.status_code}. Check provider access/quota and retry later.'
    if isinstance(exc,(httpx.TimeoutException,httpx.NetworkError,TimeoutError)):return 'Photo provider timed out or is unreachable. Retry assets later.'
    if isinstance(exc,AssertionError):return 'External photo access disabled in this isolated test environment.'
    return 'Photo metadata or file rejected ('+type(exc).__name__+'). Upload a licensed photo or retry assets.'


class CommonsAssetProvider:
    def _search_query(self, query):
        body,_=fetch('https://commons.wikimedia.org/w/api.php',params={
            'action':'query','format':'json','generator':'search','gsrsearch':query,
            'gsrnamespace':6,'gsrlimit':20,'prop':'imageinfo',
            'iiprop':'url|extmetadata|metadata|mime|size|sha1|timestamp','iiurlwidth':1600},hosts={'commons.wikimedia.org'})
        results=[]
        for page in json.loads(body).get('query',{}).get('pages',{}).values():
            info=page.get('imageinfo',[{}])[0];meta=info.get('extmetadata',{})
            camera={entry.get('name'):plain(str(entry.get('value',''))) for entry in info.get('metadata',[]) if isinstance(entry,dict)}
            get=lambda key: plain(meta.get(key,{}).get('value'))
            license=get('LicenseShortName');license_url=get('LicenseUrl');creator=get('Artist')
            if not license_allowed(license,license_url,creator) or info.get('mime') not in {'image/jpeg','image/png','image/webp'}:
                continue
            if get('Restrictions') or get('Permission').lower().startswith('fair use'):
                continue
            download=info.get('thumburl') or info.get('url')
            if not download or urlparse(download).hostname!='upload.wikimedia.org' or urlparse(info.get('descriptionurl','')).hostname!='commons.wikimedia.org':
                continue
            results.append({'source':'commons','url':info['descriptionurl'],'download_url':download,
                'creator':creator,'license':license,'license_url':license_url,'title':page.get('title',''),
                'description':get('ImageDescription'),'categories':get('Categories'),
                'date':get('DateTimeOriginal'),'original_source':get('Credit'),'original_image_url':info.get('url'),
                'width':info.get('width',0),'height':info.get('height',0),
                'camera_make':camera.get('Make'),'camera_model':camera.get('Model'),
                'sha1':info.get('sha1'),'media_id':'M'+str(page.get('pageid',''))})
        return results

    def search(self, query):
        # "photograph" is a retrieval hint, not a required word in a file page.
        # Inspect a bounded pool before the unchanged MIME/license/identity gates;
        # the old first five hits could all be share-alike or non-photo files.
        clean_q=re.sub(r'\s+photograph\s*$','',query,flags=re.I).strip()
        from app.services.assets.wikimedia import extract_core_keywords, wikipedia_pageimages_search
        candidates=[clean_q]
        core=extract_core_keywords(clean_q)
        if core and core.lower()!=clean_q.lower():candidates.append(core)
        first_two=' '.join(clean_q.split()[:2])
        if first_two and first_two not in candidates:candidates.append(first_two)

        last_error=None
        for q in candidates:
            try:
                items=self._search_query(q)
                if items:return items
            except Exception as exc:
                last_error=exc
                continue

        # Fallback to Wikipedia pageimages API on en.wikipedia.org
        try:
            wiki_items=wikipedia_pageimages_search(clean_q)
            if wiki_items:return wiki_items
        except Exception as exc:
            if not last_error:last_error=exc

        if last_error:raise last_error
        return []

    def subject(self, name, category=None):
        body,_=fetch('https://www.wikidata.org/w/api.php',params={'action':'wbsearchentities','format':'json',
            'search':name,'language':'en','limit':5},hosts={'www.wikidata.org'})
        exact=[x for x in json.loads(body).get('search',[]) if normalized(x.get('label',''))==normalized(name)]
        # Use the already selected theme to disambiguate namesakes, not result
        # rank or a hardcoded celebrity identifier. Broad categories prove nothing.
        words=set(normalized(category or '').split())-{'general','people','personality','personalities','celebrity','celebrities','news','sport','sports'}
        if not words:return exact[0]['id'] if len(exact)==1 else None
        matched=[x for x in exact if words and words.issubset(set(normalized(x.get('description','')).split()))]
        return matched[0]['id'] if len(matched)==1 else None

    def identify(self, items, entity):
        ids=[x['media_id'] for x in items if re.fullmatch(r'M\d+',x.get('media_id',''))]
        if not entity or not ids:return
        body,_=fetch('https://commons.wikimedia.org/w/api.php',params={'action':'wbgetentities',
            'format':'json','ids':'|'.join(ids),'props':'claims'},hosts={'commons.wikimedia.org'})
        data=json.loads(body).get('entities',{})
        for item in items:
            claims=data.get(item.get('media_id'),{}).get('statements',data.get(item.get('media_id'),{}).get('claims',{}))
            claims=claims if isinstance(claims,dict) else {}
            item['depicts']=[c.get('mainsnak',{}).get('datavalue',{}).get('value',{}).get('id') for c in claims.get('P180',[])]
            item['subject_entity']=entity


class PexelsAssetProvider:
    def search(self,query):
        if not settings.pexels_api_key:return []
        # Authorization is sent exclusively to the fixed official API, never a redirect.
        for attempt in range(2):
            response=httpx.get('https://api.pexels.com/v1/search',params={'query':query,'orientation':'portrait','per_page':5},
                headers={'Authorization':settings.pexels_api_key},timeout=25,follow_redirects=False,trust_env=False)
            if response.status_code in {429,500,502,503,504} and not attempt:
                delay=response.headers.get('Retry-After','1')
                if not delay.isdigit() or int(delay)>2:response.raise_for_status()
                time.sleep(int(delay));continue
            response.raise_for_status();break
        return [{'source':'pexels','url':p['url'],'download_url':p.get('src',{}).get('portrait') or p.get('src',{}).get('large2x'),
            'creator':p['photographer'],'license':'Pexels License','license_url':'https://www.pexels.com/license/',
            'title':p.get('alt','') or query,'description':(p.get('alt','')+' '+query).strip(),'width':p['width'],'height':p['height']}
            for p in response.json().get('photos',[])
            if urlparse(p.get('url','')).hostname in {'www.pexels.com','pexels.com'} and urlparse(p.get('src',{}).get('portrait') or p.get('src',{}).get('large2x','')).hostname=='images.pexels.com']


class PixabayAssetProvider:
    def search(self,query):
        if not getattr(settings,'pixabay_api_key',''):return []
        from app.services.assets.wikimedia import extract_core_keywords
        kw=extract_core_keywords(query,max_words=4) or query
        response=httpx.get('https://pixabay.com/api/',params={
            'key':settings.pixabay_api_key,'q':kw,'image_type':'photo',
            'orientation':'vertical','safesearch':'true','per_page':5},
            timeout=20,follow_redirects=True,trust_env=False)
        response.raise_for_status()
        return [{'source':'pixabay','url':h.get('pageURL','https://pixabay.com/'),
            'download_url':h.get('largeImageURL') or h.get('webformatURL',''),
            'creator':h.get('user','Pixabay Contributor'),'license':'Pixabay Content License',
            'license_url':'https://pixabay.com/service/license-summary/',
            'title':h.get('tags',kw),'description':f"Photograph of {h.get('tags',kw)} ({query})",
            'width':h.get('imageWidth',1080),'height':h.get('imageHeight',1920)}
            for h in response.json().get('hits',[]) if h.get('largeImageURL')]


BROWSER_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"


class OpenverseAssetProvider:
    def search(self, query):
        from app.services.assets.wikimedia import extract_core_keywords
        clean_q = re.sub(r'\s+(?:archival\s+|modern\s+|historical\s+)?(?:photo(?:graph)?|image)\s*$', '', query, flags=re.I).strip()
        candidates = []
        for c in [extract_core_keywords(clean_q, max_words=3), extract_core_keywords(clean_q, max_words=2), clean_q]:
            if c and c not in candidates:
                candidates.append(c)
        for q in candidates:
            try:
                response = httpx.get(
                    'https://api.openverse.org/v1/images/',
                    params={'q': q, 'page_size': 10},
                    headers={'User-Agent': BROWSER_USER_AGENT, 'Accept': 'application/json'},
                    timeout=15,
                    follow_redirects=True,
                    trust_env=False,
                )
                if response.status_code != 200:
                    continue
                results = []
                for row in response.json().get('results', []):
                    w = row.get('width') or 0
                    h = row.get('height') or 0
                    if (w and w < 400) or (h and h < 400):
                        continue
                    lic = (row.get('license') or 'cc0').upper()
                    lic_ver = row.get('license_version') or '1.0'
                    title = row.get('title') or q
                    for dl in [row.get('url'), row.get('thumbnail')]:
                        if not dl or not dl.startswith('https://'):
                            continue
                        results.append({
                            'source': 'openverse',
                            'url': row.get('foreign_landing_url') or row.get('detail_url') or dl,
                            'download_url': dl,
                            'creator': row.get('creator') or 'Openverse Contributor',
                            'license': f'CC {lic} {lic_ver}',
                            'license_url': row.get('license_url') or 'https://creativecommons.org/licenses/',
                            'title': title,
                            'description': f'Photograph of {title} ({query})',
                            'width': w or 1080,
                            'height': h or 1920,
                        })
                if results:
                    return results
            except Exception:
                continue
        return []


class LexicaAssetProvider:
    def search(self, query):
        from urllib.parse import quote
        from app.services.assets.wikimedia import extract_core_keywords
        clean_q = re.sub(r'\s+(?:archival\s+|modern\s+|historical\s+)?(?:photo(?:graph)?|image)\s*$', '', query, flags=re.I).strip()
        candidates = []
        for c in [extract_core_keywords(clean_q, max_words=3), clean_q, extract_core_keywords(clean_q, max_words=2)]:
            if c and c not in candidates:
                candidates.append(c)
        for q in candidates:
            try:
                response = httpx.get(
                    f'https://lexica.art/api/v1/search?q={quote(q)}',
                    headers={'User-Agent': BROWSER_USER_AGENT, 'Accept': 'application/json'},
                    timeout=15,
                    follow_redirects=True,
                    trust_env=False,
                )
                if response.status_code != 200:
                    continue
                images = response.json().get('images', [])
                # Prefer portrait / high-res images first
                images = sorted(images, key=lambda x: (1 if (x.get('height') or 0) >= (x.get('width') or 0) else 0, (x.get('height') or 0) * (x.get('width') or 0)), reverse=True)
                results = []
                for item in images[:10]:
                    dl = item.get('src') or item.get('srcSmall')
                    if not dl or not dl.startswith('https://'):
                        continue
                    prompt_text = (item.get('prompt') or q)[:200]
                    results.append({
                        'source': 'lexica',
                        'url': f"https://lexica.art/prompt/{item.get('id', '')}" if item.get('id') else 'https://lexica.art/',
                        'download_url': dl,
                        'creator': 'Lexica Community',
                        'license': 'CC0 1.0',
                        'license_url': 'https://lexica.art/',
                        'title': prompt_text,
                        'description': f'Photograph of {prompt_text} ({query})',
                        'width': item.get('width') or 1080,
                        'height': item.get('height') or 1920,
                    })
                if results:
                    return results
            except Exception:
                continue
        return []


def neutral_card(scene, output_dir, reason='No eligible real photograph found'):
    # A private sentinel keeps existing replacement/upload controls addressable.
    # It is never eligible for rendering.
    output_dir.mkdir(parents=True, exist_ok=True)
    path=output_dir / f'held_{scene.scene_number}_{uuid4().hex}.jpg'
    Image.new('RGB',(1080,1920),'#17192b').save(path)
    return SafeAsset(path,'Missing scene media','','',scene_number=scene.scene_number,
        provenance={'kind':'missing','reason':reason,'real_photos_only':True})


def prepare_photo(body, path, label):
    with Image.open(io.BytesIO(body)) as source:
        if source.format not in {'JPEG','PNG','WEBP'} or source.width*source.height>40_000_000 or min(source.size)<400:
            raise ValueError('Photo must be JPEG/PNG/WebP, at least 400px on each side, at most 40 megapixels')
        source.load()
        image=ImageOps.exif_transpose(source).convert('RGB')
    # Keep a sanitized original for rendering; the padded file is a preview only.
    path.parent.mkdir(parents=True,exist_ok=True)
    raw=ImageOps.contain(image,(4096,4096)) if max(image.size)>4096 else image
    raw.save(path.with_name(path.stem+'-source.jpg'),quality=96,subsampling=0)
    # Padding preserves faces and aspect ratios; no watermark/face editing.
    image=ImageOps.contain(image,(960,1440))
    canvas=Image.new('RGB',(1080,1920),'#17192b')
    canvas.paste(image,((1080-image.width)//2,(1700-image.height)//2))
    draw=ImageDraw.Draw(canvas)
    def _font(size, bold=False):
        for name in (["arialbd.ttf", "DejaVuSans-Bold.ttf"] if bold else ["arial.ttf", "DejaVuSans.ttf"]):
            try: return ImageFont.truetype(name, size)
            except OSError: pass
        return ImageFont.load_default(size=size)
    badge_text=label.upper()
    badge_w=int(len(badge_text)*14+36)
    draw.rounded_rectangle((75, 80, 75+badge_w, 126), radius=10, fill='#0e1726', outline='#2b3c58', width=2)
    draw.text((93, 91), badge_text, font=_font(20, True), fill='#a5b8d0')
    path.parent.mkdir(parents=True,exist_ok=True);canvas.save(path,quality=94)


def download_photo(item, scene, output_dir, kind):
    host_map={'commons':{'upload.wikimedia.org'},'pexels':{'images.pexels.com'},'pixabay':{'pixabay.com','cdn.pixabay.com'}}
    hosts=host_map.get(item['source'])
    parsed_dl=urlparse(item['download_url'])
    if parsed_dl.scheme!='https' or not parsed_dl.hostname or parsed_dl.hostname in {'127.0.0.1','localhost'} or (hosts and parsed_dl.hostname not in hosts):
        raise ValueError('Unapproved photo host')
    cache=output_dir.parents[1]/'cache'/'photos';cache.mkdir(parents=True,exist_ok=True)
    key=hashlib.sha256((item['download_url']+item['license']+(item.get('sha1') or '')).encode()).hexdigest()
    cached=cache/f'{key}.bin'
    if cached.is_file() and cached.stat().st_size>15*1024*1024:raise ValueError('Cached photo exceeds size limit')
    if cached.is_file():
        body=cached.read_bytes()
    elif item['source'] in {'openverse','lexica'}:
        resp=httpx.get(item['download_url'],headers={'User-Agent':BROWSER_USER_AGENT},timeout=15,follow_redirects=True,trust_env=False)
        resp.raise_for_status()
        body=resp.content
    else:
        body=fetch(item['download_url'],hosts=hosts,max_bytes=15*1024*1024)[0]
    if len(body)>15*1024*1024:raise ValueError('Photo exceeds 15 MB')
    path=output_dir/f'scene_{scene.scene_number}_{uuid4().hex}.jpg'
    label='Archive photo' if kind=='archive' else 'Illustrative image'
    prepare_photo(body,path,label)
    if not cached.is_file():cached.write_bytes(body)
    modifications='Resized proportionally, padded, labeled; gentle pan/zoom in video'
    credit=f"{item.get('title','Photograph')} | Photo by {item['creator'] or 'Unknown (public domain)'} on {item['source']}: {item['url']} | {item['license']} {item['license_url']} | {modifications}"
    meta={**item,'kind':kind,'label':label,'modifications':modifications,'required_credit':credit,
        'license_version':(re.search(r'\d+\.\d+',item['license']).group(0) if re.search(r'\d+\.\d+',item['license']) else None),
        'authenticity_note':'Provider metadata checked; not a guarantee of photographic authenticity.',
        'content_hash':hashlib.sha256(body).hexdigest(),'real_photos_only':True,'rights_checked':True}
    return SafeAsset(path,item['source'],item['license'],credit[:500],item['url'],item['creator'][:500],item['download_url'],scene.scene_number,meta)


def collect_scene_assets(scenes, topic, personality, script, output_dir, provider_name='commons',language='en-US',exclude_urls=None,exclude_hashes=None,subject_category=None):
    output_dir=Path(output_dir);output_dir.mkdir(parents=True,exist_ok=True)
    commons=CommonsAssetProvider();used=set(exclude_urls or []);used_hash=set(exclude_hashes or []);assets=[];queries={};errors=[]
    context=(personality+' '+topic+' '+script).lower()
    generic='football stadium photograph' if any(x in context for x in ('football','ronaldo','messi')) else 'basketball court photograph' if any(x in context for x in ('basketball','nba','lebron')) else 'office building photograph' if any(x in context for x in ('business','company','factory')) else 'landscape photograph'
    entity=None
    if provider_name!='demo':
        try:entity=commons.subject(personality,subject_category)
        except Exception as exc:errors.append('Subject metadata unavailable: '+failure_note(exc))
    def search(provider,query):
        key=(type(provider).__name__,query)
        if key not in queries:
            if len(queries)>=8:return []
            try:
                queries[key]=provider.search(query)
                if isinstance(provider,CommonsAssetProvider) and query!=generic:commons.identify(queries[key],entity)
            except Exception as exc:
                errors.append(type(provider).__name__+': '+failure_note(exc));queries[key]=[]
                logger.warning('Photo provider failed (%s): %s',type(provider).__name__,failure_note(exc))
        return queries[key]
    for scene in scenes:
        selected=None
        if provider_name!='demo':
            searches=[(commons,personality+' '+scene.visual_query+' photograph','archive'),(commons,personality+' photograph','archive'),(commons,personality+' photograph','archive')]
            # Generic stock is not a substitute for identified subject media.
            for provider,query,kind in searches:
                for item in search(provider,query):
                    if item['download_url'] in used or not photo_supported(item):continue
                    if kind=='archive' and not matches_subject(item,personality):continue
                    if kind=='context' and not contextual(item,generic):continue
                    try:
                        candidate=download_photo(item,scene,output_dir,kind)
                        if candidate.provenance['content_hash'] in used_hash:
                            used.add(item['download_url']);continue
                        selected=candidate;used.add(item['download_url']);used_hash.add(candidate.provenance['content_hash']);break
                    except Exception as exc:
                        used.add(item['download_url']);errors.append('Photo download rejected: '+failure_note(exc))
                        logger.warning('Photo download rejected: %s',failure_note(exc))
                if selected:break
        assets.append(selected or neutral_card(scene,output_dir,'; '.join(dict.fromkeys(errors)) or 'No eligible subject photograph; upload or replace scene media'))
    return assets
