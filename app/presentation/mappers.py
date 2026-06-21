from app.domain.job import Job

from .schemas import HotelResultResponse, JobProgressResponse, JobResultsResponse, JobSummaryResponse


def job_to_summary(job: Job) -> JobSummaryResponse:
    return JobSummaryResponse(
        job_id=job.id,
        status=job.status.value,
        sources=job.sources,
        total_hotels=len(job.hotels),
        created_at=job.created_at.isoformat(),
        progress={
            source: JobProgressResponse(done=p.done, total=p.total) for source, p in job.progress.items()
        },
        error=job.error,
    )


def job_to_results(job: Job) -> JobResultsResponse:
    return JobResultsResponse(
        job_id=job.id,
        status=job.status.value,
        results={
            source: [HotelResultResponse(**r.to_dict()) for r in results]
            for source, results in job.results.items()
        },
    )
