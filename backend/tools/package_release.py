"""Create a source/build archive from explicit allowlists. Never include user data/secrets."""
import hashlib,json,zipfile
from pathlib import Path


def main():
    root=Path(__file__).resolve().parents[2]
    release=root/'release';release.mkdir(exist_ok=True)
    target=release/'ai-shorts-handover.zip'
    paths=[]
    for directory in ['backend/app','backend/migrations','backend/tests','frontend/src','frontend/public','frontend/dist']:
        paths.extend(p for p in (root/directory).rglob('*') if p.is_file() and '__pycache__' not in p.parts and '.pytest_cache' not in p.parts)
    names=['backend/requirements.txt','backend/.env.example','backend/alembic.ini','backend/pytest.ini',
        'backend/tools/setup_owner.py','backend/tools/verify_handover_sample.py','backend/tools/package_release.py','backend/tools/verify_release_package.py','backend/tools/manual_check_helper.py',
        'frontend/package.json','frontend/package-lock.json','frontend/index.html','frontend/vite.config.js',
        'start-backend.ps1','start-frontend.ps1','RELEASE_GUIDE.md','HANDOVER_CHECKLIST.md','GOOGLE_OAUTH_SETUP.md','RELEASE_VERIFICATION.md','RELEASE_TEST_FAILURES.md','DEPLOYMENT_PREPARATION.md','backend/Dockerfile']
    paths.extend(root/name for name in names if (root/name).is_file())
    for path in paths:
        relative=path.relative_to(root)
        assert not any(part in {'.env','.session_secret','backups','node_modules','.venv','generated'} for part in relative.parts)
        assert path.suffix.lower() not in {'.db','.sqlite','.sqlite3','.pem','.key','.log','.pyc'}
    manifest=[]
    with zipfile.ZipFile(target,'w',zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(set(paths)):
            name=path.relative_to(root).as_posix();archive.write(path,name)
            manifest.append({'path':name,'sha256':hashlib.sha256(path.read_bytes()).hexdigest()})
    (release/'manifest.json').write_text(json.dumps({'archive':target.name,'files':manifest},indent=2),encoding='utf8')
    print(str(target));print('Files:',len(manifest));print('SHA256:',hashlib.sha256(target.read_bytes()).hexdigest())


if __name__=='__main__':main()
