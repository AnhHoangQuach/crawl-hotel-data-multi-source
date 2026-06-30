from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central application configuration, sourced from environment
    variables / a .env file. Replaces scattered os.environ.get() calls so
    every setting has one documented, typed home.
    """

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- Server ---
    host: str = "0.0.0.0"
    port: int = 8000

    # --- Shared provider tuning ---
    request_timeout_seconds: float = 20.0


@lru_cache
def get_settings() -> Settings:
    return Settings()
