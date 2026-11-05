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
    gemini_model: str = "gemini-flash-latest"
    gemini_fallback_model: str = ""
    tts_provider: str = "local"
    title_short_tts_provider: Literal["local", "kokoro_onnx", "elevenlabs"] = "local"
    title_short_voice: str = ""
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
