from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ENV_FILE = Path(__file__).resolve().parent.parent.parent / ".env"


class Settings(BaseSettings):
    DATABASE_URL: str = "sqlite+aiosqlite:///./salesboost.db"
    GOOGLE_API_KEY: str = ""
    GEMINI_MODEL: str = "gemini-2.5-pro"
    SECRET_KEY: str = "your-secret-key-for-dev-only"

    model_config = SettingsConfigDict(
        env_file=str(ENV_FILE),
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
