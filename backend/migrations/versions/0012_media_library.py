"""Add private reusable media; existing job/review data remains intact."""
from alembic import op
import sqlalchemy as sa
revision='0012_media_library'
down_revision='0011_photo_assets'


def upgrade():
    from app.models import MediaCollection,LibraryMedia,MediaUsage
    bind=op.get_bind()
    for table in (MediaCollection.__table__,LibraryMedia.__table__):table.create(bind,checkfirst=True)
    columns={c['name'] for c in sa.inspect(bind).get_columns('video_jobs')}
    if 'content_mode' not in columns:op.add_column('video_jobs',sa.Column('content_mode',sa.String(20),nullable=False,server_default='hybrid'))
    # SQLite's additive FK column is supported without rebuilding existing jobs.
    if 'collection_id' not in columns:
        if bind.dialect.name=='sqlite':op.execute('ALTER TABLE video_jobs ADD COLUMN collection_id VARCHAR REFERENCES media_collections(id)')
        else:op.add_column('video_jobs',sa.Column('collection_id',sa.String(),sa.ForeignKey('media_collections.id')))
    if 'avoid_recent_media' not in columns:op.add_column('video_jobs',sa.Column('avoid_recent_media',sa.Boolean(),nullable=False,server_default='1'))
    MediaUsage.__table__.create(bind,checkfirst=True)


def downgrade():
    raise RuntimeError('Restore a verified backup for destructive rollback')
