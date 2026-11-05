import json,subprocess,hashlib
from pathlib import Path
from app.core.config import settings
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'generated/imagery-continuation/alignment';OUT.mkdir(exist_ok=True)
source=json.loads((OUT.parent/'investigation.json').read_text())
for j in source['pilots']:
 jid=j['id'];audio=OUT/f'{jid}-16k.wav';request=OUT/f'{jid}-request.json';result=OUT/f'{jid}-recognition.json'
 subprocess.run([settings.ffmpeg_path,'-y','-v','error','-i',j['audio_path'],'-ar','16000','-ac','1','-c:a','pcm_s16le',str(audio)],check=True,capture_output=True,timeout=30)
 request.write_text(json.dumps({'text':j['script']['full_script'],'audio_path':str(audio),'script_sha256':hashlib.sha256(j['script']['full_script'].encode()).hexdigest()}),encoding='utf8')
 try:
  p=subprocess.run(['powershell.exe','-NoProfile','-File',str(ROOT/'backend/tools/recognize_pilot_audio.ps1'),'-InputPath',str(request),'-OutputPath',str(result)],capture_output=True,text=True,timeout=90)
  print(j['personality_name'],p.returncode,p.stderr[:1200],flush=True)
  if p.returncode==0:
   data=json.loads(result.read_text(encoding='utf-8-sig'));print('words',len(data['words']),'confidence',data['confidence'],'first',data['words'][:2],'last',data['words'][-2:],flush=True)
 except subprocess.TimeoutExpired:print(j['personality_name'],'recognizer timeout',flush=True)
