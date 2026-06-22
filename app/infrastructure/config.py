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

    # --- RapidAPI (shared key, per-provider host/path overrides) ---
    rapidapi_key: str = ""

    tripadvisor_rapidapi_host: str = "tripadvisor-scraper.p.rapidapi.com"
    tripadvisor_search_path: str = "/hotels/search"
    tripadvisor_details_path: str = "/hotels/detail"

    booking_rapidapi_host: str = "booking-com15.p.rapidapi.com"
    booking_search_destination_path: str = "/api/v1/hotels/searchDestination"
    booking_search_hotels_path: str = "/api/v1/hotels/searchHotels"
    booking_details_path: str = "/api/v1/hotels/getHotelDetails"
    booking_currency_code: str = "VND"

    # --- Shared provider tuning ---
    # Below this, the picked search result is probably the wrong hotel --
    # either the provider's own ranking went off into an unrelated city/
    # country, or the only "best" candidate just happens to share a generic
    # location with the query (e.g. "Soul Boutique Hotel Phu Quoc" scored
    # 0.46 against query "THE SEA PHU QUOC" / "Kien Giang" purely on shared
    # province text). Empirically (on Traveloka), correct matches in testing
    # scored 0.67-0.74; wrong ones scored 0.28-0.46 -- 0.5 sits in the gap.
    # The result is still returned but flagged so it isn't mistaken for a
    # real match.
    match_score_threshold: float = 0.5
    request_timeout_seconds: float = 20.0


@lru_cache
def get_settings() -> Settings:
    return Settings()
