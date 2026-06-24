from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

from .cleaning import clean_hotel_result_dict

_CRAWLED_SCALAR_FIELDS = (
    "name",
    "accommodation_type",
    "star_rating",
    "address",
    "latitude",
    "longitude",
    "detail_url",
)
_CRAWLED_ARRAY_FIELDS = (
    "rating_summary",
    "amenities",
    "facilities",
    "description",
    "reviews",
    "rooms",
    "photos",
)


@dataclass(frozen=True)
class HotelQuery:
    """One input row: the hotel a provider should search for.

    `id` is optional passthrough for the caller's own record id (e.g. a
    staging-table row id), so results can be correlated back to the source
    system. It plays no role in search/matching.
    """

    name: str
    address: str = ""
    id: Optional[str] = None


@dataclass
class HotelResult:
    """The one shape every provider (Traveloka, Booking.com, ...) must fill
    in. Keeping this as a single entity is what lets the API
    treat all sources identically and lets downstream consumers parse any
    job's results the same way regardless of source.
    """

    source: str
    query_name: str
    query_address: Optional[str] = None
    query_id: Optional[str] = None
    name: Optional[str] = None
    accommodation_type: Optional[str] = None
    star_rating: Optional[str] = None
    rating_summary: List[str] = field(default_factory=list)
    address: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    amenities: List[str] = field(default_factory=list)
    facilities: List[str] = field(default_factory=list)
    description: List[str] = field(default_factory=list)
    reviews: List[List[str]] = field(default_factory=list)
    rooms: List[Dict[str, Any]] = field(default_factory=list)
    photos: List[str] = field(default_factory=list)
    detail_url: Optional[str] = None
    error: Optional[str] = None

    @classmethod
    def empty(cls, query: HotelQuery, source: str) -> "HotelResult":
        return cls(
            source=source, query_name=query.name, query_address=query.address, query_id=query.id
        )

    def to_raw_dict(self) -> dict:
        return asdict(self)

    def to_dict(self) -> dict:
        cleaned = clean_hotel_result_dict(self.to_raw_dict())
        if cleaned.get("error"):
            for field_name in _CRAWLED_SCALAR_FIELDS:
                cleaned[field_name] = None
            for field_name in _CRAWLED_ARRAY_FIELDS:
                cleaned[field_name] = []
        return cleaned
