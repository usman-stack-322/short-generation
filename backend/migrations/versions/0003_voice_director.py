"""Persist automatic narration direction without replacing existing records."""
from alembic import op
import sqlalchemy as sa

revision = '0003_voice_director'
down_revision = '0002_day2'


def upgrade():
    op.add_column('channels', sa.Column('voice_style', sa.String(30), server_default='auto', nullable=False))
    op.add_column('video_jobs', sa.Column('voice_style', sa.String(30), server_default='auto', nullable=False))
    op.add_column('video_jobs', sa.Column('tts_provider', sa.String(30), nullable=True))
    op.add_column('voice_generations', sa.Column('voice_profile', sa.Text(), nullable=True))
    op.add_column('voice_generations', sa.Column('delivery', sa.Text(), nullable=True))


def downgrade():
    raise RuntimeError('Restore a verified backup for a destructive rollback')
