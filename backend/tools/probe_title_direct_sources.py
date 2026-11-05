import json,feedparser
from app.core.network import public_get
from urllib.parse import urlencode
from app.research.evergreen import ArticleText
from pathlib import Path
out=[]
for url in ['https://www.bing.com/search?'+urlencode({'q':'artificial intelligence Dartmouth 1956 proposal','format':'rss'}),'https://home.dartmouth.edu/about/artificial-intelligence-ai-coined-dartmouth','https://www-formal.stanford.edu/jmc/history/dartmouth/dartmouth.html','https://ai.dartmouth.edu/our-story']:
 r={'url':url}
 try:
  b,h=public_get(url,max_bytes=1500000,timeout=20);p=ArticleText();p.feed(b.decode('utf-8',errors='replace'));r.update(size=len(b),headers={k:v for k,v in h.items() if k in ['content-type','content-encoding']},text_length=len(p.text()),lead=p.text()[:250]);
  if 'bing' in url:r['feed']=dict(feedparser.parse(b).feed)
 except Exception as e:r.update(error=type(e).__name__,detail=str(e)[:350])
 out.append(r)
Path('../generated/title-short-live/direct-source-probe.json').write_text(json.dumps(out,indent=2));print(json.dumps(out,indent=2))
