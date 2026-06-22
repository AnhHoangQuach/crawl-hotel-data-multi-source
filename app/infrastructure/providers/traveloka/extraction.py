import re

from ..dom_extraction import extract_all_texts, extract_text, human_delay, safe_inner_text
from . import config

SCORE_LINE_RE = re.compile(r"\d+(?:\.\d+)?\s*/\s*10")


async def extract_coordinates(page):
    try:
        html = await page.content()
    except Exception:
        return None, None
    m = config.LATLNG_RE.search(html)
    if not m:
        return None, None
    return float(m.group(1)), float(m.group(2))


async def extract_gallery_photos(detail_page, max_photos=config.MAX_PHOTOS):
    """Open the full photo lightbox (clicking the hero image + 'see more')
    and collect every unique photo asset, deduped by ignoring resize params.
    Falls back to the small overview gallery row if the lightbox never opens.
    """
    photos = []
    try:
        big = detail_page.locator(config.BIG_THUMBNAIL_SELECTOR).first
        if await big.count():
            await big.click(timeout=5000, force=True)
            await human_delay(detail_page)

        see_more = detail_page.locator(config.SEE_MORE_PHOTOS_SELECTOR).first
        if await see_more.count():
            await see_more.click(timeout=5000, force=True)
            await human_delay(detail_page)

        lightbox = detail_page.locator(config.PHOTO_LIGHTBOX_SELECTOR)
        if await lightbox.count():
            srcs = await detail_page.evaluate(
                f"""() => Array.from(document.querySelectorAll(
                    "{config.PHOTO_LIGHTBOX_SELECTOR} img"
                )).map(i => i.src)"""
            )
        else:
            srcs = await detail_page.evaluate(
                f"""() => Array.from(document.querySelectorAll(
                    "{config.GALLERY_FALLBACK_SELECTOR}"
                )).map(i => i.src)"""
            )

        seen = set()
        for src in srcs:
            key = src.split("?")[0]
            if not key or key in seen:
                continue
            seen.add(key)
            photos.append(src)
            if len(photos) >= max_photos:
                break

        close_btn = detail_page.locator(config.PHOTO_LIGHTBOX_CLOSE_SELECTOR).first
        if await close_btn.count():
            await close_btn.click(timeout=3000, force=True)
            await human_delay(detail_page)
    except Exception:
        pass
    return photos


def _split_review_blob(blob):
    """Split a 'review-list-container' text blob into individual reviews.

    Reviews don't have a stable per-item selector (Traveloka renders them as
    bare divs with auto-generated testids), so we locate each review by its
    "<score> /10" line and walk back ~2 lines to pick up the reviewer
    name/category that precedes it.
    """
    score_matches = list(SCORE_LINE_RE.finditer(blob))
    if not score_matches:
        return []

    block_starts = []
    prev_end = 0
    for m in score_matches:
        # Walk back up to 3 lines (avatar initials / name / category) to
        # capture the reviewer header, but never cross into the previous
        # review's comment text.
        prefix = blob[prev_end : m.start()]
        newline_positions = [i for i, c in enumerate(prefix) if c == "\n"]
        if len(newline_positions) >= 3:
            cut = newline_positions[-3] + 1
        elif newline_positions:
            cut = newline_positions[0] + 1
        else:
            cut = 0
        block_starts.append(prev_end + cut)
        prev_end = m.end()

    blocks = []
    for i, start in enumerate(block_starts):
        end = block_starts[i + 1] if i + 1 < len(block_starts) else len(blob)
        chunk = blob[start:end].strip()
        if chunk and len(chunk) > 5:
            blocks.append(chunk)
    return blocks


async def extract_full_reviews(detail_page, max_pages=config.MAX_REVIEW_PAGES):
    """Walk the paginated 'More Reviews' list and return individual review
    blocks. Capped at max_pages to keep runtime reasonable on hotels with
    hundreds of reviews -- this is a best-effort sample, not literally every
    review ever posted.
    """
    reviews = []
    try:
        link = detail_page.locator(config.REVIEW_TAB_LINK_SELECTOR).first
        if await link.count():
            await link.click(timeout=5000, force=True)
            await human_delay(detail_page)
    except Exception:
        return reviews

    seen_blobs = set()
    container = detail_page.locator(config.REVIEW_LIST_CONTAINER_SELECTOR).first

    for _ in range(max_pages):
        try:
            if not await container.count():
                break
            blob = await container.inner_text()
        except Exception:
            break
        if not blob or blob in seen_blobs:
            break
        seen_blobs.add(blob)
        reviews.extend(_split_review_blob(blob))

        next_btn = detail_page.locator(config.REVIEW_NEXT_PAGE_SELECTOR).first
        try:
            if not await next_btn.count():
                break
            if await next_btn.get_attribute("aria-disabled") == "true":
                break
            await next_btn.click(timeout=5000, force=True)
            await human_delay(detail_page)
        except Exception:
            break

    deduped = []
    seen_text = set()
    for r in reviews:
        if r not in seen_text:
            seen_text.add(r)
            deduped.append(r)
    return deduped


async def extract_rooms(detail_page, max_rooms=config.MAX_ROOMS):
    rooms = []
    try:
        cards = detail_page.locator(config.ROOM_CARD_SELECTOR)
        count = await cards.count()
    except Exception:
        return rooms

    for i in range(min(count, max_rooms)):
        card = cards.nth(i)
        rooms.append(
            {
                "name": await safe_inner_text(card.locator(config.ROOM_NAME_SELECTOR).first),
                "bed_type": await safe_inner_text(card.locator(config.ROOM_BED_TYPE_SELECTOR).first),
                "breakfast": await safe_inner_text(card.locator(config.ROOM_BREAKFAST_SELECTOR).first),
                "price_summary": await safe_inner_text(
                    card.locator(config.ROOM_PRICE_SUMMARY_SELECTOR).first
                ),
                "rooms_left": await safe_inner_text(card.locator(config.ROOM_NUM_LEFT_SELECTOR).first),
                "cancellation_policy": await safe_inner_text(
                    card.locator(config.ROOM_CANCELLATION_SELECTOR).first
                ),
            }
        )
    return rooms
