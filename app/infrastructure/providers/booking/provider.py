import datetime
from typing import Optional

import httpx

from app.application.services.fuzzy_matcher import best_suggestion_index
from app.domain.entities import HotelQuery, HotelResult
from app.infrastructure.config import Settings
from app.infrastructure.providers.base import BaseHotelProvider
from app.infrastructure.providers.utils import dig

from . import client

SOURCE_NAME = "booking"


def _default_dates():
    """Booking.com's search/detail endpoints require a stay date range --
    default to tomorrow/day-after, matching Traveloka's default search dates.
    """
    checkin = datetime.date.today() + datetime.timedelta(days=1)
    checkout = checkin + datetime.timedelta(days=1)
    return checkin.isoformat(), checkout.isoformat()


class BookingProvider(BaseHotelProvider):
    """RapidAPI-backed provider: resolves the query to a destination, lists
    hotels in it, re-ranks them with the same fuzzy matcher Traveloka uses,
    then fetches full details for the best match.

    Field mapping below targets the "Booking-com15" RapidAPI product (see
    Settings.booking_*). If you're on a different subscription, only
    `_map_detail()` and the candidate-label extraction should need changing
    -- the search/match/fetch flow stays the same.
    """

    source_name = SOURCE_NAME
    delay_range = (1, 2)

    def __init__(self, settings: Settings):
        self._settings = settings
        self._http: Optional[httpx.AsyncClient] = None

    async def setup(self) -> None:
        self._http = httpx.AsyncClient(base_url=f"https://{self._settings.booking_rapidapi_host}")

    async def teardown(self) -> None:
        if self._http:
            await self._http.aclose()

    async def fetch_one(self, query: HotelQuery) -> HotelResult:
        result = HotelResult.empty(query, SOURCE_NAME)

        if not self._settings.rapidapi_key:
            result.error = "Missing RAPIDAPI_KEY environment variable."
            return result

        checkin, checkout = _default_dates()

        dest_resp = await client.search_destination(
            self._http, self._settings, f"{query.name} {query.address}".strip()
        )
        destinations = dig(dest_resp, "data", default=[]) or []
        if not destinations:
            result.error = "No destination found on Booking.com."
            return result

        dest_labels = [dig(d, "name", default="") for d in destinations]
        d_idx, _ = best_suggestion_index(query.name, query.address, dest_labels)
        dest = destinations[d_idx]
        dest_id = dig(dest, "dest_id")
        search_type = dig(dest, "search_type") or dig(dest, "dest_type")
        if not dest_id:
            result.error = "Could not extract a dest_id from the Booking.com result."
            return result

        hotels_resp = await client.search_hotels(
            self._http, self._settings, dest_id, search_type, checkin, checkout
        )
        hotels = dig(hotels_resp, "data", "hotels", default=[]) or []
        if not hotels:
            result.error = "No hotel found on Booking.com."
            return result

        hotel_labels = [
            dig(h, "property", "name", default="") or dig(h, "hotel_name", default="")
            for h in hotels
        ]
        idx, score = best_suggestion_index(query.name, query.address, hotel_labels)
        result.match_score = round(score, 3)
        result.low_confidence = score < self._settings.match_score_threshold
        if result.low_confidence:
            result.error = (
                f"Skipped: no confidently matching hotel found "
                f"(score={score:.2f} < {self._settings.match_score_threshold})."
            )
            return result

        hotel = hotels[idx]
        hotel_id = dig(hotel, "hotel_id") or dig(hotel, "property", "id")
        if not hotel_id:
            result.error = "Could not extract a hotel_id from the Booking.com result."
            return result

        detail_resp = await client.get_hotel_details(self._http, self._settings, hotel_id, checkin, checkout)
        detail = dig(detail_resp, "data", default={}) or {}
        self._map_detail(result, detail)
        return result

    def _map_detail(self, result: HotelResult, detail: dict) -> None:
        result.name = dig(detail, "hotel_name") or dig(detail, "property", "name")
        result.accommodation_type = dig(detail, "accommodation_type_name")
        result.star_rating = dig(detail, "propertyClass") or dig(detail, "class")

        score = dig(detail, "reviewScore") or dig(detail, "review_score")
        review_count = dig(detail, "reviewCount") or dig(detail, "review_nr")
        if score is not None:
            result.rating_summary = f"{score} ({review_count} reviews)" if review_count else str(score)

        result.address = dig(detail, "address")
        result.latitude = dig(detail, "latitude")
        result.longitude = dig(detail, "longitude")
        result.description = dig(detail, "description")
        result.detail_url = dig(detail, "url")

        # Photos/facilities/rooms: exact response shape depends on the
        # RapidAPI plan in use -- left minimal pending confirmation of the
        # real subscription's docs (see class docstring).
        photos = dig(detail, "photos", default=[]) or []
        result.photos = [
            url for url in (dig(p, "url_original") or dig(p, "url_max") for p in photos) if url
        ][:30]
