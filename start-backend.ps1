$ErrorActionPreference = 'Stop'
Set-Location (Join-Path $PSScriptRoot 'backend')
# Supervised operation. Publishing must remain disabled.
$env:YOUTUBE_UPLOADS_ENABLED = 'false'
$env:SCHEDULER_ENABLED = 'false'
$env:SEED_DEMO = 'false'
& (Join-Path $PSScriptRoot '.venv\Scripts\python.exe') -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 1
