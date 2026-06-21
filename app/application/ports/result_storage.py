from abc import ABC, abstractmethod
from typing import List

from app.domain.entities import HotelResult


class ResultStoragePort(ABC):
    """Persists a job's per-source results somewhere durable (disk, object
    storage, ...) so they outlive the in-memory job record.
    """

    @abstractmethod
    def save(self, job_id: str, source: str, results: List[HotelResult]) -> None: ...
