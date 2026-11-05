"""Read-only API downloads and technical inspection of only this run's new IDs."""
import json,subprocess,hashlib,re,collections,os
from pathlib import Path
import httpx
from PIL import Image,ImageDraw
from app.core.config import settings
from app.database.session import SessionLocal
from app.models import VideoJob
ROOT=Path(__file__).resolve().parents[2];OUT=(ROOT/'generated'/os.environ.get('PILOT_EVIDENCE_SUBDIR','fresh-verification')).resolve()
assert (ROOT/'generated').resolve() in OUT.parents
OUT.mkdir(exist_ok=True,parents=True)
rows=json.loads((ROOT/'generated/fresh-pilots.json').read_text());results=[]
def run(args,timeout=120):
 p=subprocess.run(args,capture_output=True,text=True,timeout=timeout)
 return {'exit':p.returncode,'stdout':p.stdout,'stderr':p.stderr}
with httpx.Client(base_url='http://127.0.0.1:8000',timeout=60) as c:
 a=c.post('/api/auth/login',json={'email':'owner@example.com','password':'DemoOwner123!'});a.raise_for_status();headers={'Authorization':'Bearer '+a.json()['access_token']}
 config=c.get('/api/settings',headers=headers).json();assert config['uploads_enabled'] is False
 for row in rows:
  response=c.get('/api/videos/'+row['job_id'],headers=headers);response.raise_for_status();j=response.json()
  info={'subject':row['subject'],'job_id':row['job_id'],'job':j,'uploads_disabled':config['uploads_enabled'] is False,'browser':'Not verified: IAB localhost timeout; Windows Computer Use stopped because current browser URL could not be determined safely.'}
  results.append(info)
  if j['status']!='ready_for_review':continue
  with SessionLocal() as db:
   record=db.get(VideoJob,row['job_id']);path=Path(record.video.output_path)
  info['mp4_path']=str(path);info['sha256']=hashlib.sha256(path.read_bytes()).hexdigest();info['bytes']=path.stat().st_size
  info['subtitle_timing']=json.loads((path.parent/'subtitle-timing.json').read_text()) if (path.parent/'subtitle-timing.json').exists() else None
  info['probe']=run([settings.ffprobe_path,'-v','error','-show_streams','-show_format','-of','json',str(path)])
  info['decode']=run([settings.ffmpeg_path,'-v','error','-i',str(path),'-f','null','-'])
  info['signal']=run([settings.ffmpeg_path,'-hide_banner','-i',str(path),'-vn','-af','volumedetect','-f','null','-'])
  info['blank_frames']=run([settings.ffmpeg_path,'-hide_banner','-i',str(path),'-an','-vf','blackdetect=d=0.1:pix_th=0.02','-f','null','-'])
  d=c.get(j['video_url']+'&download=true',headers=headers)
  downloaded=OUT/(j['id']+'-download.mp4');downloaded.write_bytes(d.content)
  info['download']={'status':d.status_code,'attachment':d.headers.get('content-disposition'),'sha256_matches':hashlib.sha256(d.content).hexdigest()==info['sha256']}
  anonymous=httpx.get('http://127.0.0.1:8000'+j['video_url'],timeout=30)
  info['anonymous_status']=anonymous.status_code
  seek=c.get(j['video_url'],headers={**headers,'Range':'bytes=100000-149999'})
  info['http_range']={'status':seek.status_code,'content_range':seek.headers.get('content-range')}
  info['scene_assets']=dict(collections.Counter(a['media_type'] for a in j['assets']))
  info['subtitles']=(ROOT/'generated/subtitles'/f"{j['id']}.srt").read_text(encoding='utf8')
  frames=[]
  actual_duration=float(json.loads(info['probe']['stdout'])['format']['duration'])
  for t in [min(t,actual_duration-.15) for t in [1,5,10,15,20,26,29]]:
   frame=OUT/f"{j['id']}-{t}.jpg"
   extraction=run([settings.ffmpeg_path,'-y','-v','error','-ss',str(t),'-i',str(path),'-frames:v','1',str(frame)])
   if extraction['exit']==0 and frame.is_file():
    im=Image.open(frame).convert('RGB');im.thumbnail((270,480));frames.append((t,im))
  sheet=Image.new('RGB',(270*len(frames),510),'white');draw=ImageDraw.Draw(sheet)
  for n,(t,im) in enumerate(frames):sheet.paste(im,(n*270,30));draw.text((n*270+10,8),str(t)+' seconds',fill='black')
  sheet_path=OUT/(j['id']+'-frames.jpg');sheet.save(sheet_path);info['contact_sheet']=str(sheet_path)
(OUT/'results.json').write_text(json.dumps(results,indent=2),encoding='utf8')
for r in results:print(r['subject'],r['job']['status'],r.get('mp4_path'),r.get('download'),r.get('scene_assets'))
