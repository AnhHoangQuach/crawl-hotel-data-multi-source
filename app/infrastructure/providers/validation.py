import re
import unicodedata

from app.domain.entities import HotelResult


def normalize_location_text(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text or "")
    no_accents = "".join(c for c in decomposed if not unicodedata.combining(c))
    normalized = re.sub(r"[^a-zA-Z0-9\s]", " ", no_accents).lower()
    return re.sub(r"\s+", " ", normalized).strip()


def mentions_vietnam(text: str) -> bool:
    normalized = normalize_location_text(text)
    return bool(re.search(r"\bviet\s*nam\b|\bvietnam\b", normalized))


def is_non_vietnam_location(text: str) -> bool:
    normalized = normalize_location_text(text)
    return bool(normalized and not mentions_vietnam(normalized))


def clear_result_details(result: HotelResult, error: str) -> None:
    result.name = None
    result.accommodation_type = None
    result.star_rating = None
    result.rating_summary = None
    result.address = None
    result.latitude = None
    result.longitude = None
    result.amenities = None
    result.facilities = None
    result.description = None
    result.reviews = []
    result.rooms = []
    result.photos = []
    result.detail_url = None
    result.error = error
