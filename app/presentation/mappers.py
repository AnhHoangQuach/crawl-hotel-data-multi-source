import re
from typing import Dict

from app.domain.entities import HotelQuery, HotelResult

from .schemas import CrawlRequest, CrawlResponse, HotelResultResponse

_WHITESPACE_RE = re.compile(r"\s+")


def _clean(value) -> str:
    return _WHITESPACE_RE.sub(" ", value or "").strip()


def request_to_hotel_query(request: CrawlRequest) -> HotelQuery:
    return HotelQuery(name=_clean(request.name), address=_clean(request.address), id=_clean(request.id) or None)


def results_to_response(results: Dict[str, HotelResult]) -> CrawlResponse:
    return {source: HotelResultResponse(**result.to_dict()) for source, result in results.items()}
