from typing import Optional

from app.application.services.fuzzy_matcher import best_match_index, best_suggestion_index
from app.domain.entities import HotelQuery, HotelResult

from ..dom_extraction import extract_all_texts, human_delay
from . import config, extraction

SOURCE_NAME = "booking"


class HotelScraper:
    """Drives one Playwright page through Booking.com's search flow and
    pulls detail-page data for the closest-matching hotel, mirroring the
    Traveloka/TripAdvisor scrapers' search -> fuzzy-match -> detail flow.

    Unlike TripAdvisor, picking a suggestion here (even a hotel-type one)
    and submitting always lands on an intermediate city/listing page first
    -- verified directly, Booking.com never routes straight from the
    homepage search to a specific property page -- so this always runs
    both match stages (suggestion, then card).

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
            suggestion_score = await self._search(page)
            await self._dismiss_calendar_overlay(page)

            idx, card_score = await self._pick_best_card(page)
            if idx is None:
                result.error = "No hotel results found on Booking.com."
                return

            detail_page = await self._open_detail_page(page, context, idx)

            # Same rationale as Traveloka/TripAdvisor: overall confidence is
            # bounded by whichever stage was less sure.
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

    async def _search(self, page) -> float:
        """Type the query into the homepage search box and resolve the best
        autocomplete suggestion. Returns 1.0 (i.e. "no signal, don't
        penalize") whenever no autocomplete list shows up at all, deferring
        entirely to the card-matching stage.
        """
        search_box = page.locator(config.SEARCH_INPUT_SELECTOR).first
        await search_box.wait_for(state="visible", timeout=45000)
        await search_box.click(timeout=5000, force=True)
        await human_delay(page)
        await search_box.press_sequentially(self.query.name, delay=80)
        await human_delay(page)

        suggestions = page.locator(config.SUGGESTION_ITEM_SELECTOR)
        try:
            await suggestions.first.wait_for(state="visible", timeout=8000)
        except Exception:
            await self._submit_search(page)
            return 1.0

        texts = await extract_all_texts(page, config.SUGGESTION_ITEM_SELECTOR)
        hotel_idxs = []
        for i in range(await suggestions.count()):
            if await suggestions.nth(i).locator(config.SUGGESTION_HOTEL_ICON_SELECTOR).count():
                hotel_idxs.append(i)

        # Restrict to suggestions explicitly flagged as a hotel (vs. a city
        # or landmark), same purpose as the old RapidAPI provider's
        # destination-type filter -- keeps non-hotel suggestions out of the
        # fuzzy-match candidate pool.
        candidate_idxs = hotel_idxs or list(range(len(texts)))
        candidate_texts = [texts[i] for i in candidate_idxs if i < len(texts)]
        if not candidate_texts:
            await self._submit_search(page)
            return 1.0

        rel_idx, score = best_suggestion_index(self.query.name, self.query.address, candidate_texts)
        real_idx = candidate_idxs[rel_idx]

        await suggestions.nth(real_idx).click(timeout=5000, force=True)
        await human_delay(page)
        await self._submit_search(page)
        return score

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

    async def _pick_best_card(self, page):
        links = page.locator(config.HOTEL_CARD_LINK_SELECTOR)
        try:
            await links.first.wait_for(state="visible", timeout=15000)
        except Exception:
            return None, 0.0

        texts = await self._card_texts(page)
        if not texts:
            return None, 0.0
        return best_match_index(self.query.name, self.query.address, texts, [])
