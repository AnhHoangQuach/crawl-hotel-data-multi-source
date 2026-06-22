import json

from ..dom_extraction import extract_all_texts, extract_text
from ..utils import dig
from . import config


def _iter_json_ld_nodes(data):
    if isinstance(data, list):
        for item in data:
            yield from _iter_json_ld_nodes(item)
    elif isinstance(data, dict):
        graph = data.get("@graph")
        if isinstance(graph, list):
            for item in graph:
                yield from _iter_json_ld_nodes(item)
        else:
            yield data


async def extract_json_ld(page) -> dict:
    """Find the schema.org Hotel/LodgingBusiness block TripAdvisor embeds
    for Google's hotel rich results. Structured data like this is far more
    stable than the page's hashed CSS classes, so it's the primary source
    for every detail field it covers; CSS-selector extraction is only a
    fallback for fields it doesn't carry (see config.py module docstring).
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
            types = node.get("@type")
            types = types if isinstance(types, list) else [types]
            if any(t and ("hotel" in t.lower() or "lodging" in t.lower()) for t in types):
                return node
    return {}


def address_to_text(address) -> str:
    if not address:
        return None
    if isinstance(address, str):
        return address
    if isinstance(address, dict):
        parts = [
            address.get("streetAddress"),
            address.get("addressLocality"),
            address.get("addressRegion"),
            address.get("postalCode"),
            address.get("addressCountry"),
        ]
        return ", ".join(p for p in parts if p) or None
    return None


def images_from_json_ld(image_field, max_photos) -> list:
    if not image_field:
        return []
    items = image_field if isinstance(image_field, list) else [image_field]
    urls = []
    for item in items:
        if isinstance(item, str):
            urls.append(item)
        elif isinstance(item, dict):
            url = item.get("url") or item.get("contentUrl")
            if url:
                urls.append(url)
    return urls[:max_photos]


def reviews_from_json_ld(review_field, max_reviews) -> list:
    if not review_field:
        return []
    items = review_field if isinstance(review_field, list) else [review_field]
    texts = []
    for item in items:
        if not isinstance(item, dict):
            continue
        body = item.get("reviewBody") or item.get("description")
        if body:
            texts.append(body)
        if len(texts) >= max_reviews:
            break
    return texts


def amenities_from_json_ld(amenity_field) -> str:
    if not amenity_field:
        return None
    items = amenity_field if isinstance(amenity_field, list) else [amenity_field]
    names = []
    for item in items:
        if not isinstance(item, dict):
            continue
        name = item.get("name")
        value = item.get("value")
        if name and (value is None or value is True or str(value).lower() == "true"):
            names.append(name)
    return ", ".join(names) if names else None


async def extract_cdn_photos(page, max_photos=config.MAX_PHOTOS) -> list:
    """Collect gallery photos by CDN host instead of CSS class -- the
    `media-cdn.tripadvisor.com` domain is a stable serving convention,
    unlike the page's obfuscated presentation classes.
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
        key = src.split("?")[0]
        if key in seen:
            continue
        seen.add(key)
        photos.append(src)
        if len(photos) >= max_photos:
            break
    return photos


async def extract_css_reviews(page, max_reviews=config.MAX_REVIEW_BLOCKS) -> list:
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
    result.accommodation_type = await extract_text(page, config.DETAIL_TYPE_SELECTOR)

    star = dig(json_ld, "starRating", "ratingValue")
    result.star_rating = (
        str(star) if star is not None else await extract_text(page, config.DETAIL_STAR_RATING_SELECTOR)
    )

    rating = dig(json_ld, "aggregateRating", "ratingValue")
    review_count = dig(json_ld, "aggregateRating", "reviewCount") or dig(
        json_ld, "aggregateRating", "ratingCount"
    )
    if rating is not None:
        result.rating_summary = f"{rating} ({review_count} reviews)" if review_count else str(rating)
    else:
        result.rating_summary = await extract_text(page, config.DETAIL_RATING_SUMMARY_SELECTOR)

    result.address = address_to_text(json_ld.get("address")) or await extract_text(
        page, config.DETAIL_ADDRESS_SELECTOR
    )

    lat = dig(json_ld, "geo", "latitude")
    lng = dig(json_ld, "geo", "longitude")
    try:
        result.latitude = float(lat) if lat is not None else None
        result.longitude = float(lng) if lng is not None else None
    except (TypeError, ValueError):
        result.latitude = result.longitude = None

    result.description = json_ld.get("description") or await extract_text(
        page, config.DETAIL_DESCRIPTION_SELECTOR
    )
    result.amenities = amenities_from_json_ld(json_ld.get("amenityFeature")) or await extract_text(
        page, config.DETAIL_AMENITIES_SELECTOR
    )

    result.photos = images_from_json_ld(json_ld.get("image"), config.MAX_PHOTOS) or await extract_cdn_photos(
        page
    )

    reviews = reviews_from_json_ld(json_ld.get("review"), config.MAX_REVIEW_BLOCKS)
    result.reviews = reviews or await extract_css_reviews(page)
