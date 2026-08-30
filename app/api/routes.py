from fastapi import APIRouter, Depends, HTTPException, status
from typing import Optional

from app.models.requests import ScrapeRequest
from app.models.responses import (
    JobAcceptedResponse,
    JobStatusResponse,
    JobCompletedResponse,
    JobErrorResponse,
    ErrorResponse,
)
from app.dependencies import get_db, verify_api_key
from app.services.job_service import JobService

router = APIRouter(tags=["scrape"])

@router.post(
    "/scrape",
    response_model=JobAcceptedResponse,
    status_code=status.HTTP_202_ACCEPTED,
    responses={
        400: {"model": ErrorResponse, "description": "Invalid request"},
        401: {"model": ErrorResponse, "description": "Invalid API key"},
        429: {"model": ErrorResponse, "description": "Rate limited"},
        503: {"model": ErrorResponse, "description": "Service unavailable"},
    }
)
async def create_scrape_job(
    request: ScrapeRequest,
    db=Depends(get_db),
    api_key: str = Depends(verify_api_key)
):
    """Submit a LinkedIn profile URL for scraping"""
    job_service = JobService()
    
    # Create job
    job_id = await job_service.create(
        db,
        url=request.profile_url,
        webhook_url=request.webhook_url,
        include_fields=request.include_fields
    )
    
    # Get estimated wait time
    queue_depth = await job_service.get_queue_depth(db)
    estimated_wait = queue_depth * 5  # ~5 seconds per job estimate
    
    return JobAcceptedResponse(
        job_id=job_id,
        status="queued",
        estimated_wait_seconds=estimated_wait,
        poll_url=f"/api/v1/scrape/{job_id}"
    )

@router.get(
    "/scrape/{job_id}",
    responses={
        200: {"description": "Job status or result"},
        401: {"model": ErrorResponse, "description": "Invalid API key"},
        404: {"model": ErrorResponse, "description": "Job not found"},
    }
)
async def get_scrape_status(
    job_id: str,
    db=Depends(get_db),
    api_key: str = Depends(verify_api_key)
):
    """Get the status and result of a scrape job"""
    job_service = JobService()
    
    job = await job_service.get(db, job_id)
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "JOB_NOT_FOUND", "message": f"Job {job_id} not found"}}
        )
    
    job_dict = job_service.to_dict(job)
    
    if job.status == "completed":
        return JobCompletedResponse(
            job_id=job.id,
            status=job.status,
            duration_ms=job.duration_ms or 0,
            data=job.result or {},
            scraped_at=job_dict.get("updated_at"),
            from_cache=job.from_cache or False
        )
    elif job.status == "failed":
        return JobErrorResponse(
            job_id=job.id,
            status=job.status,
            error={
                "code": job.error_code or "UNKNOWN",
                "message": job.error_message or "Unknown error"
            }
        )
    else:
        return JobStatusResponse(
            job_id=job.id,
            status=job.status,
            created_at=job_dict.get("created_at")
        )
