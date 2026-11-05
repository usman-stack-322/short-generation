"""Independent title-to-short review drafts; existing videos are untouched."""
from alembic import op
import sqlalchemy as sa
revision='0014_title_shorts'
down_revision='0013_channel_defaults'

def upgrade():
    op.create_table('title_short_drafts',sa.Column('id',sa.String(),primary_key=True),
        sa.Column('workspace_id',sa.String(),sa.ForeignKey('workspaces.id'),nullable=False),
        sa.Column('creator_id',sa.String(),sa.ForeignKey('users.id'),nullable=False),
        sa.Column('title',sa.String(500),nullable=False),sa.Column('duration',sa.Integer(),nullable=False),
        sa.Column('language',sa.String(20),nullable=False),sa.Column('style',sa.String(30),nullable=False),
        sa.Column('status',sa.String(30),nullable=False),sa.Column('revision',sa.Integer(),nullable=False),
        sa.Column('data',sa.Text(),nullable=False),sa.Column('error_message',sa.Text()),
        sa.Column('created_at',sa.DateTime(timezone=True),nullable=False),sa.Column('updated_at',sa.DateTime(timezone=True),nullable=False))
    op.create_index('ix_title_short_drafts_workspace_id','title_short_drafts',['workspace_id'])

def downgrade():
    raise RuntimeError('Restore a verified backup for destructive rollback')
