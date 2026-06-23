import logging
import re
import unicodedata
from typing import Optional

from app.application.services.fuzzy_matcher import score_candidate_details, score_suggestion_details
from app.domain.entities import HotelQuery, HotelResult

from ..dom_extraction import extract_all_texts, human_delay
from . import config, extraction

SOURCE_NAME = "booking"
logger = logging.getLogger(__name__)


def _normalize_search_text(text: str) -> str:
    text = unicodedata.normalize("NFKD", text or "")
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = re.sub(r"[^a-zA-Z0-9\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _address_search_hint(address: str) -> str:
    parts = [p.strip() for p in (address or "").split(",") if p.strip()]
    if len(parts) < 2:
        return ""
    for part in reversed(parts[:-1]):
        normalized = _normalize_search_text(part).lower()
        if normalized in {"viet nam", "vietnam"}:
            continue
        normalized = re.sub(r"\b(thanh pho|tp|city|province|tinh)\b", " ", normalized)
        normalized = re.sub(r"\s+", " ", normalized).strip()
        if normalized:
            return normalized
    return ""


class HotelScraper:
    """Drives one Playwright page through Booking.com's search flow and
    pulls detail-page data for the closest-matching hotel, mirroring the
    Traveloka scraper's search -> fuzzy-match -> detail flow.

    Picking a suggestion here (even a hotel-type one) and submitting always
    lands on an intermediate city/listing page first -- verified directly,
    Booking.com never routes straight from the homepage search to a specific
    property page -- so this always runs both match stages (suggestion, then
    card).

    Bound as a crawl4ai `after_goto` hook, so `query` must be set on the
    instance before each `crawler.arun()` call.
    """

    def __init__(self, match_score_threshold: float):
        self.match_score_threshold = match_score_threshold
        self.query: Optional[HotelQuery] = None
        self.result: Optional[HotelResult] = None

    def _search_text(self) -> str:
        name = _normalize_search_text(self.query.name)
        hint = _address_search_hint(self.query.address)
        if not hint or hint in name.lower():
            return name
        return f"{name} {hint}"

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

            # Same rationale as Traveloka: overall confidence is
            # bounded by whichever stage was less sure.
            score = min(suggestion_score, card_score)
            logger.info(
                "[%s][score][final] query=%r suggestion_score=%.3f card_score=%.3f final_score=%.3f threshold=%.3f selected_card_index=%s",
                SOURCE_NAME,
                self.query.name,
                suggestion_score,
                card_score,
                score,
                self.match_score_threshold,
                idx,
            )
            result.match_score = round(score, 3)
            result.low_confidence = score < self.match_score_threshold
            if result.low_confidence:
                result.error = (
                    f"Skipped: no confidently matching hotel found "
                    f"(score={score:.2f} < {self.match_score_threshold}). "
                    "Check the name/address in the CSV."
                )
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
            return 1.0

        texts = await extract_all_texts(page, config.SUGGESTION_ITEM_SELECTOR)
        hotel_idxs = []
        for i in range(await suggestions.count()):
            if await suggestions.nth(i).locator(config.SUGGESTION_HOTEL_ICON_SELECTOR).count():
                hotel_idxs.append(i)

        # Restrict to suggestions explicitly flagged as a hotel (vs. a city
        # or landmark), keeping non-hotel suggestions out of the fuzzy-match
        # candidate pool.
        candidate_idxs = hotel_idxs or list(range(len(texts)))
        candidate_texts = [texts[i] for i in candidate_idxs if i < len(texts)]
        if not candidate_texts:
            await self._submit_search(page)
            return 1.0

        score_details = [
            score_suggestion_details(self.query.name, self.query.address, text)
            for text in candidate_texts
        ]
        self._log_score_details("suggestion", score_details)
        rel_idx, score = self._best_score_detail(score_details)
        real_idx = candidate_idxs[rel_idx]

        await suggestions.nth(real_idx).click(timeout=5000, force=True)
        await human_delay(page)
        await self._submit_search(page)
        return score

    def _best_score_detail(self, score_details):
        if not score_details:
            return 0, 0.0
        best_idx, best = max(enumerate(score_details), key=lambda item: item[1]["score"])
        return best_idx, best["score"]

    def _log_score_details(self, stage: str, score_details: list) -> None:
        logger.info(
            "[%s][score][%s] query_name=%r query_address=%r candidates=%d",
            SOURCE_NAME,
            stage,
            self.query.name,
            self.query.address,
            len(score_details),
        )
        for idx, detail in enumerate(score_details):
            logger.info(
                "[%s][score][%s] candidate=%d score=%.3f reason=%s name_score=%.3f address_score=%.3f "
                "name_contains=%s name_token_contains=%s exact_address=%s coarse_address=%s "
                "loose_location=%s query_location_hint=%s name=%r location=%r",
                SOURCE_NAME,
                stage,
                idx,
                detail["score"],
                detail["reason"],
                detail["name_score"],
                detail["address_score"],
                detail["name_contains"],
                detail["name_token_contains"],
                detail["exact_address_matches"],
                detail["coarse_address_matches"],
                detail["loose_location_matches"],
                detail["query_location_hint_matches"],
                detail["candidate_name"],
                detail["candidate_location"],
            )

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

    async def _card_addresses(self, page):
        try:
            return await page.eval_on_selector_all(
                config.HOTEL_CARD_LINK_SELECTOR,
                f"""els => els.map(e => {{
                    const card = e.closest("{config.HOTEL_CARD_CONTAINER_SELECTOR}");
                    const addressEl = card ? card.querySelector("{config.HOTEL_CARD_ADDRESS_SELECTOR}") : null;
                    return addressEl ? (addressEl.textContent || '') : '';
                }})""",
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
        addresses = await self._card_addresses(page)
        score_details = [
            score_candidate_details(
                self.query.name,
                self.query.address,
                name,
                addresses[i] if i < len(addresses) else "",
                require_address_match=True,
            )
            for i, name in enumerate(texts)
        ]
        self._log_score_details("card", score_details)
        return self._best_score_detail(score_details)
