import json
from pathlib import Path
r=Path(__file__).resolve().parents[2]
for row in json.loads((r/'generated/pilot-blocker-investigation.json').read_text()):
 h=row['historical'];print(row['id'],json.dumps({k:h.get(k) for k in ['discovered','attempted','accessible','budget_exhausted','remaining_unattempted','outcome']}));print(json.dumps(row['reasons']))
print((r/'generated/supervised-backend.log').read_text(errors='replace')[-4500:])
