import logging

from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig, ProxyConfig

from app.domain.entities import HotelQuery, HotelResult
from app.infrastructure.config import Settings
from app.infrastructure.providers.base import BaseHotelProvider

from ..free_proxy import get_working_proxies
from .config import HOMEPAGE_URL
from .scraper import SOURCE_NAME, HotelScraper

logger = logging.getLogger(__name__)


class TravelokaProvider(BaseHotelProvider):
    """Playwright/crawl4ai-driven provider: searches Traveloka, picks the
    best-matching hotel card, opens the detail page and scrapes it.
    """

    source_name = SOURCE_NAME
    # Traveloka rate-limits/blocks aggressive bots -- keep the human-paced gap
    # between hotels that proved reliable in practice.
    delay_range = (3, 6)

    def __init__(self, settings: Settings):
        self.scraper = HotelScraper(settings.match_score_threshold)
        self.crawler = None
        self.run_cfg = None

    async def setup(self) -> None:
        logger.info("Looking for public free proxies as a fallback...")
        proxies = await get_working_proxies()
        if proxies:
            logger.info("Found %d live proxies.", len(proxies))
            # Try direct first: a human-like search flow has proven far more
            # reliable than free proxies, which often "work" at the network
            # level (HTTP 200) but render too slowly/incompletely for the
            # page's JS to finish hydrating. Proxies are kept only as a
            # fallback for the case where Traveloka does serve a real block page.
            proxy_configs = ["direct"] + [ProxyConfig(server=f"http://{p}") for p in proxies]
        else:
            logger.info("No live free proxies found right now, running direct.")
            proxy_configs = None

        browser_cfg = BrowserConfig(headless=True, viewport_width=1400, viewport_height=900)
        self.run_cfg = CrawlerRunConfig(
            proxy_config=proxy_configs if proxy_configs else None,
            # The proxy list already ends with a "direct" fallback entry, so
            # one pass through it is enough -- max_retries would multiply the
            # whole list (very slow once most free proxies are dead).
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
        self.scraper.result = None

        try:
            await self.crawler.arun(url=HOMEPAGE_URL, config=self.run_cfg)
        except Exception as e:
            result = HotelResult.empty(query, self.source_name)
            result.error = str(e)
            return result

        result = self.scraper.result or HotelResult.empty(query, self.source_name)
        if not result.name:
            self.scraper.result = None
            try:
                await self.crawler.arun(url=HOMEPAGE_URL, config=self.run_cfg)
                result = self.scraper.result or result
            except Exception as e:
                result.error = result.error or str(e)
        return result
