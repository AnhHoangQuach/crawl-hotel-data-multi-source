import asyncio
import logging
import random
from typing import List

from app.application.ports.hotel_provider import HotelProviderPort
from app.domain.entities import HotelQuery, HotelResult

logger = logging.getLogger(__name__)


class BaseHotelProvider(HotelProviderPort):
    """Shared `crawl_many` template method: iterate queries, normalize
    errors into a HotelResult, rate-limit, log progress. Concrete providers
    (Traveloka, Booking.com) only need to implement `fetch_one()`.
    """

    source_name = "base"
    # (min, max) seconds to sleep between hotels. None/empty disables the delay.
    delay_range = (1, 2)

    async def setup(self) -> None:
        """Open any shared resources (browser, http client) once before the
        crawl loop starts. Override as needed."""

    async def teardown(self) -> None:
        """Release resources opened in `setup()`. Override as needed."""

    async def fetch_one(self, query: HotelQuery) -> HotelResult:
        raise NotImplementedError

    async def crawl_many(self, queries: List[HotelQuery]) -> List[HotelResult]:
        results: List[HotelResult] = []
        last_index = len(queries) - 1
        await self.setup()
        try:
            for index, query in enumerate(queries):
                logger.info("[%s] crawling: %s (%s)", self.source_name, query.name, query.address or "no address")
                try:
                    result = await self.fetch_one(query)
                except Exception as e:
                    result = HotelResult.empty(query, self.source_name)
                    result.error = str(e)

                status = "OK" if result.name else "FAIL"
                logger.info("  -> %s: %s", status, result.name or result.error)
                results.append(result)

                # Only pace *between* hotels in the same browser session -- no
                # point delaying after the last (or only) one before returning.
                if self.delay_range and index < last_index:
                    await asyncio.sleep(random.uniform(*self.delay_range))
        finally:
            await self.teardown()
        return results
