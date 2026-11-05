"""Personal ownership and administrator capabilities; preserve content and approvals."""
from alembic import op
import sqlalchemy as sa
revision = '0015_private_members'
down_revision = '0014_title_shorts'


def upgrade():
    schema=sa.inspect(op.get_bind())
    if 'can_manage_admins' not in {c['name'] for c in schema.get_columns('workspace_members')}:
        op.add_column('workspace_members', sa.Column('can_manage_admins', sa.Boolean(), server_default=sa.false(), nullable=False))
    op.execute("UPDATE workspace_members SET role='MEMBER' WHERE role IN ('EDITOR','VIEWER')")
    for name, kind, default in [('description', sa.Text(), ''), ('width', sa.Integer(), None), ('height', sa.Integer(), None), ('original_path', sa.Text(), None)]:
        if name not in {c['name'] for c in schema.get_columns('library_media')}:
            op.add_column('library_media', sa.Column(name, kind, nullable=name!='description', server_default=default))
    if 'admin_audit' not in schema.get_table_names():
        op.create_table('admin_audit', sa.Column('id',sa.String(),primary_key=True),
        sa.Column('workspace_id',sa.String(),sa.ForeignKey('workspaces.id'),nullable=False),
        sa.Column('actor_id',sa.String(),nullable=False),sa.Column('target_id',sa.String(),nullable=False),
        sa.Column('action',sa.String(80),nullable=False),sa.Column('details',sa.Text(),nullable=False),
        sa.Column('created_at',sa.DateTime(timezone=True),nullable=False))


def downgrade():
    raise RuntimeError('Restore a verified backup for destructive rollback')
