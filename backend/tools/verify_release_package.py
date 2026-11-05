"""Verify distributable extraction and fresh-database startup without private data."""
import ast,hashlib,json,os,subprocess,sys,uuid,zipfile,tokenize
from pathlib import Path


def main():
    root=Path(__file__).resolve().parents[2];archive=root/'release'/'ai-shorts-handover.zip'
    target=root/'release'/('extraction-check-'+uuid.uuid4().hex)
    manifest=json.loads((archive.parent/'manifest.json').read_text())
    forbidden={'.env','.session_secret','backups','node_modules','.venv','__pycache__','.pytest_cache','generated'}
    with zipfile.ZipFile(archive) as z:
        assert z.testzip() is None,'ZIP CRC check failed'
        for name in z.namelist():
            path=Path(name)
            assert not path.is_absolute() and '..' not in path.parts
            assert not forbidden.intersection(path.parts),name
            assert path.suffix.lower() not in {'.db','.sqlite','.sqlite3','.log','.pyc','.key','.pem'},name
            assert not path.name.startswith('.env') or path.name=='.env.example',name
        z.extractall(target)
    for record in manifest['files']:
        path=target/record['path']
        assert path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest()==record['sha256'],record['path']
        if path.suffix=='.py':
            with tokenize.open(path) as source:ast.parse(source.read(),filename=str(path))
    required=['start-backend.ps1','start-frontend.ps1','backend/requirements.txt','backend/.env.example',
        'backend/tools/setup_owner.py','backend/alembic.ini','backend/migrations/env.py','frontend/package.json',
        'frontend/package-lock.json','frontend/dist/index.html','RELEASE_GUIDE.md','HANDOVER_CHECKLIST.md',
        'GOOGLE_OAUTH_SETUP.md','RELEASE_VERIFICATION.md','RELEASE_TEST_FAILURES.md','DEPLOYMENT_PREPARATION.md','backend/tools/manual_check_helper.py']
    assert all((target/name).is_file() for name in required)
    example=(target/'backend/.env.example').read_text()
    sensitive=['GEMINI_API_KEY','GOOGLE_CLIENT_ID','GOOGLE_CLIENT_SECRET','TOKEN_ENCRYPTION_KEY','APP_SECRET_KEY',
        'ELEVENLABS_API_KEY','GOOGLE_TTS_API_KEY','BRAVE_SEARCH_API_KEY','PEXELS_API_KEY','PIXABAY_API_KEY']
    for line in example.splitlines():
        if '=' in line:
            key,value=line.split('=',1)
            if key in sensitive:assert not value.strip(),'Non-empty example credential: '+key
    package=json.loads((target/'frontend/package.json').read_text())
    lock=json.loads((target/'frontend/package-lock.json').read_text())
    assert package['dependencies']==lock['packages']['']['dependencies']
    assert package['devDependencies']==lock['packages']['']['devDependencies']
    assert package['scripts']['dev']=='vite' and package['scripts']['build']=='vite build'
    code="""from fastapi.testclient import TestClient
from app.main import app
from app.core.config import settings
assert not settings.seed_demo and not settings.scheduler_enabled and not settings.youtube_uploads_enabled
with TestClient(app) as c:
 assert c.get('/api/health').status_code==200
 assert c.get('/api/channels').status_code==401
 r=c.post('/api/auth/register',json={'name':'Package verification','email':'package-check@example.com','password':'Test-only-password-123!'})
 assert r.status_code==201,r.text
 assert r.json()['role']=='MEMBER'
 h={'Authorization':'Bearer '+r.json()['access_token']}
 r=c.get('/api/youtube/connect',headers=h)
 assert r.status_code==503 and 'GOOGLE_CLIENT_ID' in r.json()['detail']
 assert c.get('/api/members',headers=h).status_code==403
print('Fresh migration, startup, Member registration, admin denial and missing-OAuth setup message verified.')
"""
    env={**os.environ,'PYTHONPATH':str(target/'backend'),'DATABASE_URL':'sqlite:///'+(target/'verification.db').as_posix(),
        'GENERATED_DIR':str(target/'verification-media'),'SEED_DEMO':'false','SCHEDULER_ENABLED':'false',
        'YOUTUBE_UPLOADS_ENABLED':'false','GEMINI_API_KEY':'','GOOGLE_CLIENT_ID':'','GOOGLE_CLIENT_SECRET':''}
    result=subprocess.run([sys.executable,'-c',code],cwd=target/'backend',env=env,capture_output=True,text=True,timeout=90)
    if result.returncode:raise RuntimeError('Extracted startup verification failed: '+result.stderr[-5000:])
    report={'archive':str(archive),'archive_sha256':hashlib.sha256(archive.read_bytes()).hexdigest(),
        'files_verified':len(manifest['files']),'zip_crc':'Verified','excluded_private_files':'Verified',
        'extracted_file_hashes':'Verified','python_syntax':'Verified','frontend_manifest_lock_match':'Verified',
        'example_credentials_blank':'Verified','fresh_database_migration_and_api_startup':'Verified',
        'instructions_required_files':'Verified','fresh_machine_dependency_install':'Not Tested',
        'browser_ui':'Blocked','live_google_oauth':'Blocked','live_upload':'Not Tested',
        'extraction_directory':str(target),'startup_result':result.stdout.strip()}
    (archive.parent/'archive-verification.json').write_text(json.dumps(report,indent=2),encoding='utf8')
    print(json.dumps(report,indent=2))


if __name__=='__main__':main()
