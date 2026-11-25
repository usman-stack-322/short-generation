"""Full FastAPI + SQLAlchemy integration tests (run with `pytest` on your local machine)."""

import os
import sqlite3
import tempfile

import pytest


def _register_and_auth_headers(
    client,
    email: str = "creator@studio.test",
    password: str = "StrongPass123!",
    display_name: str = "Test Creator",
) -> dict[str, str]:
    resp = client.post(
        "/api/auth/register",
        json={"email": email, "password": password, "display_name": display_name},
    )
    assert resp.status_code == 201, resp.text
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_auth_register_login_me_and_route_protection():
    pytest.importorskip("sqlalchemy")
    from fastapi.testclient import TestClient
    from sqlalchemy import inspect, select

    with tempfile.TemporaryDirectory() as tmp:
        db_file = f"{tmp}/test_auth.db"
        # Seed a legacy users table missing hashed_password to verify idempotent ALTER TABLE migration
        conn = sqlite3.connect(db_file)
        conn.execute(
            "CREATE TABLE users (id VARCHAR(36) PRIMARY KEY, email VARCHAR(255) UNIQUE NOT NULL, "
            "display_name VARCHAR(120), plan_tier VARCHAR(32), created_at DATETIME)"
        )
        conn.execute(
            "INSERT INTO users (id, email, display_name, plan_tier) VALUES "
            "('legacy-id', 'legacy@local.studio', 'Legacy Owner', 'personal')"
        )
        conn.commit()
        conn.close()

        os.environ["DATABASE_URL"] = f"sqlite:///{db_file}"
        os.environ["WORKER_SHARED_SECRET"] = "test-secret"
        os.environ["JWT_SECRET"] = "test-jwt-secret-key-at-least-32-bytes-long"
        os.environ["STORAGE_MODE"] = "local"

        from backend.app.config import get_settings

        get_settings.cache_clear()
        from backend.app import database
        from backend.app.models import User

        database.reconfigure_engine(os.environ["DATABASE_URL"])
        from backend.app.main import app

        try:
            with TestClient(app) as client:
                # 1. Legacy table received hashed_password automatically on startup
                cols = {c["name"] for c in inspect(database.engine).get_columns("users")}
                assert "hashed_password" in cols

                # 2. Protected routes reject unauthenticated callers
                assert client.get("/api/auth/me").status_code == 401
                assert client.get("/api/celebrities").status_code == 401
                assert client.get("/api/clips").status_code == 401
                assert client.get("/api/projects").status_code == 401

                # 3. Register returns JWT + bcrypt hash (never plaintext)
                reg = client.post(
                    "/api/auth/register",
                    json={
                        "email": "User1@Example.com",
                        "password": "MyPassword123",
                        "display_name": "Creator One",
                    },
                )
                assert reg.status_code == 201
                reg_data = reg.json()
                assert reg_data["token_type"] == "bearer"
                assert reg_data["user"]["email"] == "user1@example.com"
                assert reg_data["user"]["display_name"] == "Creator One"
                token_1 = reg_data["access_token"]

                with database.SessionLocal() as db:
                    user_row = db.execute(
                        select(User).where(User.email == "user1@example.com")
                    ).scalar_one()
                    assert user_row.hashed_password is not None
                    assert user_row.hashed_password.startswith("$2")
                    assert "MyPassword123" not in user_row.hashed_password

                # 4. Duplicate registration fails cleanly
                dup = client.post(
                    "/api/auth/register",
                    json={"email": "user1@example.com", "password": "OtherPassword1"},
                )
                assert dup.status_code == 409

                # 5. Legacy unauthenticated owner row can claim a password once via register
                legacy_claim = client.post(
                    "/api/auth/register",
                    json={"email": "legacy@local.studio", "password": "LegacyPassword1"},
                )
                assert legacy_claim.status_code == 201

                # 6. Login verifies password and rejects wrong password
                bad_login = client.post(
                    "/api/auth/login",
                    json={"email": "user1@example.com", "password": "WrongPassword"},
                )
                assert bad_login.status_code == 401

                good_login = client.post(
                    "/api/auth/login",
                    json={"email": "user1@example.com", "password": "MyPassword123"},
                )
                assert good_login.status_code == 200
                login_token = good_login.json()["access_token"]

                # 7. /api/auth/me works with valid token and rejects forged token
                me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {login_token}"})
                assert me.status_code == 200
                assert me.json()["email"] == "user1@example.com"
                assert (
                    client.get(
                        "/api/auth/me", headers={"Authorization": "Bearer invalid.jwt.token"}
                    ).status_code
                    == 401
                )

                # 8. Cross-user isolation on projects
                proj = client.post(
                    "/api/projects",
                    headers={"Authorization": f"Bearer {token_1}"},
                    json={
                        "mode": "short",
                        "input_type": "title",
                        "title": "User One Private Short",
                        "raw_input": "User One Private Short",
                    },
                )
                assert proj.status_code == 201
                proj_id = proj.json()["id"]

                user2_headers = _register_and_auth_headers(client, email="user2@example.com")
                assert client.get("/api/projects", headers=user2_headers).json() == []
                assert client.delete(f"/api/projects/{proj_id}", headers=user2_headers).status_code == 404
        finally:
            database.engine.dispose()


