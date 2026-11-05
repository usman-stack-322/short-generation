import json,subprocess,hashlib
from pathlib import Path
from app.core.config import settings
R=Path(__file__).resolve().parents[2];B=R/'generated/hybrid-review';O=B/'narration-caption-audit-20261028';rows=[]
for subject in ['Ronaldo','Messi']:
 p=O/'browser-playback'/f'{subject}-download.mp4';r=subprocess.run([settings.ffmpeg_path,'-v','error','-i',str(p),'-f','null','-'],capture_output=True,text=True,timeout=180)
 rows.append({'subject':subject,'file':str(p),'decode_exit':r.returncode,'decode_errors':r.stderr,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()});assert r.returncode==0
(O/'exact-browser-download-decodes.json').write_text(json.dumps(rows,indent=2));print(json.dumps(rows,indent=2))
