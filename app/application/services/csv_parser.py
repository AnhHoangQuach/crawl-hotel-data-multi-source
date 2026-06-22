import csv
import io
from typing import List

from app.domain.entities import HotelQuery
from app.domain.exceptions import CsvParseError

from .name_normalizer import clean_hotel_name

NAME_HEADER_ALIASES = {"name", "hotel_name", "hotel", "ten", "ten_khach_san"}
ADDRESS_HEADER_ALIASES = {"address", "city", "location", "dia_chi", "diachi"}
ID_HEADER_ALIASES = {"id", "hotel_id", "staging_id", "ma_khach_san"}


def _find_column(fieldnames, aliases):
    lowered = {f.strip().lower(): f for f in fieldnames}
    for alias in aliases:
        if alias in lowered:
            return lowered[alias]
    return None


def parse_hotel_queries(text: str) -> List[HotelQuery]:
    """Parse uploaded CSV content into a list of HotelQuery.

    Accepts a few header spellings (English and Vietnamese) for the name/
    address columns so the same parser works for CSVs from either locale.
    An `id` column, if present, is carried through to HotelResult.query_id
    so callers can correlate results back to their own records (e.g. a
    staging-table row id) -- it's optional and ignored for matching.
    """
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        return []

    name_col = _find_column(reader.fieldnames, NAME_HEADER_ALIASES)
    addr_col = _find_column(reader.fieldnames, ADDRESS_HEADER_ALIASES)
    id_col = _find_column(reader.fieldnames, ID_HEADER_ALIASES)
    if not name_col:
        raise CsvParseError(
            f"Could not find a hotel name column in the CSV. Columns found: {reader.fieldnames}"
        )

    queries = []
    for row in reader:
        name = (row.get(name_col) or "").strip()
        if not name:
            continue
        name = clean_hotel_name(name)
        address = (row.get(addr_col) or "").strip() if addr_col else ""
        row_id = (row.get(id_col) or "").strip() if id_col else ""
        queries.append(HotelQuery(name=name, address=address, id=row_id or None))
    return queries
