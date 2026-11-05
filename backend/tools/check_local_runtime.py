import httpx,json
from app.core.config import settings
print(json.dumps({k:getattr(settings,k) for k in ['gemini_model','gemini_fallback_model','research_provider','asset_provider','youtube_uploads_enabled','scheduler_enabled']}))
for port in [8000,5173]:
 try:
  r=httpx.get(f'http://127.0.0.1:{port}/',timeout=3);print(port,r.status_code)
 except Exception as e:print(port,type(e).__name__)
