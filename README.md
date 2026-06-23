# crawl-traveloka

A FastAPI service that crawls hotel details from multiple sources, given a list of hotels (name + address) uploaded as a CSV:

- **Traveloka** — crawled directly via Playwright/crawl4ai (no API key needed).
- **Booking.com** — crawled directly via Playwright/crawl4ai (no API key needed).

Every source implements the same **provider interface** (`HotelProviderPort`) and produces the same **result schema** (`HotelResult`), so jobs can run one or several sources at once and results can be compared/merged easily.

Crawling is triggered through the **API**: upload a CSV, the server creates a background **job**, you poll its status, then fetch the JSON results once it's done.

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

See "Using the API" below for how to submit a crawl job. Full setup details (CSV format, plain `docker build`/`docker run`) are further down.

## Architecture

The codebase follows a layered (clean) architecture, with dependencies pointing inward (presentation → application → domain; infrastructure implements application's ports):

```
app/
  domain/                  Framework-free business model
    entities.py             HotelQuery, HotelResult
    job.py                   Job, JobProgress
    enums.py                  JobStatus
    exceptions.py              DomainError and subtypes

  application/             Use cases + the ports infrastructure must implement
    ports/
      hotel_provider.py      HotelProviderPort (contract every source implements)
      job_repository.py       JobRepositoryPort (contract job storage implements)
      result_storage.py        ResultStoragePort (contract result persistence implements)
    services/
      csv_parser.py            parse uploaded CSV text into HotelQuery list
      fuzzy_matcher.py          name/address matching shared by every provider
      source_resolver.py        validate a requested source string against available providers
    use_cases/
      create_crawl_job.py      parse CSV, validate sources, register a Job
      run_crawl_job.py           execute a Job's crawl across its sources
      get_job.py / get_job_results.py / list_jobs.py

  infrastructure/          Concrete adapters for the ports above
    config.py                Settings (env vars / .env), single source of config
    persistence/
      in_memory_job_repository.py
    storage/
      json_result_writer.py    writes results to output/<job_id>/hotels_result_<source>.json
    providers/
      base.py                  BaseHotelProvider: shared crawl loop (retry, rate-limit, progress)
      registry.py               source name -> provider class
      traveloka/                 Playwright/crawl4ai scraper
      booking/                     Playwright/crawl4ai scraper

  presentation/             FastAPI-specific wiring
    schemas.py                Pydantic request/response DTOs
    mappers.py                  domain entities -> DTOs
    dependencies.py              FastAPI Depends() wiring (DI)
    error_handlers.py             maps domain exceptions to HTTP responses
    routers/
      health.py
      jobs.py

  app_factory.py            FastAPI app factory (create_app())

main.py                     entrypoint: runs uvicorn
```

### Adding a new source

1. Create `app/infrastructure/providers/<name>/provider.py` with a class extending `BaseHotelProvider`.
2. Implement `async def fetch_one(self, query: HotelQuery) -> HotelResult`, starting from `HotelResult.empty(query, "<name>")`.
3. Register the class in `PROVIDER_REGISTRY` in `app/infrastructure/providers/registry.py`.

`BaseHotelProvider` already handles iterating the hotel list, normalizing errors into a `HotelResult`, rate-limiting, logging, and progress reporting — a new provider only needs to fetch data for one hotel. No other layer needs to change.

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

### 1. Create a crawl job (upload a CSV)

The CSV needs a `name` column; `address` is optional but improves matching when multiple hotels share a name. An optional `id` column (e.g. your own staging-table row id) is carried through to `query_id` in the results, so you can correlate them back without relying on name matching (sample: `hotels.csv`):

```csv
id,name,address
84110,Muong Thanh Luxury Phu Quoc Hotel,"Kien Giang"
84112,THE SEA PHÚ QUỐC,"Kien Giang"
```

```bash
curl -X POST http://localhost:8000/jobs \
  -F "file=@hotels.csv" \
  -F "source=traveloka"          # or: "traveloka,booking" / "all" (default if omitted)
```

Response:

```json
{
  "job_id": "a1b2c3...",
  "status": "pending",
  "sources": ["traveloka"],
  "total_hotels": 2,
  "created_at": "2026-06-22T08:00:00+00:00",
  "progress": {"traveloka": {"done": 0, "total": 2}},
  "error": null
}
```

### 2. Poll job progress

```bash
curl http://localhost:8000/jobs/a1b2c3...
```

`status` moves through `pending` -> `running` -> `done` (or `failed`). `progress` shows how many hotels have been crawled per source.

### 3. Fetch results

```bash
curl http://localhost:8000/jobs/a1b2c3.../results
```

Returns `{"job_id": ..., "status": "done", "results": {"traveloka": [...], "booking": [...]}}` — each item follows the schema described below. Calling this before the job is done returns `409`.

### Other endpoints

| Method | Path | Description |
|---|---|---|
| GET | `/health` | health check |
| GET | `/sources` | list of supported source names |
| GET | `/jobs` | list all jobs (newest first) |
| GET | `/jobs/{job_id}` | one job's status + progress |
| GET | `/jobs/{job_id}/results` | one job's crawl results |

Each job's results are also written to `output/<job_id>/hotels_result_<source>.json` for debugging/archival. The in-memory job list is lost on server restart, but those files persist independently.

## Result schema (shared by every source)

Each item in `results.<source>` is an object:

| Field | Meaning |
|---|---|
| `source` | data source: `traveloka` / `booking` |
| `query_id`, `query_name`, `query_address` | original input from the CSV (`query_id` is `null` if the CSV had no `id` column) |
| `match_score` | similarity (0-1) between the input and the matched hotel |
| `name`, `accommodation_type`, `star_rating` | name, property type, star rating |
| `rating_summary` | review score + review count, exported as cleaned summary parts (for example `["8.6/10", "Very Good", "143 reviews"]`) |
| `address`, `latitude`, `longitude` | cleaned primary address string and coordinates |
| `amenities`, `facilities`, `description` | amenities/facilities are arrays of cleaned items; description is an array of cleaned paragraphs |
| `photos` | list of photo URLs |
| `reviews` | list of reviews; each review is an array of meaningful cleaned text parts |
| `rooms` | available rooms: name, bed type, breakfast, price, rooms left, cancellation policy |
| `detail_url`, `error` | detail page URL, error message if the crawl failed |
| `low_confidence` | `true` if the match score was too low — the result may be the wrong hotel |

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

The image is built on `python:3.12-slim` and runs `crawl4ai-setup` at build time to install Playwright/Chromium plus the required OS dependencies. The container runs a single uvicorn worker — see "Known limitations" below for why.

## Known limitations

- **Job store**: kept in the server process's memory, lost on restart. This also means **don't run more than one worker/replica** (e.g. `uvicorn --workers N>1`, multiple compose replicas) — each process would have its own job list, so polling a job created on a different worker would 404. Fine for a single-instance internal tool; if you need multiple instances or long-lived job history, swap `InMemoryJobRepository` for a DB/Redis-backed `JobRepositoryPort` implementation — not needed yet given the current scale.
- **Traveloka**: reviews are capped at `MAX_REVIEW_PAGES` pages (5 by default) — a large sample, not every review. `rooms` is empty if the hotel has no availability for the default search dates (tomorrow/day after). Traveloka can change its page structure at any time — if the scraper stops finding data, check the selectors in `app/infrastructure/providers/traveloka/config.py`.
- **Booking.com**: room/price data is currently empty because it requires reliable date-picker interaction. Booking.com can change its page structure at any time — if the scraper stops finding data, check the selectors in `app/infrastructure/providers/booking/config.py`.
