from typing import Dict, Type

from app.infrastructure.config import Settings
from app.infrastructure.providers.base import BaseHotelProvider
from app.infrastructure.providers.booking.provider import BookingProvider
from app.infrastructure.providers.traveloka.provider import TravelokaProvider
from app.infrastructure.providers.tripadvisor.provider import TripAdvisorProvider

PROVIDER_REGISTRY: Dict[str, Type[BaseHotelProvider]] = {
    TravelokaProvider.source_name: TravelokaProvider,
    TripAdvisorProvider.source_name: TripAdvisorProvider,
    BookingProvider.source_name: BookingProvider,
}


def available_sources() -> list:
    return list(PROVIDER_REGISTRY)


def create_provider(source: str, settings: Settings) -> BaseHotelProvider:
    provider_cls = PROVIDER_REGISTRY[source]
    return provider_cls(settings)
