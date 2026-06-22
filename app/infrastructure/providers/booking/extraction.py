import json

from ..dom_extraction import extract_all_texts, extract_text
from ..utils import dig
from . import config


def _iter_json_ld_nodes(data):
    if isinstance(data, list):
        for item in data:
            yield from _iter_json_ld_nodes(item)
    elif isinstance(data, dict):
        yield data


async def extract_json_ld(page) -> dict:
    """Booking.com hotel pages embed a clean schema.org Hotel block (name,
    structured address, description, aggregateRating, a hero image) -- far
    more stable than the page's hashed CSS classes, so it's the primary
    source for every detail field it covers.
    """
    try:
        texts = await page.evaluate(
            "() => Array.from(document.querySelectorAll("
            "'script[type=\"application/ld+json\"]')).map(s => s.textContent)"
        )
    except Exception:
        return {}

    for text in texts or []:
        try:
            data = json.loads(text)
        except Exception:
            continue
        for node in _iter_json_ld_nodes(data):
            if node.get("@type") == "Hotel":
                return node
    return {}


def address_to_text(address) -> str:
    """Booking.com's own JSON-LD is redundant in practice: `streetAddress`
    is often already the full "street, ward, city, country" string, with
    `addressLocality`/`addressCountry` repeating pieces of it verbatim
    (confirmed while building this) -- skip any part already contained in
    a part already included, rather than concatenating duplicates.
    """
    if not address:
        return None
    if isinstance(address, str):
        return address
    if isinstance(address, dict):
        parts = []
        for key in ("streetAddress", "addressLocality", "addressRegion", "addressCountry"):
            val = address.get(key)
            if val and not any(val in p for p in parts):
                parts.append(val)
        return ", ".join(parts) or None
    return None


def images_from_json_ld(image_field, max_photos) -> list:
    if not image_field:
        return []
    items = image_field if isinstance(image_field, list) else [image_field]
    return [item for item in items if isinstance(item, str)][:max_photos]


async def extract_coordinates(page):
    try:
        latlng = await page.locator(config.COORDS_ATTR_SELECTOR).first.get_attribute("data-atlas-latlng")
    except Exception:
        return None, None
    if not latlng or "," not in latlng:
        return None, None
    try:
        lat_str, lng_str = latlng.split(",", 1)
        return float(lat_str), float(lng_str)
    except ValueError:
        return None, None


async def extract_cdn_photos(page, max_photos=config.MAX_PHOTOS) -> list:
    """Collect gallery photos by CDN host instead of CSS class -- the
    bstatic.com domain is a stable serving convention, unlike the page's
    obfuscated presentation classes.
    """
    try:
        srcs = await page.evaluate(
            "() => Array.from(document.querySelectorAll('img')).map(i => i.src).filter(Boolean)"
        )
    except Exception:
        return []

    seen = set()
    photos = []
    for src in srcs:
        if not any(host in src for host in config.PHOTO_CDN_HOSTS):
            continue
        if config.PHOTO_PATH_HINT not in src:
            continue
        key = src.split("?")[0]
        if key in seen:
            continue
        seen.add(key)
        photos.append(src)
        if len(photos) >= max_photos:
            break
    return photos


async def extract_reviews(page, max_reviews=config.MAX_REVIEWS) -> list:
    texts = await extract_all_texts(page, config.REVIEW_TEXT_SELECTOR)
    deduped = []
    seen = set()
    for text in texts:
        if text and text not in seen:
            seen.add(text)
            deduped.append(text)
        if len(deduped) >= max_reviews:
            break
    return deduped


async def extract_detail_fields(page, result) -> None:
    json_ld = await extract_json_ld(page)

    result.name = json_ld.get("name") or await extract_text(page, config.DETAIL_NAME_SELECTOR)
    result.accommodation_type = await extract_text(page, config.ACCOMMODATION_TYPE_SELECTOR)

    star = dig(json_ld, "starRating", "ratingValue") or json_ld.get("starRating")
    result.star_rating = str(star) if star is not None else None

    rating = dig(json_ld, "aggregateRating", "ratingValue")
    review_count = dig(json_ld, "aggregateRating", "reviewCount")
    best_rating = dig(json_ld, "aggregateRating", "bestRating")
    if rating is not None:
        scale = f"/{best_rating}" if best_rating else ""
        result.rating_summary = (
            f"{rating}{scale} ({review_count} reviews)" if review_count else f"{rating}{scale}"
        )

    result.address = address_to_text(json_ld.get("address")) or await extract_text(
        page, config.DETAIL_ADDRESS_SELECTOR
    )
    result.latitude, result.longitude = await extract_coordinates(page)
    result.description = json_ld.get("description") or await extract_text(
        page, config.DETAIL_DESCRIPTION_SELECTOR
    )
    result.amenities = await extract_text(page, config.AMENITIES_SELECTOR)
    result.facilities = await extract_text(page, config.FACILITIES_SELECTOR)

    # JSON-LD's `image` is just a single hero shot, not the full gallery --
    # lead with it (verified, semantic), then fill out with the CDN-host
    # scan rather than treating the one hero image as "enough".
    hero_images = images_from_json_ld(json_ld.get("image"), config.MAX_PHOTOS)
    cdn_images = await extract_cdn_photos(page, config.MAX_PHOTOS)
    seen = set()
    photos = []
    for url in hero_images + cdn_images:
        key = url.split("?")[0]
        if key in seen:
            continue
        seen.add(key)
        photos.append(url)
        if len(photos) >= config.MAX_PHOTOS:
            break
    result.photos = photos
    result.reviews = await extract_reviews(page)
    # See config.py -- room/price data needs date-picker interaction this
    # scraper doesn't perform yet.
    result.rooms = []
