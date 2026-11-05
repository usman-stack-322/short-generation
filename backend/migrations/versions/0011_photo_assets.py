"""Preserve photo provenance without changing existing assets or references."""
from alembic import op
import sqlalchemy as sa
revision='0011_photo_assets'
down_revision='0010_evergreen_references'


def upgrade():
    op.add_column('assets',sa.Column('provenance',sa.Text(),nullable=False,server_default='{}'))


def downgrade():
    raise RuntimeError('Restore a verified backup for destructive rollback')
