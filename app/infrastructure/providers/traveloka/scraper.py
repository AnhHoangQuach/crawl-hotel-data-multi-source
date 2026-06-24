import logging
import re
from difflib import SequenceMatcher
from typing import Optional

from app.domain.entities import HotelQuery, HotelResult

from ..dom_extraction import human_delay, safe_inner_text
from ..search_text import build_search_text, normalize_search_text
from ..validation import mentions_vietnam
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

    def _normalized_name_terms(self):
        normalized = normalize_search_text(self.query.name).lower()
        return [w for w in normalized.split() if len(w) > 2]

    def _address_terms(self):
        terms = []
        for part in (self.query.address or "").split(","):
            normalized = normalize_search_text(part).lower()
            normalized = re.sub(
                r"\b(viet nam|vietnam|thanh pho|tp|city|province|tinh|quan|huyen|phuong|ward|district)\b",
                " ",
                normalized,
            )
            normalized = re.sub(r"\s+", " ", normalized).strip()
            if not normalized or any(ch.isdigit() for ch in normalized):
                continue
            if normalized not in terms:
                terms.append(normalized)
        return terms

    def _name_score(self, text: str) -> int:
        normalized = normalize_search_text(text).lower()
        return sum(1 for term in self._normalized_name_terms() if term in normalized)

    def _name_similarity(self, text: str) -> float:
        query_name = normalize_search_text(self.query.name).lower()
        candidate_name = normalize_search_text(text).lower()
        if not query_name or not candidate_name:
            return 0.0
        return SequenceMatcher(None, query_name, candidate_name).ratio()

    def _location_score(self, text: str) -> int:
        normalized = normalize_search_text(text).lower()
        score = 1 if mentions_vietnam(text) else 0
        for term in self._address_terms():
            if term in normalized:
                score += len(term.split())
        return score

    def _matches_target_location(self, text: str) -> bool:
        if mentions_vietnam(text):
            return True
        if not self._address_terms():
            return True
        return self._location_score(text) > 0

    def _split_suggestion_text(self, text: str):
        lines = [line.strip() for line in (text or "").splitlines() if line.strip()]
        if not lines:
            return "", ""
        return lines[0], " ".join(lines[1:])

    def _suggestion_matches_query(self, text: str) -> bool:
        name, address = self._split_suggestion_text(text)
        return self._name_similarity(name) > 0.5 and self._matches_target_location(address)

    async def after_goto_hook(self, page, context=None, **kwargs):
        result = HotelResult.empty(self.query, SOURCE_NAME)
        self.result = result

        try:
            search_error = await self._open_search_results(page)
            if search_error:
                result.error = search_error
                return
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

        await self._select_all_accommodation_tab(page)

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

        best_suggestion = None
        best_score = -1
        for i in range(await suggestions.count()):
            text = await safe_inner_text(suggestions.nth(i)) or ""
            if not self._suggestion_matches_query(text):
                continue
            name, address = self._split_suggestion_text(text)
            score = self._name_similarity(name) * 100 + self._location_score(address)
            if score > best_score:
                best_suggestion = i
                best_score = score

        if best_suggestion is None:
            return "No autocomplete suggestion matching the query location was found on Traveloka."

        logger.info(
            "[%s][search] selected_suggestion=%d score=%.2f",
            SOURCE_NAME,
            best_suggestion,
            best_score,
        )
        await suggestions.nth(best_suggestion).click(force=True)
        await human_delay(page)

        await page.locator(config.SEARCH_SUBMIT_SELECTOR).click(timeout=5000, force=True)
        await page.wait_for_url(re.compile(r".*/hotel/search.*"), timeout=15000)
        await human_delay(page)
        return None

    async def _select_all_accommodation_tab(self, page):
        """Search from Traveloka's broad "All" accommodation tab.

        Traveloka can keep the UI scoped to "Hotel" from a previous state,
        which hides valid non-hotel autocomplete results. The all-tab is
        text-rendered in the current locale, so use a localized exact-text
        match and tolerate absence because the DOM changes by market/device.
        """
        try:
            tab = page.get_by_text(config.ALL_ACCOMMODATION_TAB_RE).first
            if await tab.count():
                await tab.click(timeout=3000, force=True)
                await human_delay(page)
        except Exception:
            logger.info("[%s][search] all_accommodation_tab_not_selected", SOURCE_NAME)

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

        locations = await extraction.extract_all_texts(page, config.HOTEL_CARD_LOCATION_SELECTOR)
        best_idx = None
        best_score = -1
        for idx, name in enumerate(names):
            location = locations[idx] if idx < len(locations) else ""
            combined = f"{name} {location}"
            if not self._matches_target_location(combined):
                continue
            if self._name_similarity(name) <= 0.5:
                continue
            score = self._name_score(name) * 10 + self._location_score(location)
            if score > best_score:
                best_idx = idx
                best_score = score

        if best_idx is not None:
            location = locations[best_idx] if best_idx < len(locations) else ""
            logger.info(
                "[%s][card] selected_card=%d score=%d name=%r location=%r candidates=%d",
                SOURCE_NAME,
                best_idx,
                best_score,
                names[best_idx],
                location,
                len(names),
            )
            return best_idx

        logger.info("[%s][card] no_card_matched_query_location candidates=%d", SOURCE_NAME, len(names))
        return None

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
