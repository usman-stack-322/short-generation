import json
from pathlib import Path
from app.services.assets.licensed import CommonsAssetProvider
try:
    rows=CommonsAssetProvider().search('football stadium')
    result={'provider':'wikimedia-commons','matches':rows[:3],'passed':bool(rows)}
except Exception as exc:
    result={'provider':'wikimedia-commons','passed':False,'error':type(exc).__name__+': '+str(exc)}
Path('../generated/day2-assets-probe.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
print(json.dumps(result,indent=2))
