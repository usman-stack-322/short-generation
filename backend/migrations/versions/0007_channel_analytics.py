"""Isolated channel-period analytics cache; existing data is untouched."""
from alembic import op
import sqlalchemy as sa
revision = '0007_channel_analytics'
down_revision = '0006_high_fixes'

def upgrade():
    op.create_table('channel_analytics_cache',
        sa.Column('workspace_id', sa.String(), sa.ForeignKey('workspaces.id'), primary_key=True),
        sa.Column('channel_id', sa.String(), sa.ForeignKey('channels.id', ondelete='CASCADE'), primary_key=True),
        sa.Column('report_key', sa.String(120), primary_key=True),
        sa.Column('payload', sa.Text()), sa.Column('synced_at', sa.DateTime(timezone=True)),
        sa.Column('attempted_at', sa.DateTime(timezone=True)),
        sa.Column('lease_until', sa.DateTime(timezone=True)), sa.Column('error', sa.Text()))

def downgrade():
    raise RuntimeError('Restore a verified backup for destructive rollback')
