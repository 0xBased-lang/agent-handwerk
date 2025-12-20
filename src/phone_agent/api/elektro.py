"""Elektro-Betrieb API Endpoints.

REST API for the electrician company dashboard:
- Job management with conversation transcripts
- Calendar slot availability
- Dashboard statistics
"""
from __future__ import annotations

from datetime import date
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from itf_shared import get_logger

from phone_agent.db import get_db
from phone_agent.db.repositories import ContactRepository, JobRepository, TranscriptRepository
from phone_agent.services.elektro_service import ElektroService

log = get_logger(__name__)

router = APIRouter(prefix="/elektro", tags=["Elektro-Betrieb"])


# ============================================================================
# Request/Response Models
# ============================================================================


class ConversationTurn(BaseModel):
    """Single conversation turn."""

    role: str = Field(..., description="'user' or 'assistant'")
    content: str = Field(..., description="Message content")
    language: str = Field(default="de", description="Language of this turn")
    timestamp: str | None = Field(default=None, description="ISO timestamp")


class ElektroJobCreateRequest(BaseModel):
    """Request to create an elektro job with conversation."""

    # Customer info
    customer_name: str = Field(..., min_length=1, description="Customer name")
    customer_phone: str | None = Field(default=None, description="Phone number")

    # Address
    address_street: str | None = Field(default=None, description="Street address")
    address_zip: str | None = Field(default=None, description="ZIP code")
    address_city: str | None = Field(default=None, description="City")

    # Job details
    description: str = Field(..., min_length=1, description="Problem description")
    urgency: str = Field(default="normal", description="notfall, dringend, normal, routine")

    # Conversation data
    session_id: str | None = Field(default=None, description="Voice session ID")
    conversation_turns: list[ConversationTurn] | None = Field(
        default=None,
        description="Conversation history"
    )
    detected_language: str = Field(default="de", description="Primary language")

    # Scheduling
    preferred_slot_id: str | None = Field(default=None, description="Selected time slot")


class ElektroJobResponse(BaseModel):
    """Response after creating a job."""

    job_id: str
    job_number: str
    status: str
    contact_id: str
    trade_category: str
    urgency: str
    message: str
    transcript_id: str | None = None
    slot_booked: bool = False


class TimeSlotResponse(BaseModel):
    """Available time slot."""

    id: str
    start: str
    end: str
    provider_name: str
    duration_minutes: int


class DashboardStatsResponse(BaseModel):
    """Dashboard statistics."""

    total_jobs: int
    today_jobs: int
    open_jobs: int
    emergencies: int
    urgent: int
    normal: int
    period_days: int


# ============================================================================
# Dependencies
# ============================================================================


async def get_elektro_service(session=Depends(get_db)) -> ElektroService:
    """Create ElektroService with dependencies."""
    return ElektroService(
        contact_repo=ContactRepository(session),
        job_repo=JobRepository(session),
        transcript_repo=TranscriptRepository(session),
    )


# ============================================================================
# Endpoints
# ============================================================================


@router.get("/slots", response_model=list[TimeSlotResponse])
async def get_available_slots(
    urgency: str = Query(default="normal", description="Urgency level"),
    days_ahead: int = Query(default=7, ge=1, le=30, description="Days to look ahead"),
    service: ElektroService = Depends(get_elektro_service),
):
    """Get available appointment slots.

    Returns slots adjusted for urgency:
    - notfall: Today only, next 3 slots
    - dringend: Today + tomorrow, next 5 slots
    - normal: Next 7 days, next 10 slots
    """
    slots = await service.get_available_slots(
        urgency=urgency,
        days_ahead=days_ahead,
    )
    return slots


@router.get("/slots/formatted")
async def get_slots_formatted(
    urgency: str = Query(default="normal", description="Urgency level"),
    language: str = Query(default="de", description="Response language"),
    service: ElektroService = Depends(get_elektro_service),
):
    """Get available slots formatted for AI to speak.

    Returns a human-readable string of available times.
    """
    text = await service.format_slots_for_ai(urgency=urgency, language=language)
    return {"text": text, "language": language}


