import json
from pathlib import Path
from app.services.assets.licensed import CommonsAssetProvider,failure_note
out={}
try:
 items=CommonsAssetProvider().search('Cam Newton podcast studio');out={'ok':True,'eligible_items':len(items)}
except Exception as exc:
 out={'ok':False,'type':type(exc).__name__,'reason':failure_note(exc),'status_code':getattr(exc,'status_code',None),'failure_kind':getattr(exc,'failure_kind',None),'request_suppressed':getattr(exc,'request_suppressed',False)}
Path('../generated/super-bowl-script/asset-diagnostics.json').write_text(json.dumps(out,indent=2));print(json.dumps(out,indent=2))
