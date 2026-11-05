"""Conservative local cleanup with a recoverable database/config backup. No network."""
import hashlib,json,sqlite3,shutil
from pathlib import Path
from datetime import datetime,timezone

ROOT=Path(__file__).resolve().parents[2]
BACKEND=ROOT/'backend'


def run():
    database=BACKEND/'ai_shorts.db'
    backup=BACKEND/'backups'/('handover-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%f'))
    backup.mkdir(parents=True)
    with sqlite3.connect(database) as source,sqlite3.connect(backup/'ai_shorts.db') as target:source.backup(target)
    for name in ('.env','.session_secret'):
        if (BACKEND/name).is_file():shutil.copy2(BACKEND/name,backup/name)
    db=sqlite3.connect(database);db.row_factory=sqlite3.Row
    db.execute('PRAGMA foreign_keys=ON')
    protected={t:[dict(r) for r in db.execute('SELECT * FROM '+t)] for t in ('users','workspace_members','workspace_settings','scripts','videos','approvals','title_short_drafts','library_media','channel_authorizations')}
    removed=[];cleared=[]
    # Exact seed signature plus absence of content. Never infer samples from a person's name.
    for row in db.execute("SELECT id FROM video_jobs WHERE error_message=? AND status='failed'",('Seeded sample job. Use Create Short to run the complete local video pipeline.',)).fetchall():
        key=row['id']
        if any(db.execute('SELECT 1 FROM '+table+' WHERE job_id=?',(key,)).fetchone() for table in ('scripts','videos','approvals','assets','voice_generations')):continue
        db.execute('DELETE FROM video_jobs WHERE id=?',(key,));removed.append(key)
    # Seed channel has real later projects. Remove simulated connection, retain project container.
    for row in db.execute("SELECT id FROM channels WHERE youtube_channel_id='demo-channel-001' AND status='demo'").fetchall():
        if db.execute('SELECT 1 FROM channel_authorizations WHERE channel_id=?',(row['id'],)).fetchone():continue
        db.execute("UPDATE channels SET youtube_channel_id=NULL,status='disconnected' WHERE id=?",(row['id'],));cleared.append(row['id'])
    # Disable local automatic preparation; retain every project and its actual files.
    db.execute('UPDATE channels SET automatic_generation_enabled=0')
    for table,rows in protected.items():
        assert rows==[dict(r) for r in db.execute('SELECT * FROM '+table)],'Protected data changed: '+table
    assert not db.execute('PRAGMA foreign_key_check').fetchall()
    db.commit()
    env=BACKEND/'.env'
    text=env.read_text(encoding='utf8') if env.exists() else ''
    import re
    for key in ('SEED_DEMO','SCHEDULER_ENABLED','YOUTUBE_UPLOADS_ENABLED'):
        text=re.sub(r'^'+key+r'=.*$',key+'=false',text,flags=re.M) if re.search(r'^'+key+'=',text,re.M) else text+'\n'+key+'=false\n'
    env.write_text(text,encoding='utf8')
    report={'backup':str(backup),'removed_seed_job_ids':removed,'cleared_simulated_channel_ids':cleared,
        'generated_files_deleted':[], 'preserved':{t:len(rows) for t,rows in protected.items()},
        'remaining_channels':[dict(r) for r in db.execute('SELECT id,status,youtube_channel_id FROM channels')],
        'analytics_rows':db.execute('SELECT count(*) FROM video_analytics').fetchone()[0],
        'note':'Legacy demo-marked channels with real projects and all accounts preserved. No ambiguous projects or media removed. Backup includes secrets: keep local; exclude from shared release.'}
    (ROOT/'HANDOVER_CLEANUP.json').write_text(json.dumps(report,indent=2),encoding='utf8')
    print(json.dumps(report,indent=2))


if __name__=='__main__':run()
