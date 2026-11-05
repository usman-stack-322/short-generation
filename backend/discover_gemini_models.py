"""Official Gemini models.list discovery; no generation or retry loop."""
import json
from pathlib import Path
import httpx
from app.core.config import settings
from app.ai.reliability import safe_detail

assert settings.gemini_api_key.strip(),'Gemini key missing'
assert not settings.youtube_uploads_enabled,'Uploads must remain disabled'
models=[]
page=None
try:
    with httpx.Client(timeout=45,headers={'x-goog-api-key':settings.gemini_api_key}) as client:
        for _ in range(20):
            params={'pageSize':100}
            if page:params['pageToken']=page
            response=client.get('https://generativelanguage.googleapis.com/v1beta/models',params=params)
            response.raise_for_status()
            payload=response.json()
            models.extend(payload.get('models',[]))
            page=payload.get('nextPageToken')
            if not page:break
        else:raise RuntimeError('Model listing pagination exceeded safety limit')
    path=Path(settings.generated_dir).resolve()/'gemini-available-models.json'
    path.write_text(json.dumps({'models':models},indent=2),encoding='utf-8')
    print(json.dumps({'listing_status':'Passed','total_models':len(models),'content_generation_models':[
        model for model in models if 'generateContent' in model.get('supportedGenerationMethods',[])]},indent=2))
except httpx.HTTPStatusError as exc:
    print(json.dumps({'listing_status':'Failed','http_status':exc.response.status_code,'error':safe_detail(exc.response.text)},indent=2))
except Exception as exc:
    print(json.dumps({'listing_status':'Failed','type':type(exc).__name__,'error':safe_detail(exc)},indent=2))
