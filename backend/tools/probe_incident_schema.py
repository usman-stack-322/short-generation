import httpx,json
from app.core.config import settings
from app.services.title_evidence import IncidentAssessment
r=httpx.post('https://generativelanguage.googleapis.com/v1beta/models/'+settings.title_short_ai_model+':generateContent',headers={'x-goog-api-key':settings.gemini_api_key},json={'contents':[{'parts':[{'text':'Return an unsupported incident assessment with reason no evidence and no claims.'}]}],'generationConfig':{'responseMimeType':'application/json','responseJsonSchema':IncidentAssessment.model_json_schema()}},timeout=35,trust_env=False)
print(r.status_code)
if r.status_code!=200:print(r.json().get('error',{}).get('message','')[:2000])
else:print('Schema accepted')
