from uuid import uuid4

from fastapi.testclient import TestClient

import app.main as main
from app.core.config import settings
from app.ai.scripts import generate_script, generate_seo
from app.services.pipeline import _set_step


def owner_token(client: TestClient) -> str:
    response = client.post("/api/auth/login", json={"email": "owner@example.com", "password": "DemoOwner123!"})
    assert response.status_code == 200
    return response.json()["access_token"]


def editor_token(client: TestClient) -> str:
    # The seeded demo channel is private to the Demo Editor membership; the owner cannot see it.
    response = client.post("/api/auth/login", json={"email": "editor@example.com", "password": "DemoEditor123!"})
    assert response.status_code == 200
    return response.json()["access_token"]


def test_health_endpoint():
    with TestClient(main.app) as client:
        response = client.get("/api/health")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"


def test_register_creates_user_and_workspace():
    with TestClient(main.app) as client:
        response = client.post("/api/auth/register", json={
            "name": "Test Creator", "email": f"{uuid4()}@example.com",
            "password": "A-long-test-password!", "workspace_name": "Test Studio",
        })
        assert response.status_code == 201
        assert response.json()["role"] == "MEMBER"
        assert response.json()["access_token"]


def test_demo_seed_and_channel_creation():
    with TestClient(main.app) as client:
        token = editor_token(client)
        channels = client.get("/api/channels", headers={"Authorization": f"Bearer {token}"})
        assert channels.status_code == 200
        assert any(channel["name"] == "Demo Sports Channel" for channel in channels.json())
        created = client.post("/api/channels", headers={"Authorization": f"Bearer {token}"}, json={"name": f"Channel {uuid4().hex[:6]}"})
        assert created.status_code == 201
        assert created.json()["status"] == "demo"


def test_member_creation_and_status_change():
    with TestClient(main.app) as client:
        token = owner_token(client)
        headers = {"Authorization": f"Bearer {token}"}
        response = client.post("/api/members", headers=headers, json={"name": "Test Editor", "email": f"{uuid4()}@example.com", "role": "MEMBER"})
        assert response.status_code == 201
        assert response.json()["temporary_password"].startswith("Temp-")
        member_id = response.json()["id"]
        assert client.patch(f"/api/members/{member_id}", headers=headers, json={"active": False}).status_code == 200
        assert client.patch(f"/api/members/{member_id}", headers=headers, json={"active": True}).status_code == 200


def test_personality_creation_and_video_job_creation(monkeypatch):
    with TestClient(main.app) as client:
        token = editor_token(client)
        headers = {"Authorization": f"Bearer {token}"}
        channels = client.get("/api/channels", headers=headers).json()
        channel = next(item for item in channels if item["name"] == "Demo Sports Channel")
        personality = client.post("/api/personalities", headers=headers, json={
            "name": f"Test Theme {uuid4().hex[:6]}", "category": "Football",
            "keywords": ["football"], "research_keywords": ["training"],
            "default_duration": 45, "channel_id": channel["id"],
        })
        assert personality.status_code == 201

        def fake_pipeline(db, job, _personality, _channel):
            job.status = "ready_for_review"
            job.current_step = "ready_for_review"
            db.commit()
            return {"id": job.id, "status": job.status}

        monkeypatch.setattr("app.api.videos.run_job", lambda *args: None)
        response = client.post("/api/videos/generate", headers=headers, json={
            "channel_id": channel["id"], "personality_id": personality.json()["id"],
            "topic_mode": "manual", "manual_topic": "A unique test story",
            "duration": 45, "voice": "en-US",
        })
        assert response.status_code == 201
        assert response.json()["status"] == "researching"


def test_script_parser_and_seo_shape(monkeypatch):
    monkeypatch.setattr(settings, "gemini_api_key", "")
    script, provider = generate_script("A test topic", "A test theme", "Clear", 30)
    assert provider == "development fallback"
    assert set(script) == {"hook", "context", "main_story", "why_it_matters", "ending", "full_script"}
    seo = generate_seo("A test topic", "A test theme", script)
    assert seo["title"]
    assert 3 <= len(seo["hashtags"]) <= 6
    assert 2 <= len(seo["cover_text"].split()) <= 4


def test_video_job_status_transitions():
    class FakeSession:
        def commit(self):
            pass

    class FakeJob:
        status = "researching"
        current_step = "researching"

    job = FakeJob()
    _set_step(FakeSession(), job, "script_generation")
    assert job.status == "script_generation"
    try:
        _set_step(FakeSession(), job, "uploaded")
    except ValueError as error:
        assert "Invalid video job transition" in str(error)
    else:
        raise AssertionError("Invalid status transition was accepted.")
