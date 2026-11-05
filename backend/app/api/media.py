"""Short-lived media links are issued only by authorized job responses."""
import hashlib
import hmac
import time
from pathlib import Path
from fastapi import APIRouter, HTTPException,Depends,Request
from fastapi.responses import FileResponse
from app.core.config import settings
from app.core.security import current_context,bearer
from fastapi.security import HTTPAuthorizationCredentials
from app.database.session import get_db
from sqlalchemy.orm import Session
from app.youtube.permissions import job_access

router = APIRouter()


def _signature(path, expires):
    return hmac.new(settings.app_secret_key.encode(), f'{path}:{expires}'.encode(), hashlib.sha256).hexdigest()


def media_link(path):
    expires = (int(time.time()) // 900 + 2) * 900
    return f'/generated/{path}?expires={expires}&signature={_signature(path, expires)}'


@router.get('/generated/{path:path}')
def media(path: str, expires: int, signature: str,request:Request,download:bool=False,revision:int|None=None,credentials=Depends(bearer),db:Session=Depends(get_db)):
    if expires < time.time() or not hmac.compare_digest(signature, _signature(path, expires)):
        raise HTTPException(status_code=403, detail='Media link expired or invalid. Refresh the review page.')
    root = Path(settings.generated_dir).resolve()
    target = (root / path).resolve()
    if root not in target.parents or target.suffix.lower() not in {'.mp4', '.png', '.jpg', '.wav', '.srt'}:
        raise HTTPException(status_code=404, detail='Media not found')
    if credentials is None and request.cookies.get('media_session'):
        credentials=HTTPAuthorizationCredentials(scheme='Bearer',credentials=request.cookies['media_session'])
    context=current_context(credentials,db)
    parts=Path(path).parts
    if not parts or parts[0] not in {'videos','images','audio','subtitles','thumbnails'}:
        raise HTTPException(404,'Job media not found')
    job_id=parts[1] if parts[0] in {'videos','images'} and len(parts)>2 else Path(parts[-1]).stem
    job=job_access(db,job_id,context[1])
    if revision is not None and (revision!=job.media_revision or target.suffix.lower()=='.mp4' and (not job.video or job.video.media_revision!=revision or target!=Path(job.video.output_path).resolve())):
        raise HTTPException(409,'This video revision is stale. Refresh the review page.')
    if not target.is_file():
        raise HTTPException(status_code=404, detail='Media not found')
    headers={'Cache-Control':'private, no-store, max-age=0','X-Content-Revision':str(job.content_revision),'X-Media-Revision':str(job.media_revision)}
    if download:
        # The filename is derived only from the authorized job ID and fixed type.
        return FileResponse(target,filename=f'ai-shorts-{job_id}{target.suffix.lower()}',content_disposition_type='attachment',headers=headers)
    return FileResponse(target,headers=headers)
