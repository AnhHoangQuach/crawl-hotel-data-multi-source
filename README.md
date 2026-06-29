# crawl-hotel-data-multi-source

A FastAPI service that crawls hotel details from multiple sources, given one hotel (id + name + address) per call:

- **Traveloka** — crawled directly via Playwright/crawl4ai (no API key needed).
- **Booking.com** — crawled directly via Playwright/crawl4ai (no API key needed).

Every source implements the same **provider interface** (`HotelProviderPort`) and produces the same **result schema** (`HotelResult`), so a request can run one or several sources at once and results can be compared/merged easily.

Crawling is triggered through the **API**: POST one hotel's JSON object to `/crawl` and the server crawls it synchronously, returning the result in the same response once it's done. To crawl many hotels, call `/crawl` once per hotel.

## Quick start

Pick one:

**A. Run from source**

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
playwright install chromium   # only needed for the Traveloka provider

python3 main.py                # serves on http://localhost:8000
```

**B. Run with Docker Compose**

```bash
cp .env.example .env           # optional: HOST/PORT/OUTPUT_DIR overrides
docker compose up --build      # serves on http://localhost:8000
```

Either way, once the server is up:

```bash
curl http://localhost:8000/health
open http://localhost:8000/docs   # Swagger UI
```

See "Using the API" below for how to submit a crawl request. Full setup details (request format, plain `docker build`/`docker run`) are further down.

## Architecture

The codebase follows a layered (clean) architecture, with dependencies pointing inward (presentation → application → domain; infrastructure implements application's ports):

```
app/
  domain/                  Framework-free business model
    entities.py             HotelQuery, HotelResult
    exceptions.py              DomainError and subtypes

  application/             Use cases + the ports infrastructure must implement
    ports/
      hotel_provider.py      HotelProviderPort (contract every source implements)
      result_storage.py        ResultStoragePort (contract result persistence implements)
    services/
      source_resolver.py        validate a requested source string against available providers
    use_cases/
      crawl_hotels.py          validate sources, crawl one hotel across every source, return results

  infrastructure/          Concrete adapters for the ports above
    config.py                Settings (env vars / .env), single source of config
    storage/
      json_result_writer.py    writes results to output/<request_id>/hotels_result_<source>.json
    providers/
      base.py                  BaseHotelProvider: shared crawl loop (error handling, rate-limit, logging)
      registry.py               source name -> provider class
      traveloka/                 Playwright/crawl4ai scraper
      booking/                     Playwright/crawl4ai scraper

  presentation/             FastAPI-specific wiring
    schemas.py                Pydantic request/response DTOs
    mappers.py                  DTOs <-> domain entities
    dependencies.py              FastAPI Depends() wiring (DI)
    error_handlers.py             maps domain exceptions to HTTP responses
    routers/
      health.py
      crawl.py

  app_factory.py            FastAPI app factory (create_app())

main.py                     entrypoint: runs uvicorn
```

### Adding a new source

1. Create `app/infrastructure/providers/<name>/provider.py` with a class extending `BaseHotelProvider`.
2. Implement `async def fetch_one(self, query: HotelQuery) -> HotelResult`, starting from `HotelResult.empty(query, "<name>")`.
3. Register the class in `PROVIDER_REGISTRY` in `app/infrastructure/providers/registry.py`.

`BaseHotelProvider` already handles normalizing errors into a `HotelResult`, rate-limiting, and logging — a new provider only needs to fetch data for one hotel. No other layer needs to change.

## Requirements

- Python 3.10+
- Google Chrome/Chromium, managed automatically by Playwright/crawl4ai

## Setup

```bash
python3 -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate

pip install -r requirements.txt
playwright install chromium       # browser for crawl4ai (Traveloka provider only)
```

Create a `.env` from the template if you want to override defaults:

```bash
cp .env.example .env
```

## Running the server

```bash
source venv/bin/activate
python3 main.py
```

The server listens on `http://0.0.0.0:8000` by default (override via `HOST`/`PORT` in `.env`). Swagger UI is available at `http://localhost:8000/docs`.

## Using the API

