import json,httpx,time
from app.core.config import settings
url='https://generativelanguage.googleapis.com/v1beta/models/'+settings.gemini_model+':generateContent'
result={'model':settings.gemini_model}
for trust in [False]:
 start=time.monotonic()
 try:
  with httpx.Client(trust_env=trust,timeout=20) as client:
   r=client.post(url,headers={'x-goog-api-key':settings.gemini_api_key},json={'contents':[{'parts':[{'text':'Return the JSON object {"ok":true}.'}]}],'generationConfig':{'responseMimeType':'application/json'}})
  result.update(status=r.status_code,elapsed=round(time.monotonic()-start,2),trust_env=trust)
  if r.is_error:result['error_type']=r.json().get('error',{}).get('status')
 except Exception as exc:result.update(error_type=type(exc).__name__,elapsed=round(time.monotonic()-start,2),trust_env=trust)
print(json.dumps(result))
