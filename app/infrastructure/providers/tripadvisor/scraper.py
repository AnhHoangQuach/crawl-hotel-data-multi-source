from typing import Optional

from app.application.services.fuzzy_matcher import best_match_index, best_suggestion_index
from app.domain.entities import HotelQuery, HotelResult

from ..dom_extraction import extract_all_texts, human_delay
from . import config, extraction

SOURCE_NAME = "tripadvisor"


class HotelScraper:
    """Drives one Playwright page through TripAdvisor's search flow and
    pulls detail-page data for the closest-matching hotel, mirroring the
    Traveloka scraper's search -> fuzzy-match -> detail flow.

    One structural difference from Traveloka: TripAdvisor's autocomplete can
    navigate straight to a hotel's detail page when the picked suggestion is
    itself a hotel (no separate results-list page in between), so this class
    detects which case happened from the resulting URL instead of always
    expecting a results list.

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
            await self._dismiss_cookie_banner(page)
            suggestion_score, landed_on_detail = await self._search(page)

            if landed_on_detail:
                card_score = suggestion_score
            else:
                idx, card_score = await self._pick_best_card(page)
                if idx is None:
                    result.error = "No hotel results found on TripAdvisor."
                    return
                await page.locator(config.HOTEL_CARD_LINK_SELECTOR).nth(idx).click(
                    timeout=5000, force=True
                )
                await page.wait_for_url(config.HOTEL_REVIEW_URL_RE, timeout=15000)
                await human_delay(page)

            # Same rationale as Traveloka: overall confidence is bounded by
            # whichever stage was less sure -- a great card match means
            # nothing if autocomplete already sent us into the wrong hotel.
            score = min(suggestion_score, card_score)
            result.match_score = round(score, 3)
            result.low_confidence = score < self.match_score_threshold
            if result.low_confidence:
                result.error = (
                    f"Skipped: no confidently matching hotel found "
                    f"(score={score:.2f} < {self.match_score_threshold}). "
                    "Check the name/address in the CSV."
                )
                return

            await human_delay(page)
            result.detail_url = page.url
            await extraction.extract_detail_fields(page, result)
        except Exception as e:
            result.error = str(e)

    async def _dismiss_cookie_banner(self, page):
        await human_delay(page)
        try:
            btn = page.locator(config.COOKIE_ACCEPT_SELECTOR).first
            if await btn.count():
                await btn.click(timeout=3000, force=True)
                await human_delay(page)
        except Exception:
            pass

    def _on_detail_page(self, page) -> bool:
        return bool(config.HOTEL_REVIEW_URL_RE.search(page.url))

    async def _search(self, page):
        """Type the query into the homepage search box and resolve the best
        autocomplete suggestion. Returns (score, landed_on_detail) -- score
        is 1.0 (i.e. "no signal, don't penalize") whenever no autocomplete
        list shows up at all, deferring entirely to the card-matching stage.
        """
        search_box = page.locator(config.SEARCH_INPUT_SELECTOR).first
        await search_box.wait_for(state="visible", timeout=45000)
        await search_box.click()
        await human_delay(page)
        await search_box.press_sequentially(self.query.name, delay=80)
        await human_delay(page)

        suggestions = page.locator(config.SUGGESTION_ITEM_SELECTOR)
        try:
            await suggestions.first.wait_for(state="visible", timeout=8000)
        except Exception:
            await self._submit_search(page)
            return 1.0, self._on_detail_page(page)

        texts = await extract_all_texts(page, config.SUGGESTION_ITEM_SELECTOR)
        hrefs = await self._suggestion_hrefs(page)

        # Restrict to suggestions that already link to a hotel page, same
        # purpose as the old RapidAPI provider's `place_type == "HOTEL"`
        # filter -- keeps city/attraction suggestions out of the candidate
        # pool the fuzzy matcher picks from.
        hotel_idxs = [i for i, h in enumerate(hrefs) if h and config.HOTEL_REVIEW_URL_RE.search(h)]
        candidate_idxs = hotel_idxs or list(range(len(texts)))
        candidate_texts = [texts[i] for i in candidate_idxs if i < len(texts)]
        if not candidate_texts:
            await self._submit_search(page)
            return 1.0, self._on_detail_page(page)

        rel_idx, score = best_suggestion_index(self.query.name, self.query.address, candidate_texts)
        real_idx = candidate_idxs[rel_idx]

        await suggestions.nth(real_idx).click(timeout=5000, force=True)
        await human_delay(page)
        return score, self._on_detail_page(page)

    async def _suggestion_hrefs(self, page):
        try:
            return await page.eval_on_selector_all(
                config.SUGGESTION_ITEM_SELECTOR,
                "els => els.map(e => (e.querySelector('a') || e).href || null)",
            )
        except Exception:
            return []

    async def _submit_search(self, page):
        try:
            await page.locator(config.SEARCH_SUBMIT_SELECTOR).first.click(timeout=5000, force=True)
        except Exception:
            try:
                await page.keyboard.press("Enter")
            except Exception:
                pass
        await human_delay(page)

    async def _pick_best_card(self, page):
        links = page.locator(config.HOTEL_CARD_LINK_SELECTOR)
        try:
            await links.first.wait_for(state="visible", timeout=15000)
        except Exception:
            return None, 0.0

        names = await extract_all_texts(page, config.HOTEL_CARD_LINK_SELECTOR)
        locations = await extract_all_texts(page, config.HOTEL_CARD_LOCATION_SELECTOR)
        if not names:
            return None, 0.0
        return best_match_index(self.query.name, self.query.address, names, locations)
