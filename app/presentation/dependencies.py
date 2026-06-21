from functools import lru_cache

from fastapi import Depends

from app.application.ports.job_repository import JobRepositoryPort
from app.application.use_cases.create_crawl_job import CreateCrawlJobUseCase
from app.application.use_cases.get_job import GetJobUseCase
from app.application.use_cases.get_job_results import GetJobResultsUseCase
from app.application.use_cases.list_jobs import ListJobsUseCase
from app.application.use_cases.run_crawl_job import RunCrawlJobUseCase
from app.infrastructure.config import Settings, get_settings
from app.infrastructure.persistence.in_memory_job_repository import InMemoryJobRepository
from app.infrastructure.providers.registry import available_sources, create_provider
from app.infrastructure.storage.json_result_writer import JsonResultWriter


@lru_cache
def get_job_repository() -> JobRepositoryPort:
    """Process-wide singleton -- see InMemoryJobRepository for why this is
    fine for a single-instance internal tool."""
    return InMemoryJobRepository()


def get_create_crawl_job_use_case(
    job_repository: JobRepositoryPort = Depends(get_job_repository),
) -> CreateCrawlJobUseCase:
    return CreateCrawlJobUseCase(job_repository, available_sources())


def get_run_crawl_job_use_case(
    settings: Settings = Depends(get_settings),
) -> RunCrawlJobUseCase:
    return RunCrawlJobUseCase(
        provider_factory=lambda source: create_provider(source, settings),
        result_storage=JsonResultWriter(settings.output_dir),
    )


def get_get_job_use_case(
    job_repository: JobRepositoryPort = Depends(get_job_repository),
) -> GetJobUseCase:
    return GetJobUseCase(job_repository)


def get_get_job_results_use_case(
    job_repository: JobRepositoryPort = Depends(get_job_repository),
) -> GetJobResultsUseCase:
    return GetJobResultsUseCase(job_repository)


def get_list_jobs_use_case(
    job_repository: JobRepositoryPort = Depends(get_job_repository),
) -> ListJobsUseCase:
    return ListJobsUseCase(job_repository)
