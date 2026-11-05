"""Read-only live diagnosis and preserved comparison artifacts for existing pilots."""
import os,json,shutil,hashlib,socket,time,sqlite3,importlib.util
from pathlib import Path
from urllib.parse import urlencode
from app.core.config import settings
from app.database.session import SessionLocal
from app.models import VideoJob,Asset,LibraryMedia
from app.services.pipeline import serialize_job
from app.services.assets import wikimedia
from tools.photo_acceptance import diagnostic_error
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'generated/imagery-continuation';OUT.mkdir(exist_ok=True)
IDS=['230904a6-bfc0-4182-b240-c4d498cd99fe','7f51b5de-a19d-4faf-9318-43dc15ba2b06','0f4ddd93-61f6-452d-abfb-b4c6f212f3b2']
result={'pilots':[],'library':[],'cached_real_assets':[],'requests':[],'dns':{},'providers':{'pexels_configured':bool(settings.pexels_api_key),'uploads_enabled':settings.youtube_uploads_enabled},'alignment_modules':{n:bool(importlib.util.find_spec(n)) for n in ['whisper','faster_whisper','vosk','torch','numpy','speech_recognition','playwright']}}
def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
with SessionLocal() as db:
 for jid in IDS:
  j=db.get(VideoJob,jid);assert j and j.status=='ready_for_review'
  folder=OUT/'before'/jid;folder.mkdir(parents=True,exist_ok=True)
  info=serialize_job(j,db)
  for key in ['video_url','narration_url','thumbnail_url']:info.pop(key,None)
  info.update(mp4_path=j.video.output_path,audio_path=j.voice_generation.output_path)
  for src in [Path(j.video.output_path),Path(j.voice_generation.output_path),Path(settings.generated_dir)/'subtitles'/f'{jid}.srt']:
   dst=folder/src.name
   if not dst.exists():shutil.copy2(src,dst)
   info.setdefault('preserved',[]).append({'path':str(dst),'sha256':digest(dst)})
  result['pilots'].append(info)
 result['library']=[{c.name:getattr(r,c.name) for c in LibraryMedia.__table__.columns} for r in db.query(LibraryMedia).all()]
 result['cached_real_assets']=[{'job_id':a.job_id,'path':a.local_path,'source':a.source,'url':a.url,'license':a.license,'creator':a.creator,'provenance':json.loads(a.provenance or '{}')} for a in db.query(Asset).all() if a.source not in ['demo','Local text card','Original local illustration']]
for host in ['commons.wikimedia.org','www.wikidata.org','upload.wikimedia.org']:
 try:result['dns'][host]={'addresses':sorted({a[4][0] for a in socket.getaddrinfo(host,443,type=socket.SOCK_STREAM)})}
 except Exception as e:result['dns'][host]=diagnostic_error(e)
secrets=[getattr(settings,k,'') for k in ['gemini_api_key','pexels_api_key','app_secret_key','wikimedia_operator_contact']]
for params in [{'action':'query','format':'json','meta':'siteinfo'},{'action':'query','format':'json','generator':'search','gsrsearch':'Cristiano Ronaldo','gsrnamespace':6,'gsrlimit':20,'prop':'imageinfo','iiprop':'url|extmetadata|metadata|mime|size|sha1|timestamp','iiurlwidth':1600}]:
 url='https://commons.wikimedia.org/w/api.php';entry={'url':url+'?'+urlencode({**params,'maxlag':5}),'timeout':10};start=time.monotonic()
 try:
  body,headers=wikimedia.fetch(url,params=params,timeout=10,refresh=True)
  entry.update(status=200,cached=headers.get('X-AIShorts-Cache')=='hit',bytes=len(body))
  (OUT/('siteinfo.json' if 'meta' in params else 'search.json')).write_bytes(body)
 except Exception as exc:
  entry['error']=diagnostic_error(exc,secrets);entry['chain']=[];cause=exc
  while cause and len(entry['chain'])<6:
   value=str(cause)
   for secret in secrets:
    if secret:value=value.replace(secret,'[REDACTED]')
   entry['chain'].append({'type':type(cause).__name__,'detail':value[:500]});cause=cause.__cause__ or cause.__context__
 entry['elapsed_seconds']=round(time.monotonic()-start,2);result['requests'].append(entry)
(OUT/'investigation.json').write_text(json.dumps(result,indent=2,default=str),encoding='utf8')
print(json.dumps({k:result[k] for k in ['dns','requests','providers','alignment_modules']},indent=2));print('library',len(result['library']),'real normal assets',len(result['cached_real_assets']))
