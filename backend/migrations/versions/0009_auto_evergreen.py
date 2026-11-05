"""Opt-in channel preparation/fallback, with channel-scoped event reservations."""
from alembic import op
import sqlalchemy as sa
revision='0009_auto_evergreen'
down_revision='0008_research_trace'


def upgrade():
    op.add_column('channels',sa.Column('automatic_evergreen_fallback',sa.Boolean(),nullable=False,server_default=sa.false()))
    op.add_column('channels',sa.Column('automatic_generation_enabled',sa.Boolean(),nullable=False,server_default=sa.false()))
    op.add_column('channels',sa.Column('generation_duration',sa.Integer(),nullable=False,server_default='45'))
    op.add_column('channels',sa.Column('niche',sa.String(160),nullable=False,server_default=''))
    op.add_column('topics',sa.Column('event_identity',sa.String(64),nullable=True))
    op.create_index('uq_channel_event_identity','topics',['channel_id','event_identity'],unique=True)


def downgrade():
    raise RuntimeError('Restore a verified backup for destructive rollback')
