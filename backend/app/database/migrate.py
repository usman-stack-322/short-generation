"""Adopt the Day 1 schema, back it up, then run versioned Alembic migrations."""
from datetime import datetime, timezone
from pathlib import Path
import sqlite3
from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, text
from app.database.session import engine


def migrate_database():
    root = Path(__file__).resolve().parents[2]
    config = Config(str(root/'alembic.ini'))
    config.set_main_option('script_location', str(root/'migrations'))
    tables = inspect(engine).get_table_names()
    with engine.connect() as connection:
        version = connection.execute(text('SELECT version_num FROM alembic_version')).scalar() if 'alembic_version' in tables else None
    if version == '0018_workspace_invites':
        return
    if engine.dialect.name == 'sqlite' and engine.url.database and Path(engine.url.database).is_file() and tables:
        backups=root/'backups'
        backups.mkdir(exist_ok=True)
        target=backups/f'ai_shorts-before-day2-{datetime.now(timezone.utc):%Y%m%dT%H%M%S%f}.db'
        with sqlite3.connect(engine.url.database) as source, sqlite3.connect(target) as destination:
            source.backup(destination)
    if version is None and tables:
        from migrations.day1_schema import Base as Legacy
        schema=inspect(engine)
        for table in Legacy.metadata.sorted_tables:
            if table.name not in tables or not {c.name for c in table.columns}.issubset({c['name'] for c in schema.get_columns(table.name)}):
                raise RuntimeError('Unrecognized database schema; restore/inspect it before migration')
        command.stamp(config,'0001_day1')
    command.upgrade(config,'head')
    with engine.connect() as connection:
        if engine.dialect.name == 'sqlite' and connection.exec_driver_sql('PRAGMA foreign_key_check').fetchall():
            raise RuntimeError('Migration foreign-key verification failed; restore backup before continuing')


if __name__ == '__main__':
    migrate_database()
    print('Database is at 0018_workspace_invites. Existing data preserved; pre-upgrade SQLite backup retained.')

