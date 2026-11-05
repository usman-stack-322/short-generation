# Final release verification — 30 October 2026

Verdict: **release candidate, not unconditional release sign-off**. The essential API/integration group passes; the full historical backend suite does not. Browser UI, live OAuth/upload and listening review remain outstanding. No production cleanup was repeated. No real account/project/media/approval/backup was deleted. No public deployment or live YouTube upload was performed.

## Final-code test results

| Run | Exact result | Local evidence |
|---|---|---|
| Three saved backend corrections | 3 passed, 9 deselected, 1 warning | `release/evidence/three-corrections.xml` |
| Initial publishing/configuration investigation | 19 passed, 12 failed, 1 warning | `release/evidence/final-corrections.xml` |
| Full backend suite (`pytest tests`) | 371 passed, 71 failed, 6 errors, 1 warning | `release/evidence/backend-full.xml` |
| Release-critical group in one run | 99 passed, 1 warning | `release/evidence/release-core.xml` |
| Frontend test suite | Not Tested: no test script/suite configured | `frontend/package.json` |
| Frontend production build | Verified: Vite build completed; rebuilt after the disconnected-channel Studio fallback correction | `frontend/dist` |

Counts above describe separate runs and are not summed. All tests use isolated temporary databases. The full-suite failure inventory is [RELEASE_TEST_FAILURES.md](RELEASE_TEST_FAILURES.md). Many failures exercise superseded owner-wide access, legacy Editor/Viewer creation or automatic scheduling; they have not all been individually migrated or dismissed as harmless. Full regression sign-off is Failed until those cases are reconciled.

The three correction tests specifically verify that title export copies narration from its render revision directory, uncertain-upload reconciliation checks processing before reporting success, and administrative settings audit stores field names rather than values.

The 99-test group covers member-default registration, multiple Admins and delegation, active-session revocation, private channel/media/file access, folder traversal and corrupt images, scene replacement, title-to-video handoff, duplicate prevention, wrong-channel prevention, revoked connection handling, Private request/worker enforcement, factual-evidence gates, local rendering with explicitly synthetic test audio, byte-range preview and downloads. Mocked Google/AI responses are not live verification. Synthetic test audio does not establish pronunciation/naturalness.

## Startup and browser verification

Temporary smoke UI: `http://127.0.0.1:5186`; API: `http://127.0.0.1:8026/api/health`. Both returned HTTP 200 from the workstation. The smoke backend used a database copy with upload/scheduling/seeding flags false.

Browser status: **Blocked**. Chrome was not exposed to the browser tool. The available in-app browser timed out navigating to the explicit localhost UI URL although workstation HTTP checks succeeded. The user context subsequently showed `http://127.0.0.1:5186/login`, but attempting to bind that exact tab also timed out and reset the tool kernel. Login/navigation/forms/playback have therefore not received browser sign-off. API/integration checks above are the fallback evidence, not a substitute claim of UI completion.

Normal installation uses `http://127.0.0.1:5173` and API port 8000. Existing `start-backend.ps1` and `start-frontend.ps1` are packaged. Windows-specific narration remains a deployment dependency; Linux/cloud portability is not verified.

## Live Google readiness

**Blocked**: actual `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET` are absent; zero stored OAuth credential records. User confirmed setup is not complete. Exact local setup instructions and variable names are in [GOOGLE_OAUTH_SETUP.md](GOOGLE_OAUTH_SETUP.md). No actual channel name/ID can be verified before consent. Do not put credentials in chat.

`YOUTUBE_UPLOADS_ENABLED=false`, `SCHEDULER_ENABLED=false`, and `SEED_DEMO=false` remain effective. Private-only behavior is mock verified. A live upload requires the member's explicit initiation for the approved revision and selected owned channel; never automatically publish/schedule.

## Preserved pilot listening review

Workstation file: `generated/videos/267bb2ff-06d7-4085-8a10-b2dd1cc7b406/short.mp4` (3,168,822 bytes). It is intentionally excluded from the distributable because it is preserved user content. Preview/download directly from this workstation file or the owning member's authorized video review page.

Previous technical evidence remains in `release/evidence/sample-verification.json`: 30 seconds, 1080×1920 H.264, mono AAC 22050 Hz, full decode without errors, mean -20.4 dB/peak -0.4 dB. Scene midpoint images show six illustrations and burned-in captions. It is a historical development pilot, not evidence of live factual generation or YouTube upload.

**Not Tested**: actual listening, pronunciation, naturalness and perceived caption synchronization. The user must listen before demonstration/client sign-off.

## Archive verification

The archive is generated by `backend/tools/package_release.py` from explicit source/build/document allowlists. `.env.example` is included; real `.env`, signing secrets, tokens, databases, backups, logs, caches, node_modules, virtual environments and private generated content are excluded. A file SHA256 manifest is written beside the archive.

Archive extraction, content validation and fresh-database migration/startup passed and are recorded in `release/archive-verification.json`. All 231 packaged files passed hash checks; ZIP CRC, Python syntax, frontend manifest/lock matching and blank example credentials were checked. The extracted app passed health, Member registration, admin denial and the actionable missing-Google-credentials response. These checks use the existing workstation Python dependencies; they do not claim a fresh-machine dependency installation or browser sign-off.
