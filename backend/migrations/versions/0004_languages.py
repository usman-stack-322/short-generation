"""Snapshot historical video languages and preserve existing content."""
from alembic import op
import sqlalchemy as sa

revision='0004_languages'
down_revision='0003_voice_director'


def upgrade():
    for column,size,default in [('language_code',20,'en-US'),('language_name',80,'English'),('locale',20,'en-US')]:
        op.add_column('video_jobs',sa.Column(column,sa.String(size),nullable=False,server_default=default))
    # Fixed migration mapping: future catalog changes cannot reinterpret old jobs.
    names={'en-US':'English','ur-PK':'Urdu','es-ES':'Spanish','it-IT':'Italian','zh-CN':'Chinese',
           'ar-SA':'Arabic','fr-FR':'French','de-DE':'German','hi-IN':'Hindi','pt-BR':'Portuguese'}
    connection=op.get_bind()
    for code,name in names.items():
        alias=code.split('-')[0]
        connection.execute(sa.text('UPDATE video_jobs SET language_code=:code, language_name=:name, locale=:code WHERE language IN (:code,:alias)'),
                           {'code':code,'name':name,'alias':alias})
        connection.execute(sa.text('UPDATE channels SET default_language=:code WHERE default_language=:alias'),{'code':code,'alias':alias})
    connection.execute(sa.text("UPDATE video_jobs SET language_code=language, locale=language, language_name='Unknown historical language' WHERE language NOT IN ('en','es','fr','ur','it','zh','ar','de','hi','pt','en-US','ur-PK','es-ES','it-IT','zh-CN','ar-SA','fr-FR','de-DE','hi-IN','pt-BR')"))


def downgrade():
    raise RuntimeError('Restore a verified backup for a destructive rollback')
