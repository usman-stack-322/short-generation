import json
from app.core.config import settings
from app.services.assets.wikimedia import user_agent
result={'pexels_configured':bool(settings.pexels_api_key),'uploads_disabled':not settings.youtube_uploads_enabled,'scheduling_disabled':not settings.scheduler_enabled}
try:user_agent();result['wikimedia_identity_configured']=True
except Exception as exc:result['wikimedia_identity_configured']=False;result['configuration_error']=str(exc)
print(json.dumps(result,indent=2))
