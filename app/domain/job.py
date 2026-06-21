from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional

from .entities import HotelQuery, HotelResult
from .enums import JobStatus


@dataclass
class JobProgress:
    done: int = 0
    total: int = 0


@dataclass
class Job:
    """A crawl request: a list of hotels to look up across one or more
    sources, tracked from submission through completion.
    """

    id: str
    sources: List[str]
    hotels: List[HotelQuery]
    status: JobStatus = JobStatus.PENDING
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    progress: Dict[str, JobProgress] = field(default_factory=dict)
    results: Dict[str, List[HotelResult]] = field(default_factory=dict)
    error: Optional[str] = None

    def __post_init__(self):
        if not self.progress:
            self.progress = {source: JobProgress(total=len(self.hotels)) for source in self.sources}

    def mark_running(self) -> None:
        self.status = JobStatus.RUNNING

    def mark_done(self) -> None:
        self.status = JobStatus.DONE

    def mark_failed(self, error: str) -> None:
        self.status = JobStatus.FAILED
        self.error = error

    def record_progress(self, source: str, done: int) -> None:
        self.progress[source].done = done

    def is_ready(self) -> bool:
        return self.status in (JobStatus.DONE, JobStatus.FAILED)
