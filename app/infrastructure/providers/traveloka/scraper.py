import logging
import re
from typing import Optional

from app.domain.entities import HotelQuery, HotelResult

from ..dom_extraction import human_delay
from ..search_text import build_search_text
from . import config, extraction

SOURCE_NAME = "traveloka"
logger = logging.getLogger(__name__)


class HotelScraper:
    """Drives one Playwright page through Traveloka's search flow and pulls
    full detail-page data for the top-ranked hotel card, trusting
    Traveloka's own search ranking rather than re-scoring candidates.

    Bound as a crawl4ai `after_goto` hook, so `query` must be set on the
    instance before each `crawler.arun()` call.
    """

    def __init__(self):
        self.query: Optional[HotelQuery] = None
        self.result: Optional[HotelResult] = None

    async def after_goto_hook(self, page, context=None, **kwargs):
        result = HotelResult.empty(self.query, SOURCE_NAME)
        self.result = result

        try:
            await self._open_search_results(page)
            best_idx = await self._pick_first_card(page)
            if best_idx is None:
                result.error = (
                    "Skipped: no Traveloka result cards were found after search. "
                    "The selected destination may have no available accommodations, "
                    "or Traveloka returned an empty result list."
                )
                return

            detail_page = await self._open_detail_page(page, context, best_idx)
            await human_delay(detail_page)

            await self._extract_detail(detail_page, result)
            await detail_page.close()
        except Exception as e:
            result.error = str(e)

    async def _open_detail_page(self, page, context, idx):
        name_el = page.locator(config.HOTEL_CARD_NAME_SELECTOR).nth(idx)
        href = ""
        try:
            href = await name_el.evaluate(
                """el => {
                    const link = el.closest('a') || el.querySelector('a') || el.parentElement?.closest('a');
                    return link ? link.href : '';
                }"""
            )
        except Exception:
            pass

        if context:
            try:
                async with context.expect_page(timeout=5000) as new_page_info:
                    await name_el.click(timeout=5000, force=True)
                detail_page = await new_page_info.value
                await detail_page.wait_for_load_state("domcontentloaded", timeout=20000)
                return detail_page
            except Exception:
                pass

        if href:
            await page.goto(href, wait_until="domcontentloaded", timeout=30000)
            return page

        await name_el.click(timeout=5000, force=True)
        await page.wait_for_load_state("domcontentloaded", timeout=20000)
        return page

    async def _open_search_results(self, page):
        await human_delay(page)
        try:
            await page.keyboard.press("Escape")
        except Exception:
            pass
        await human_delay(page)

        # Keep the default accommodation scope. Forcing the "Hotels" tab adds
        # `ACCOMMODATION_TYPE-HOTEL` to the result URL and hides valid resort
        # listings, e.g. "Hon Co Resort - Ca Na" returns "0 properties found"
        # under that filter even though the autocomplete resolves the property.

        search_box = page.locator(config.SEARCH_INPUT_SELECTOR)
        # Generous timeout: through a slow/degraded free proxy the page can
        # respond (HTTP 200) long before it's actually finished hydrating.
        await search_box.wait_for(state="visible", timeout=45000)
        await search_box.click()
        await human_delay(page)
        search_text = build_search_text(self.query.name, self.query.address)
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
        await suggestions.first.wait_for(state="visible", timeout=10000)

        # Trust Traveloka's own autocomplete ranking: always take the first
        # suggestion instead of re-ranking the list by fuzzy match.
        logger.info("[%s][search] selected_suggestion=0", SOURCE_NAME)
        await suggestions.first.click(force=True)
        await human_delay(page)

        await page.locator(config.SEARCH_SUBMIT_SELECTOR).click(timeout=5000, force=True)
        await page.wait_for_url(re.compile(r".*/hotel/search.*"), timeout=15000)
        await human_delay(page)

    async def _pick_first_card(self, page):
        name_el = page.locator(config.HOTEL_CARD_NAME_SELECTOR).first
        try:
            await name_el.wait_for(state="visible", timeout=15000)
        except Exception:
            empty_list = page.locator(config.EMPTY_LIST_SELECTOR).first
            try:
                if await empty_list.count() and await empty_list.is_visible(timeout=1000):
                    return None
            except Exception:
                pass
            raise

        names = await extraction.extract_all_texts(page, config.HOTEL_CARD_NAME_SELECTOR)
        if not names:
            return None

        # Trust Traveloka's own search ranking: always take the top result
        # card.
        logger.info(
            "[%s][card] selected_card=0 name=%r candidates=%d",
            SOURCE_NAME,
            names[0],
            len(names),
        )
        return 0

    async def _extract_detail(self, detail_page, result: HotelResult):
        result.detail_url = detail_page.url
        result.name = await extraction.extract_text(detail_page, config.DISPLAY_NAME_SELECTOR)
        result.accommodation_type = await extraction.extract_text(detail_page, config.ACCOM_TYPE_SELECTOR)
        result.star_rating = await extraction.extract_text(detail_page, config.STAR_RATING_SELECTOR)
        result.rating_summary = await extraction.extract_text(detail_page, config.REVIEW_RATING_SELECTOR)
        result.address = await extraction.extract_text(detail_page, config.ADDRESS_SELECTOR)
        result.latitude, result.longitude = await extraction.extract_coordinates(detail_page)
        result.amenities = await extraction.extract_text(detail_page, config.AMENITIES_SELECTOR)
        result.facilities = await extraction.extract_text(detail_page, config.FACILITIES_SELECTOR)
        result.description = await extraction.extract_text(detail_page, config.DESCRIPTION_SELECTOR)
        result.rooms = await extraction.extract_rooms(detail_page)
        result.photos = await extraction.extract_gallery_photos(detail_page)
        result.reviews = await extraction.extract_full_reviews(detail_page)
