from app.infrastructure.config import Settings


def _headers(settings: Settings):
    return {
        "x-rapidapi-key": settings.rapidapi_key,
        "x-rapidapi-host": settings.tripadvisor_rapidapi_host,
    }


async def search_location(http, settings: Settings, query: str):
    resp = await http.get(
        settings.tripadvisor_search_path,
        params={"query": query},
        headers=_headers(settings),
        timeout=settings.request_timeout_seconds,
    )
    resp.raise_for_status()
    return resp.json()


async def get_hotel_details(http, settings: Settings, location_id):
    resp = await http.get(
        settings.tripadvisor_details_path,
        params={"id": location_id, "currencyCode": "VND"},
        headers=_headers(settings),
        timeout=settings.request_timeout_seconds,
    )
    resp.raise_for_status()
    return resp.json()
