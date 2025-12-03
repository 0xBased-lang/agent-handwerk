"""Outbound calling API endpoints for Healthcare.

Endpoints for:
- Appointment reminder campaigns
- Recall campaign calling
- No-show follow-up
- Dialer control (pause/resume/status)
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, BackgroundTasks
from pydantic import BaseModel, Field

from phone_agent.industry.gesundheit.outbound import (
    OutboundDialer,
    DialerStatus,
    CallPriority,
    get_outbound_dialer,
    AppointmentReminderWorkflow,
    ReminderCampaignConfig,
    create_reminder_workflow,
    RecallCampaignWorkflow,
    create_recall_workflow,
    NoShowFollowupWorkflow,
    NoShowConfig,
    create_noshow_workflow,
)
from phone_agent.industry.gesundheit.recall import RecallType, get_recall_service


router = APIRouter(prefix="/outbound")


# ============ REQUEST/RESPONSE MODELS ============


class ReminderCampaignRequest(BaseModel):
    """Request model for starting a reminder campaign."""

    target_date: str | None = Field(
        default=None,
        description="Target date for appointments (YYYY-MM-DD). Defaults to tomorrow.",
    )
    appointment_types: list[str] | None = Field(
        default=None,
        description="Filter by appointment types (acute, regular, followup, etc.)",
    )
    reminder_hours_before: int = Field(
        default=24,
        ge=2,
        le=72,
        description="Hours before appointment to start reminders",
    )
    practice_name: str = Field(
        default="Ihre Arztpraxis",
        description="Practice name for scripts",
    )
    sms_enabled: bool = Field(default=True, description="Enable SMS confirmation")


class ReminderStatsResponse(BaseModel):
    """Response model for reminder campaign statistics."""

    total_appointments: int
    reminders_sent: int
    confirmed: int
    rescheduled: int
    cancelled: int
    no_answer: int
    declined: int
    confirmation_rate: float
    no_show_prevention_rate: float
    started_at: str
    completed_at: str | None


class RecallStartRequest(BaseModel):
    """Request model for starting recall campaign calling."""

    campaign_id: str = Field(..., description="UUID of the recall campaign")
    max_calls: int | None = Field(
        default=None,
        ge=1,
        le=1000,
        description="Maximum calls to queue (for batching)",
    )
    practice_name: str = Field(
        default="Ihre Arztpraxis",
        description="Practice name for scripts",
    )


class RecallStatsResponse(BaseModel):
    """Response model for recall campaign statistics."""

    campaign_id: str
    campaign_name: str
    recall_type: str
    total_patients: int
    calls_attempted: int
    appointments_made: int
    declined: int
    unreachable: int
    pending: int
    success_rate: float
    contact_rate: float
    started_at: str
    completed_at: str | None


class NoShowProcessRequest(BaseModel):
    """Request model for processing no-shows."""

    target_date: str | None = Field(
        default=None,
        description="Date to check for no-shows (YYYY-MM-DD). Defaults to yesterday.",
    )
    min_hours_after: float = Field(
        default=0.5,
        ge=0,
        description="Minimum hours after missed appointment to start calling",
    )
    max_hours_after: float = Field(
        default=72,
        description="Maximum hours after which not to call",
    )


class NoShowStatsResponse(BaseModel):
    """Response model for no-show follow-up statistics."""

    total_missed: int
    calls_attempted: int
    rescheduled: int
    declined: int
    unreachable: int
    barriers_identified: int
    needs_followup: int
    reschedule_rate: float
    started_at: str
    completed_at: str | None


class DialerStatusResponse(BaseModel):
    """Response model for dialer status."""

    status: str
    queue_size: int
    active_calls: int
    completed_today: int
    business_hours_active: bool
    next_business_start: str | None


class QueuedCallResponse(BaseModel):
    """Response model for a queued call."""

    id: str
    patient_id: str
    phone_number: str
    call_type: str
    priority: str
    queued_at: str
    metadata: dict[str, Any]


# ============ WORKFLOW SINGLETONS ============

_reminder_workflow: AppointmentReminderWorkflow | None = None
_recall_workflow: RecallCampaignWorkflow | None = None
_noshow_workflow: NoShowFollowupWorkflow | None = None


def get_reminder_workflow() -> AppointmentReminderWorkflow:
    """Get or create reminder workflow singleton."""
    global _reminder_workflow
    if _reminder_workflow is None:
        dialer = get_outbound_dialer()
        _reminder_workflow = create_reminder_workflow(dialer)
    return _reminder_workflow


def get_recall_workflow() -> RecallCampaignWorkflow:
    """Get or create recall workflow singleton."""
    global _recall_workflow
    if _recall_workflow is None:
        dialer = get_outbound_dialer()
        _recall_workflow = create_recall_workflow(dialer)
    return _recall_workflow


def get_noshow_workflow() -> NoShowFollowupWorkflow:
    """Get or create no-show workflow singleton."""
    global _noshow_workflow
    if _noshow_workflow is None:
        dialer = get_outbound_dialer()
        _noshow_workflow = create_noshow_workflow(dialer)
    return _noshow_workflow


# ============ REMINDER ENDPOINTS ============


@router.post("/reminder-campaign", response_model=ReminderStatsResponse)
async def start_reminder_campaign(
    request: ReminderCampaignRequest,
    background_tasks: BackgroundTasks,
) -> ReminderStatsResponse:
    """
    Start an appointment reminder campaign.

    Calls patients with appointments on the target date to confirm,
    reschedule, or cancel. Sends SMS confirmations after successful calls.

    The campaign runs in the background - check /reminder-campaign/stats for progress.
    """
    workflow = get_reminder_workflow()

    # Parse target date
    target_date = None
    if request.target_date:
        try:
            target_date = date.fromisoformat(request.target_date)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid date format: {request.target_date}. Use YYYY-MM-DD.",
            )

    # Parse appointment types
    from phone_agent.industry.gesundheit.scheduling import AppointmentType

    appointment_types = None
    if request.appointment_types:
        try:
            appointment_types = [AppointmentType(t) for t in request.appointment_types]
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

    # Update workflow config
    workflow._config.reminder_hours_before = request.reminder_hours_before
    workflow._config.practice_name = request.practice_name
    workflow._config.sms_enabled = request.sms_enabled

    # Start campaign
    stats = await workflow.start_campaign(
        target_date=target_date,
        appointment_types=appointment_types,
    )

    return ReminderStatsResponse(
        total_appointments=stats.total_appointments,
        reminders_sent=stats.reminders_sent,
        confirmed=stats.confirmed,
        rescheduled=stats.rescheduled,
        cancelled=stats.cancelled,
        no_answer=stats.no_answer,
        declined=stats.declined,
        confirmation_rate=stats.confirmation_rate,
        no_show_prevention_rate=stats.no_show_prevention_rate,
        started_at=stats.started_at.isoformat(),
        completed_at=stats.completed_at.isoformat() if stats.completed_at else None,
    )


@router.get("/reminder-campaign/stats", response_model=ReminderStatsResponse)
async def get_reminder_stats() -> ReminderStatsResponse:
    """Get current reminder campaign statistics."""
    workflow = get_reminder_workflow()
    stats = workflow.get_stats()

    return ReminderStatsResponse(
        total_appointments=stats.total_appointments,
        reminders_sent=stats.reminders_sent,
        confirmed=stats.confirmed,
        rescheduled=stats.rescheduled,
        cancelled=stats.cancelled,
        no_answer=stats.no_answer,
        declined=stats.declined,
        confirmation_rate=stats.confirmation_rate,
        no_show_prevention_rate=stats.no_show_prevention_rate,
        started_at=stats.started_at.isoformat(),
        completed_at=stats.completed_at.isoformat() if stats.completed_at else None,
    )


@router.get("/reminder-campaign/tasks")
async def get_reminder_tasks() -> list[dict[str, Any]]:
    """Get all reminder tasks with their current status."""
    workflow = get_reminder_workflow()
    return [task.to_dict() for task in workflow.get_all_tasks()]


# ============ RECALL CALLING ENDPOINTS ============


@router.post("/recall/{campaign_id}/start", response_model=RecallStatsResponse)
async def start_recall_calling(
    campaign_id: str,
    request: RecallStartRequest | None = None,
) -> RecallStatsResponse:
    """
    Start outbound calling for a recall campaign.

    Uses the campaign's configured phone scripts and contact methods.
    Calls are queued with priority based on patient urgency.

    The campaign runs in the background - check /recall/{campaign_id}/stats for progress.
    """
    workflow = get_recall_workflow()

    # Validate campaign exists
    recall_service = get_recall_service()
    try:
        campaign_uuid = UUID(campaign_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid campaign ID format")

    if campaign_uuid not in recall_service._campaigns:
        raise HTTPException(status_code=404, detail=f"Campaign {campaign_id} not found")

    # Update practice name if provided
    if request and request.practice_name:
        workflow._practice_name = request.practice_name

    max_calls = request.max_calls if request else None

    # Start campaign calling
    try:
        stats = await workflow.start_campaign(
            campaign_id=campaign_uuid,
            max_calls=max_calls,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return RecallStatsResponse(
        campaign_id=str(stats.campaign_id),
        campaign_name=stats.campaign_name,
        recall_type=stats.recall_type.value,
        total_patients=stats.total_patients,
        calls_attempted=stats.calls_attempted,
        appointments_made=stats.appointments_made,
        declined=stats.declined,
        unreachable=stats.unreachable,
        pending=stats.pending,
        success_rate=stats.success_rate,
        contact_rate=stats.contact_rate,
        started_at=stats.started_at.isoformat(),
        completed_at=stats.completed_at.isoformat() if stats.completed_at else None,
    )


@router.get("/recall/{campaign_id}/stats", response_model=RecallStatsResponse | None)
async def get_recall_calling_stats(campaign_id: str) -> RecallStatsResponse | None:
    """Get statistics for recall campaign calling."""
    workflow = get_recall_workflow()

    try:
        campaign_uuid = UUID(campaign_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid campaign ID format")

    stats = workflow.get_campaign_stats(campaign_uuid)
    if not stats:
        return None

    return RecallStatsResponse(
        campaign_id=str(stats.campaign_id),
        campaign_name=stats.campaign_name,
        recall_type=stats.recall_type.value,
        total_patients=stats.total_patients,
        calls_attempted=stats.calls_attempted,
        appointments_made=stats.appointments_made,
        declined=stats.declined,
        unreachable=stats.unreachable,
        pending=stats.pending,
        success_rate=stats.success_rate,
        contact_rate=stats.contact_rate,
        started_at=stats.started_at.isoformat(),
        completed_at=stats.completed_at.isoformat() if stats.completed_at else None,
    )


@router.post("/recall/{campaign_id}/pause")
async def pause_recall_campaign(campaign_id: str) -> dict[str, Any]:
    """Pause a recall campaign."""
    workflow = get_recall_workflow()

    try:
        campaign_uuid = UUID(campaign_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid campaign ID format")

    success = await workflow.pause_campaign(campaign_uuid)
    if not success:
        raise HTTPException(status_code=404, detail=f"Campaign {campaign_id} not found")

    return {"status": "paused", "campaign_id": campaign_id}


@router.post("/recall/{campaign_id}/resume")
async def resume_recall_campaign(campaign_id: str) -> dict[str, Any]:
    """Resume a paused recall campaign."""
    workflow = get_recall_workflow()

    try:
        campaign_uuid = UUID(campaign_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid campaign ID format")

    success = await workflow.resume_campaign(campaign_uuid)
    if not success:
        raise HTTPException(status_code=404, detail=f"Campaign {campaign_id} not found")

    return {"status": "resumed", "campaign_id": campaign_id}


# ============ NO-SHOW FOLLOW-UP ENDPOINTS ============


@router.post("/no-show/process", response_model=NoShowStatsResponse)
async def process_no_shows(request: NoShowProcessRequest) -> NoShowStatsResponse:
    """
    Process no-shows from a specific day and start follow-up calls.

    Typically run at end of day or next morning for previous day's no-shows.
    Uses empathetic conversation to understand why patient missed and offer rebooking.
    """
    workflow = get_noshow_workflow()

    # Parse target date
    target_date = None
    if request.target_date:
        try:
            target_date = date.fromisoformat(request.target_date)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid date format: {request.target_date}. Use YYYY-MM-DD.",
            )

    # Update config
    workflow._config.min_hours_after_missed = request.min_hours_after
    workflow._config.max_hours_after_missed = request.max_hours_after

    # Process no-shows
    stats = await workflow.process_daily_no_shows(target_date)

    return NoShowStatsResponse(
        total_missed=stats.total_missed,
        calls_attempted=stats.calls_attempted,
        rescheduled=stats.rescheduled,
        declined=stats.declined,
        unreachable=stats.unreachable,
        barriers_identified=stats.barriers_identified,
        needs_followup=stats.needs_followup,
        reschedule_rate=stats.reschedule_rate,
        started_at=stats.started_at.isoformat(),
        completed_at=stats.completed_at.isoformat() if stats.completed_at else None,
    )


@router.get("/no-show/stats", response_model=NoShowStatsResponse)
async def get_noshow_stats() -> NoShowStatsResponse:
    """Get current no-show follow-up statistics."""
    workflow = get_noshow_workflow()
    stats = workflow.get_stats()

    return NoShowStatsResponse(
        total_missed=stats.total_missed,
        calls_attempted=stats.calls_attempted,
        rescheduled=stats.rescheduled,
        declined=stats.declined,
        unreachable=stats.unreachable,
        barriers_identified=stats.barriers_identified,
        needs_followup=stats.needs_followup,
        reschedule_rate=stats.reschedule_rate,
        started_at=stats.started_at.isoformat(),
        completed_at=stats.completed_at.isoformat() if stats.completed_at else None,
    )


@router.get("/no-show/needs-followup")
async def get_tasks_needing_followup() -> list[dict[str, Any]]:
    """Get no-show tasks that need manual staff follow-up.

    Returns tasks where:
    - Patient was unreachable after all attempts
    - Barrier was identified (transportation, childcare, etc.)
    """
    workflow = get_noshow_workflow()
    tasks = workflow.get_tasks_needing_manual_followup()
    return [task.to_dict() for task in tasks]


# ============ DIALER CONTROL ENDPOINTS ============


@router.get("/queue", response_model=list[QueuedCallResponse])
async def get_call_queue() -> list[QueuedCallResponse]:
    """Get current call queue."""
    dialer = get_outbound_dialer()
    calls = dialer.get_queue_snapshot()

    return [
        QueuedCallResponse(
            id=str(call.id),
            patient_id=str(call.patient_id),
            phone_number=call.phone_number[:8] + "...",  # Partial for privacy
            call_type=call.call_type.value,
            priority=call.priority.name,
            queued_at=call.queued_at.isoformat(),
            metadata=call.metadata,
        )
        for call in calls
    ]


@router.get("/stats", response_model=DialerStatusResponse)
async def get_dialer_status() -> DialerStatusResponse:
    """Get dialer status and statistics."""
    dialer = get_outbound_dialer()
    stats = dialer.get_stats()

    return DialerStatusResponse(
        status=stats["status"],
        queue_size=stats["queue_size"],
        active_calls=stats["active_calls"],
        completed_today=stats["completed_today"],
        business_hours_active=stats["business_hours_active"],
        next_business_start=stats.get("next_business_start"),
    )


@router.post("/pause")
async def pause_dialer() -> dict[str, str]:
    """Pause the outbound dialer.

    Queued calls are preserved but not executed until resumed.
    Active calls continue to completion.
    """
    dialer = get_outbound_dialer()
    dialer.pause()
    return {"status": "paused"}


@router.post("/resume")
async def resume_dialer() -> dict[str, str]:
    """Resume the outbound dialer."""
    dialer = get_outbound_dialer()
    dialer.resume()
    return {"status": "running"}


@router.delete("/queue/{call_id}")
async def cancel_queued_call(call_id: str) -> dict[str, Any]:
    """Cancel a queued call (before it starts)."""
    dialer = get_outbound_dialer()

    try:
        call_uuid = UUID(call_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid call ID format")

    success = await dialer.cancel_call(call_uuid)
    if not success:
        raise HTTPException(
            status_code=404,
            detail=f"Call {call_id} not found or already in progress",
        )

    return {"status": "cancelled", "call_id": call_id}


@router.delete("/queue")
async def clear_call_queue() -> dict[str, Any]:
    """Clear all queued calls (for emergencies only)."""
    dialer = get_outbound_dialer()
    count = await dialer.clear_queue()
    return {"status": "cleared", "calls_removed": count}


# ============ UTILITY ENDPOINTS ============


@router.get("/call-types")
async def get_call_types() -> list[dict[str, str]]:
    """Get available outbound call types."""
    from phone_agent.industry.gesundheit.outbound.conversation_outbound import OutboundCallType

    return [
        {"value": ct.value, "name": ct.name}
        for ct in OutboundCallType
    ]


@router.get("/priorities")
async def get_priorities() -> list[dict[str, Any]]:
    """Get call priority levels."""
    return [
        {"value": p.value, "name": p.name}
        for p in CallPriority
    ]
