import re
import unicodedata
from difflib import SequenceMatcher


def normalize(text):
    if not text:
        return ""
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = text.lower()
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def similarity(a, b):
    a, b = normalize(a), normalize(b)
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a, b).ratio()


def best_match_index(query_name, query_address, candidate_names, candidate_locations):
    """Pick the candidate whose name + location best matches the query.

    Name similarity is weighted higher since it's the primary identifier;
    address similarity breaks ties between same-name hotels in different areas.
    """
    best_idx, best_score = 0, -1.0
    for i, cand_name in enumerate(candidate_names):
        cand_loc = candidate_locations[i] if i < len(candidate_locations) else ""
        name_score = similarity(query_name, cand_name)
        addr_score = similarity(query_address, cand_loc) if query_address else 0.0
        score = name_score * 0.7 + addr_score * 0.3
        if score > best_score:
            best_score, best_idx = score, i
    return best_idx, best_score


def best_suggestion_index(query_name, query_address, suggestion_texts):
    """Pick the autocomplete suggestion that best matches the query.

    Traveloka's own autocomplete ranking is sometimes wrong for unusual or
    ambiguous names (e.g. it once ranked "Kansai International Airport"
    above any Phu Quoc hotel for the query "THE SEA PHU QUOC"), so we
    re-rank the visible suggestions ourselves instead of always taking the
    first one. Each suggestion is a multi-line blob (name/type/location),
    scored as one block against "name + address" combined.
    """
    query = f"{query_name} {query_address}".strip()
    best_idx, best_score = 0, -1.0
    for i, text in enumerate(suggestion_texts):
        score = similarity(query, text)
        if score > best_score:
            best_score, best_idx = score, i
    return best_idx, best_score
