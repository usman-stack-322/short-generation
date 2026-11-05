import json,subprocess,sys,hashlib,wave
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'generated/imagery-continuation/alignment'
pilots=json.loads((OUT.parent/'investigation.json').read_text())['pilots']
for j in pilots:
 path=OUT/(j['id']+'-sapi.wav');speed=j['voice_delivery']['controls']['speed'];volume=j['voice_delivery']['controls']['volume']
 p=subprocess.run([sys.executable,'-m','app.tts.local_worker',str(path),j['narrator_voice'],str(speed),str(volume)],input=j['script']['full_script'],encoding='utf8',capture_output=True,timeout=75)
 if p.returncode:print(j['personality_name'],p.stderr[:1000]);continue
 side=path.with_suffix('.words.json')
 if not side.exists():print(j['personality_name'],'No native boundaries');continue
 data=json.loads(side.read_text());original=Path(j['audio_path'])
 with wave.open(str(original),'rb') as a:pcm=hashlib.sha256(a.readframes(a.getnframes())).hexdigest()
 data['comparison_pcm_equal']=pcm==data['pcm_sha256']
 if data['comparison_pcm_equal']:
  data['audio_sha256']=hashlib.sha256(original.read_bytes()).hexdigest()
  original.with_suffix('.words.json').write_text(json.dumps(data,indent=2),encoding='utf8')
 side.write_text(json.dumps(data,indent=2),encoding='utf8')
 print(j['personality_name'],'PCM equal',data['comparison_pcm_equal'],'words',len(data['words']),'first',data['words'][:2],'last',data['words'][-2:],flush=True)
