FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements.txt .
# crawl4ai-setup installs Playwright/Patchright Chromium plus all required
# OS-level deps (apt) and initializes crawl4ai's local db/cache dirs -- this
# is the officially supported post-install step, safer than hand-rolling
# `playwright install` against a base image that may not match the exact
# Playwright version crawl4ai pins.
RUN pip install -r requirements.txt && crawl4ai-setup

COPY . .

EXPOSE 8000

# Single worker only: job state lives in an in-memory repository
# (app/infrastructure/persistence/in_memory_job_repository.py), so a second
# worker process would not see jobs created on the first one.
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"

CMD ["uvicorn", "app.app_factory:app", "--host", "0.0.0.0", "--port", "8000"]
