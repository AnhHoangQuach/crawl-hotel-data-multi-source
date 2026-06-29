from abc import ABC, abstractmethod
from typing import List

from app.domain.entities import HotelResult


class ResultStoragePort(ABC):
    """Persists a crawl request's per-source results somewhere durable
    (disk, object storage, ...) for debugging/archival.
    """

    @abstractmethod
    def save(self, request_id: str, source: str, results: List[HotelResult]) -> None: ...
