import asyncio
import logging

from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig, ProxyConfig

from app.domain.entities import HotelQuery, HotelResult
from app.infrastructure.config import Settings
from app.infrastructure.providers.base import BaseHotelProvider

from ..free_proxy import get_working_proxies
from .config import HOMEPAGE_URL
from .scraper import SOURCE_NAME, HotelScraper

logger = logging.getLogger(__name__)

# Attempt phases for one hotel: 2 immediate attempts, then (if both failed) a
# cooldown before one final attempt -- bounded so a hotel that's permanently
# blocked can't hang the whole batch job, but transient DataDome hiccups get
# a real second chance once the wall has had a minute to relax.
_ATTEMPT_PHASES = (2, 1)
_RETRY_COOLDOWN_SECONDS = 60


class TripAdvisorProvider(BaseHotelProvider):
    """Playwright/crawl4ai-driven provider: searches tripadvisor.com directly
    and scrapes the best-matching hotel's page, same approach as
    TravelokaProvider. Replaces the previous RapidAPI-backed implementation,
    which hit that subscription's request limits.

    TripAdvisor sits behind DataDome, a much stronger anti-bot wall than
    Traveloka's -- every request from this dev environment (direct, headless
    and non-headless Playwright, and 10 free proxies) was blocked by a
    CAPTCHA challenge before any page rendered, and detail-page selectors in
    `config.py` could not be verified against live markup as a result. The
    flow/architecture mirrors Traveloka; selectors will need correcting
    against real page HTML once reachable (residential proxy, etc.).
    """

    source_name = SOURCE_NAME
    # TripAdvisor's anti-bot is stricter than Traveloka's -- pace even slower.
    delay_range = (5, 9)

    def __init__(self, settings: Settings):
        self.scraper = HotelScraper(settings.match_score_threshold)
        self.crawler = None
        self.run_cfg = None

    async def setup(self) -> None:
        logger.info("Looking for public free proxies as a fallback...")
        proxies = await get_working_proxies()
        if proxies:
            logger.info("Found %d live proxies.", len(proxies))
            proxy_configs = ["direct"] + [ProxyConfig(server=f"http://{p}") for p in proxies]
        else:
            logger.info("No live free proxies found right now, running direct.")
            proxy_configs = None

        browser_cfg = BrowserConfig(
            headless=True, viewport_width=1400, viewport_height=900, enable_stealth=True
        )
        self.run_cfg = CrawlerRunConfig(
            proxy_config=proxy_configs if proxy_configs else None,
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
