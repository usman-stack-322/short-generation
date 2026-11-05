import json
from pathlib import Path
from app.services.assets.licensed import CommonsAssetProvider,photo_supported
out=[]
for q in ['Dartmouth College campus photograph','John McCarthy computer scientist photograph','early computer mainframe photograph']:
 try:
  rows=CommonsAssetProvider().search(q);out.append({'query':q,'count':len(rows),'eligible':sum(photo_supported(x) for x in rows),'items':rows[:3]})
 except Exception as e:out.append({'query':q,'error':type(e).__name__,'detail':str(e)[:400]})
Path('../generated/title-short-live/visual-probe.json').write_text(json.dumps(out,indent=2));print(json.dumps([{k:v for k,v in x.items() if k!='items'} for x in out],indent=2))
