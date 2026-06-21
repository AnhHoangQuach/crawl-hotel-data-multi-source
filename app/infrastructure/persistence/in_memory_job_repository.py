from typing import Dict, List, Optional

from app.application.ports.job_repository import JobRepositoryPort
from app.domain.job import Job


class InMemoryJobRepository(JobRepositoryPort):
    """Process-local job store. Fine for a single-instance internal tool --
    job metadata is lost on restart, but completed results are also written
    to disk (see infrastructure/storage) so they survive independently.
    """

    def __init__(self):
        self._jobs: Dict[str, Job] = {}

    def add(self, job: Job) -> None:
        self._jobs[job.id] = job

    def get(self, job_id: str) -> Optional[Job]:
        return self._jobs.get(job_id)

    def list(self) -> List[Job]:
        return sorted(self._jobs.values(), key=lambda j: j.created_at, reverse=True)
