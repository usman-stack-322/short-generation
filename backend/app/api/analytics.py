from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.core.security import current_context
from app.database.session import get_db
from app.models import Channel
from app.api.access import _accessible_channel_ids
from app.youtube.permissions import channel_access
from app.youtube import channel_analytics as service

router = APIRouter(prefix='/api/analytics', tags=['Channel analytics'])

@router.get('/channels')
def channels(context=Depends(current_context), db: Session=Depends(get_db)):
    member = context[1]
    query = db.query(Channel).filter_by(workspace_id=member.workspace_id)
    ids = _accessible_channel_ids(db, member)
    if ids is not None:
        query = query.filter(Channel.id.in_(ids))
    return [{'id': c.id, 'name': c.name, 'avatar': c.profile_image_url,
             'connection': service.connection(db, c),
             'can_connect': member.role != 'VIEWER' and c.member_id == member.id} for c in query.order_by(Channel.name)]

@router.get('/channels/{channel_id}')
def channel_report(channel_id: str, start_date: str | None=None, end_date: str | None=None,
                   refresh: bool=False, context=Depends(current_context), db: Session=Depends(get_db)):
    channel = db.get(Channel, channel_id)
    channel_access(channel, context[1])
    start, end = service.date_range(start_date, end_date)
    return service.report(db, channel, start, end, refresh)
