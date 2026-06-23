import re
import unicodedata
from difflib import SequenceMatcher
from typing import List, Tuple


def normalize(text: str) -> str:
    if not text:
        return ""
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = text.lower()
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def similarity(a: str, b: str) -> float:
    a, b = normalize(a), normalize(b)
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a, b).ratio()


def name_contains(query_name: str, candidate_name: str) -> bool:
    """True if one normalized name wholly contains the other.

    Plain substring containment is a much more precise signal than
    character-overlap ratio for hotel-chain-style names (e.g. "Senior
    Hotel" is contained in "Senior Hotel 2", but a ratio would also reward
    "Hotel Senior" -- a different, reordered name -- almost as highly).
    """
    a, b = normalize(query_name), normalize(candidate_name)
    if not a or not b:
        return False
    return a in b or b in a


_GENERIC_NAME_TOKENS = {
    "and",
    "apartment",
    "apartments",
    "boutique",
    "hotel",
    "hotels",
    "residence",
    "resort",
    "spa",
    "the",
    "villa",
    "villas",
}

_LOCATION_FILLER_TOKENS = {
    "city",
    "country",
    "district",
    "duong",
    "nam",
    "phuong",
    "pho",
    "province",
    "quan",
    "region",
    "street",
    "thanh",
    "tinh",
    "viet",
    "vietnam",
    "ward",
}


def _name_tokens(text: str) -> set:
    return {t for t in normalize(text).split() if t not in _GENERIC_NAME_TOKENS and len(t) > 1}


def name_token_contains(query_name: str, candidate_name: str) -> bool:
    """True when one meaningful name-token set contains the other.

    This catches searches that append a city to the hotel name, e.g.
    "Golden Crown Ho Chi Minh" vs "Golden Crown Hotel", without treating a
    single generic/shared word as a confident match.
    """
    query_tokens = _name_tokens(query_name)
    candidate_tokens = _name_tokens(candidate_name)
    if len(query_tokens) < 2 or len(candidate_tokens) < 2:
        return False
    common = query_tokens & candidate_tokens
    smaller = min(len(query_tokens), len(candidate_tokens))
    return len(common) >= 2 and len(common) == smaller


def query_location_hint_matches(query_name: str, candidate_name: str, candidate_location: str) -> bool:
    """True if query-name tokens not used by the candidate name appear in location.

    Booking users often search "hotel name + city". In that shape, the
    extra query tokens are location hints, not a reason to penalize the
    hotel-name match.
    """
    location_tokens = set(normalize(candidate_location).split())
    if not location_tokens:
        return False
    extra_tokens = _name_tokens(query_name) - _name_tokens(candidate_name)
    extra_tokens = {t for t in extra_tokens if len(t) > 1}
    if len(extra_tokens) < 2:
        return False
    return len(extra_tokens & location_tokens) / len(extra_tokens) >= 0.75


def location_text_matches(query_location: str, candidate_location: str) -> bool:
    """Loose location containment for full-address vs city/province text.

    Booking suggestions often expose only "Ho Chi Minh City, Vietnam",
    while the CSV has a full street address like "... Quận Phú Nhuận,
    Hồ Chí Minh, Việt Nam". Score by how much of the shorter/provider
    location is present in the query address, not by the full street token
    count, otherwise correct city-level matches get diluted below threshold.
    """
    q_tokens = {
        t
        for t in normalize(query_location).split()
        if len(t) > 1 and t not in _LOCATION_FILLER_TOKENS
    }
    c_tokens = {
        t
        for t in normalize(candidate_location).split()
        if len(t) > 1 and t not in _LOCATION_FILLER_TOKENS
    }
    if len(q_tokens) < 2 or not c_tokens:
        return False
    denominator = max(1, min(len(q_tokens), len(c_tokens)))
    return len(q_tokens & c_tokens) / denominator >= 0.75


def _location_segments(location: str) -> List[str]:
    """Split a "City, Province, Country"-shaped string into normalized
    parts, most-specific first, dropping the trailing country segment --
    matching on country alone would accept any same-country candidate
    regardless of city, the exact failure this module exists to avoid.
    """
    parts = [normalize(p) for p in location.split(",")]
    parts = [p for p in parts if p]
    return parts[:-1] if len(parts) > 1 else parts


