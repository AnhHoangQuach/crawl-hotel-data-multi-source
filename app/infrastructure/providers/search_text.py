import re
import unicodedata

_COUNTRY_NAMES = {"viet nam", "vietnam"}
_ADMIN_FILLER_RE = re.compile(r"\b(thanh pho|tp|city|province|tinh)\b")


def normalize_search_text(text: str) -> str:
    """Strip accents/punctuation and collapse whitespace, keeping casing --
    this is the literal text typed into a provider's search box."""
    text = unicodedata.normalize("NFKD", text or "")
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = re.sub(r"[^a-zA-Z0-9\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _is_street_segment(normalized: str) -> bool:
    """True when an address segment is street-level detail rather than a
    city/province/district name, e.g. "136-138-140 Phan Chau Trinh" -- a
    house-number-and-street string, not a place -- vs. "Da Nang"."""
    if any(ch.isdigit() for ch in normalized):
        return True
    return len(normalized.split()) > 4


def address_search_hint(address: str) -> str:
    """Pick the most specific city/province-looking segment out of a
    "<street>, <district>, <city>[, <country>]"-shaped address.

    Many source addresses are just a street address with no city at all
    (e.g. "136-138-140 Phan Chau Trinh"), so there's nothing usable here --
    returns "" rather than guessing the street itself is a place.
    """
    parts = [p.strip() for p in (address or "").split(",") if p.strip()]
    for part in reversed(parts):
        normalized = normalize_search_text(part).lower()
        if normalized in _COUNTRY_NAMES:
            continue
        normalized = _ADMIN_FILLER_RE.sub(" ", normalized)
        normalized = re.sub(r"\s+", " ", normalized).strip()
        if normalized and not _is_street_segment(normalized):
            return normalized
    return ""


def build_search_text(name: str, address: str) -> str:
    """Combine a hotel name with whatever city hint its address yields.

    ("Moonlight Hotel Da Nang", "136-138-140 Phan Chau Trinh") ->
    "Moonlight Hotel Da Nang" -- no comma-separated city in that address,
    so no hint is added (the name already carries "Da Nang"). Skips
    appending the hint whenever it's already a substring of the name, so a
    name that already embeds its city isn't duplicated.
    """
    norm_name = normalize_search_text(name)
    hint = address_search_hint(address)
    if not hint or hint in norm_name.lower():
        return norm_name
    return f"{norm_name} {hint}"
