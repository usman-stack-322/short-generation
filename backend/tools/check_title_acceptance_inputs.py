import json
from pathlib import Path
from app.services.title_shorts import research,cached_subject_photo
from app.database.session import SessionLocal
from app.models import TitleShortDraft
urls=['https://www.skysports.com/football/news/4575921/ronaldo-wins-ballon-d-or','https://www.uefa.com/uefachampionsleague/news/01d4-0e707fe4919f-772c18bc5bc3-1000--ballon-d-or-crowns-ronaldo-s-golden-year/']
d=[]
try:
 rows=research({'search_queries':[]},urls,d);print(json.dumps({'source_count':len(rows),'sources':[{'url':r['url'],'words':len(r['excerpt'].split())} for r in rows]}))
except Exception as e:print(json.dumps({'error':str(e)}))
Path('../generated/title-short-live/source-retrieval-check.json').write_text(json.dumps(d,indent=2))
with SessionLocal() as db:
 draft=db.get(TitleShortDraft,'97e2bfd4-2c9b-4144-ab64-f410062a05b7');assets=[]
 for i in range(3):
  asset=cached_subject_photo(draft,{'image_query':'Cristiano Ronaldo archive photograph','number':i+1},assets)
  if asset:assets.append(asset)
 print(json.dumps({'licensed_workspace_photos':len(assets),'licenses':[a['license'] for a in assets]}))
