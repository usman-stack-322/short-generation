import json,re,subprocess
from pathlib import Path
from app.core.config import settings
p=Path('../generated/title-short-live/technical-verification.json');data=json.loads(p.read_text())
for name,filter in [('black','blackdetect=d=0.05:pix_th=0.02'),('freeze','freezedetect=n=-60dB:d=0.7')]:
 r=subprocess.run([settings.ffmpeg_path,'-hide_banner','-i',data['video'],'-an','-vf',filter,'-f','null','-'],capture_output=True,text=True,timeout=180)
 data[name]={'exit':r.returncode,'stdout':r.stdout,'stderr':r.stderr};assert r.returncode==0,r.stderr
bad_black=bool(re.search('black_start:',data['black']['stderr']));bad_freeze=bool(re.search('freeze_start:',data['freeze']['stderr']))
data['objective_checks_passed']=all([data['render_decode']['exit']==0,not data['render_decode']['stderr'],data['exact_browser_download_decode']['exit']==0,data['download_hash_matches'],data['clipped_pcm_samples']==0,data['captions']['script_words_exact'],data['captions']['nonoverlapping'],data['captions']['within_audio'],data['captions']['maximum_native_start_delta']<=.011,not bad_black,not bad_freeze])
data['detector_correction']='Installed FFmpeg rejects .7 duration; rerun used 0.7. Successful exits are mandatory.'
p.write_text(json.dumps(data,indent=2));print(json.dumps({'black_exit':data['black']['exit'],'freeze_exit':data['freeze']['exit'],'black_events':bad_black,'freeze_events':bad_freeze,'objective_checks_passed':data['objective_checks_passed']}))
