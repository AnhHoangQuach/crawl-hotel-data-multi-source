import asyncio
import logging

from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig

from app.domain.entities import HotelQuery, HotelResult
from app.infrastructure.config import Settings
from app.infrastructure.providers.base import BaseHotelProvider

from .config import HOMEPAGE_URL
from .scraper import SOURCE_NAME, HotelScraper

logger = logging.getLogger(__name__)

# Same bounded-retry shape as TripAdvisorProvider: 2 immediate attempts,
# then (if both failed) a cooldown before one final attempt -- a hotel that
# keeps failing can't hang the whole batch job, but a transient hiccup gets
# a real second chance.
_ATTEMPT_PHASES = (2, 1)
_RETRY_COOLDOWN_SECONDS = 60


class BookingProvider(BaseHotelProvider):
    """Playwright/crawl4ai-driven provider: searches booking.com directly
    and scrapes the best-matching hotel's page, same approach as
    TravelokaProvider/TripAdvisorProvider. Replaces the previous
    RapidAPI-backed implementation, which hit that subscription's request
    limits.

    Unlike TripAdvisor, booking.com's anti-bot (an AWS WAF JS challenge)
    resolves automatically in a real/headless browser -- every selector in
    `config.py` was verified against real, organically-fetched page HTML
    while building this (search -> results -> detail), not guessed. The one
    real gotcha found: an inline date-picker calendar can sit on top of the
    results list and silently swallow clicks (see scraper.py).

    Deliberately runs direct only, no free-proxy fallback (unlike Traveloka/
    TripAdvisor): direct connections already pass the WAF challenge
    reliably every time in testing, while booking.com's destination search
    is geo-biased by the requester's IP -- a free proxy in a random country
    was confirmed to make it match a same-named hotel in the proxy's
    country instead of the intended one. The fallback would trade a problem
    that doesn't occur here for one that does.
    """

    source_name = SOURCE_NAME
    delay_range = (3, 6)

    def __init__(self, settings: Settings):
        self.scraper = HotelScraper(settings.match_score_threshold)
        self.crawler = None
        self.run_cfg = None

    async def setup(self) -> None:
        browser_cfg = BrowserConfig(
            headless=True, viewport_width=1400, viewport_height=900, enable_stealth=True
        )
        self.run_cfg = CrawlerRunConfig(
            max_retries=0,
            wait_until="domcontentloaded",
            page_timeout=60000,
        )
        self.crawler = AsyncWebCrawler(config=browser_cfg)
        await self.crawler.__aenter__()
        self.crawler.crawler_strategy.set_hook("after_goto", self.scraper.after_goto_hook)

    async def teardown(self) -> None:
        if self.crawler:
            await self.crawler.__aexit__(None, None, None)

    async def fetch_one(self, query: HotelQuery) -> HotelResult:
        self.scraper.query = query
        result = None

        for phase_idx, attempts in enumerate(_ATTEMPT_PHASES):
            if phase_idx > 0:
                logger.info(
                    "[%s] %s: %d attempt(s) failed, cooling down %ds before retrying",
                    self.source_name, query.name, sum(_ATTEMPT_PHASES[:phase_idx]), _RETRY_COOLDOWN_SECONDS,
                )
                await asyncio.sleep(_RETRY_COOLDOWN_SECONDS)

            for _ in range(attempts):
                self.scraper.result = None
                try:
                    await self.crawler.arun(url=HOMEPAGE_URL, config=self.run_cfg)
                    result = self.scraper.result
                except Exception as e:
                    result = HotelResult.empty(query, self.source_name)
                    result.error = str(e)

                if result and result.name:
                    return result

        return result or HotelResult.empty(query, self.source_name)
