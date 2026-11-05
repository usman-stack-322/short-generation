import json,subprocess,hashlib
from pathlib import Path
from app.core.config import settings
BASE=Path(__file__).resolve().parents[2]/'generated/hybrid-review'
item=json.loads((BASE/'improved-pilot.json').read_text());download=BASE/'browser-download.mp4'
if not download.is_file():raise ValueError('Browser download missing')
r=subprocess.run([settings.ffmpeg_path,'-v','error','-i',str(download),'-f','null','-'],capture_output=True,text=True,timeout=120)
result={'download_decode_exit':r.returncode,'stderr':r.stderr,'sha256_matches':hashlib.sha256(download.read_bytes()).hexdigest()==item['sha256']}
(BASE/'download-decode.json').write_text(json.dumps(result,indent=2));print(result,flush=True)
for voice in ['bm_george','bf_emma','sapi_david']:
 files=[BASE/'comparison-v2'/(voice+'-'+p+'-listen.wav') for p in ['hook','serious','achievement']]
 command=[settings.ffmpeg_path,'-y','-v','error']
 for f in files:command+=['-i',str(f)]
 graph='[0:a]apad=pad_dur=0.5[a0];[1:a]apad=pad_dur=0.5[a1];[a0][a1][2:a]concat=n=3:v=0:a=1[out]'
 out=BASE/'comparison-v2'/(voice+'-comparison.mp3')
 subprocess.run(command+['-filter_complex',graph,'-map','[out]','-c:a','libmp3lame','-b:a','160k',str(out)],check=True,capture_output=True,timeout=60)
print('Three comparison reels created from the matched-level samples',flush=True)
