"""Application configuration loaded from environment variables."""

from functools import lru_cache
from urllib.parse import urlparse

from arq.connections import RedisSettings
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Patchwork runtime settings matching `.env.example`."""

    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/patchwork"
    redis_url: str = "redis://localhost:6379/0"

    gemini_api_key: str = ""
    gemini_model: str = "gemini-3.8-flash"
    groq_api_key: str = ""
    primary_llm_provider: str = "gemini"

    sandbox_image: str = "patchwork-sandbox:latest"
    github_token: str = ""

    webhook_secret: str = ""
    max_agent_retries: int = 3
    max_files_per_patch: int = 3
    sql_echo: bool = False

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


def parse_arq_redis_settings(redis_url: str) -> RedisSettings:
    """Parse `redis://` (non-TLS, e.g. Redis Cloud) or `rediss://` (TLS) into ARQ RedisSettings."""
    parsed = urlparse(redis_url)
    use_ssl = parsed.scheme.lower() == "rediss"
    settings = RedisSettings.from_dsn(redis_url)
    settings.ssl = use_ssl
    return settings


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings instance."""
    return Settings()
