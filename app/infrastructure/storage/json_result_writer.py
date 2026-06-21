import json
import os
from typing import List

from app.application.ports.result_storage import ResultStoragePort
from app.domain.entities import HotelResult


class JsonResultWriter(ResultStoragePort):
    """Writes each source's results to OUTPUT_DIR/<job_id>/hotels_result_<source>.json."""

    def __init__(self, output_dir: str):
        self._output_dir = output_dir

    def save(self, job_id: str, source: str, results: List[HotelResult]) -> None:
        job_dir = os.path.join(self._output_dir, job_id)
        os.makedirs(job_dir, exist_ok=True)
        path = os.path.join(job_dir, f"hotels_result_{source}.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump([r.to_dict() for r in results], f, ensure_ascii=False, indent=2)
