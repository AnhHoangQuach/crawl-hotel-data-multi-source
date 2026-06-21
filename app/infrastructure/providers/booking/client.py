from app.infrastructure.config import Settings


def _headers(settings: Settings):
    return {
        "x-rapidapi-key": settings.rapidapi_key,
        "x-rapidapi-host": settings.booking_rapidapi_host,
    }


async def search_destination(http, settings: Settings, query: str):
    resp = await http.get(
        settings.booking_search_destination_path,
        params={"query": query},
        headers=_headers(settings),
        timeout=settings.request_timeout_seconds,
    )
    resp.raise_for_status()
    return resp.json()


async def search_hotels(http, settings: Settings, dest_id, search_type, checkin, checkout):
    resp = await http.get(
        settings.booking_search_hotels_path,
        params={
            "dest_id": dest_id,
            "search_type": search_type,
            "arrival_date": checkin,
            "departure_date": checkout,
            "currency_code": settings.booking_currency_code,
        },
        headers=_headers(settings),
        timeout=settings.request_timeout_seconds,
    )
    resp.raise_for_status()
    return resp.json()


async def get_hotel_details(http, settings: Settings, hotel_id, checkin, checkout):
    resp = await http.get(
        settings.booking_details_path,
        params={
            "hotel_id": hotel_id,
            "arrival_date": checkin,
            "departure_date": checkout,
            "currency_code": settings.booking_currency_code,
        },
        headers=_headers(settings),
        timeout=settings.request_timeout_seconds,
    )
    resp.raise_for_status()
    return resp.json()
