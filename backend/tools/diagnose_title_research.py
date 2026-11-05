import json,httpx,feedparser,hashlib
from pathlib import Path
from app.core.config import settings
from app.core.network import public_get,validate_url
from app.services.title_shorts import reliable
out=Path('../generated/title-short-live');out.mkdir(exist_ok=True)
rows=[]
for q in ['artificial intelligence Dartmouth 1956 proposal','Cristiano Ronaldo 2008 Ballon d Or winner official']:
 body,h=public_get(settings.evergreen_search_url,params={'q':q,'format':'rss'},hosts={'www.bing.com','bing.com'},max_bytes=1000000)
 entries=feedparser.parse(body).entries
 rec={'query':q,'content_type':h.get('content-type'),'bytes':len(body),'feed_entries':len(entries),'entries':[]}
 for e in entries[:10]:
  url=e.get('link','');r={'url':url,'title':e.get('title',''),'reliable':reliable(url)}
  if r['reliable']:
   try:
    b,headers=public_get(url,hosts={(httpx.URL(url).host or '').removeprefix('www.')},max_bytes=1500000,timeout=15)
    r.update(fetch='ok',size=len(b),content_type=headers.get('content-type'),encoding=headers.get('content-encoding'))
   except Exception as exc:r.update(fetch='failed',exception=type(exc).__name__,detail=str(exc)[:400])
  rec['entries'].append(r)
 rows.append(rec)
(out/'research-diagnosis.json').write_text(json.dumps(rows,indent=2));print(json.dumps(rows,indent=2))
