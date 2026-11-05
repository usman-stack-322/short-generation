"""Scoped identity without merging historical duplicates or exposing private themes."""
import unicodedata
from sqlalchemy import update
from app.models import Workspace,Personality


def normalize_name(name):
    return ' '.join(unicodedata.normalize('NFKC',name).casefold().split())


def find_equivalent(db,member,name,channel_id,visibility):
    # A short workspace row lock serializes check-and-create on SQLite and
    # PostgreSQL, including concurrent submissions. No new uniqueness constraint
    # is imposed on historical duplicates; their IDs/references stay intact.
    db.execute(update(Workspace).where(Workspace.id==member.workspace_id).values(name=Workspace.name))
    query=db.query(Personality).filter_by(workspace_id=member.workspace_id,channel_id=channel_id,visibility=visibility)
    if visibility=='personal':query=query.filter_by(creator_member_id=member.id)
    return next((row for row in query.order_by(Personality.enabled.desc(),Personality.created_at,Personality.id)
                 if normalize_name(row.name)==normalize_name(name)),None)
