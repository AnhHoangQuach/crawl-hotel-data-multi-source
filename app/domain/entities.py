from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Union

from .cleaning import clean_hotel_result_dict


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
    rating_summary: Optional[Union[str, List[str]]] = None
    address: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    amenities: Optional[Union[str, List[str]]] = None
    facilities: Optional[Union[str, List[str]]] = None
    description: Optional[Union[str, List[str]]] = None
    reviews: List[Union[str, List[str]]] = field(default_factory=list)
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
        return clean_hotel_result_dict(self.to_raw_dict())
