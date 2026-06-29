from fastapi import Depends

from app.application.use_cases.crawl_hotels import CrawlHotelsUseCase
from app.infrastructure.config import Settings, get_settings
from app.infrastructure.providers.registry import available_sources, create_provider
from app.infrastructure.storage.json_result_writer import JsonResultWriter


def get_crawl_hotels_use_case(
    settings: Settings = Depends(get_settings),
) -> CrawlHotelsUseCase:
    return CrawlHotelsUseCase(
        provider_factory=lambda source: create_provider(source, settings),
        result_storage=JsonResultWriter(settings.output_dir),
        available_sources=available_sources(),
    )
