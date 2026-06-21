from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.domain.exceptions import CsvParseError, InvalidSourceError, JobNotFoundError, JobNotReadyError


def _handler(status_code: int):
    async def handle(request: Request, exc: Exception) -> JSONResponse:
        return JSONResponse(status_code=status_code, content={"detail": str(exc)})

    return handle


def register_error_handlers(app: FastAPI) -> None:
    """Maps domain exceptions to HTTP responses in one place, so use cases
    can raise plain domain errors without knowing about HTTP status codes.
    """
    app.add_exception_handler(CsvParseError, _handler(400))
    app.add_exception_handler(InvalidSourceError, _handler(400))
    app.add_exception_handler(JobNotFoundError, _handler(404))
    app.add_exception_handler(JobNotReadyError, _handler(409))
