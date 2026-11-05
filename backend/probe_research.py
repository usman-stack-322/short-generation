import json
from pathlib import Path
from app.core.config import settings
from app.research.live import RSSResearchProvider, assess
settings.rss_feeds += ',https://news.google.com/rss/search?q=Cristiano%20Ronaldo%20when%3A3d&hl=en-US&gl=US&ceid=US%3Aen'
try:
    rows=RSSResearchProvider().candidates('Cristiano Ronaldo',['Ronaldo','CR7'])
    ranked=assess(rows,'Cristiano Ronaldo',['Ronaldo'],[])
    result={'provider':'rss','candidates':ranked,'verified_count':sum(r['status']=='verified' for r in ranked)}
except Exception as exc:
    result={'provider':'rss','error':str(exc),'verified_count':0}
Path('../generated/day2-research-probe.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
print(json.dumps({'verified_count':result['verified_count'],'error':result.get('error'),'candidates':[{k:r[k] for k in ('title','source_name','status','rejection_reason')} for r in result.get('candidates',[])[:12]]},indent=2))
