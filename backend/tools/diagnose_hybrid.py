import os,json,hashlib,wave
from pathlib import Path
os.environ['YOUTUBE_UPLOADS_ENABLED']='false'
os.environ['SCHEDULER_ENABLED']='false'
from app.database.session import SessionLocal
from app.models import VideoJob
ROOT=Path(__file__).resolve().parents[2];results=[]
with SessionLocal() as db:
 for jid in ['230904a6-bfc0-4182-b240-c4d498cd99fe','7f51b5de-a19d-4faf-9318-43dc15ba2b06','0f4ddd93-61f6-452d-abfb-b4c6f212f3b2']:
  j=db.get(VideoJob,jid);v=j.voice_generation;p=Path(j.video.output_path);audio=p.parent/'narration.wav'
  with wave.open(str(audio)) as w: fmt={'rate':w.getframerate(),'channels':w.getnchannels(),'duration':w.getnframes()/w.getframerate()}
  results.append({'id':jid,'revision':j.content_revision,'status':j.status,'mp4':str(p),'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'actual_provider':v.provider,'voice':v.voice,'speed':v.speed,'profile':json.loads(v.voice_profile or '{}'),'delivery':json.loads(v.delivery or '{}'),'script':j.script.full_script,'audio':str(audio),'audio_sha256':hashlib.sha256(audio.read_bytes()).hexdigest(),'format':fmt,'native_alignment':json.loads(audio.with_suffix('.words.json').read_text()),'seo_description':j.script.seo.description})
(ROOT/'generated/hybrid-review/current-diagnosis.json').write_text(json.dumps(results,indent=2))
for r in results:print(json.dumps({k:v for k,v in r.items() if k not in ['native_alignment','seo_description']}),flush=True)
