import logging

from fastapi import FastAPI

from app.presentation.error_handlers import register_error_handlers
from app.presentation.routers import api_router


def create_app() -> FastAPI:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    app = FastAPI(
        title="Hotel Crawler API",
        description=(
            "Upload a CSV (name, address columns) to crawl hotel data from "
            "Traveloka, TripAdvisor, and Booking.com behind one common interface."
        ),
        version="2.0.0",
    )
    register_error_handlers(app)
    app.include_router(api_router)
    return app


app = create_app()
