
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models import Channel, WorkspaceMember, ChannelAssignment
from sqlalchemy import or_

def _membership_for_workspace(db: Session, workspace_id: str, member_id: str):
    member = db.get(WorkspaceMember, member_id)
    if not member or member.workspace_id != workspace_id or not member.active:
        raise HTTPException(status_code=400, detail="Select an active member in this workspace.")
    return member


def _accessible_channel_ids(db: Session, membership: WorkspaceMember) -> set[str] | None:
    return {
        row.id for row in db.query(Channel.id).filter(
            Channel.workspace_id == membership.workspace_id,
            Channel.member_id == membership.id,
        ).all()
    }


def personality_visible(personality,member,channel_ids):
    if not personality or personality.workspace_id!=member.workspace_id:return False
    if personality.visibility=='personal':return personality.creator_member_id==member.id
    return personality.channel_id is not None and personality.channel_id in channel_ids


