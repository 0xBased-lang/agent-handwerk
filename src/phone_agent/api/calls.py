"""Call management endpoints.

Provides API endpoints for call management with database persistence.
Replaces in-memory storage with SQLAlchemy-backed repository.
"""
from __future__ import annotations

from datetime import datetime, date, timezone
from enum import Enum
from typing import Any, Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from phone_agent.db import get_db
from phone_agent.db.models.core import CallModel
from phone_agent.db.repositories.calls import CallRepository
from phone_agent.api.rate_limits import limiter, RateLimits


router = APIRouter()


# ============================================================================
# Pydantic Schemas (API layer - unchanged for backward compatibility)
# ============================================================================

class CallStatus(str, Enum):
    """Call status enumeration."""

    INCOMING = "incoming"
    RINGING = "ringing"
    IN_PROGRESS = "in_progress"
    ACTIVE = "active"
    ON_HOLD = "on_hold"
    COMPLETED = "completed"
    MISSED = "missed"
    FAILED = "failed"
    NO_ANSWER = "no_answer"
    TRANSFERRED = "transferred"


class CallDirection(str, Enum):
    """Call direction."""

    INBOUND = "inbound"
    OUTBOUND = "outbound"


class CallCreate(BaseModel):
    """Schema for creating a new call."""

    direction: CallDirection
    caller_id: str = Field(
        ...,
        max_length=50,
        pattern=r'^\+?[1-9]\d{1,14}$',
        description="Caller phone number in E.164 format",
    )
    callee_id: str = Field(
        ...,
        max_length=50,
        pattern=r'^\+?[1-9]\d{1,14}$',
        description="Callee phone number in E.164 format",
    )
    industry: str = Field(
        default="gesundheit",
        max_length=50,
        description="Industry vertical",
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional metadata (max 10KB)",
    )


class CallUpdate(BaseModel):
    """Schema for updating a call."""

    status: CallStatus | None = None
    ended_at: datetime | None = None
    duration_seconds: int | None = Field(None, ge=0, le=86400)  # Max 24 hours
    transcript: str | None = Field(None, max_length=100000)  # Max 100KB
    summary: str | None = Field(None, max_length=10000)  # Max 10KB
    triage_result: str | None = Field(None, max_length=1000)
    appointment_id: UUID | None = None
    appointment_booked: bool | None = None
    transferred: bool | None = None
    transfer_target: str | None = Field(None, max_length=50)
    metadata: dict[str, Any] | None = None


class Call(BaseModel):
    """Call record schema for API responses."""

    id: UUID
    direction: str
    status: str
    caller_id: str
    callee_id: str
    started_at: datetime
    ended_at: datetime | None = None
    duration_seconds: int | None = None
    transcript: str | None = None
    summary: str | None = None
    triage_result: str | None = None
    appointment_id: UUID | None = None
    appointment_booked: bool = False
    transferred: bool = False
    industry: str | None = None
    contact_id: UUID | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime | None = None

    model_config = {"from_attributes": True}

    @classmethod
    def from_model(cls, model: CallModel) -> "Call":
        """Create schema from ORM model."""
        return cls(
            id=model.id,
            direction=model.direction,
            status=model.status,
            caller_id=model.caller_id,
            callee_id=model.callee_id,
            started_at=model.started_at,
            ended_at=model.ended_at,
            duration_seconds=model.duration_seconds,
            transcript=model.transcript,
            summary=model.summary,
            triage_result=model.triage_result,
            appointment_id=model.appointment_id,
            appointment_booked=model.appointment_booked or False,
            transferred=model.transferred or False,
            industry=model.industry,
            contact_id=model.contact_id,
            metadata=model.metadata or {},
            created_at=model.created_at,
        )


class CallListResponse(BaseModel):
    """Paginated call list response."""

    calls: list[Call]
    total: int
    page: int
    page_size: int


class CallDailyStats(BaseModel):
    """Daily call statistics."""

    date: str
    total_calls: int
    inbound: int
    outbound: int
    completed: int
    missed: int
    failed: int
    avg_duration: float
    total_duration: int
    appointments_booked: int
    completion_rate: float
    appointment_conversion_rate: float


class WebhookPayload(BaseModel):
    """SIP webhook payload."""

    event: str
    call_id: str
    caller_id: str
    callee_id: str
    timestamp: str
    data: dict[str, Any] = Field(default_factory=dict)


