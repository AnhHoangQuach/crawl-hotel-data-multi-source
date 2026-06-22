import asyncio

from app.infrastructure.config import Settings

# This RapidAPI product scrapes TripAdvisor live on each call and is flaky
# under load: it intermittently 500s, or returns 200 with an empty/null
# body for a query that works fine moments later. A couple of retries
# clears almost all of these without masking real errors (4xx, no-match).
_MAX_ATTEMPTS = 3
_RETRY_DELAY_SECONDS = 1.5


def _headers(settings: Settings):
    return {
        "x-rapidapi-key": settings.rapidapi_key,
        "x-rapidapi-host": settings.tripadvisor_rapidapi_host,
    }


async def _get_json(http, path, params, settings: Settings, *, retry_if_empty=False):
    resp = None
    for attempt in range(_MAX_ATTEMPTS):
        resp = await http.get(
            path, params=params, headers=_headers(settings), timeout=settings.request_timeout_seconds
        )
        is_last = attempt == _MAX_ATTEMPTS - 1
        if resp.status_code >= 500 and not is_last:
            await asyncio.sleep(_RETRY_DELAY_SECONDS)
            continue
        resp.raise_for_status()
        data = resp.json()
        if retry_if_empty and not data.get("name") and not is_last:
            await asyncio.sleep(_RETRY_DELAY_SECONDS)
            continue
        return data
    return resp.json()


async def search_location(http, settings: Settings, query: str):
    return await _get_json(http, settings.tripadvisor_search_path, {"query": query}, settings)


async def get_hotel_details(http, settings: Settings, location_id):
    return await _get_json(
        http,
        settings.tripadvisor_details_path,
        {"query": location_id},
        settings,
        retry_if_empty=True,
    )
