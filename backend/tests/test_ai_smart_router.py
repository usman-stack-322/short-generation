import json
from types import SimpleNamespace
import httpx
import pytest

from app.ai import smart_router
from app.core.config import settings
from app.services import title_shorts as ts_service


@pytest.fixture(autouse=True)
def reset_router(monkeypatch):
    smart_router.clear_cooldowns()
    smart_router._PROMPT_CACHE.clear()
    monkeypatch.setattr(settings, "gemini_api_key", "key-primary-123456")
    monkeypatch.setattr(settings, "gemini_api_keys", "")
    monkeypatch.setattr(settings, "gemini_model", "gemini-2.5-flash")
    monkeypatch.setattr(settings, "gemini_fallback_model", "gemini-2.5-flash-lite")
    monkeypatch.setattr(settings, "gemini_fallback_models", "gemini-2.0-flash,gemma-3-27b-it")
    monkeypatch.setattr(settings, "groq_api_key", "")
    monkeypatch.setattr(settings, "openai_compat_base_url", "")
    monkeypatch.setattr(settings, "openai_compat_model", "")
    monkeypatch.setattr(settings, "ollama_model", "")
    monkeypatch.setattr(settings, "ai_auto_detect_ollama", False)
    yield
    smart_router.clear_cooldowns()


def _analysis_payload():
    return {
        "topic": "Basketball Interview",
        "viewer_intent": "Understand what sparked the debate",
        "angle": "What specific defense claim prompted the discussion?",
        "rationale": "Focused single debate point fits a 45-second short.",
        "search_queries": ["Iman Shumpert Steph Curry interview"],
        "people": ["Iman Shumpert", "Gilbert Arenas", "Steph Curry"],
        "alleged_claims": [],
    }


def test_cascades_on_429_to_next_gemini_model(monkeypatch):
    called_models = []

    def fake_post(url, **kwargs):
        model = url.split("/models/")[1].split(":")[0]
        called_models.append((model, kwargs["headers"]["x-goog-api-key"]))
        if model == "gemini-2.5-flash":
            return httpx.Response(
                429,
                json={"error": {"status": "RESOURCE_EXHAUSTED", "message": "Quota exceeded. Please retry in 2h0m0s."}},
                request=httpx.Request("POST", url),
            )
        return httpx.Response(
            200,
            json={"candidates": [{"content": {"parts": [{"text": json.dumps(_analysis_payload())}]}}]},
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(smart_router.httpx, "post", fake_post)
    result = smart_router.run_structured_ai("Analyze title", ts_service.Analysis)
    assert result["topic"] == "Basketball Interview"
    assert [m for m, _ in called_models] == ["gemini-2.5-flash", "gemini-2.5-flash-lite"]
    # Exhausted model stays in cooldown and is skipped on the very next call
    called_models.clear()
    smart_router.run_structured_ai("Analyze title 2", ts_service.Analysis)
    assert [m for m, _ in called_models] == ["gemini-2.5-flash-lite"]


def test_rotates_multiple_keys_before_downgrading_model(monkeypatch):
    monkeypatch.setattr(settings, "gemini_api_key", "key-one-abcdef,key-two-ghijkl")
    seen = []

    def fake_post(url, **kwargs):
        key = kwargs["headers"]["x-goog-api-key"]
        seen.append(key)
        if key == "key-one-abcdef":
            return httpx.Response(429, json={"error": {"status": "RESOURCE_EXHAUSTED", "message": "limit reached"}}, request=httpx.Request("POST", url))
        return httpx.Response(
            200,
            json={"candidates": [{"content": {"parts": [{"text": json.dumps(_analysis_payload())}]}}]},
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(smart_router.httpx, "post", fake_post)
    smart_router.run_structured_ai("Analyze", ts_service.Analysis)
    assert seen == ["key-one-abcdef", "key-two-ghijkl"]


def test_falls_back_to_groq_when_all_gemini_hit_429(monkeypatch):
    monkeypatch.setattr(settings, "groq_api_key", "gsk_test_secret_key")

    def fake_post(url, **kwargs):
        if "generativelanguage.googleapis.com" in url:
            return httpx.Response(429, json={"error": {"status": "RESOURCE_EXHAUSTED", "message": "daily quota"}}, request=httpx.Request("POST", url))
        assert "api.groq.com" in url
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": json.dumps(_analysis_payload())}}]},
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(smart_router.httpx, "post", fake_post)
    res = smart_router.run_structured_ai("Analyze", ts_service.Analysis)
    assert res["topic"] == "Basketball Interview"
    assert smart_router.get_ai_status()["last_success"]["provider"] == "groq"


def test_gemma_model_omits_response_schema_and_parses_fenced_json(monkeypatch):
    monkeypatch.setattr(settings, "gemini_model", "gemma-3-27b-it")
    monkeypatch.setattr(settings, "gemini_fallback_model", "")
    monkeypatch.setattr(settings, "gemini_fallback_models", "")
    captured = {}

    def fake_post(url, **kwargs):
        captured.update(kwargs["json"])
        fenced = "```json\n" + json.dumps(_analysis_payload()) + "\n```"
        return httpx.Response(200, json={"candidates": [{"content": {"parts": [{"text": fenced}]}}]}, request=httpx.Request("POST", url))

    monkeypatch.setattr(smart_router.httpx, "post", fake_post)
    res = smart_router.run_structured_ai("Analyze", ts_service.Analysis)
    assert "responseJsonSchema" not in captured["generationConfig"]
    assert res["people"] == ["Iman Shumpert", "Gilbert Arenas", "Steph Curry"]


def test_extractive_quota_fallback_builds_valid_english_plan():
    draft = SimpleNamespace(title="Iman Shumpert defends Steph Curry against Gilbert Arenas", duration=45, language="English", style="educational", data="{}")
    sources = [
        {"id": "S1", "url": "https://one.edu/a", "publisher_group": "one", "excerpt": "Iman Shumpert responded to comments from Gilbert Arenas about Steph Curry during a recorded interview. The discussion centered on championship defense rules and shooting efficiency across different basketball eras."},
        {"id": "S2", "url": "https://two.edu/b", "publisher_group": "two", "excerpt": "Analysts reviewing the podcast pointed out that Steph Curry won multiple titles while guarded aggressively every night. Several former players weighed in on how modern spacing changed perimeter defense."},
    ]
    analysis = ts_service._local_analysis_from_title(draft.title, draft.duration, draft.style)
    data = {"analysis": analysis, "lead": {"people": ["Iman Shumpert", "Steph Curry", "Gilbert Arenas"]}, "sources": sources}
    plan = ts_service._extractive_grounded_plan(draft, data)
    assert plan is not None
    checked = ts_service.check_plan(draft, plan, sources, verify=False)
    assert len(checked["scenes"]) == 4

