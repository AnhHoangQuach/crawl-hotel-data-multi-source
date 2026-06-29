import uuid
from typing import Callable, Dict, List

from app.application.ports.hotel_provider import HotelProviderPort
from app.application.ports.result_storage import ResultStoragePort
from app.application.services.source_resolver import resolve_sources
from app.domain.entities import HotelQuery, HotelResult

ProviderFactory = Callable[[str], HotelProviderPort]


class CrawlHotelsUseCase:
    """Crawls one hotel across every requested source and returns one
    result per source directly -- the caller awaits this and gets the
    result back in the same request, no job tracking/polling involved.
    """

    def __init__(
        self,
        provider_factory: ProviderFactory,
        result_storage: ResultStoragePort,
        available_sources: List[str],
    ):
        self._provider_factory = provider_factory
        self._result_storage = result_storage
        self._available_sources = available_sources

    async def execute(self, hotel: HotelQuery, source: str) -> Dict[str, HotelResult]:
        sources = resolve_sources(source, self._available_sources)

        request_id = uuid.uuid4().hex
        results: Dict[str, HotelResult] = {}
        for src in sources:
            provider = self._provider_factory(src)
            result = (await provider.crawl_many([hotel]))[0]
            results[src] = result
            self._result_storage.save(request_id, src, [result])
        return results
