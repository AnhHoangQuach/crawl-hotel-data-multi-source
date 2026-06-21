from typing import Optional

import httpx

from app.application.services.fuzzy_matcher import best_suggestion_index
from app.domain.entities import HotelQuery, HotelResult
from app.infrastructure.config import Settings
from app.infrastructure.providers.base import BaseHotelProvider
from app.infrastructure.providers.utils import dig

from . import client

SOURCE_NAME = "tripadvisor"


class TripAdvisorProvider(BaseHotelProvider):
    """RapidAPI-backed provider: searches TripAdvisor's location endpoint,
    re-ranks candidates with the same fuzzy matcher Traveloka uses, then
    fetches full details for the best match.

    Field mapping below targets the "Tripadvisor16" RapidAPI product (see
    Settings.tripadvisor_*). If you're on a different subscription, only
    `_map_detail()` and the candidate-label extraction should need changing
    -- the search/match/fetch flow stays the same.
    """

    source_name = SOURCE_NAME
    delay_range = (1, 2)

    def __init__(self, settings: Settings):
        self._settings = settings
        self._http: Optional[httpx.AsyncClient] = None

    async def setup(self) -> None:
        self._http = httpx.AsyncClient(base_url=f"https://{self._settings.tripadvisor_rapidapi_host}")

    async def teardown(self) -> None:
        if self._http:
            await self._http.aclose()

    async def fetch_one(self, query: HotelQuery) -> HotelResult:
        result = HotelResult.empty(query, SOURCE_NAME)

        if not self._settings.rapidapi_key:
            result.error = "Missing RAPIDAPI_KEY environment variable."
            return result

        search_resp = await client.search_location(self._http, self._settings, query.name)
        candidates = dig(search_resp, "data", default=[]) or []
        if not candidates:
            result.error = "No results found on TripAdvisor."
            return result

        labels = [
            f"{dig(c, 'title', default='')} {dig(c, 'secondaryText', default='')}".strip()
            for c in candidates
        ]
        idx, score = best_suggestion_index(query.name, query.address, labels)
        result.match_score = round(score, 3)
        result.low_confidence = score < self._settings.match_score_threshold
        if result.low_confidence:
            result.error = (
                f"Skipped: no confidently matching hotel found "
                f"(score={score:.2f} < {self._settings.match_score_threshold})."
            )
            return result

        location_id = dig(candidates, idx, "locationId") or dig(candidates, idx, "geoId")
        if not location_id:
            result.error = "Could not extract a location id from the TripAdvisor result."
            return result

        detail_resp = await client.get_hotel_details(self._http, self._settings, location_id)
        detail = dig(detail_resp, "data", default={}) or {}
        self._map_detail(result, detail)
        return result

    def _map_detail(self, result: HotelResult, detail: dict) -> None:
        result.name = dig(detail, "name")
        result.accommodation_type = dig(detail, "accommodationCategory") or dig(
            detail, "category", "name"
        )
        result.star_rating = dig(detail, "hotelClass")

        rating = dig(detail, "rating")
        review_count = dig(detail, "numberReviews") or dig(detail, "reviewSummary", "count")
        if rating is not None:
            result.rating_summary = (
                f"{rating} ({review_count} reviews)" if review_count else str(rating)
            )

        result.address = dig(detail, "address") or dig(detail, "addressObj", "addressString")
        result.latitude = dig(detail, "latitude")
        result.longitude = dig(detail, "longitude")
        result.description = dig(detail, "description")
        result.detail_url = dig(detail, "webUrl") or dig(detail, "link")

        amenities = dig(detail, "amenities", default=[]) or []
        if amenities:
            result.amenities = ", ".join(a for a in amenities if isinstance(a, str))

        photos = dig(detail, "photos", default=[]) or []
        result.photos = [
            url for url in (dig(p, "image", "url") or dig(p, "url") for p in photos) if url
        ][:30]

        reviews = dig(detail, "reviews", default=[]) or []
        result.reviews = [text for text in (dig(r, "text") for r in reviews) if text]
