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
    output_dir: str = "output"

    # --- Shared provider tuning ---
    # Below this, the picked search result is probably the wrong hotel.
    # fuzzy_matcher scores a confirmed address+name match near 1.0, a
    # confirmed address mismatch is heavily discounted regardless of how
    # similar the names look (the failure mode that let e.g. a Bangkok,
    # Thailand candidate outscore the real Hai Phong, Vietnam hotel before
    # this scoring was address-first), and 0.5 sits comfortably below any
    # genuine match and above a name-only coincidence in the wrong place.
    # The result is still returned but flagged so it isn't mistaken for a
    # real match.
    match_score_threshold: float = 0.5
    request_timeout_seconds: float = 20.0


@lru_cache
def get_settings() -> Settings:
    return Settings()
