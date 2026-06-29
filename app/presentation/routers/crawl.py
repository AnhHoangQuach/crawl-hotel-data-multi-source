from fastapi import APIRouter, Depends

from app.application.use_cases.crawl_hotels import CrawlHotelsUseCase

from ..dependencies import get_crawl_hotels_use_case
from ..mappers import request_to_hotel_query, results_to_response
from ..schemas import CrawlRequest, CrawlResponse

router = APIRouter(tags=["crawl"])


@router.post("/crawl", response_model=CrawlResponse, status_code=200)
async def crawl(
    request: CrawlRequest,
    use_case: CrawlHotelsUseCase = Depends(get_crawl_hotels_use_case),
):
    hotel = request_to_hotel_query(request)

    # May raise InvalidSourceError -- mapped to HTTP 400 by the global
    # handlers in app.presentation.error_handlers.
    results = await use_case.execute(hotel, request.source)

    return results_to_response(results)
