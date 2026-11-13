"""Shareable workspace & isolated partner invite links table."""
from alembic import op
import sqlalchemy as sa

revision = '0018_workspace_invites'
down_revision = '0017_celebrity_vault'


def upgrade():
    schema = sa.inspect(op.get_bind())
    tables = set(schema.get_table_names())
    if 'workspace_invites' not in tables:
        op.create_table(
            'workspace_invites',
            sa.Column('id', sa.String(), primary_key=True),
            sa.Column('workspace_id', sa.String(), sa.ForeignKey('workspaces.id'), nullable=False),
            sa.Column('created_by_user_id', sa.String(), sa.ForeignKey('users.id'), nullable=False),
            sa.Column('token_hash', sa.String(64), nullable=False, unique=True),
            sa.Column('role', sa.String(20), nullable=False, server_default='MEMBER'),
            sa.Column('isolated', sa.Boolean(), nullable=False, server_default='0'),
            sa.Column('label', sa.String(120), nullable=False, server_default=''),
            sa.Column('target_email', sa.String(255), nullable=True),
            sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
            sa.Column('used_at', sa.DateTime(timezone=True), nullable=True),
            sa.Column('used_by_user_id', sa.String(), sa.ForeignKey('users.id'), nullable=True),
            sa.Column('revoked', sa.Boolean(), nullable=False, server_default='0'),
            sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        )
        op.create_index('ix_workspace_invites_workspace_id', 'workspace_invites', ['workspace_id'])
        op.create_index('ix_workspace_invites_token_hash', 'workspace_invites', ['token_hash'], unique=True)


def downgrade():
    raise RuntimeError('Restore a verified backup for destructive rollback')
