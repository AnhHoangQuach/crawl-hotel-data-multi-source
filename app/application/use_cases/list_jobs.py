from typing import List

from app.application.ports.job_repository import JobRepositoryPort
from app.domain.job import Job


class ListJobsUseCase:
    def __init__(self, job_repository: JobRepositoryPort):
        self._job_repository = job_repository

    def execute(self) -> List[Job]:
        return self._job_repository.list()
