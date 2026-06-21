from app.application.ports.job_repository import JobRepositoryPort
from app.domain.exceptions import JobNotFoundError
from app.domain.job import Job


class GetJobUseCase:
    def __init__(self, job_repository: JobRepositoryPort):
        self._job_repository = job_repository

    def execute(self, job_id: str) -> Job:
        job = self._job_repository.get(job_id)
        if job is None:
            raise JobNotFoundError(f"Job '{job_id}' not found.")
        return job
