from abc import ABC, abstractmethod
from typing import List

from app.domain.entities import HotelQuery, HotelResult


class HotelProviderPort(ABC):
    """The contract every hotel data source (Traveloka, Booking.com, ...)
    must satisfy. Use cases depend on this port, never on a concrete
    provider, so adding a new source never requires touching application code.
    """

    source_name: str

    @abstractmethod
    async def fetch_one(self, query: HotelQuery) -> HotelResult:
        """Crawl a single hotel and return a populated HotelResult."""

    @abstractmethod
    async def crawl_many(self, queries: List[HotelQuery]) -> List[HotelResult]:
        """Crawl every query, in order, returning one HotelResult each."""
