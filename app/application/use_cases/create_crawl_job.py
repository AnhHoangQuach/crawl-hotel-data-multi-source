import uuid
from typing import List

from app.application.ports.job_repository import JobRepositoryPort
from app.application.services.csv_parser import parse_hotel_queries
from app.application.services.source_resolver import resolve_sources
from app.domain.exceptions import CsvParseError
from app.domain.job import Job


class CreateCrawlJobUseCase:
    """Parses the uploaded CSV, validates the requested sources, and
    registers a new (not-yet-started) Job. Running the job is a separate
    use case (RunCrawlJobUseCase) so the API can return immediately and
    schedule the crawl in the background.
    """

    def __init__(self, job_repository: JobRepositoryPort, available_sources: List[str]):
        self._job_repository = job_repository
        self._available_sources = available_sources

    def execute(self, csv_text: str, source: str) -> Job:
        hotels = parse_hotel_queries(csv_text)
        if not hotels:
            raise CsvParseError("The CSV does not contain any hotel to crawl.")

        sources = resolve_sources(source, self._available_sources)

        job = Job(id=uuid.uuid4().hex, sources=sources, hotels=hotels)
        self._job_repository.add(job)
        return job
