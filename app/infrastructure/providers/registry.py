from typing import Dict, Type

from app.infrastructure.config import Settings
from app.infrastructure.providers.base import BaseHotelProvider
from app.infrastructure.providers.booking.provider import BookingProvider
from app.infrastructure.providers.traveloka.provider import TravelokaProvider

PROVIDER_REGISTRY: Dict[str, Type[BaseHotelProvider]] = {
    TravelokaProvider.source_name: TravelokaProvider,
    BookingProvider.source_name: BookingProvider,
}


def available_sources() -> list:
    return list(PROVIDER_REGISTRY)


def create_provider(source: str, settings: Settings) -> BaseHotelProvider:
    provider_cls = PROVIDER_REGISTRY[source]
    return provider_cls(settings)
