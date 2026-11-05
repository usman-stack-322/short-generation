"""Password reset / e-mail verification codes and password_resets table."""
from alembic import op
import sqlalchemy as sa
revision = '0016_password_reset'
down_revision = '0015_private_members'


def upgrade():
    schema=sa.inspect(op.get_bind())
    if 'email_verified_at' not in {c['name'] for c in schema.get_columns('users')}:
        op.add_column('users', sa.Column('email_verified_at', sa.DateTime(timezone=True), nullable=True))
    if 'password_resets' not in schema.get_table_names():
        op.create_table('password_resets', sa.Column('id',sa.String(),primary_key=True),
        sa.Column('user_id',sa.String(),sa.ForeignKey('users.id'),nullable=False),
        sa.Column('purpose',sa.String(20),nullable=False,server_default='reset'),
        sa.Column('code_hash',sa.String(128),nullable=False),
        sa.Column('attempts',sa.Integer(),nullable=False,server_default='0'),
        sa.Column('created_at',sa.DateTime(timezone=True),nullable=False),
        sa.Column('expires_at',sa.DateTime(timezone=True),nullable=False),
        sa.Column('used_at',sa.DateTime(timezone=True),nullable=True))
        op.create_index('ix_password_resets_user_id','password_resets',['user_id'])


def downgrade():
    raise RuntimeError('Restore a verified backup for destructive rollback')
