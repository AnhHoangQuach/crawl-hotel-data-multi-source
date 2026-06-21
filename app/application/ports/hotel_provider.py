from abc import ABC, abstractmethod
from typing import Callable, List, Optional

from app.domain.entities import HotelQuery, HotelResult

# Fires after each hotel is crawled: on_progress(done_count, total_count, result).
ProgressCallback = Callable[[int, int, HotelResult], None]


class HotelProviderPort(ABC):
    """The contract every hotel data source (Traveloka, TripAdvisor,
    Booking.com, ...) must satisfy. Use cases depend on this port, never on
    a concrete provider, so adding a new source never requires touching
    application code.
    """

    source_name: str

    @abstractmethod
    async def fetch_one(self, query: HotelQuery) -> HotelResult:
        """Crawl a single hotel and return a populated HotelResult."""

    @abstractmethod
    async def crawl_many(
        self,
        queries: List[HotelQuery],
        on_progress: Optional[ProgressCallback] = None,
    ) -> List[HotelResult]:
        """Crawl every query, in order, returning one HotelResult each."""
