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

    Field mapping below targets the "tripadvisor-scraper" RapidAPI product
    (see Settings.tripadvisor_*). If you're on a different subscription,
    only `_map_detail()` and the candidate-label extraction should need
    changing -- the search/match/fetch flow stays the same.
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

        search_resp = await client.search_location(
            self._http, self._settings, f"{query.name} {query.address}".strip()
        )
        candidates = dig(search_resp, "results", default=[]) or []
        # The search endpoint mixes in cities/states alongside actual
        # hotels -- restrict to real hotel entities so the fuzzy matcher
        # never picks a city/state result for a hotel query.
        hotel_candidates = [c for c in candidates if dig(c, "place_type") == "HOTEL"]
        candidates = hotel_candidates or candidates
        if not candidates:
            result.error = "No results found on TripAdvisor."
            return result

        labels = [
            f"{dig(c, 'name', default='')} {dig(c, 'address', default='')} "
            f"{dig(c, 'parent_location', default='')}".strip()
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

        location_id = dig(candidates, idx, "tripadvisor_entity_id")
        if not location_id:
            result.error = "Could not extract a location id from the TripAdvisor result."
            return result

        detail = await client.get_hotel_details(self._http, self._settings, location_id)
        self._map_detail(result, detail or {})
        return result

    def _map_detail(self, result: HotelResult, detail: dict) -> None:
        result.name = dig(detail, "name")
        result.accommodation_type = (dig(detail, "type") or "").title() or None
        result.star_rating = dig(detail, "hotel_class") or dig(detail, "hotel_class_attribution")

        rating = dig(detail, "rating")
        review_count = dig(detail, "reviews")
        if rating is not None:
            result.rating_summary = (
                f"{rating} ({review_count} reviews)" if review_count else str(rating)
            )

        result.address = dig(detail, "address")
        result.latitude = dig(detail, "coordinates", "latitude")
        result.longitude = dig(detail, "coordinates", "longitude")
        result.description = dig(detail, "description")
        result.detail_url = dig(detail, "link")

        highlighted = dig(detail, "amenities", "highlighted_amenities", "property_amenities", default=[]) or []
        non_highlighted = dig(
            detail, "amenities", "non_highlighted_amenities", "property_amenities", default=[]
        ) or []
        if highlighted:
            result.amenities = ", ".join(highlighted)
        if non_highlighted:
            result.facilities = ", ".join(non_highlighted)

        images = dig(detail, "images", default=[]) or []
        result.photos = [
            url for url in (dig(img, "image_link") for img in images) if url
        ][:30]

        initial_reviews = dig(detail, "initial_reviews", default=[]) or []
        result.reviews = [text for text in (dig(r, "text") for r in initial_reviews) if text]

        # No real room inventory on this product -- the closest analog is
        # its OTA price-comparison list, so surface that as "rooms" using
        # the same dict shape Traveloka's rooms use.
        offers = (dig(detail, "booking_offers", default=[]) or []) + (
            dig(detail, "more_booking_offers", default=[]) or []
        )
        result.rooms = [
            {
                "name": dig(offer, "provider_name"),
                "bed_type": None,
                "breakfast": None,
                "price_summary": dig(offer, "price", "text"),
                "rooms_left": dig(offer, "rooms_remaining"),
                "cancellation_policy": None,
            }
            for offer in offers
        ]
