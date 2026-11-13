from pathlib import Path
from typing import Literal
from pydantic import field_validator,Field

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    app_secret_key: str = ""
    database_url: str = "sqlite:///./ai_shorts.db"
    frontend_origin: str = "http://localhost:5173"
    cors_origins: str = ""
    gemini_api_key: str = ""
    gemini_api_keys: str = ""
    gemini_model: str = "gemini-2.5-flash"
    gemini_fallback_model: str = ""
    gemini_fallback_models: str = "gemini-2.5-flash-lite,gemini-3.5-flash-lite,gemini-2.0-flash,gemini-flash-latest,gemma-3-27b-it"
    groq_api_key: str = ""
    groq_model: str = "llama-3.3-70b-versatile"
    openai_compat_base_url: str = ""
    openai_compat_api_key: str = ""
    openai_compat_model: str = ""
    ollama_base_url: str = "http://127.0.0.1:11434"
    ollama_model: str = ""
    ai_auto_detect_ollama: bool = True
    tts_provider: str = "local"
    title_short_tts_provider: Literal["local", "kokoro_onnx", "elevenlabs", "gemini_tts"] = "local"
    title_short_voice: str = ""
    title_short_voice_style: str = "Newscaster"
    title_short_voice_pace: str = "Rapid"
    title_short_voice_accent: str = "American English"
    title_short_ai_model: str = ""
    title_short_search_provider: Literal["bing_rss", "brave"] = "bing_rss"
    brave_search_api_key: str = ""
    google_tts_api_key: str = ""
    elevenlabs_api_key: str = ""
    elevenlabs_voice_id: str = ""
    ffprobe_path: str = "ffprobe"
    seed_demo: bool = False
    ffmpeg_path: str = "ffmpeg"
    generated_dir: Path = Path("../generated")
    google_client_id: str = ""
    google_client_secret: str = ""
    google_redirect_uri: str = "http://127.0.0.1:8000/api/youtube/callback"
    token_encryption_key: str = ""
    research_provider: Literal['demo', 'rss'] = "demo"
    rss_feeds: str = "https://feeds.bbci.co.uk/sport/football/rss.xml,https://www.theguardian.com/football/rss,https://news.google.com/rss/search?q=football%20when%3A3d&hl=en-US&gl=US&ceid=US%3Aen"
    research_max_age_hours: int = 72
    review_drafts_enabled: bool = False
    evergreen_search_url: str = 'https://www.bing.com/search'
    evergreen_max_sources: int = Field(default=12,ge=1,le=20)
    research_sources_file: str = 'app/research/sources.json'
    asset_provider: str = "commons"
    pexels_api_key: str = ""
    pixabay_api_key: str = ""
    elevenlabs_allowed_voice_ids: str = ""
    google_tts_voice: str = "en-US-Neural2-D"
    google_application_credentials: str = ""
    scheduler_enabled: bool = True
    youtube_uploads_enabled: bool = False
    youtube_test_channel_ids: str = ""
    local_media_roots: str = "{}"  # JSON member ID -> explicitly permitted absolute folder
    analytics_cache_seconds: int = 900
    analytics_refresh_seconds: int = 60
    network_user_agent: str = "AIShortsPlatform/0.2 (local user-operated research)"
    wikimedia_operator_contact: str = ''
    wikimedia_cache_seconds: int = Field(default=900,ge=0,le=86400)
    smtp_host: str = ''
    smtp_port: int = 587
    smtp_user: str = ''
    smtp_password: str = ''
    smtp_from: str = ''

    model_config = SettingsConfigDict(env_file=BACKEND_DIR / '.env', env_file_encoding='utf-8', extra="ignore")

    @field_validator('generated_dir')
    @classmethod
    def generated_path(cls, value):
        return value if value.is_absolute() else (BACKEND_DIR / value).resolve()

    @field_validator('database_url')
    @classmethod
    def database_path(cls, value):
        if value.startswith('sqlite:///') and value != 'sqlite:///:memory:':
            path = Path(value[len('sqlite:///'):])
            if not path.is_absolute():
                return 'sqlite:///' + (BACKEND_DIR / path).resolve().as_posix()
        return value


settings = Settings()

# A persistent local signing key avoids a shared default secret.
if not settings.app_secret_key:
    import secrets
    secret_file = Path(__file__).resolve().parents[2] / ".session_secret"
    if not secret_file.exists():
        secret_file.write_text(secrets.token_urlsafe(48), encoding="utf-8")
    settings.app_secret_key = secret_file.read_text(encoding="utf-8").strip()


RUNTIME_AI_FIELDS = (
    "gemini_api_key",
    "gemini_api_keys",
    "gemini_model",
    "gemini_fallback_model",
    "gemini_fallback_models",
    "title_short_ai_model",
    "groq_api_key",
    "groq_model",
    "openai_compat_base_url",
    "openai_compat_api_key",
    "openai_compat_model",
    "ollama_base_url",
    "ollama_model",
    "ai_auto_detect_ollama",
)
RUNTIME_AI_FILE = BACKEND_DIR / ".ai_providers.json"


def apply_runtime_ai_overrides() -> None:
    """Load persisted server-side AI provider overrides when present (skipped in pytest)."""
    import json, sys
    if "pytest" in sys.modules or settings.seed_demo:
        return
    if not RUNTIME_AI_FILE.is_file():
        return
    try:
        data = json.loads(RUNTIME_AI_FILE.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            for field in RUNTIME_AI_FIELDS:
                if field in data and data[field] is not None:
                    setattr(settings, field, data[field])
    except Exception:
        pass


def save_runtime_ai_overrides(updates: dict) -> dict:
    """Persist AI provider overrides on disk and update in-memory settings immediately."""
    import json
    existing = {}
    if RUNTIME_AI_FILE.is_file():
        try:
            loaded = json.loads(RUNTIME_AI_FILE.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                existing = loaded
        except Exception:
            existing = {}
    for field in RUNTIME_AI_FIELDS:
        if field in updates and updates[field] is not None:
            existing[field] = updates[field]
            setattr(settings, field, updates[field])
    RUNTIME_AI_FILE.write_text(json.dumps(existing, indent=2), encoding="utf-8")
    return existing


apply_runtime_ai_overrides()