@router.post("/jobs", response_model=ElektroJobResponse)
async def create_job(
    request: ElektroJobCreateRequest,
    service: ElektroService = Depends(get_elektro_service),
):
    """Create a new elektro job with conversation transcript.

    Stores the full conversation history linked to the job
    for viewing in the admin dashboard.
    """
    # Build address dict
    address = None
    if request.address_street or request.address_zip or request.address_city:
        address = {
            "street": request.address_street,
            "zip": request.address_zip,
            "city": request.address_city,
        }

    # Convert conversation turns to dicts
    turns = None
    if request.conversation_turns:
        turns = [turn.model_dump() for turn in request.conversation_turns]

    try:
        result = await service.create_job_with_transcript(
            customer_name=request.customer_name,
            description=request.description,
            urgency=request.urgency,
            customer_phone=request.customer_phone,
            address=address,
            session_id=request.session_id,
            conversation_turns=turns,
            detected_language=request.detected_language,
            preferred_slot_id=request.preferred_slot_id,
        )

        return ElektroJobResponse(**result)

    except Exception as e:
        log.error("Failed to create elektro job", error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to create job: {str(e)}")


@router.get("/jobs")
async def list_jobs(
    status: str | None = Query(default=None, description="Filter by status"),
    urgency: str | None = Query(default=None, description="Filter by urgency"),
    limit: int = Query(default=50, ge=1, le=200, description="Max results"),
    offset: int = Query(default=0, ge=0, description="Pagination offset"),
    days_back: int | None = Query(default=30, description="Days to look back"),
    service: ElektroService = Depends(get_elektro_service),
):
    """List elektro jobs for dashboard.

    Returns jobs with customer info and transcript summary.
    """
    jobs = await service.get_jobs_list(
        status=status,
        urgency=urgency,
        limit=limit,
        offset=offset,
        days_back=days_back,
    )
    return {"jobs": jobs, "count": len(jobs)}


@router.get("/jobs/{job_id}")
async def get_job_detail(
    job_id: UUID,
    service: ElektroService = Depends(get_elektro_service),
):
    """Get detailed job information including full transcript."""
    job = await service.get_job_detail(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.get("/jobs/{job_id}/transcript")
async def get_job_transcript(
    job_id: UUID,
    service: ElektroService = Depends(get_elektro_service),
):
    """Get conversation transcript for a job."""
    job = await service.get_job_detail(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if "transcript" not in job or not job["transcript"]:
        raise HTTPException(status_code=404, detail="No transcript for this job")

    return job["transcript"]


@router.get("/stats", response_model=DashboardStatsResponse)
async def get_dashboard_stats(
    days_back: int = Query(default=7, ge=1, le=90, description="Stats period in days"),
    service: ElektroService = Depends(get_elektro_service),
):
    """Get dashboard statistics.

    Returns KPIs for the elektro dashboard:
    - Total jobs
    - Today's jobs
    - Open jobs (not completed)
    - Emergencies count
    """
    stats = await service.get_dashboard_stats(days_back=days_back)
    return DashboardStatsResponse(**stats)


@router.get("/calendar")
async def get_calendar_view(
    start_date: date | None = Query(default=None, description="Start date"),
    end_date: date | None = Query(default=None, description="End date"),
    service: ElektroService = Depends(get_elektro_service),
):
    """Get calendar view data for scheduled jobs.

    Returns jobs grouped by date for calendar display.
    """
    # Default to current week
    from datetime import timedelta
    today = date.today()
    if not start_date:
        start_date = today - timedelta(days=today.weekday())  # Monday
    if not end_date:
        end_date = start_date + timedelta(days=6)  # Sunday

    # Get scheduled jobs
    jobs = await service.get_jobs_list(
        status="scheduled",
        days_back=None,  # Get all
        limit=200,
    )

    # Group by date
    calendar = {}
    for job in jobs:
        scheduled_date = job.get("scheduled_date")
        if scheduled_date:
            if scheduled_date not in calendar:
                calendar[scheduled_date] = []
            calendar[scheduled_date].append(job)

    return {
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "calendar": calendar,
    }
