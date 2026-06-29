from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator


class CrawlRequest(BaseModel):
    """One hotel to crawl per call. `id` is an optional passthrough for the
    caller's own record id (e.g. a staging-table row id), carried through to
    `query_id` in the results so it can be correlated back without relying
    on name matching."""

    id: Optional[str] = None
    name: str = Field(..., min_length=1)
    address: Optional[str] = ""
    source: str = "all"

    @field_validator("name")
    @classmethod
    def _name_must_not_be_blank(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("name must not be blank")
        return v


class HotelResultResponse(BaseModel):
    """Mirrors app.domain.entities.HotelResult -- the one shape every
    provider (Traveloka, Booking.com, ...) fills in."""

    source: str
    query_name: str
    query_address: Optional[str] = None
    query_id: Optional[str] = None
    name: Optional[str] = None
    accommodation_type: Optional[str] = None
    star_rating: Optional[str] = None
    rating_summary: List[str] = Field(default_factory=list)
    address: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    amenities: List[str] = Field(default_factory=list)
    facilities: List[str] = Field(default_factory=list)
    description: List[str] = Field(default_factory=list)
    reviews: List[List[str]] = Field(default_factory=list)
    rooms: List[Dict[str, Any]] = Field(default_factory=list)
    photos: List[str] = Field(default_factory=list)
    detail_url: Optional[str] = None
    error: Optional[str] = None


# Response of POST /crawl: source name -> that source's HotelResult, e.g.
# {"traveloka": {...}, "booking": {...}}.
CrawlResponse = Dict[str, HotelResultResponse]
