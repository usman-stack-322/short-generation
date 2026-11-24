"""Full FastAPI + SQLAlchemy integration tests (run with `pytest` on your local machine)."""

import os
import tempfile

import pytest


def test_end_to_end_phase1_api_flow():
    pytest.importorskip("sqlalchemy")
    from fastapi.testclient import TestClient

    with tempfile.TemporaryDirectory() as tmp:
        os.environ["DATABASE_URL"] = f"sqlite:///{tmp}/test_v2.db"
        os.environ["WORKER_SHARED_SECRET"] = "test-secret"
        os.environ["STORAGE_MODE"] = "local"

        from backend.app.config import get_settings

        get_settings.cache_clear()
        from backend.app import database

        database.reconfigure_engine(os.environ["DATABASE_URL"])
        from backend.app.main import app

        try:
            with TestClient(app) as client:
                # 1. Health check (works cleanly in local storage mode without R2 keys)
                health = client.get("/api/health")
                assert health.status_code == 200
                assert health.json()["status"] == "ok"
                assert health.json()["storage_mode"] == "local"
                assert health.json()["r2_configured"] is False

                # 2. Bulk index clips (auto-creates celebrity, including local:// URIs & idempotency)
                local_clip = {
                    "celebrity_name": "LeBron James",
                    "category": "NBA",
                    "r2_key": "local://D:/CelebrityClips/LeBron James/espn_interview.mp4",
                    "filename": "espn_interview.mp4",
                    "file_hash": "hash_abc123",
                    "file_size_bytes": 15000000,
                    "duration_sec": 14.5,
                    "width": 1920,
                    "height": 1080,
                    "aspect_ratio": "16:9",
                    "source_type": "vault_upload",
                    "tags": ["espn", "interview"],
                }
                bulk = client.post("/api/clips/bulk-index", json={"clips": [local_clip]})
                assert bulk.status_code == 200
                assert bulk.json()["inserted"] == 1
                assert bulk.json()["celebrities_created"] == 1

                dup_bulk = client.post("/api/clips/bulk-index", json={"clips": [local_clip]})
                assert dup_bulk.status_code == 200
                assert dup_bulk.json()["inserted"] == 0
                assert dup_bulk.json()["skipped_existing"] == 1

                # 3. Create Short project & auto-detect celebrity
                proj = client.post(
                    "/api/projects",
                    json={
                        "mode": "short",
                        "input_type": "title",
                        "title": "LeBron James shocked everyone in this interview",
                        "raw_input": "LeBron James shocked everyone in this interview",
                    },
                )
                assert proj.status_code == 201
                data = proj.json()
                assert "LeBron James" in data["detected_celebrities"]
                assert data["latest_job"]["status"] == "queued"

                # 4. Local PC Worker claims job and reports completion
                claimed = client.post(
                    "/api/projects/worker/claim?worker_id=usman-pc",
                    headers={"x-worker-token": "test-secret"},
                )
                assert claimed.status_code == 200
                job_id = claimed.json()["latest_job"]["id"]

                done = client.post(
                    f"/api/projects/worker/jobs/{job_id}/progress",
                    headers={"x-worker-token": "test-secret"},
                    json={
                        "current_step": "completed",
                        "progress_pct": 100,
                        "status": "completed",
                        "output_r2_key": "renders/short_001.mp4",
                    },
                )
                assert done.status_code == 200
                assert done.json()["status"] == "completed"
        finally:
            database.engine.dispose()


def test_cloud_deployment_configs_and_db_normalization():
    import json
    from pathlib import Path
    from backend.app.config import Settings
    from backend.app.database import normalize_database_url

    assert (
        normalize_database_url("postgresql://user:pass@ep-host.neon.tech/neondb?sslmode=require")
        == "postgresql+psycopg://user:pass@ep-host.neon.tech/neondb?sslmode=require"
    )
    assert (
        normalize_database_url("postgres://user:pass@host/db")
        == "postgresql+psycopg://user:pass@host/db"
    )
    assert normalize_database_url("sqlite:///./ai_shorts_v2.db") == "sqlite:///./ai_shorts_v2.db"

    cfg = Settings(
        api_cors_origins="https://app.vercel.app/, http://localhost:5173/",
        cors_origins="https://app.vercel.app,https://preview.vercel.app/",
    )
    assert cfg.cors_origin_list == [
        "https://app.vercel.app",
        "http://localhost:5173",
        "https://preview.vercel.app",
    ]

    repo_root = Path(__file__).resolve().parents[2]
    vercel_cfg = json.loads((repo_root / "frontend" / "vercel.json").read_text(encoding="utf-8"))
    assert {"source": "/(.*)", "destination": "/index.html"} in vercel_cfg["rewrites"]

    render_yaml = (repo_root / "render.yaml").read_text(encoding="utf-8")
    assert "rootDir: backend" in render_yaml
    assert "uvicorn app.main:app" in render_yaml
    assert "healthCheckPath: /api/health" in render_yaml
