from app.application.ports.job_repository import JobRepositoryPort
from app.domain.exceptions import JobNotFoundError, JobNotReadyError
from app.domain.job import Job


class GetJobResultsUseCase:
    def __init__(self, job_repository: JobRepositoryPort):
        self._job_repository = job_repository

    def execute(self, job_id: str) -> Job:
        job = self._job_repository.get(job_id)
        if job is None:
            raise JobNotFoundError(f"Job '{job_id}' not found.")
        if not job.is_ready():
            raise JobNotReadyError(f"Job '{job_id}' is still '{job.status.value}'.")
        return job
