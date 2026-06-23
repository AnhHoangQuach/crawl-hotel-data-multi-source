import html
import re
from copy import deepcopy
from typing import Any, Dict, Iterable, List, Optional


_TAG_RE = re.compile(r"<[^>]+>")
_BLOCK_TAG_RE = re.compile(r"(?i)<\s*/?\s*(br|p|div|li|ul|ol|section|article|h[1-6])[^>]*>")
_WHITESPACE_RE = re.compile(r"\s+")
_DISTANCE_LINE_RE = re.compile(r"^\d+(?:[.,]\d+)?\s*(?:m|km)$", re.IGNORECASE)
_HELPFUL_LINE_RE = re.compile(r"^\d+\s+people?\s+find\s+it\s+helpful$", re.IGNORECASE)
_PHOTO_COUNT_LINE_RE = re.compile(r"^\+\d+$")
_SCORE_VALUE_RE = re.compile(r"^\d+(?:\.\d+)?$")
_SCORE_SCALE_RE = re.compile(r"^/\s*\d+$")

_COMMON_NOISE_LINES = {
    "read more",
    "see original",
    "find this review helpful?",
}
_ADDRESS_NOISE_LINES = {
    "in the area",
    "see map",
    "view map",
    "show map",
    "location",
}
_AMENITY_NOISE_LINES = {
    "main facilities",
    "most popular facilities",
    "read more",
}


def clean_text(value: Any) -> Optional[str]:
    """Return one-line, HTML-decoded text suitable for JSON export."""
    if value is None:
        return None
    text = str(value)
    text = _decode_and_strip_tags(text)
    text = _WHITESPACE_RE.sub(" ", text).strip()
    return text or None


def clean_hotel_result_dict(data: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize raw provider output into clean, JSON-friendly data.

    Providers intentionally scrape text with `inner_text()` because it is more
    resilient than parsing each provider's volatile DOM into structure. This
    function is the shared boundary that turns that raw text into clean export
    data without newline escapes, HTML entities/tags, or common UI labels.
    """
    cleaned = deepcopy(data)

    for field in (
        "source",
        "query_name",
        "query_address",
        "query_id",
        "name",
        "accommodation_type",
        "star_rating",
        "detail_url",
        "error",
    ):
        if field in cleaned:
            cleaned[field] = clean_text(cleaned[field])

    if "rating_summary" in cleaned:
        cleaned["rating_summary"] = clean_rating_summary(cleaned["rating_summary"])
    if "address" in cleaned:
        cleaned["address"] = clean_address(cleaned["address"])
    if "amenities" in cleaned:
        cleaned["amenities"] = clean_lines(cleaned["amenities"], _AMENITY_NOISE_LINES)
    if "facilities" in cleaned:
        cleaned["facilities"] = clean_facilities(cleaned["facilities"])
    if "description" in cleaned:
        cleaned["description"] = clean_paragraphs(cleaned["description"])

    cleaned["reviews"] = clean_reviews(cleaned.get("reviews") or [])
    cleaned["rooms"] = [_clean_room(room) for room in cleaned.get("rooms") or [] if room]
    cleaned["photos"] = _dedupe_keep_order(
        text for text in (clean_text(photo) for photo in cleaned.get("photos") or []) if text
    )

    return cleaned


def clean_address(value: Any) -> Optional[str]:
    lines = _text_lines(value)
    candidates = []
    for line in lines:
        lower = line.lower()
        if lower in _ADDRESS_NOISE_LINES:
            continue
        if _DISTANCE_LINE_RE.match(line):
            continue
        candidates.append(line)

    candidates = _dedupe_keep_order(candidates)
    for line in candidates:
        if "," in line:
            return line
    return clean_text(" ".join(candidates))


def clean_rating_summary(value: Any) -> List[str]:
    return _merge_score_scale_lines(clean_lines(value))


def clean_paragraphs(value: Any) -> List[str]:
    if value is None:
        return []

    text = _decode_and_strip_tags(str(value), block_tags_as_newlines=True)
    chunks = re.split(r"\n\s*\n+", text)
    paragraphs = []
    for chunk in chunks:
        paragraph = clean_text(chunk)
        if paragraph and paragraph.lower() not in _COMMON_NOISE_LINES:
            paragraphs.append(paragraph)
    return _dedupe_keep_order(paragraphs)


def clean_lines(value: Any, noise_lines: Iterable[str] = ()) -> List[str]:
    noise = {line.lower() for line in noise_lines}
    items = []
    for line in _text_lines(value):
        if line.lower() in noise:
            continue
        items.append(line)
    return _dedupe_keep_order(items)


def clean_facilities(value: Any) -> List[str]:
    items = []
    for line in _text_lines(value):
        lower = line.lower()
        if lower in _COMMON_NOISE_LINES:
            continue
        if lower.startswith("all facilities in "):
            continue
        items.append(line)
    return _dedupe_keep_order(items)


def clean_reviews(reviews: Iterable[Any]) -> List[List[str]]:
    cleaned = []
    for review in reviews:
        lines = []
        for line in _text_lines(review):
            lower = line.lower()
            if lower == "accommodation's reply":
                break
            if lower in _COMMON_NOISE_LINES:
                continue
            if _HELPFUL_LINE_RE.match(line):
                continue
            if _PHOTO_COUNT_LINE_RE.match(line):
                continue
            lines.append(line)

        lines = _merge_score_scale_lines(lines)
        while lines and _looks_like_stray_initials(lines[-1]):
            lines.pop()

        if lines and lines not in cleaned:
            cleaned.append(lines)
    return cleaned


def _clean_room(room: Dict[str, Any]) -> Dict[str, Any]:
    cleaned = {}
    for key, value in room.items():
        if key == "price_summary":
            cleaned[key] = clean_lines(value)
        elif isinstance(value, str):
            cleaned[key] = clean_text(value)
        else:
            cleaned[key] = value
    return cleaned


def _text_lines(value: Any) -> List[str]:
    if value is None:
        return []
    text = _decode_and_strip_tags(str(value), block_tags_as_newlines=True)
    return [cleaned for line in text.splitlines() if (cleaned := clean_text(line))]


def _decode_and_strip_tags(value: str, block_tags_as_newlines: bool = False) -> str:
    text = html.unescape(value).replace("\xa0", " ")
    if block_tags_as_newlines:
        text = _BLOCK_TAG_RE.sub("\n", text)
    else:
        text = _BLOCK_TAG_RE.sub(" ", text)
    return _TAG_RE.sub(" ", text)


def _dedupe_keep_order(items: Iterable[str]) -> List[str]:
    deduped = []
    seen = set()
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        deduped.append(item)
    return deduped


def _merge_score_scale_lines(lines: List[str]) -> List[str]:
    merged = []
    i = 0
    while i < len(lines):
        current = lines[i]
        if i + 1 < len(lines) and _SCORE_VALUE_RE.match(current) and _SCORE_SCALE_RE.match(lines[i + 1]):
            merged.append(f"{current}{lines[i + 1].replace(' ', '')}")
            i += 2
            continue
        merged.append(current)
        i += 1
    return merged


def _looks_like_stray_initials(line: str) -> bool:
    compact = line.replace(".", "").replace(" ", "")
    return 1 <= len(compact) <= 3 and compact.isalpha() and compact.upper() == compact
