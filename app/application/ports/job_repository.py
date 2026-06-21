from abc import ABC, abstractmethod
from typing import List, Optional

from app.domain.job import Job


class JobRepositoryPort(ABC):
    """Storage contract for crawl jobs. Use cases depend on this port, not
    on the concrete (in-memory, DB, ...) implementation.
    """

    @abstractmethod
    def add(self, job: Job) -> None: ...

    @abstractmethod
    def get(self, job_id: str) -> Optional[Job]: ...

    @abstractmethod
    def list(self) -> List[Job]: ...
