"""Optional public reference inputs for independently researched evergreen claims."""
from alembic import op
import sqlalchemy as sa
revision='0010_evergreen_references'
down_revision='0009_auto_evergreen'


def upgrade():
    op.add_column('channels',sa.Column('evergreen_source_urls',sa.Text(),nullable=False,server_default='[]'))


def downgrade():
    raise RuntimeError('Restore a verified backup for destructive rollback')