# ============================================================================
# Dependencies
# ============================================================================

async def get_call_repository(
    session: Annotated[AsyncSession, Depends(get_db)]
) -> CallRepository:
    """Get call repository instance."""
    return CallRepository(session)


# ============================================================================
# Call Endpoints
# ============================================================================

@router.get("/calls", response_model=CallListResponse)
@limiter.limit(RateLimits.READ)
async def list_calls(
    request: Request,
    repo: Annotated[CallRepository, Depends(get_call_repository)],
    status: CallStatus | None = None,
    direction: CallDirection | None = None,
    industry: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> CallListResponse:
    """List calls with optional filtering and pagination.

    Args:
        request: FastAPI request object (for rate limiting)
        status: Filter by call status
        direction: Filter by call direction
        industry: Filter by industry
        page: Page number (1-indexed)
        page_size: Number of results per page

    Returns:
        Paginated list of calls
    """
    skip = (page - 1) * page_size

    if status:
        calls = await repo.get_by_status(status.value, skip=skip, limit=page_size)
    elif direction:
        calls = await repo.get_by_direction(direction.value, skip=skip, limit=page_size)
    else:
        calls = await repo.get_multi(skip=skip, limit=page_size)

    # Get total count
    total = await repo.count()

    return CallListResponse(
        calls=[Call.from_model(c) for c in calls],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/calls/today", response_model=CallListResponse)
async def list_today_calls(
    repo: Annotated[CallRepository, Depends(get_call_repository)],
    industry: str | None = None,
) -> CallListResponse:
    """Get all calls from today.

    Args:
        industry: Optional industry filter

    Returns:
        List of today's calls
    """
    calls = await repo.get_today(industry=industry)

    return CallListResponse(
        calls=[Call.from_model(c) for c in calls],
        total=len(calls),
        page=1,
        page_size=len(calls),
    )


@router.get("/calls/stats/daily", response_model=CallDailyStats)
async def get_daily_stats(
    repo: Annotated[CallRepository, Depends(get_call_repository)],
    target_date: date | None = None,
    industry: str | None = None,
) -> CallDailyStats:
    """Get daily call statistics.

    Args:
        target_date: Date to get stats for (default: today)
        industry: Optional industry filter

    Returns:
        Daily call statistics
    """
    stats = await repo.get_daily_stats(target_date, industry=industry)
    return CallDailyStats(**stats)


@router.get("/calls/stats/hourly")
async def get_hourly_distribution(
    repo: Annotated[CallRepository, Depends(get_call_repository)],
    target_date: date | None = None,
    industry: str | None = None,
) -> dict[str, Any]:
    """Get call distribution by hour.

    Args:
        target_date: Date to analyze (default: today)
        industry: Optional industry filter

    Returns:
        Dictionary with hour -> call count
    """
    distribution = await repo.get_hourly_distribution(target_date, industry=industry)
    return {
        "date": (target_date or date.today()).isoformat(),
        "hourly_distribution": distribution,
        "peak_hour": max(distribution, key=distribution.get) if distribution else None,
    }


@router.get("/calls/active")
async def get_active_calls(
    repo: Annotated[CallRepository, Depends(get_call_repository)],
) -> list[Call]:
    """Get all currently active calls.

    Returns:
        List of active calls (ringing or in_progress)
    """
    calls = await repo.get_active_calls()
    return [Call.from_model(c) for c in calls]


@router.get("/calls/{call_id}", response_model=Call)
async def get_call(
    call_id: UUID,
    repo: Annotated[CallRepository, Depends(get_call_repository)],
) -> Call:
    """Get a specific call by ID.

    Args:
        call_id: UUID of the call

    Returns:
        Call details

    Raises:
        HTTPException: If call not found
    """
    call = await repo.get(call_id)
    if call is None:
        raise HTTPException(status_code=404, detail="Call not found")
    return Call.from_model(call)


@router.post("/calls", response_model=Call, status_code=201)
async def create_call(
    call_in: CallCreate,
    repo: Annotated[CallRepository, Depends(get_call_repository)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Call:
    """Create a new call record.

    Args:
        call_in: Call creation data

    Returns:
        Created call
    """
    call = CallModel(
        id=uuid4(),
        direction=call_in.direction.value,
        status=CallStatus.INCOMING.value,
        caller_id=call_in.caller_id,
        callee_id=call_in.callee_id,
        started_at=datetime.utcnow(),
        industry=call_in.industry,
    )
    call.metadata = call_in.metadata

    created = await repo.create(call)
    await db.commit()

    return Call.from_model(created)


@router.patch("/calls/{call_id}", response_model=Call)
async def update_call(
    call_id: UUID,
    call_in: CallUpdate,
    repo: Annotated[CallRepository, Depends(get_call_repository)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Call:
    """Update a call record.

    Args:
        call_id: UUID of the call
        call_in: Update data

    Returns:
        Updated call

    Raises:
        HTTPException: If call not found
    """
    update_data = call_in.model_dump(exclude_unset=True)

    # Convert enum to value if present
    if "status" in update_data and update_data["status"]:
        update_data["status"] = update_data["status"].value

    updated = await repo.update(call_id, update_data)
    if updated is None:
        raise HTTPException(status_code=404, detail="Call not found")

    await db.commit()
    return Call.from_model(updated)


@router.post("/calls/{call_id}/end", response_model=Call)
async def end_call(
    call_id: UUID,
    repo: Annotated[CallRepository, Depends(get_call_repository)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Call:
    """End an active call.

    Args:
        call_id: UUID of the call

    Returns:
        Ended call

    Raises:
        HTTPException: If call not found or not active
    """
    call = await repo.get(call_id)
    if call is None:
        raise HTTPException(status_code=404, detail="Call not found")

    if call.status not in ["ringing", "in_progress", "active", "on_hold"]:
        raise HTTPException(status_code=400, detail="Call is not active")

    # Calculate duration with timezone-aware datetime
    ended_at = datetime.now(timezone.utc)
    # Ensure started_at is timezone-aware for comparison
    started_at = call.started_at
    if started_at.tzinfo is None:
        started_at = started_at.replace(tzinfo=timezone.utc)
    duration = int((ended_at - started_at).total_seconds())

    updated = await repo.update(call_id, {
        "status": CallStatus.COMPLETED.value,
        "ended_at": ended_at,
        "duration_seconds": duration,
    })

    await db.commit()
    return Call.from_model(updated)


@router.post("/calls/{call_id}/transfer")
async def transfer_call(
    call_id: UUID,
    target: str,
    repo: Annotated[CallRepository, Depends(get_call_repository)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, str]:
    """Transfer an active call to another number.

    Args:
        call_id: UUID of the call
        target: Transfer target number

    Returns:
        Transfer status

    Raises:
        HTTPException: If call not found or not active
    """
    call = await repo.get(call_id)
    if call is None:
        raise HTTPException(status_code=404, detail="Call not found")

    if call.status not in ["in_progress", "active"]:
        raise HTTPException(status_code=400, detail="Call is not active")

    from itf_shared import get_logger
    from phone_agent.dependencies import get_telephony_service

    log = get_logger(__name__)

    # Get the SIP/channel ID for this call
    sip_call_id = call.sip_call_id
    channel_uuid = call.metadata.get("channel_uuid") if call.metadata else None

    # Attempt the transfer
    transfer_success = False
    transfer_error = None

    try:
        service = get_telephony_service()

        # Try FreeSWITCH transfer if channel UUID exists
        if channel_uuid and service.freeswitch_client:
            transfer_success = await service.freeswitch_client.transfer(
                channel_uuid=channel_uuid,
                destination=target,
            )
        # Try SIP REFER transfer if SIP call ID exists
        elif sip_call_id and service.sip_client:
            # Find the call in SIP client
            for sip_call in service.sip_client.active_calls:
                if sip_call.sip_call_id == sip_call_id:
                    transfer_success = await service.sip_client.transfer(
                        call_id=sip_call.call_id,
                        target=target,
                    )
                    break
        else:
            # No backend available - log warning and mark as transferred anyway
            log.warning(
                "No telephony backend for transfer",
                call_id=str(call_id),
                target=target,
            )
            transfer_success = True  # Assume external system handles transfer

    except Exception as e:
        transfer_error = str(e)
        log.error("Transfer failed", call_id=str(call_id), error=transfer_error)

    # Update call record
    update_data = {
        "status": CallStatus.TRANSFERRED.value if transfer_success else CallStatus.FAILED.value,
        "transferred": transfer_success,
        "transfer_target": target,
    }
    if transfer_error:
        update_data["notes"] = f"Transfer error: {transfer_error}"

    await repo.update(call_id, update_data)
    await db.commit()

    log.info(
        "Call transfer",
        call_id=str(call_id),
        target=target,
        success=transfer_success,
    )

    if not transfer_success:
        raise HTTPException(
            status_code=500,
            detail=f"Transfer failed: {transfer_error or 'Unknown error'}",
        )

    return {"status": "transferred", "target": target, "success": True}


# ============================================================================
# Contact-based Call Queries
# ============================================================================

@router.get("/contacts/{contact_id}/calls", response_model=list[Call])
async def get_contact_calls(
    contact_id: UUID,
    repo: Annotated[CallRepository, Depends(get_call_repository)],
    limit: int = Query(50, ge=1, le=200),
) -> list[Call]:
    """Get all calls for a specific contact.

    Args:
        contact_id: UUID of the contact
        limit: Maximum number of results

    Returns:
        List of calls for the contact
    """
    calls = await repo.get_by_contact(contact_id, limit=limit)
    return [Call.from_model(c) for c in calls]


# ============================================================================
# Webhook Handlers
# ============================================================================

@router.post("/webhooks/call")
async def handle_call_webhook(
    payload: WebhookPayload,
    repo: Annotated[CallRepository, Depends(get_call_repository)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, str]:
    """Handle incoming SIP webhook events.

    Events:
    - call.incoming: New inbound call
    - call.answered: Call was answered
    - call.ended: Call ended
    - call.failed: Call failed

    Args:
        payload: Webhook event payload

    Returns:
        Acknowledgment status
    """
    from itf_shared import get_logger

    log = get_logger(__name__)
    log.info(
        "Received call webhook",
        event=payload.event,
        call_id=payload.call_id,
        caller=payload.caller_id,
    )

    if payload.event == "call.incoming":
        # Create new call record
        call = CallModel(
            id=uuid4(),
            direction=CallDirection.INBOUND.value,
            status=CallStatus.INCOMING.value,
            caller_id=payload.caller_id,
            callee_id=payload.callee_id,
            started_at=datetime.fromisoformat(payload.timestamp),
            sip_call_id=payload.call_id,
        )
        call.metadata = payload.data

        await repo.create(call)
        await db.commit()

        log.info("New inbound call created", call_id=str(call.id))

        # Trigger call handling pipeline
        try:
            from phone_agent.dependencies import get_telephony_service

            service = get_telephony_service()

            # Handle incoming call through telephony service
            result = await service.handle_webhook_incoming(
                call_id=payload.call_id,
                caller_id=payload.caller_id,
                callee_id=payload.callee_id,
                metadata={
                    "internal_call_id": str(call.id),
                    "event": payload.event,
                    **payload.data,
                },
            )

            log.info(
                "Call pipeline triggered",
                call_id=str(call.id),
                action=result.get("action"),
            )

        except Exception as e:
            log.error(
                "Failed to trigger call pipeline",
                call_id=str(call.id),
                error=str(e),
            )
            # Don't fail the webhook - call record is created, pipeline can be retried

    elif payload.event == "call.answered":
        # Update call to in_progress
        call = await repo.find_one(sip_call_id=payload.call_id)
        if call:
            await repo.update(call.id, {"status": CallStatus.IN_PROGRESS.value})
            await db.commit()
            log.info("Call answered", call_id=str(call.id))

    elif payload.event == "call.ended":
        # End the call
        call = await repo.find_one(sip_call_id=payload.call_id)
        if call:
            ended_at = datetime.fromisoformat(payload.timestamp)
            duration = int((ended_at - call.started_at).total_seconds())
            await repo.update(call.id, {
                "status": CallStatus.COMPLETED.value,
                "ended_at": ended_at,
                "duration_seconds": duration,
            })
            await db.commit()
            log.info("Call ended", call_id=str(call.id), duration=duration)

    elif payload.event == "call.failed":
        # Mark call as failed
        call = await repo.find_one(sip_call_id=payload.call_id)
        if call:
            await repo.update(call.id, {
                "status": CallStatus.FAILED.value,
                "ended_at": datetime.fromisoformat(payload.timestamp),
            })
            await db.commit()
            log.info("Call failed", call_id=str(call.id))

    return {"status": "received"}