def test_end_to_end_phase1_api_flow():
    pytest.importorskip("sqlalchemy")
    from fastapi.testclient import TestClient

    with tempfile.TemporaryDirectory() as tmp:
        os.environ["DATABASE_URL"] = f"sqlite:///{tmp}/test_v2.db"
        os.environ["WORKER_SHARED_SECRET"] = "test-secret"
        os.environ["JWT_SECRET"] = "test-jwt-secret-key-at-least-32-bytes-long"
        os.environ["STORAGE_MODE"] = "local"

        from backend.app.config import get_settings

        get_settings.cache_clear()
        from backend.app import database

        database.reconfigure_engine(os.environ["DATABASE_URL"])
        from backend.app.main import app

        try:
            with TestClient(app) as client:
                # 1. Health check + CORS origins for production Vercel frontend
                health = client.get("/api/health", headers={"Origin": "https://aishorts.space"})
                assert health.status_code == 200
                assert health.headers.get("access-control-allow-origin") == "https://aishorts.space"
                health_www = client.get("/api/health", headers={"Origin": "https://www.aishorts.space"})
                assert health_www.status_code == 200
                assert health_www.headers.get("access-control-allow-origin") == "https://www.aishorts.space"
                assert health.json()["status"] == "ok"
                assert health.json()["storage_mode"] == "local"
                assert health.json()["r2_configured"] is False

                auth_headers = _register_and_auth_headers(client)

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
                bulk = client.post("/api/clips/bulk-index", headers=auth_headers, json={"clips": [local_clip]})
                assert bulk.status_code == 200
                assert bulk.json()["inserted"] == 1
                assert bulk.json()["celebrities_created"] == 1

                dup_bulk = client.post("/api/clips/bulk-index", headers=auth_headers, json={"clips": [local_clip]})
                assert dup_bulk.status_code == 200
                assert dup_bulk.json()["inserted"] == 0
                assert dup_bulk.json()["skipped_existing"] == 1

                # 3. Create Short project & auto-detect celebrity
                proj = client.post(
                    "/api/projects",
                    headers=auth_headers,
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
    rewrites = vercel_cfg["rewrites"]
    api_rewrite = {
        "source": "/api/:path*",
        "destination": "https://short-generation-production.up.railway.app/api/:path*",
    }
    spa_rewrite = {"source": "/(.*)", "destination": "/index.html"}
    assert api_rewrite in rewrites
    assert spa_rewrite in rewrites
    assert rewrites.index(api_rewrite) < rewrites.index(spa_rewrite)

    render_yaml = (repo_root / "render.yaml").read_text(encoding="utf-8")
    assert "rootDir: backend" in render_yaml
    assert "uvicorn app.main:app" in render_yaml
    assert "healthCheckPath: /api/health" in render_yaml


def test_cors_headers_on_preflight_401_and_500_errors(monkeypatch):
    pytest.importorskip("sqlalchemy")
    from fastapi.testclient import TestClient

    with tempfile.TemporaryDirectory() as tmp:
        os.environ["DATABASE_URL"] = f"sqlite:///{tmp}/test_cors_err.db"
        os.environ["WORKER_SHARED_SECRET"] = "test-secret"
        os.environ["JWT_SECRET"] = "test-jwt-secret-key-at-least-32-bytes-long"
        os.environ["STORAGE_MODE"] = "local"

        from backend.app.config import get_settings

        get_settings.cache_clear()
        from backend.app import database

        database.reconfigure_engine(os.environ["DATABASE_URL"])
        from backend.app import main as main_mod

        try:
            with TestClient(main_mod.app, raise_server_exceptions=False) as client:
                for origin in ("https://www.aishorts.space", "https://aishorts.space"):
                    preflight = client.options(
                        "/api/projects",
                        headers={
                            "Origin": origin,
                            "Access-Control-Request-Method": "GET",
                            "Access-Control-Request-Headers": "authorization",
                        },
                    )
                    assert preflight.status_code == 200
                    assert preflight.headers.get("access-control-allow-origin") == origin

                    unauth = client.get("/api/projects", headers={"Origin": origin})
                    assert unauth.status_code == 401
                    assert unauth.headers.get("access-control-allow-origin") == origin

                monkeypatch.setattr(
                    main_mod,
                    "get_settings",
                    lambda: (_ for _ in ()).throw(RuntimeError("Simulated failure")),
                )
                err500 = client.get(
                    "/api/health",
                    headers={"Origin": "https://www.aishorts.space"},
                )
                assert err500.status_code == 500
                assert err500.headers.get("access-control-allow-origin") == "https://www.aishorts.space"
        finally:
            database.engine.dispose()
