import asyncio
from typing import List

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from app.application.use_cases.create_crawl_job import CreateCrawlJobUseCase
from app.application.use_cases.get_job import GetJobUseCase
from app.application.use_cases.get_job_results import GetJobResultsUseCase
from app.application.use_cases.list_jobs import ListJobsUseCase
from app.application.use_cases.run_crawl_job import RunCrawlJobUseCase

from ..dependencies import (
    get_create_crawl_job_use_case,
    get_get_job_results_use_case,
    get_get_job_use_case,
    get_list_jobs_use_case,
    get_run_crawl_job_use_case,
)
from ..mappers import job_to_results, job_to_summary
from ..schemas import JobResultsResponse, JobSummaryResponse

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.post("", response_model=JobSummaryResponse, status_code=201)
async def create_job(
    file: UploadFile = File(..., description="CSV file with 'name' and 'address' columns"),
    source: str = Form("all", description="Source name(s), comma-separated, or 'all' (default)"),
    create_use_case: CreateCrawlJobUseCase = Depends(get_create_crawl_job_use_case),
    run_use_case: RunCrawlJobUseCase = Depends(get_run_crawl_job_use_case),
):
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(400, "File must have a .csv extension")

    raw = await file.read()
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise HTTPException(400, "CSV file must be UTF-8 encoded")

    # May raise CsvParseError / InvalidSourceError -- mapped to HTTP 400 by
    # the global handlers in app.presentation.error_handlers.
    job = create_use_case.execute(text, source)

    asyncio.create_task(run_use_case.execute(job))
    return job_to_summary(job)


@router.get("", response_model=List[JobSummaryResponse])
async def list_jobs(use_case: ListJobsUseCase = Depends(get_list_jobs_use_case)):
    return [job_to_summary(job) for job in use_case.execute()]


@router.get("/{job_id}", response_model=JobSummaryResponse)
async def get_job(job_id: str, use_case: GetJobUseCase = Depends(get_get_job_use_case)):
    # May raise JobNotFoundError -- mapped to HTTP 404 globally.
    job = use_case.execute(job_id)
    return job_to_summary(job)


@router.get("/{job_id}/results", response_model=JobResultsResponse)
async def get_job_results(
    job_id: str, use_case: GetJobResultsUseCase = Depends(get_get_job_results_use_case)
):
    # May raise JobNotFoundError (404) / JobNotReadyError (409) -- mapped globally.
    job = use_case.execute(job_id)
    return job_to_results(job)
