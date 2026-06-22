import re
import unicodedata

# Generic accommodation-type words that source CSVs often glue onto the
# actual property name, anywhere in it ("Khach san ABC", "ABC Hotel", "ABC
# Hotel & Spa"). Providers rarely index a listing under that generic word, so
# leaving it in hurts autocomplete/search matching -- strip every occurrence
# before searching, not just leading/trailing ones.
# Longer phrases are listed before the single words they contain so e.g.
# "khach san" is matched as one unit rather than leaving a stray "khach".
_GENERIC_TERMS = [
    "khach san",
    "nha nghi",
    "nha khach",
    "guest house",
    "ks",
    "hotel",
    "resort",
    "motel",
    "homestay",
    "hostel",
    "inn",
    "guesthouse",
]
_GENERIC_TERM_WORDS = [term.split() for term in _GENERIC_TERMS]

_PUNCT_RE = re.compile(r"^\W+|\W+$")


def _strip_accents(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(c for c in decomposed if not unicodedata.combining(c))


def _normalize_token(token: str) -> str:
    return _PUNCT_RE.sub("", _strip_accents(token).lower())


def clean_hotel_name(name: str) -> str:
    """Strip generic accommodation-type words (e.g. "Khach san", "Hotel",
    "Resort") from anywhere in a raw hotel name -- prefix, suffix, or in the
    middle -- before it's used to search a provider, so the search/matching
    is driven by the actual property name.

    Matching is accent- and case-insensitive (so it catches "Khách sạn",
    "khach san", "KHACH SAN", ...) but the original casing/diacritics of the
    kept words are preserved. Falls back to the original name if stripping
    would remove every word (e.g. the name is just "Hotel").
    """
    if not name:
        return name

    tokens = name.split()
    norm_tokens = [_normalize_token(t) for t in tokens]

    kept = []
    i = 0
    while i < len(tokens):
        match_len = 0
        for words in _GENERIC_TERM_WORDS:
            n = len(words)
            if norm_tokens[i : i + n] == words:
                match_len = n
                break
        if match_len:
            i += match_len
        else:
            kept.append(tokens[i])
            i += 1

    cleaned = " ".join(kept).strip()
    return cleaned or name
