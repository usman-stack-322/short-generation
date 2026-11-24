from functools import lru_cache
from typing import List

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: str = "development"
    app_name: str = "AI Shorts Studio v2"
    storage_mode: str = "local"
    api_cors_origins: str = "http://localhost:5173"
    cors_origins: str = ""
    default_owner_email: str = "owner@local.studio"

    database_url: str = "sqlite:///./ai_shorts_v2.db"

    r2_account_id: str = ""
    r2_access_key_id: str = ""
    r2_secret_access_key: str = ""
    r2_bucket_name: str = "ai-shorts-vault"
    r2_public_url: str = ""

    gemini_api_key: str = ""
    worker_shared_secret: str = "dev-worker-secret"

    @property
    def cors_origin_list(self) -> List[str]:
        combined = ",".join(part for part in (self.api_cors_origins, self.cors_origins) if part)
        cleaned = [origin.strip().rstrip("/") for origin in combined.split(",") if origin.strip().rstrip("/")]
        return list(dict.fromkeys(cleaned))

    @property
    def r2_endpoint_url(self) -> str:
        if not self.r2_account_id:
            return ""
        return f"https://{self.r2_account_id}.r2.cloudflarestorage.com"

    @property
    def is_local_storage(self) -> bool:
        return (self.storage_mode or "local").strip().lower() == "local"

    @property
    def r2_configured(self) -> bool:
        if self.is_local_storage:
            return False
        placeholders = {
            "your_cloudflare_account_id",
            "your_r2_access_key_id",
            "your_r2_secret_access_key",
        }
        values = [self.r2_account_id, self.r2_access_key_id, self.r2_secret_access_key, self.r2_bucket_name]
        return all(bool(val and val.strip() and val.strip() not in placeholders) for val in values)


@lru_cache
def get_settings() -> Settings:
    return Settings()
