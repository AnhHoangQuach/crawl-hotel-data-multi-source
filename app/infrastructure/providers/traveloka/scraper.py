import re
from typing import Optional

from app.application.services.fuzzy_matcher import best_match_index, best_suggestion_index
from app.domain.entities import HotelQuery, HotelResult

from ..dom_extraction import human_delay
from . import config, extraction

SOURCE_NAME = "traveloka"


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

            name_el = page.locator(config.HOTEL_CARD_NAME_SELECTOR).nth(best_idx)
            async with context.expect_page() as new_page_info:
                await name_el.click(timeout=5000, force=True)
            detail_page = await new_page_info.value
            await detail_page.wait_for_load_state("domcontentloaded", timeout=20000)
            await human_delay(detail_page)

            await self._extract_detail(detail_page, result)
            await detail_page.close()
        except Exception as e:
            result.error = str(e)

    async def _open_search_results(self, page):
        await human_delay(page)
        try:
            await page.keyboard.press("Escape")
        except Exception:
            pass
        await human_delay(page)

        # Default landing tab is "All" (hotels + villas + apartments mixed
        # in); pinning to "Hotels" keeps results/autocomplete scoped to
        # actual hotels, which is what query.name/query.address are for.
        try:
            hotels_tab = page.locator(config.ACCOM_TYPE_PICKER_SELECTOR).get_by_text(
                "Hotels", exact=True
            ).first
            await hotels_tab.click(timeout=5000, force=True)
            await human_delay(page)
        except Exception:
            pass

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
        await suggestions.nth(suggestion_idx).click(force=True)
        await human_delay(page)

        await page.locator(config.SEARCH_SUBMIT_SELECTOR).click(timeout=5000, force=True)
        await page.wait_for_url(re.compile(r".*/hotel/search.*"), timeout=15000)
        await human_delay(page)
        return suggestion_score

    async def _pick_best_match(self, page):
        name_el = page.locator(config.HOTEL_CARD_NAME_SELECTOR).first
        await name_el.wait_for(state="visible", timeout=10000)

        names = await extraction.extract_all_texts(page, config.HOTEL_CARD_NAME_SELECTOR)
        locations = await extraction.extract_all_texts(page, config.HOTEL_CARD_LOCATION_SELECTOR)
        if not names:
            return 0, 0.0
        return best_match_index(self.query.name, self.query.address, names, locations)

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
