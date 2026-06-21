from typing import Callable

from app.application.ports.hotel_provider import HotelProviderPort
from app.application.ports.result_storage import ResultStoragePort
from app.domain.job import Job

ProviderFactory = Callable[[str], HotelProviderPort]


class RunCrawlJobUseCase:
    """Executes a previously created Job: crawls each requested source in
    turn, recording progress and persisting results as it goes. Intended to
    run as a background task -- the caller already has the Job object back
    from CreateCrawlJobUseCase and doesn't wait on this.
    """

    def __init__(self, provider_factory: ProviderFactory, result_storage: ResultStoragePort):
        self._provider_factory = provider_factory
        self._result_storage = result_storage

    async def execute(self, job: Job) -> None:
        job.mark_running()
        try:
            for source in job.sources:
                provider = self._provider_factory(source)

                def on_progress(done, _total, _result, _source=source):
                    job.record_progress(_source, done)

                results = await provider.crawl_many(job.hotels, on_progress=on_progress)
                job.results[source] = results
                self._result_storage.save(job.id, source, results)
            job.mark_done()
        except Exception as e:
            job.mark_failed(str(e))
