import json,time
from pathlib import Path
from app.services.title_shorts import research
out=Path('../generated/title-to-short-verification/live-research-probe.json');start=time.monotonic()
try:
 rows=research({'search_queries':['artificial intelligence beginnings Dartmouth proposal history site:dartmouth.edu','history artificial intelligence beginnings site:computerhistory.org']})
 data={'status':'sources_accessible','sources':rows,'note':'Independent real search probe using supplied example terms; not an AI-generated script or completed video.'}
except Exception as exc:data={'status':'unavailable','error':str(exc),'type':type(exc).__name__}
data['elapsed_seconds']=round(time.monotonic()-start,2);out.write_text(json.dumps(data,indent=2));print(json.dumps({k:v for k,v in data.items() if k!='sources'}))
