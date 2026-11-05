"""Run in the project's normal Windows terminal, not through an agent sandbox.

Default: read-only fixed-host diagnostics. --accept: clone the prior genuine
acceptance DB into a new test directory, refresh real assets through the normal
API and render using its saved script/SEO/narration. No LLM, upload or fixture
image is permitted. A newly fetched photo is mandatory for success.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import socket
import sqlite3
import subprocess
import sys
from datetime import datetime, timezone
from urllib.parse import urlparse
from urllib.request import getproxies
from uuid import uuid4

ROOT=Path(__file__).resolve().parents[2]
BACKEND=ROOT/'backend'
COMMONS='https://commons.wikimedia.org/w/api.php?action=query&format=json&meta=siteinfo'
CDN='https://upload.wikimedia.org/'


def safe_error(exc,secrets=()):
    value=str(exc)
    for secret in secrets:
        if secret:value=value.replace(secret,'[REDACTED]')
    return {'type':type(exc).__name__,'message':value[:600],'errno':getattr(exc,'errno',None)}


def inside_generated(value):
    path=Path(value).resolve()
    if (ROOT/'generated').resolve() not in path.parents:
        raise ValueError('Acceptance files must be inside this project generated directory')
    return path


def successful_assets(rows):
    return [a for a in rows if a.get('source') in {'commons','pexels'} and a.get('preview_url')
            and a.get('url') and a.get('attribution')]


def check_dns(host):
    try:return {'ok':True,'addresses':sorted({r[4][0] for r in socket.getaddrinfo(host,443,type=socket.SOCK_STREAM)})}
    except OSError as exc:return {'ok':False,**safe_error(exc)}


def diagnostic_error(exc,secrets=()):
    from app.services.assets.wikimedia import WikimediaAccessError,WikimediaConfigurationError,WikimediaTransportError
    result=safe_error(exc,secrets)
    if isinstance(exc,WikimediaTransportError):
        result.update(kind=exc.failure_kind,http_status=None,request_url=exc.request_url,request_suppressed=getattr(exc,'request_suppressed',False))
    elif isinstance(exc,WikimediaAccessError):
        result.update(kind='provider_access_denied' if exc.status_code==403 else 'provider_api_error' if exc.api_code else 'provider_http_error',
            http_status=exc.status_code,server_message=exc.server_message,reference=exc.reference,retry_after=exc.retry_after,
            api_code=exc.api_code,request_suppressed=getattr(exc,'request_suppressed',False))
    elif isinstance(exc,WikimediaConfigurationError):result['kind']='provider_configuration'
    elif isinstance(exc,socket.gaierror):result['kind']='dns_failure'
    else:
        import ssl
        error=exc;chain=[]
        while error and len(chain)<8:
            chain.append(error);error=error.__cause__ or error.__context__
        result['kind']='tls_failure' if any(isinstance(e,ssl.SSLError) or 'CERTIFICATE_VERIFY_FAILED' in str(e) for e in chain) else 'network_failure'
    return result


def diagnose(live_check=False):
    from app.core.config import settings
    from app.services.assets import wikimedia
    secrets=[str(getattr(settings,key,'')) for key in ('pexels_api_key','gemini_api_key','google_client_secret','app_secret_key','token_encryption_key')]
    result={'time_utc':datetime.now(timezone.utc).isoformat(),'interpreter':sys.executable,
        'cwd':str(Path.cwd()),'tls_verification':True,'asset_provider':settings.asset_provider,
        'pexels_configured':bool(settings.pexels_api_key),'uploads_enabled':settings.youtube_uploads_enabled,
        'proxy_types_present':sorted(getproxies()),'dns':{},'https':[]}
    try:result['outgoing_user_agent']=wikimedia.user_agent()
    except Exception as exc:
        result['commons_api']={'ok':False,'error':diagnostic_error(exc,secrets)}
        return result
    for host in ['commons.wikimedia.org','upload.wikimedia.org']:result['dns'][host]=check_dns(host)
    # One identified Action API preflight. No generic-httpx duplicates or CDN
    # root request, whose 403 does not test a real image download.
    try:
        body,headers=wikimedia.fetch(COMMONS,hosts={'commons.wikimedia.org'},timeout=10,refresh=live_check)
        cache_hit=__import__('httpx').Headers(headers).get('X-AIShorts-Cache')=='hit'
        result['https'].append({'url':COMMONS,'tls_connected':None if cache_hit else True,'http_status':200,'trust_env':False,'cached':cache_hit})
        result['commons_api']={'ok':True,'siteinfo_received':bool(json.loads(body).get('query'))}
    except Exception as exc:
        error=diagnostic_error(exc,secrets)
        result['commons_api']={'ok':False,'error':error}
        result['https'].append({'url':COMMONS,'tls_connected':None if error.get('request_suppressed') else bool(error.get('http_status')),'error':error})
        return result  # Denial is terminal; do not run another search/preflight.
    if live_check:return result
    try:
        from app.services.assets.licensed import CommonsAssetProvider
        rows=CommonsAssetProvider().search('football stadium photograph')
        result['commons_api']['eligible_license_results']=len(rows)
        if rows:
            item=rows[0];url=item['download_url']
            result['actual_download']={'url':url,'hostname':urlparse(url).hostname,'source_page':item['url']}
            body,_=wikimedia.fetch(url,hosts={'upload.wikimedia.org'},max_bytes=15*1024*1024,timeout=10)
            result['actual_download'].update(ok=True,bytes=len(body),sha256=hashlib.sha256(body).hexdigest())
    except Exception as exc:result['commons_api']={'ok':False,'error':diagnostic_error(exc,secrets)}
    result['pexels']={'status':'configured' if settings.pexels_api_key else 'unconfigured','note':'Optional existing key; never required for Commons.'}
    return result


def accept(out,serve=False):
    # Configuration must be isolated BEFORE importing application settings/ORM.
    source=ROOT/'generated'/'live-fallback-acceptance'
    manifest=json.loads((source/'manifest.json').read_text(encoding='utf-8-sig'))
    jobid=manifest['job_id']; __import__('uuid').UUID(jobid)
    database=out/'acceptance.db'
    with sqlite3.connect('file:'+(source/'acceptance.db').as_posix()+'?mode=ro',uri=True) as src,sqlite3.connect(database) as dst:src.backup(dst)
    media=out/'media'
    os.environ.update(DATABASE_URL='sqlite:///'+database.as_posix(),GENERATED_DIR=str(media),
        GEMINI_API_KEY='',FRONTEND_ORIGIN='http://127.0.0.1:5212',SCHEDULER_ENABLED='false',SEED_DEMO='false',YOUTUBE_UPLOADS_ENABLED='false',TTS_PROVIDER='local',ASSET_PROVIDER='commons')
    os.environ['PYTHONPATH']=str(BACKEND)
    from app.core.config import settings
    from app.database.migrate import migrate_database
    migrate_database()
    from app.database.session import SessionLocal
    from app.models import VideoJob,Channel
    with SessionLocal() as db:
        job=db.get(VideoJob,jobid)
        if not job or not job.script or not job.script.seo or not job.voice_generation:raise RuntimeError('Prior genuine script/SEO/local narration checkpoint is missing')
        original=inside_generated(job.voice_generation.output_path)
        audio=media/'audio'/f'{jobid}.wav';audio.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(original,audio)
        job.voice_generation.output_path=str(audio)
        channel=db.get(Channel,job.channel_id);channel.tts_provider='local';job.tts_provider='local'
        # All generated media paths are new; source DB/media/credentials are untouched.
        db.commit()
    import httpx
    def forbidden(*a,**k):raise RuntimeError('Cloud generation prohibited in photo-only acceptance')
    httpx.post=forbidden
    from fastapi.testclient import TestClient
    from app.main import app
    from app.services.assets import licensed
    # Fail before rendering placeholders if neither real provider is reachable.
    preflight=[]
    for provider in [licensed.CommonsAssetProvider()]+([licensed.PexelsAssetProvider()] if settings.pexels_api_key else []):
        try:provider.search('football stadium photograph');preflight.append({'provider':type(provider).__name__,'reachable':True})
        except Exception as exc:preflight.append({'provider':type(provider).__name__,'reachable':False,'reason':licensed.failure_note(exc),'error':diagnostic_error(exc)})
    if not any(row['reachable'] for row in preflight):
        result={'full_live_photo_acceptance':False,'download_render_acceptance':False,'stage':next((r['error']['kind'] for r in preflight if r.get('error',{}).get('kind') in {'provider_access_denied','provider_configuration'}),'provider_connectivity'),'preflight':preflight,'uploads_enabled':False}
        (out/'acceptance-result.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
        print(json.dumps(result,indent=2));return 2
    real_fetch=licensed.fetch;fresh=[]
    def observe(url,**kwargs):
        value=real_fetch(url,**kwargs)
        if urlparse(url).hostname in {'upload.wikimedia.org','images.pexels.com'}:
            fresh.append({'url':url,'bytes':len(value[0]),'sha256':hashlib.sha256(value[0]).hexdigest()})
        return value
    licensed.fetch=observe  # Observe real HTTP only; never substitute data.
    with TestClient(app) as client:
        auth=client.post('/api/auth/login',json={'email':'evergreen-acceptance@example.com','password':'IsolatedAcceptance123!'})
        auth.raise_for_status();headers={'Authorization':'Bearer '+auth.json()['access_token']}
        response=client.post(f'/api/videos/{jobid}/regenerate',headers=headers,json={'scope':'assets'});response.raise_for_status()
        job=client.get(f'/api/videos/{jobid}',headers=headers).json()
        photos=successful_assets(job['assets'])
        result={'job_id':jobid,'status':job['status'],'error':job.get('error_message'),
            'fresh_downloads':fresh,'photos':photos,'uploads_enabled':False,'source':'prior genuine live research/script checkpoint',
            'subject_identity_matched':any(p.get('kind')=='archive' for p in photos),
            'context_only':bool(photos) and not any(p.get('kind')=='archive' for p in photos),
            'full_live_photo_acceptance':False,'download_render_acceptance':False,'visual_inspection':'PENDING - inspect photo/frame and browser Scene photographs before claiming full acceptance'}
        if job['status']=='ready_for_review' and photos and fresh:
            video=media/'videos'/jobid/'short.mp4'
            subprocess.run([settings.ffmpeg_path,'-v','error','-i',str(video),'-f','null','-'],capture_output=True,check=True)
            preview=client.get(photos[0]['preview_url'],headers=headers);preview.raise_for_status()
            (out/'selected-photo.jpg').write_bytes(preview.content)
            probe=json.loads(subprocess.run([settings.ffprobe_path,'-v','error','-show_streams','-show_format','-of','json',str(video)],capture_output=True,text=True,check=True).stdout)
            assert any(s.get('width')==1080 and s.get('height')==1920 and s.get('codec_name')=='h264' for s in probe['streams'])
            assert any(s.get('codec_name')=='aac' for s in probe['streams'])
            from app.models import Scene
            with SessionLocal() as db:
                scene=db.query(Scene).filter_by(job_id=jobid,scene_number=photos[0]['scene_number']).one()
                at=(scene.start_time+scene.end_time)/2
            subprocess.run([settings.ffmpeg_path,'-y','-v','error','-ss',str(at),'-i',str(video),'-frames:v','1',str(out/'rendered-photo-frame.png')],capture_output=True,check=True)
            assert all(p['attribution'] in job['seo']['description'] for p in photos)
            result.update(download_render_acceptance=True,video=str(video),photo_scene_frame=str(out/'rendered-photo-frame.png'),credits_verified=True,authenticated_preview_http=preview.status_code)
        (out/'acceptance-result.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
        # No tokens/passwords in output or saved result.
        print(json.dumps(result,indent=2))
    if serve and result['download_render_acceptance']:
        import uvicorn
        print('Review API: http://127.0.0.1:8012 ; use frontend port 5212 with VITE_API_URL pointing to this API.')
        uvicorn.run(app,host='127.0.0.1',port=8012)
    return 0 if result['download_render_acceptance'] else 2


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--live-check',action='store_true',help='One identified Commons siteinfo check; no search, download or generation')
    parser.add_argument('--accept',action='store_true',help='Refresh real photos/render using an isolated copy of the prior genuine job; no LLM/upload')
    parser.add_argument('--serve-review',action='store_true',help='After successful --accept, serve the isolated review API on 127.0.0.1:8012')
    args=parser.parse_args()
    sys.path.insert(0,str(BACKEND))
    out=ROOT/'generated'/('photo-network-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')+'-'+uuid4().hex[:6]);out.mkdir(parents=True)
    if args.accept or args.serve_review:return accept(out,args.serve_review)
    result=diagnose(args.live_check);(out/'diagnostics.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result,indent=2));print('Saved:',out/'diagnostics.json')
    return 0 if result['commons_api']['ok'] else 2


if __name__=='__main__':raise SystemExit(main())
