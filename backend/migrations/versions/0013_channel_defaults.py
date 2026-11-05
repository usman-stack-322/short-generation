"""Channel operational preferences, separate from media library adoption."""
from alembic import op
import sqlalchemy as sa
revision='0013_channel_defaults'
down_revision='0012_media_library'


def upgrade():
    # Tolerate an in-progress local development upgrade without deleting data.
    if 'operational_defaults' not in {c['name'] for c in sa.inspect(op.get_bind()).get_columns('channels')}:
        op.add_column('channels',sa.Column('operational_defaults',sa.Text(),nullable=False,server_default='{}'))


def downgrade():
    raise RuntimeError('Restore a verified backup for destructive rollback')