def address_matches(query_address: str, candidate_location: str) -> bool:
    """True if any city/province segment of `candidate_location` appears
    in `query_address`. Source addresses are full street addresses while
    provider location text is coarse (e.g. "Nha Trang, Khanh Hoa,
    Vietnam") -- segment-level substring containment is what lets the two
    granularities line up.
    """
    qa = normalize(query_address)
    if not qa or not candidate_location:
        return False
    return any(seg in qa for seg in _location_segments(candidate_location) if len(seg) > 2)


def exact_address_matches(query_address: str, candidate_address: str) -> bool:
    """True when two full-ish addresses clearly point to the same place.

    Booking cards can expose street addresses, not just city/province text.
    For those candidates, use a stricter signal than `address_matches`:
    direct containment or strong token overlap, with matching numbers when
    both sides contain a house/building number.
    """
    qa, ca = normalize(query_address), normalize(candidate_address)
    if len(qa) < 12 or len(ca) < 12:
        return False
    if qa in ca or ca in qa:
        return True

    q_tokens = set(qa.split())
    c_tokens = set(ca.split())
    q_numbers = {t for t in q_tokens if any(c.isdigit() for c in t)}
    c_numbers = {t for t in c_tokens if any(c.isdigit() for c in t)}
    if q_numbers and not c_numbers:
        return False
    if q_numbers and c_numbers and not (q_numbers & c_numbers):
        return False

    q_words = {t for t in q_tokens if not t.isdigit() and len(t) > 1}
    c_words = {t for t in c_tokens if not t.isdigit() and len(t) > 1}
    common_words = q_words & c_words
    if len(common_words) < 3:
        return False

    denominator = max(1, min(len(q_words), len(c_words)))
    return len(common_words) / denominator >= 0.6


def _split_suggestion(text: str) -> Tuple[str, str]:
    """Autocomplete suggestion rows render as a name line followed by a
    location line (confirmed on Booking.com's dropdown: inner_text() keeps
    that as a newline). Falls back to treating the whole row as just a
    name -- with no location -- when no such split is present, so an
    unrecognized layout degrades to a plain name comparison instead of
    misreading unrelated text as a location.
    """
    if "\n" not in text:
        return text, ""
    name, _, rest = text.partition("\n")
    return name, rest.replace("\n", " ")


def score_candidate_details(
    query_name: str,
    query_address: str,
    cand_name: str,
    cand_loc: str,
    *,
    require_address_match: bool = False,
) -> dict:
    """Score one candidate, address match first, name containment second --
    matching the rest of the codebase's empirical finding that raw
    character-overlap ratio is too easily fooled by generic, same-sounding
    names in the wrong city/country (e.g. Booking.com once suggested
    "Riverside Hotels Apartments" in Bangkok, Thailand above the correct
    Hai Phong, Vietnam hotel for "Zen Riverside Hotel and Apartment", since
    the two share enough characters overall to score above threshold).

    A confirmed address match plus name containment is the strongest
    possible signal (near 1.0). A confirmed address *mismatch* heavily
    discounts name overlap, since that mismatch is what let wrong-city
    candidates outrank the real match before. Character-overlap ratio is
    only the fallback for candidates with no resolvable address at all.

    `require_address_match=True` is for Booking result cards where a street
    address is available: the address match must come first, then name
    containment decides whether the result is confidently accepted.
    """
    name_score = similarity(query_name, cand_name)
    has_loc = bool(cand_loc and cand_loc.strip())
    addr_score = similarity(query_address, cand_loc) if query_address and has_loc else 0.0
    name_hit = name_contains(query_name, cand_name)
    token_name_hit = name_token_contains(query_name, cand_name)
    exact_addr_hit = has_loc and bool(query_address) and exact_address_matches(query_address, cand_loc)
    addr_hit = has_loc and bool(query_address) and address_matches(query_address, cand_loc)
    loose_location_hit = has_loc and bool(query_address) and location_text_matches(
        query_address, cand_loc
    )
    query_location_hit = has_loc and query_location_hint_matches(query_name, cand_name, cand_loc)
    strong_name_hit = name_hit or token_name_hit
    score = 0.0
    reason = "fallback"

    if require_address_match:
        if exact_addr_hit and strong_name_hit:
            score = max(0.96, name_score)
            reason = "exact_address_and_name"
        elif (loose_location_hit or query_location_hit) and strong_name_hit:
            score = max(0.82, name_score)
            reason = "location_hint_and_name"
        elif exact_addr_hit:
            score = max(0.72, name_score * 0.4 + 0.45)
            reason = "exact_address_only"
        elif not query_address and strong_name_hit:
            score = max(0.62, name_score)
            reason = "name_only_no_query_address"
        elif has_loc and query_address:
            score = min(0.49, name_score * 0.45)
            reason = "address_mismatch"
        else:
            score = min(0.49, name_score * 0.7)
            reason = "name_fallback_below_threshold"
        return {
            "score": score,
            "reason": reason,
            "query_name": query_name,
            "query_address": query_address,
            "candidate_name": cand_name,
            "candidate_location": cand_loc,
            "name_score": name_score,
            "address_score": addr_score,
            "name_contains": name_hit,
            "name_token_contains": token_name_hit,
            "exact_address_matches": exact_addr_hit,
            "coarse_address_matches": addr_hit,
            "loose_location_matches": loose_location_hit,
            "query_location_hint_matches": query_location_hit,
            "require_address_match": require_address_match,
        }

    if strong_name_hit and (addr_hit or loose_location_hit or query_location_hit or not has_loc):
        score = max(0.9 if (addr_hit or loose_location_hit or query_location_hit) else 0.78, name_score)
        reason = "address_or_location_and_name" if has_loc else "name_without_location"
    elif addr_hit or loose_location_hit:
        score = max(0.7, name_score * 0.5 + 0.35)
        reason = "address_or_location_only"
    elif query_location_hit and strong_name_hit:
        score = max(0.82, name_score)
        reason = "query_location_hint_and_name"
    elif has_loc and query_address:
        score = name_score * 0.5
        reason = "location_present_address_mismatch"
    else:
        score = name_score * 0.7 + addr_score * 0.3
        reason = "weighted_similarity"

    return {
        "score": score,
        "reason": reason,
        "query_name": query_name,
        "query_address": query_address,
        "candidate_name": cand_name,
        "candidate_location": cand_loc,
        "name_score": name_score,
        "address_score": addr_score,
        "name_contains": name_hit,
        "name_token_contains": token_name_hit,
        "exact_address_matches": exact_addr_hit,
        "coarse_address_matches": addr_hit,
        "loose_location_matches": loose_location_hit,
        "query_location_hint_matches": query_location_hit,
        "require_address_match": require_address_match,
    }


