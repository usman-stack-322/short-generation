import json,hashlib,subprocess
from pathlib import Path
import httpx
from app.core.config import settings
base=Path('../generated/quality-revision/clean-pilots')
with httpx.Client(base_url='http://127.0.0.1:8000',timeout=90) as c:
 r=c.post('/api/auth/login',json={'email':'owner@example.com','password':'DemoOwner123!'});r.raise_for_status();h={'Authorization':'Bearer '+r.json()['access_token']}
 assert c.get('/api/settings',headers=h).json()['uploads_enabled'] is False
 for subject in ['henry','ronaldo','messi']:
  item=json.loads((base/(subject+'-candidate.json')).read_text());j=c.get('/api/videos/'+item['job_id'],headers=h).json()
  r=c.get(j['video_url']+'&download=true',headers=h);r.raise_for_status();target=base/'verification'/subject/'download.mp4';target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(r.content)
  check=subprocess.run([settings.ffmpeg_path,'-v','error','-i',str(target),'-f','null','-'],capture_output=True,text=True)
  result={'revision':j['content_revision'],'status':r.status_code,'sha256_matches':hashlib.sha256(r.content).hexdigest()==item['sha256'],'download_decode_exit':check.returncode,'stderr':check.stderr,'uploads_enabled':False,'browser_playback':'unavailable; Windows helper pipe missing, browser import failed','direct_listening':False}
  (target.parent/'download-verification.json').write_text(json.dumps(result,indent=2));print(subject,result,flush=True)
