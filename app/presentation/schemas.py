from typing import Any, Dict, List, Optional

from pydantic import BaseModel


class HotelResultResponse(BaseModel):
    """Mirrors app.domain.entities.HotelResult -- the one shape every
    provider (Traveloka, TripAdvisor, Booking.com, ...) fills in."""

    source: str
    query_name: str
    query_address: Optional[str] = None
    query_id: Optional[str] = None
    match_score: Optional[float] = None
    low_confidence: Optional[bool] = None
    name: Optional[str] = None
    accommodation_type: Optional[str] = None
    star_rating: Optional[str] = None
    rating_summary: Optional[str] = None
    address: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    amenities: Optional[str] = None
    facilities: Optional[str] = None
    description: Optional[str] = None
    reviews: List[str] = []
    rooms: List[Dict[str, Any]] = []
    photos: List[str] = []
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
