"""Frozen Day 1 schema, adoptable without deleting existing data."""
from alembic import op
from migrations.day1_schema import Base
revision = '0001_day1'
down_revision = None

def upgrade():
    Base.metadata.create_all(op.get_bind())

def downgrade():
    raise RuntimeError('Destructive downgrade is disabled; restore a verified backup instead.')
