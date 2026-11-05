"""Revision-bound artifacts and durable generation request identity."""
from alembic import op
import sqlalchemy as sa
revision='0006_high_fixes'
down_revision='0005_workspace_privacy'


def upgrade():
    op.add_column('video_jobs',sa.Column('media_revision',sa.Integer(),nullable=False,server_default='1'))
    op.add_column('video_jobs',sa.Column('row_version',sa.Integer(),nullable=False,server_default='1'))
    # Historical artifacts cannot prove which script they rendered. Preserve files,
    # but require a render before accepting a new approval/publishing request.
    op.add_column('videos',sa.Column('media_revision',sa.Integer(),nullable=False,server_default='0'))
    op.add_column('voice_generations',sa.Column('script_hash',sa.String(64),nullable=False,server_default=''))
    op.create_table('generation_requests',
        sa.Column('workspace_id',sa.String(),sa.ForeignKey('workspaces.id'),primary_key=True),
        sa.Column('operation_key',sa.String(64),primary_key=True),
        sa.Column('fingerprint',sa.String(64),nullable=False),
        sa.Column('job_id',sa.String(),sa.ForeignKey('video_jobs.id',ondelete='CASCADE'),nullable=False,unique=True))


def downgrade():
    raise RuntimeError('Restore a verified backup for destructive rollback')