def _score_candidate(
    query_name: str,
    query_address: str,
    cand_name: str,
    cand_loc: str,
    *,
    require_address_match: bool = False,
) -> float:
    return score_candidate_details(
        query_name,
        query_address,
        cand_name,
        cand_loc,
        require_address_match=require_address_match,
    )["score"]


def best_match_index(
    query_name: str,
    query_address: str,
    candidate_names: List[str],
    candidate_locations: List[str],
    *,
    require_address_match: bool = False,
) -> Tuple[int, float]:
    """Pick the candidate whose name + location best matches the query.

    See `_score_candidate` for the address-first, name-contains-second
    scoring rationale.
    """
    best_idx, best_score = 0, -1.0
    for i, cand_name in enumerate(candidate_names):
        cand_loc = candidate_locations[i] if i < len(candidate_locations) else ""
        score = _score_candidate(
            query_name,
            query_address,
            cand_name,
            cand_loc,
            require_address_match=require_address_match,
        )
        if score > best_score:
            best_score, best_idx = score, i
    return best_idx, best_score


def best_suggestion_index(
    query_name: str, query_address: str, suggestion_texts: List[str]
) -> Tuple[int, float]:
    """Pick the search/autocomplete suggestion that best matches the query.

    Provider autocomplete ranking is sometimes wrong for unusual or
    ambiguous names (e.g. Traveloka once ranked "Kansai International
    Airport" above any Phu Quoc hotel for the query "THE SEA PHU QUOC"), so
    callers re-rank the visible suggestions themselves instead of always
    taking the first one. Each suggestion is split into a name line and a
    location line (see `_split_suggestion`) and scored the same way as
    `best_match_index`, rather than fuzzy-matching one combined text blob.
    """
    best_idx, best_score = 0, -1.0
    for i, text in enumerate(suggestion_texts):
        cand_name, cand_loc = _split_suggestion(text)
        score = _score_candidate(query_name, query_address, cand_name, cand_loc)
        if score > best_score:
            best_score, best_idx = score, i
    return best_idx, best_score


def score_suggestion_details(query_name: str, query_address: str, suggestion_text: str) -> dict:
    cand_name, cand_loc = _split_suggestion(suggestion_text)
    details = score_candidate_details(query_name, query_address, cand_name, cand_loc)
    details["raw_suggestion_text"] = suggestion_text
    return details
