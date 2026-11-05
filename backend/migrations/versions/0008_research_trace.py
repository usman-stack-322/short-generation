"""Persist job-specific research candidate provenance without altering old evidence."""
from alembic import op
import sqlalchemy as sa
revision='0008_research_trace'
down_revision='0007_channel_analytics'

def upgrade():
    op.add_column('video_jobs',sa.Column('research_trace',sa.Text(),nullable=False,server_default='{}'))

def downgrade():
    raise RuntimeError('Restore a verified backup for destructive rollback')
