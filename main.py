import uvicorn

from app.infrastructure.config import get_settings


def main():
    settings = get_settings()
    uvicorn.run("app.app_factory:app", host=settings.host, port=settings.port)


if __name__ == "__main__":
    main()
