from alembic import context
from app.core.config import settings
from app.database.session import engine, Base
from app import models

def run():
    with engine.connect() as connection:
        if engine.dialect.name == 'sqlite':
            connection.exec_driver_sql('PRAGMA foreign_keys=OFF')
            connection.commit()
        context.configure(connection=connection, target_metadata=Base.metadata, render_as_batch=True)
        with context.begin_transaction():
            context.run_migrations()
        connection.commit()
        if engine.dialect.name == 'sqlite':
            connection.exec_driver_sql('PRAGMA foreign_keys=ON')

run()
