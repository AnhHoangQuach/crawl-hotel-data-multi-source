from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class HotelResultResponse(BaseModel):
    """Mirrors app.domain.entities.HotelResult -- the one shape every
    provider (Traveloka, Booking.com, ...) fills in."""

    source: str
    query_name: str
    query_address: Optional[str] = None
    query_id: Optional[str] = None
    match_score: Optional[float] = None
    low_confidence: Optional[bool] = None
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


class JobProgressResponse(BaseModel):
    done: int
    total: int


class JobSummaryResponse(BaseModel):
    job_id: str
    status: str
    sources: List[str]
    total_hotels: int
    created_at: str
    progress: Dict[str, JobProgressResponse]
    error: Optional[str] = None


class JobResultsResponse(BaseModel):
    job_id: str
    status: str
    results: Dict[str, List[HotelResultResponse]]