### Crawl a hotel (one hotel per call)

Send a JSON body for a single hotel: `name` is required; `address` is optional but improves matching when multiple hotels share a name. The optional `id` (e.g. your own staging-table row id) is carried through to `query_id` in the result, so you can correlate it back without relying on name matching. `source` is optional:

```bash
curl -X POST http://localhost:8000/crawl \
  -H "Content-Type: application/json" \
  -d '{
        "id": "84110",
        "name": "Muong Thanh Luxury Phu Quoc Hotel",
        "address": "Kien Giang",
        "source": "traveloka"
      }'
```

`source` is comma-separated (`"traveloka,booking"`) or `"all"` (default if omitted). To crawl a list of hotels, call `/crawl` once per hotel (sequentially or in parallel, as your client prefers).

The request blocks until the hotel has been crawled across every requested source, then returns one response keyed by source name directly:

```json
{
  "traveloka": { /* one HotelResult, see schema below */ }
}
```

### Other endpoints

| Method | Path | Description |
|---|---|---|
| GET | `/health` | health check |
| GET | `/sources` | list of supported source names |

Each request's results are also written to `output/<request_id>/hotels_result_<source>.json` for debugging/archival, using an internally generated id you don't need to track.

## Result schema (shared by every source)

Each top-level `<source>` key in the response maps to an object:

| Field | Meaning |
|---|---|
| `source` | data source: `traveloka` / `booking` |
| `query_id`, `query_name`, `query_address` | original input from the request (`query_id` is `null` if the hotel had no `id`) |
| `name`, `accommodation_type`, `star_rating` | name, property type, star rating |
| `rating_summary` | review score + review count, exported as cleaned summary parts (for example `["8.6/10", "Very Good", "143 reviews"]`) |
| `address`, `latitude`, `longitude` | cleaned primary address string and coordinates |
| `amenities`, `facilities`, `description` | amenities/facilities are arrays of cleaned items; description is an array of cleaned paragraphs |
| `photos` | list of photo URLs |
| `reviews` | list of reviews; each review is an array of meaningful cleaned text parts |
| `rooms` | available rooms: name, bed type, breakfast, price, rooms left, cancellation policy |
| `detail_url`, `error` | detail page URL, error message if the crawl failed |

Not every source fills every field; unavailable fields are `null`/`[]`.

## Docker

The compose service (`api`) builds from the local `Dockerfile`, maps port `8000`, and mounts `output/` so crawl results survive container restarts. `.env` is loaded if present but not required:

```bash
cp .env.example .env   # optional, see "Quick start" above
docker compose up --build
```

Equivalent plain `docker build`/`docker run`, if you're not using compose:

```bash
docker build -t crawl-traveloka .

docker run --rm -p 8000:8000 \
  -v "$(pwd)/output:/app/output" \
  --env-file .env \
  crawl-traveloka
```

(Drop `--env-file .env` entirely if you haven't created one — unlike compose, plain `docker run --env-file` requires the file to exist.)

Once the container is running, call the API as described above (`http://localhost:8000`).

The image is built on `python:3.12-slim` and runs `crawl4ai-setup` at build time to install Playwright/Chromium plus the required OS dependencies.

## Known limitations

- **Synchronous request**: `/crawl` blocks for the entire duration of the crawl (one hotel, every requested source) before responding. There's no job/polling layer, so a slow request ties up the connection until it finishes — make sure your client and any reverse proxy use a generous timeout. If you need to crawl many hotels, call `/crawl` once per hotel rather than batching.
- **Traveloka**: reviews are capped at `MAX_REVIEW_PAGES` pages (5 by default) — a large sample, not every review. `rooms` is empty if the hotel has no availability for the default search dates (tomorrow/day after). Traveloka can change its page structure at any time — if the scraper stops finding data, check the selectors in `app/infrastructure/providers/traveloka/config.py`.
- **Booking.com**: room/price data is currently empty because it requires reliable date-picker interaction. Booking.com can change its page structure at any time — if the scraper stops finding data, check the selectors in `app/infrastructure/providers/booking/config.py`.
