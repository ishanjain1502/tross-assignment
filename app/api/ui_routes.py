"""Unauthenticated UI proxy routes for local dev frontend.

Uses the server-side API key via JobService — the browser never sees credentials.
"""

from fastapi import APIRouter, Depends, HTTPException, status

from app.models.requests import ScrapeRequest
from app.models.responses import (
    JobAcceptedResponse,
    JobCompletedResponse,
    JobErrorResponse,
    JobStatusResponse,
)
from app.dependencies import get_db
from app.services.job_service import JobService

router = APIRouter(prefix="/ui", tags=["ui"])


@router.post(
    "/scrape",
    response_model=JobAcceptedResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def ui_create_scrape_job(
    request: ScrapeRequest,
    db=Depends(get_db),
):
    """Submit a LinkedIn profile URL for scraping (local UI proxy)."""
    job_service = JobService()
    job_id = await job_service.create(
        db,
        url=request.profile_url,
        webhook_url=request.webhook_url,
        include_fields=request.include_fields,
    )
    queue_depth = await job_service.get_queue_depth(db)
    return JobAcceptedResponse(
        job_id=job_id,
        status="queued",
        estimated_wait_seconds=queue_depth * 5,
        poll_url=f"/api/v1/ui/scrape/{job_id}",
    )


@router.get("/scrape/{job_id}")
async def ui_get_scrape_status(
    job_id: str,
    db=Depends(get_db),
):
    """Poll job status or retrieve results (local UI proxy)."""
    job_service = JobService()
    job = await job_service.get(db, job_id)
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": {
                    "code": "JOB_NOT_FOUND",
                    "message": f"Job {job_id} not found",
                }
            },
        )

    job_dict = job_service.to_dict(job)

    if job.status == "completed":
        return JobCompletedResponse(
            job_id=job.id,
            status=job.status,
            duration_ms=job.duration_ms or 0,
            data=job.result or {},
            scraped_at=job_dict.get("updated_at"),
            from_cache=job.from_cache or False,
        )
    if job.status == "failed":
        return JobErrorResponse(
            job_id=job.id,
            status=job.status,
            error={
                "code": job.error_code or "UNKNOWN",
                "message": job.error_message or "Unknown error",
            },
        )
    return JobStatusResponse(
        job_id=job.id,
        status=job.status,
        created_at=job_dict.get("created_at"),
    )
