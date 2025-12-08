"""Job Management API for Handwerk.

REST API endpoints for viewing and managing service jobs.
"""
from __future__ import annotations

from datetime import datetime, date
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from itf_shared import get_logger

from phone_agent.db import get_db
from phone_agent.db.repositories import JobRepository, ContactRepository
from phone_agent.db.models.handwerk import JobStatus, JobUrgency

log = get_logger(__name__)

router = APIRouter(prefix="/jobs", tags=["Jobs"])


# ============================================================================
# Request/Response Models
# ============================================================================


class JobListResponse(BaseModel):
    """Response model for job list."""

    jobs: list[dict[str, Any]]
    total: int
    page: int
    page_size: int


class JobStatsResponse(BaseModel):
    """Response model for job statistics."""

    total_jobs: int
    by_status: dict[str, int]
    by_urgency: dict[str, int]
    by_trade: dict[str, int]
    recent_jobs: int  # Last 24 hours


class UpdateJobStatusRequest(BaseModel):
    """Request model for updating job status."""

    status: str = Field(..., description="New status (requested, scheduled, in_progress, completed, cancelled)")
    notes: str | None = Field(None, description="Optional internal notes")


class AssignTechnicianRequest(BaseModel):
    """Request model for assigning technician."""

    technician_id: str = Field(..., description="Technician contact UUID")


# ============================================================================
# Endpoints
# ============================================================================


