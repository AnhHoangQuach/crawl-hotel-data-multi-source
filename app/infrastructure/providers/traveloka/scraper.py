import logging
import re
from typing import Optional

from app.application.services.fuzzy_matcher import best_match_index, best_suggestion_index
from app.domain.entities import HotelQuery, HotelResult

from ..dom_extraction import human_delay
from . import config, extraction

SOURCE_NAME = "traveloka"
logger = logging.getLogger(__name__)


class HotelScraper:
    """Drives one Playwright page through Traveloka's search flow and pulls
    full detail-page data for the closest-matching hotel card.

    Bound as a crawl4ai `after_goto` hook, so `query` must be set on the
    instance before each `crawler.arun()` call.
    """

    def __init__(self, match_score_threshold: float):
        self.match_score_threshold = match_score_threshold
        self.query: Optional[HotelQuery] = None
        self.result: Optional[HotelResult] = None

    async def after_goto_hook(self, page, context=None, **kwargs):
        result = HotelResult.empty(self.query, SOURCE_NAME)
        self.result = result

        try:
            suggestion_score = await self._open_search_results(page)
            best_idx, card_score = await self._pick_best_match(page)
            if best_idx is None:
                result.match_score = round(card_score, 3)
                result.low_confidence = True
                result.error = (
                    "Skipped: no Traveloka result cards were found after search. "
                    "The selected destination may have no available accommodations, "
                    "or Traveloka returned an empty result list."
                )
                return

            # Overall confidence is bounded by whichever step was least sure:
            # a great card match means nothing if the autocomplete already
            # sent us into the wrong city/country.
            score = min(suggestion_score, card_score)
            result.match_score = round(score, 3)
            result.low_confidence = score < self.match_score_threshold

            if result.low_confidence:
                # Don't bother opening the detail page -- whatever card we'd
                # click is probably the wrong hotel, so returning its data
                # would be worse than returning nothing.
                result.error = (
                    f"Skipped: no confidently matching hotel found "
                    f"(score={score:.2f} < {self.match_score_threshold}). "
                    "Check the name/address in the CSV."
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
        await search_box.press_sequentially(self.query.name, delay=80)
        await human_delay(page)

        suggestions = page.locator(config.SUGGESTION_ITEM_SELECTOR)
        await suggestions.first.wait_for(state="visible", timeout=10000)
        suggestion_texts = await extraction.extract_all_texts(page, config.SUGGESTION_ITEM_SELECTOR)

        suggestion_idx, suggestion_score = best_suggestion_index(
            self.query.name, self.query.address, suggestion_texts
        )
        logger.info(
            "[%s][search] query=%r selected_suggestion=%d score=%.3f text=%r",
            SOURCE_NAME,
            self.query.name,
            suggestion_idx,
            suggestion_score,
            suggestion_texts[suggestion_idx] if suggestion_idx < len(suggestion_texts) else "",
        )
        await suggestions.nth(suggestion_idx).click(force=True)
        await human_delay(page)

        await page.locator(config.SEARCH_SUBMIT_SELECTOR).click(timeout=5000, force=True)
        await page.wait_for_url(re.compile(r".*/hotel/search.*"), timeout=15000)
        await human_delay(page)
        return suggestion_score

    async def _pick_best_match(self, page):
        name_el = page.locator(config.HOTEL_CARD_NAME_SELECTOR).first
        try:
            await name_el.wait_for(state="visible", timeout=15000)
        except Exception:
            empty_list = page.locator(config.EMPTY_LIST_SELECTOR).first
            try:
                if await empty_list.count() and await empty_list.is_visible(timeout=1000):
                    return None, 0.0
            except Exception:
                pass
            raise

        names = await extraction.extract_all_texts(page, config.HOTEL_CARD_NAME_SELECTOR)
        locations = await extraction.extract_all_texts(page, config.HOTEL_CARD_LOCATION_SELECTOR)
        if not names:
            return None, 0.0
        best_idx, score = best_match_index(self.query.name, self.query.address, names, locations)
        logger.info(
            "[%s][card] query=%r selected_card=%d score=%.3f name=%r location=%r candidates=%d",
            SOURCE_NAME,
            self.query.name,
            best_idx,
            score,
            names[best_idx] if best_idx < len(names) else "",
            locations[best_idx] if best_idx < len(locations) else "",
            len(names),
        )
        return best_idx, score

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
