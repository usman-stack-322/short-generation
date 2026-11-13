"""Connected local celebrity folder & assets table."""
from alembic import op
import sqlalchemy as sa

revision = '0017_celebrity_vault'
down_revision = '0016_password_reset'


def upgrade():
    schema = sa.inspect(op.get_bind())
    tables = set(schema.get_table_names())
    if 'celebrity_folders' not in tables:
        op.create_table(
            'celebrity_folders',
            sa.Column('workspace_id', sa.String(), sa.ForeignKey('workspaces.id'), primary_key=True),
            sa.Column('folder_path', sa.Text(), nullable=False),
            sa.Column('preference', sa.String(30), nullable=False, server_default='mix_both'),
            sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        )
    if 'celebrity_assets' not in tables:
        op.create_table(
            'celebrity_assets',
            sa.Column('id', sa.String(), primary_key=True),
            sa.Column('workspace_id', sa.String(), sa.ForeignKey('workspaces.id'), nullable=False),
            sa.Column('celebrity_name', sa.String(200), nullable=False),
            sa.Column('mood_tags', sa.Text(), nullable=False, server_default='[]'),
            sa.Column('media_type', sa.String(20), nullable=False),
            sa.Column('file_name', sa.String(300), nullable=False),
            sa.Column('file_path', sa.Text(), nullable=False),
            sa.Column('ext', sa.String(20), nullable=False),
            sa.Column('duration', sa.Float(), nullable=True),
            sa.Column('content_hash', sa.String(64), nullable=False),
            sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        )
        op.create_index('ix_celebrity_assets_workspace_id', 'celebrity_assets', ['workspace_id'])
        op.create_index('ix_celebrity_assets_celebrity_name', 'celebrity_assets', ['celebrity_name'])


def downgrade():
    raise RuntimeError('Restore a verified backup for destructive rollback')