@router.get("", response_model=JobListResponse)
async def list_jobs(
    status: str | None = Query(None, description="Filter by status"),
    urgency: str | None = Query(None, description="Filter by urgency"),
    trade_category: str | None = Query(None, description="Filter by trade category"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(50, ge=1, le=100, description="Items per page"),
    db: AsyncSession = Depends(get_db),
):
    """List all jobs with optional filters and pagination.

    Args:
        status: Filter by job status
        urgency: Filter by urgency level
        trade_category: Filter by trade category
        page: Page number (1-indexed)
        page_size: Items per page
        db: Database session

    Returns:
        Paginated list of jobs with metadata
    """
    job_repo = JobRepository(db)

    skip = (page - 1) * page_size

    # Get jobs with filters
    if status:
        jobs = await job_repo.get_by_status(
            status=status,
            trade_category=trade_category,
            urgency=urgency,
            skip=skip,
            limit=page_size,
        )
    else:
        jobs = await job_repo.get_multi(skip=skip, limit=page_size)

    # Get total count
    total = await job_repo.count()

    # Convert to dict
    jobs_data = [job.to_dict() for job in jobs]

    return JobListResponse(
        jobs=jobs_data,
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/stats", response_model=JobStatsResponse)
async def get_job_stats(
    db: AsyncSession = Depends(get_db),
):
    """Get job statistics and counts.

    Returns:
        Statistics about jobs by status, urgency, and trade
    """
    job_repo = JobRepository(db)

    # Count by status
    by_status = {}
    for status in [JobStatus.REQUESTED, JobStatus.QUOTED, JobStatus.ACCEPTED,
                   JobStatus.SCHEDULED, JobStatus.IN_PROGRESS, JobStatus.COMPLETED,
                   JobStatus.CANCELLED]:
        count = await job_repo.count_by_status(status)
        if count > 0:
            by_status[status] = count

    # Count by urgency
    by_urgency = {}
    for urgency in [JobUrgency.NOTFALL, JobUrgency.DRINGEND, JobUrgency.NORMAL, JobUrgency.ROUTINE]:
        # Get jobs with this urgency
        jobs = await job_repo.get_multi(limit=1000)
        count = sum(1 for job in jobs if job.urgency == urgency)
        if count > 0:
            by_urgency[urgency] = count

    # Count by trade category
    by_trade = {}
    for trade in ["shk", "elektro", "schlosser", "dachdecker", "maler", "tischler", "allgemein"]:
        count = await job_repo.count_by_trade(trade)
        if count > 0:
            by_trade[trade] = count

    # Count recent jobs (last 24 hours)
    all_jobs = await job_repo.get_multi(limit=1000)
    recent_cutoff = datetime.now().timestamp() - (24 * 60 * 60)
    recent_jobs = sum(1 for job in all_jobs if job.created_at and job.created_at.timestamp() > recent_cutoff)

    total = await job_repo.count()

    return JobStatsResponse(
        total_jobs=total,
        by_status=by_status,
        by_urgency=by_urgency,
        by_trade=by_trade,
        recent_jobs=recent_jobs,
    )


@router.get("/{job_id}")
async def get_job(
    job_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Get detailed information about a specific job.

    Args:
        job_id: Job UUID
        db: Database session

    Returns:
        Job details with contact information

    Raises:
        HTTPException: If job not found
    """
    job_repo = JobRepository(db)

    try:
        job_uuid = UUID(job_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid job ID format")

    job = await job_repo.get(job_uuid)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    return job.to_dict()


@router.get("/number/{job_number}")
async def get_job_by_number(
    job_number: str,
    db: AsyncSession = Depends(get_db),
):
    """Get job by job number (e.g., JOB-2025-0001).

    Args:
        job_number: Human-readable job number
        db: Database session

    Returns:
        Job details

    Raises:
        HTTPException: If job not found
    """
    job_repo = JobRepository(db)

    job = await job_repo.get_by_number(job_number)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    return job.to_dict()


@router.patch("/{job_id}/status")
async def update_job_status(
    job_id: str,
    request: UpdateJobStatusRequest,
    db: AsyncSession = Depends(get_db),
):
    """Update job status.

    Args:
        job_id: Job UUID
        request: Status update request
        db: Database session

    Returns:
        Updated job details

    Raises:
        HTTPException: If job not found or invalid status
    """
    job_repo = JobRepository(db)

    try:
        job_uuid = UUID(job_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid job ID format")

    # Validate status
    valid_statuses = [
        JobStatus.REQUESTED, JobStatus.QUOTED, JobStatus.ACCEPTED,
        JobStatus.SCHEDULED, JobStatus.IN_PROGRESS, JobStatus.COMPLETED,
        JobStatus.CANCELLED, JobStatus.ON_HOLD
    ]
    if request.status not in valid_statuses:
        raise HTTPException(status_code=400, detail=f"Invalid status. Must be one of: {valid_statuses}")

    # Get job
    job = await job_repo.get(job_uuid)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    # Update status
    job.status = request.status

    # Add notes if provided
    if request.notes:
        if job.internal_notes:
            job.internal_notes += f"\n[{datetime.now().isoformat()}] {request.notes}"
        else:
            job.internal_notes = f"[{datetime.now().isoformat()}] {request.notes}"

    # Update timestamps based on status
    if request.status == JobStatus.IN_PROGRESS and not job.started_at:
        job.started_at = datetime.now()
    elif request.status == JobStatus.COMPLETED and not job.completed_at:
        job.completed_at = datetime.now()

    # Save
    await db.commit()
    await db.refresh(job)

    log.info(
        "Job status updated",
        job_id=str(job.id),
        job_number=job.job_number,
        old_status=job.status,
        new_status=request.status,
    )

    return job.to_dict()


@router.patch("/{job_id}/assign")
async def assign_technician(
    job_id: str,
    request: AssignTechnicianRequest,
    db: AsyncSession = Depends(get_db),
):
    """Assign technician to job.

    Args:
        job_id: Job UUID
        request: Technician assignment request
        db: Database session

    Returns:
        Updated job details

    Raises:
        HTTPException: If job or technician not found
    """
    job_repo = JobRepository(db)
    contact_repo = ContactRepository(db)

    try:
        job_uuid = UUID(job_id)
        tech_uuid = UUID(request.technician_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid ID format")

    # Get job
    job = await job_repo.get(job_uuid)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    # Verify technician exists
    technician = await contact_repo.get(tech_uuid)
    if not technician:
        raise HTTPException(status_code=404, detail="Technician not found")

    # Assign
    job.technician_id = tech_uuid
    if job.status == JobStatus.REQUESTED or job.status == JobStatus.ACCEPTED:
        job.status = JobStatus.SCHEDULED

    await db.commit()
    await db.refresh(job)

    log.info(
        "Technician assigned to job",
        job_id=str(job.id),
        job_number=job.job_number,
        technician_id=str(tech_uuid),
    )

    return job.to_dict()


@router.delete("/{job_id}")
async def delete_job(
    job_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Soft delete a job.

    Args:
        job_id: Job UUID
        db: Database session

    Returns:
        Success message

    Raises:
        HTTPException: If job not found
    """
    job_repo = JobRepository(db)

    try:
        job_uuid = UUID(job_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid job ID format")

    job = await job_repo.soft_delete(job_uuid)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    await db.commit()

    log.info("Job deleted", job_id=str(job_uuid), job_number=job.job_number)

    return {"message": "Job deleted successfully", "job_number": job.job_number}
