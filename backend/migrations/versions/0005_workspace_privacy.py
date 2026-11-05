"""Personality ownership and explicit channel assignment; preserve existing data."""
from alembic import op
import sqlalchemy as sa
revision='0005_workspace_privacy'
down_revision='0004_languages'


def upgrade():
    op.add_column('workspace_members',sa.Column('last_active_at',sa.DateTime(timezone=True),nullable=True))
    with op.batch_alter_table('personalities') as batch:
        batch.add_column(sa.Column('creator_member_id',sa.String(),nullable=True))
        batch.add_column(sa.Column('visibility',sa.String(20),nullable=False,server_default='workspace'))
        batch.add_column(sa.Column('default_voice_style',sa.String(30),nullable=False,server_default='auto'))
        batch.create_foreign_key('fk_personality_creator','workspace_members',['creator_member_id'],['id'])
    op.execute("UPDATE personalities SET creator_member_id=(SELECT id FROM workspace_members WHERE workspace_members.workspace_id=personalities.workspace_id AND role='OWNER' ORDER BY created_at LIMIT 1)")
    op.create_table('channel_assignments',sa.Column('channel_id',sa.String(),sa.ForeignKey('channels.id',ondelete='CASCADE'),primary_key=True),
                    sa.Column('member_id',sa.String(),sa.ForeignKey('workspace_members.id',ondelete='CASCADE'),primary_key=True))


def downgrade():
    raise RuntimeError('Restore a verified backup for destructive rollback')
