import json,time
from pathlib import Path
from app.services.assets import wikimedia as wm
from tools.photo_acceptance import diagnostic_error
ROOT=Path(__file__).resolve().parents[2];calls=[];original=wm.public_get
def observe(url,**kwargs):
    calls.append({'url':url,'params':kwargs.get('params'),'timeout':kwargs.get('timeout')})
    return original(url,**kwargs)
wm.public_get=observe;results=[]
for params in [{'action':'query','format':'json','meta':'siteinfo'},{'action':'query','format':'json','generator':'search','gsrsearch':'Lionel Messi','gsrnamespace':6,'gsrlimit':20}]:
 start=time.monotonic()
 try:
  body,headers=wm.fetch('https://commons.wikimedia.org/w/api.php',params=params,refresh=True)
  results.append({'params':params,'status':200,'bytes':len(body)})
 except Exception as exc:results.append({'params':params,'error':diagnostic_error(exc),'elapsed':round(time.monotonic()-start,3)})
data={'actual_http_attempts':calls,'results':results}
(ROOT/'generated/imagery-continuation/transport-recheck.json').write_text(json.dumps(data,indent=2),encoding='utf8')
print(json.dumps(data,indent=2))
