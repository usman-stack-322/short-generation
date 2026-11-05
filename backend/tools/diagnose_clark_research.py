import json,feedparser,httpx
from pathlib import Path
from urllib.parse import urlencode
from app.core.config import settings
from app.core.network import public_get
from app.services.title_shorts import reliable
qset=['Ryan Clark Gillie Cam Newton Jalen Hurts','"Cam Newton" "Ryan Clark" "Jalen Hurts"','"Cam Newton" "Gillie" "Jalen Hurts"','Cam Newton Jalen Hurts Ryan Clark podcast July 2025']
out={'configuration':{'search_provider':settings.title_short_search_provider,'brave_key_configured':bool(settings.brave_search_api_key),'gemini_configured':bool(settings.gemini_api_key),'title_model':settings.title_short_ai_model,'uploads_disabled':not settings.youtube_uploads_enabled,'scheduler_disabled':not settings.scheduler_enabled},'queries':[]}
for q in qset:
 row={'query':q}
 try:
  body,h=public_get(settings.evergreen_search_url+'?'+urlencode({'q':q,'format':'rss'}),hosts={'www.bing.com','bing.com'},max_bytes=1000000,timeout=15)
  parsed=feedparser.parse(body);row.update(feed_title=parsed.feed.get('title'),content_type=h.get('content-type'),results=[{'title':r.get('title'),'url':r.get('link'),'trusted':reliable(r.get('link',''))} for r in parsed.entries[:10]])
 except Exception as e:row.update(error=type(e).__name__)
 out['queries'].append(row)
try:
 b,h=public_get('https://html.duckduckgo.com/html/?'+urlencode({'q':qset[0]}),hosts={'html.duckduckgo.com','duckduckgo.com'},max_bytes=1000000,timeout=15);out['duckduckgo']={'bytes':len(b),'type':h.get('content-type'),'challenge':any(x in b.lower() for x in [b'anomaly-modal',b'captcha']), 'result_links':b.count(b'result__a')}
except Exception as e:out['duckduckgo']={'error':type(e).__name__}
Path('../generated/automatic-research-clark/before-diagnosis.json').write_text(json.dumps(out,indent=2));print(json.dumps(out,indent=2))
