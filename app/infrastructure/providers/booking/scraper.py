import logging
from typing import Optional

from app.domain.entities import HotelQuery, HotelResult

from ..dom_extraction import human_delay
from ..search_text import build_search_text
from . import config, extraction

SOURCE_NAME = "booking"
logger = logging.getLogger(__name__)


class HotelScraper:
    """Drives one Playwright page through Booking.com's search flow and
    pulls detail-page data for the top-ranked hotel.

    Picking a suggestion here (even a hotel-type one) and submitting always
    lands on an intermediate city/listing page first -- verified directly,
    Booking.com never routes straight from the homepage search to a specific
    property page -- so this always goes through both stages (suggestion,
    then result card), trusting Booking.com's own ranking at each one
    instead of re-scoring the candidates.

    Bound as a crawl4ai `after_goto` hook, so `query` must be set on the
    instance before each `crawler.arun()` call.
    """

    def __init__(self):
        self.query: Optional[HotelQuery] = None
        self.result: Optional[HotelResult] = None

    def _search_text(self) -> str:
        return build_search_text(self.query.name, self.query.address)

    async def after_goto_hook(self, page, context=None, **kwargs):
        result = HotelResult.empty(self.query, SOURCE_NAME)
        self.result = result

        try:
            await self._search(page)
            await self._dismiss_calendar_overlay(page)

            idx = await self._pick_first_card(page)
            if idx is None:
                result.error = "No hotel results found on Booking.com."
                return

            detail_page = await self._open_detail_page(page, context, idx)
            await human_delay(detail_page)
            result.detail_url = detail_page.url
            await extraction.extract_detail_fields(detail_page, result)
        except Exception as e:
            result.error = str(e)

    async def _open_detail_page(self, page, context, idx):
        """Click the matched card's link and return whichever page object
        ends up holding the property page -- the "title-link" template opens
        it in a new tab (target="_blank"), while "titleLink" navigates the
        current page (see config.py). Whichever fires first wins.
        """
        link = page.locator(config.HOTEL_CARD_LINK_SELECTOR).nth(idx)
        try:
            async with context.expect_page(timeout=4000) as new_page_info:
                await link.click(timeout=5000)
            new_page = await new_page_info.value
            await new_page.wait_for_load_state("domcontentloaded", timeout=20000)
            return new_page
        except Exception:
            pass
        await page.wait_for_url(config.HOTEL_DETAIL_URL_RE, timeout=15000)
        return page

    async def _search(self, page) -> None:
        """Type the query into the homepage search box and pick the first
        autocomplete suggestion, preferring one explicitly flagged as a
        hotel (vs. a city/landmark) when any are present.
        """
        search_box = page.locator(config.SEARCH_INPUT_SELECTOR).first
        await search_box.wait_for(state="visible", timeout=45000)
        await search_box.click(timeout=5000, force=True)
        await human_delay(page)
        search_text = self._search_text()
        logger.info(
            "[%s][search] query_name=%r query_address=%r search_text=%r",
            SOURCE_NAME,
            self.query.name,
            self.query.address,
            search_text,
        )
        await search_box.press_sequentially(search_text, delay=80)
        await human_delay(page)

        suggestions = page.locator(config.SUGGESTION_ITEM_SELECTOR)
        try:
            await suggestions.first.wait_for(state="visible", timeout=8000)
        except Exception:
            await self._submit_search(page)
            return

        hotel_idxs = []
        for i in range(await suggestions.count()):
            if await suggestions.nth(i).locator(config.SUGGESTION_HOTEL_ICON_SELECTOR).count():
                hotel_idxs.append(i)
        real_idx = hotel_idxs[0] if hotel_idxs else 0

        logger.info("[%s][search] selected_suggestion=%d", SOURCE_NAME, real_idx)
        await suggestions.nth(real_idx).click(timeout=5000, force=True)
        await human_delay(page)
        await self._submit_search(page)

    async def _submit_search(self, page):
        try:
            await page.locator(config.SEARCH_SUBMIT_SELECTOR).first.click(timeout=5000, force=True)
        except Exception:
            try:
                await page.keyboard.press("Enter")
            except Exception:
                pass
        await human_delay(page)

    async def _dismiss_calendar_overlay(self, page):
        # An inline date-picker calendar can render on top of the results
        # list and silently swallow clicks on the cards underneath it
        # (confirmed while building this) -- a neutral click closes it the
        # same way a real user clicking elsewhere on the page would.
        try:
            await page.mouse.click(5, 5)
            await human_delay(page)
        except Exception:
            pass

    async def _card_texts(self, page):
        # The two templates need different text sources: "titleLink"'s
        # `title` attribute carries a clean "<name> - Hotel in <city>", but
        # "title-link" has no such attribute and its raw textContent is
        # polluted with literal "Opens in new window" accessibility text
        # (verified while building this) -- its nested [data-testid='title']
        # element has just the clean name instead.
        try:
            return await page.eval_on_selector_all(
                config.HOTEL_CARD_LINK_SELECTOR,
                """els => els.map(e => {
                    const titleAttr = e.getAttribute('title');
                    if (titleAttr) return titleAttr;
                    const titleEl = e.querySelector("[data-testid='title']");
                    if (titleEl) return titleEl.textContent || '';
                    return e.textContent || '';
                })""",
            )
        except Exception:
            return []

    async def _pick_first_card(self, page):
        links = page.locator(config.HOTEL_CARD_LINK_SELECTOR)
        try:
            await links.first.wait_for(state="visible", timeout=15000)
        except Exception:
            return None

        texts = await self._card_texts(page)
        if not texts:
            return None

        # Trust Booking.com's own search ranking: always take the top
        # result card.
        logger.info(
            "[%s][card] selected_card=0 name=%r candidates=%d",
            SOURCE_NAME,
            texts[0],
            len(texts),
        )
        return 0
