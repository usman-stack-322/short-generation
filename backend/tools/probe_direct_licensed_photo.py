import hashlib,json
from urllib.parse import quote
from pathlib import Path
from app.services.assets.licensed import fetch,failure_note
name='Cam_Newton_2016.JPG';h=hashlib.md5(name.encode()).hexdigest();url='https://upload.wikimedia.org/wikipedia/commons/'+h[0]+'/'+h[:2]+'/'+quote(name)
out={'url':url,'source':'https://commons.wikimedia.org/wiki/File:Cam_Newton_2016.JPG'}
try:
 b,headers=fetch(url,hosts={'upload.wikimedia.org'},max_bytes=15000000,timeout=15);out.update(ok=True,bytes=len(b),type=headers.get('content-type'));Path('../generated/super-bowl-script/cam-source.jpg').write_bytes(b)
except Exception as exc:out.update(ok=False,error=failure_note(exc),failure_kind=getattr(exc,'failure_kind',None))
Path('../generated/super-bowl-script/direct-photo-probe.json').write_text(json.dumps(out,indent=2));print(json.dumps(out,indent=2))
