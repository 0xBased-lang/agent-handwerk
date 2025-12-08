"""Appointment management endpoints.

Provides API endpoints for appointment management with database persistence.
Replaces in-memory storage with SQLAlchemy-backed repository.
"""
from __future__ import annotations

from datetime import datetime, date, time, timedelta
from enum import Enum
from typing import Any, Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from phone_agent.db import get_db
from phone_agent.db.models.core import AppointmentModel
from phone_agent.db.repositories.appointments import AppointmentRepository


router = APIRouter()


# ============================================================================
# Pydantic Schemas (API layer - unchanged for backward compatibility)
# ============================================================================

class AppointmentStatus(str, Enum):
    """Appointment status."""

    SCHEDULED = "scheduled"
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"
    COMPLETED = "completed"
    NO_SHOW = "no_show"


class AppointmentType(str, Enum):
    """Appointment type."""

    CONSULTATION = "consultation"  # Beratung
    CHECKUP = "checkup"  # Vorsorge
    FOLLOWUP = "followup"  # Nachkontrolle
    EMERGENCY = "emergency"  # Notfall
    OTHER = "other"


class AppointmentCreate(BaseModel):
    """Create appointment request."""

    patient_name: str
    patient_phone: str
    patient_email: str | None = None
    appointment_date: date
    appointment_time: time
    duration_minutes: int = 15
    type: AppointmentType = AppointmentType.CONSULTATION
    notes: str | None = None
    call_id: UUID | None = None
    industry: str = "gesundheit"


class AppointmentUpdate(BaseModel):
    """Update appointment request."""

    appointment_date: date | None = None
    appointment_time: time | None = None
    duration_minutes: int | None = None
    status: AppointmentStatus | None = None
    notes: str | None = None


class Appointment(BaseModel):
    """Appointment record schema for API responses."""

    id: UUID
    patient_name: str
    patient_phone: str
    patient_email: str | None = None
    appointment_date: date
    appointment_time: time
    duration_minutes: int = 15
    type: str = "consultation"
    status: str = "scheduled"
    notes: str | None = None
    reminder_sent: bool = False
    created_at: datetime | None = None
    created_by: str = "phone-agent"
    call_id: UUID | None = None
    contact_id: UUID | None = None
    industry: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    model_config = {"from_attributes": True}

    @classmethod
    def from_model(cls, model: AppointmentModel) -> "Appointment":
        """Create schema from ORM model."""
        return cls(
            id=model.id,
            patient_name=model.patient_name,
            patient_phone=model.patient_phone,
            patient_email=model.patient_email,
            appointment_date=model.appointment_date,
            appointment_time=model.appointment_time,
            duration_minutes=model.duration_minutes or 15,
            type=model.type or "consultation",
            status=model.status,
            notes=model.notes,
            reminder_sent=model.reminder_sent or False,
            created_at=model.created_at,
            created_by=model.created_by or "phone-agent",
            call_id=UUID(model.call_id) if model.call_id else None,
            contact_id=UUID(model.contact_id) if model.contact_id else None,
            industry=None,  # Not stored in model
            metadata=model.metadata_json or {},
        )


class AppointmentListResponse(BaseModel):
    """Paginated appointment list response."""

    appointments: list[Appointment]
    total: int
    page: int
    page_size: int


class SlotAvailability(BaseModel):
    """Available time slot."""

    date: date
    time: time
    duration_minutes: int


class AppointmentDailyStats(BaseModel):
    """Daily appointment statistics."""

    date: str
    total_appointments: int
    scheduled: int
    confirmed: int
    completed: int
    cancelled: int
    no_shows: int
    completion_rate: float = 0.0
    no_show_rate: float = 0.0


# ============================================================================
# Dependencies
# ============================================================================

async def get_appointment_repository(
    session: Annotated[AsyncSession, Depends(get_db)]
) -> AppointmentRepository:
    """Get appointment repository instance."""
    return AppointmentRepository(session)


# ============================================================================
# Appointment Endpoints
# ============================================================================

@router.get("/appointments", response_model=AppointmentListResponse)
async def list_appointments(
    repo: Annotated[AppointmentRepository, Depends(get_appointment_repository)],
    status: AppointmentStatus | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    industry: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> AppointmentListResponse:
    """List appointments with optional filtering and pagination.

    Args:
        status: Filter by appointment status
        date_from: Filter by start date
        date_to: Filter by end date
        industry: Filter by industry
        page: Page number (1-indexed)
        page_size: Number of results per page

    Returns:
        Paginated list of appointments
    """
    skip = (page - 1) * page_size

    if date_from and date_to:
        appointments = await repo.get_by_date_range(
            date_from, date_to,
            status=status.value if status else None,
            industry=industry,
            skip=skip,
            limit=page_size,
        )
    elif status:
        appointments = await repo.get_by_status(status.value, skip=skip, limit=page_size)
    else:
        appointments = await repo.get_multi(skip=skip, limit=page_size)

    # Get total count
    total = await repo.count()

    return AppointmentListResponse(
        appointments=[Appointment.from_model(a) for a in appointments],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/appointments/today", response_model=list[Appointment])
async def list_today_appointments(
    repo: Annotated[AppointmentRepository, Depends(get_appointment_repository)],
    industry: str | None = None,
) -> list[Appointment]:
    """Get all appointments for today.

    Args:
        industry: Optional industry filter

    Returns:
        List of today's appointments
    """
    appointments = await repo.get_today(industry=industry)
    return [Appointment.from_model(a) for a in appointments]


@router.get("/appointments/upcoming", response_model=list[Appointment])
async def list_upcoming_appointments(
    repo: Annotated[AppointmentRepository, Depends(get_appointment_repository)],
    days: int = Query(7, ge=1, le=30),
    industry: str | None = None,
    limit: int = Query(50, ge=1, le=200),
) -> list[Appointment]:
    """Get upcoming appointments.

    Args:
        days: Number of days to look ahead
        industry: Optional industry filter
        limit: Maximum number of results

    Returns:
        List of upcoming appointments
    """
    appointments = await repo.get_upcoming(days=days, industry=industry, limit=limit)
    return [Appointment.from_model(a) for a in appointments]


@router.get("/appointments/stats/daily", response_model=AppointmentDailyStats)
async def get_daily_stats(
    repo: Annotated[AppointmentRepository, Depends(get_appointment_repository)],
    target_date: date | None = None,
    industry: str | None = None,
) -> AppointmentDailyStats:
    """Get daily appointment statistics.

    Args:
        target_date: Date to get stats for (default: today)
        industry: Optional industry filter

    Returns:
        Daily appointment statistics
    """
    stats = await repo.get_daily_stats(target_date, industry=industry)
    return AppointmentDailyStats(**stats)


@router.get("/appointments/{appointment_id}", response_model=Appointment)
async def get_appointment(
    appointment_id: UUID,
    repo: Annotated[AppointmentRepository, Depends(get_appointment_repository)],
) -> Appointment:
    """Get a specific appointment by ID.

    Args:
        appointment_id: UUID of the appointment

    Returns:
        Appointment details

    Raises:
        HTTPException: If appointment not found
    """
    appointment = await repo.get(appointment_id)
    if appointment is None:
        raise HTTPException(status_code=404, detail="Appointment not found")
    return Appointment.from_model(appointment)


@router.post("/appointments", response_model=Appointment, status_code=201)
async def create_appointment(
    data: AppointmentCreate,
    repo: Annotated[AppointmentRepository, Depends(get_appointment_repository)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Appointment:
    """Create a new appointment.

    Args:
        data: Appointment creation data

    Returns:
        Created appointment

    Raises:
        HTTPException: If time slot is already booked
    """
    from itf_shared import get_logger
    log = get_logger(__name__)

    # Check for conflicts
    is_available = await repo.check_slot_availability(
        data.appointment_date,
        data.appointment_time,
        data.duration_minutes,
    )

    if not is_available:
        raise HTTPException(
            status_code=409,
            detail="Time slot already booked",
        )

    appointment = AppointmentModel(
        id=uuid4(),
        patient_name=data.patient_name,
        patient_phone=data.patient_phone,
        patient_email=data.patient_email,
        appointment_date=data.appointment_date,
        appointment_time=data.appointment_time,
        duration_minutes=data.duration_minutes,
        type=data.type.value,
        status=AppointmentStatus.SCHEDULED.value,
        notes=data.notes,
    )

    created = await repo.create(appointment)
    await db.commit()

    log.info(
        "Appointment created",
        appointment_id=str(created.id),
        patient=created.patient_name,
        date=str(created.appointment_date),
        time=str(created.appointment_time),
    )

    # Send confirmation SMS if SMS integration enabled and phone provided
    if created.patient_phone:
        try:
            from phone_agent.config import get_settings
            from phone_agent.integrations.sms.factory import send_appointment_confirmation

            settings = get_settings()
            if settings.integrations.sms.enabled:
                # Format date and time for SMS
                date_str = created.appointment_date.strftime("%d.%m.%Y")
                time_str = created.appointment_time.strftime("%H:%M") if created.appointment_time else "TBD"

                sms_sent = await send_appointment_confirmation(
                    phone=created.patient_phone,
                    patient_name=created.patient_name or "Patient",
                    appointment_date=date_str,
                    appointment_time=time_str,
                    provider_name=created.provider_name or "Arzt",
                    practice_name=settings.industry.display_name or "Praxis",
                )

                if sms_sent:
                    log.info("Confirmation SMS sent", appointment_id=str(created.id))
                else:
                    log.warning("Failed to send confirmation SMS", appointment_id=str(created.id))

        except Exception as e:
            # Don't fail the appointment creation if SMS fails
            log.error("SMS sending error", error=str(e), appointment_id=str(created.id))

    return Appointment.from_model(created)


@router.patch("/appointments/{appointment_id}", response_model=Appointment)
async def update_appointment(
    appointment_id: UUID,
    data: AppointmentUpdate,
    repo: Annotated[AppointmentRepository, Depends(get_appointment_repository)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Appointment:
    """Update an existing appointment.

    Args:
        appointment_id: UUID of the appointment
        data: Update data

    Returns:
        Updated appointment

    Raises:
        HTTPException: If appointment not found or time slot conflict
    """
    appointment = await repo.get(appointment_id)
    if appointment is None:
        raise HTTPException(status_code=404, detail="Appointment not found")

    update_data = data.model_dump(exclude_unset=True)

    # Check for conflicts if date/time changed
    new_date = update_data.get("appointment_date", appointment.appointment_date)
    new_time = update_data.get("appointment_time", appointment.appointment_time)
    duration = update_data.get("duration_minutes", appointment.duration_minutes or 15)

    if new_date != appointment.appointment_date or new_time != appointment.appointment_time:
        is_available = await repo.check_slot_availability(
            new_date, new_time, duration, exclude_id=appointment_id
        )
        if not is_available:
            raise HTTPException(
                status_code=409,
                detail="New time slot is already booked",
            )

    # Convert enum to value if present
    if "status" in update_data and update_data["status"]:
        update_data["status"] = update_data["status"].value

    updated = await repo.update(appointment_id, update_data)
    await db.commit()

    return Appointment.from_model(updated)


@router.delete("/appointments/{appointment_id}")
async def cancel_appointment(
    appointment_id: UUID,
    repo: Annotated[AppointmentRepository, Depends(get_appointment_repository)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, str]:
    """Cancel an appointment.

    Args:
        appointment_id: UUID of the appointment

    Returns:
        Cancellation status

    Raises:
        HTTPException: If appointment not found
    """
    appointment = await repo.get(appointment_id)
    if appointment is None:
        raise HTTPException(status_code=404, detail="Appointment not found")

    await repo.update(appointment_id, {"status": AppointmentStatus.CANCELLED.value})
    await db.commit()

    from itf_shared import get_logger
    log = get_logger(__name__)
    log.info("Appointment cancelled", appointment_id=str(appointment_id))

    return {"status": "cancelled"}


@router.post("/appointments/{appointment_id}/confirm", response_model=Appointment)
async def confirm_appointment(
    appointment_id: UUID,
    repo: Annotated[AppointmentRepository, Depends(get_appointment_repository)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Appointment:
    """Confirm an appointment.

    Args:
        appointment_id: UUID of the appointment

    Returns:
        Confirmed appointment

    Raises:
        HTTPException: If appointment not found
    """
    appointment = await repo.get(appointment_id)
    if appointment is None:
        raise HTTPException(status_code=404, detail="Appointment not found")

    if appointment.status != AppointmentStatus.SCHEDULED.value:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot confirm appointment with status {appointment.status}",
        )

    updated = await repo.update(appointment_id, {"status": AppointmentStatus.CONFIRMED.value})
    await db.commit()

    return Appointment.from_model(updated)


@router.post("/appointments/{appointment_id}/complete", response_model=Appointment)
async def complete_appointment(
    appointment_id: UUID,
    repo: Annotated[AppointmentRepository, Depends(get_appointment_repository)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Appointment:
    """Mark an appointment as completed.

    Args:
        appointment_id: UUID of the appointment

    Returns:
        Completed appointment

    Raises:
        HTTPException: If appointment not found
    """
    appointment = await repo.get(appointment_id)
    if appointment is None:
        raise HTTPException(status_code=404, detail="Appointment not found")

    updated = await repo.update(appointment_id, {"status": AppointmentStatus.COMPLETED.value})
    await db.commit()

    return Appointment.from_model(updated)


@router.post("/appointments/{appointment_id}/no-show", response_model=Appointment)
async def mark_no_show(
    appointment_id: UUID,
    repo: Annotated[AppointmentRepository, Depends(get_appointment_repository)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Appointment:
    """Mark an appointment as no-show.

    Args:
        appointment_id: UUID of the appointment

    Returns:
        No-show appointment

    Raises:
        HTTPException: If appointment not found
    """
    appointment = await repo.get(appointment_id)
    if appointment is None:
        raise HTTPException(status_code=404, detail="Appointment not found")

    updated = await repo.update(appointment_id, {"status": AppointmentStatus.NO_SHOW.value})
    await db.commit()

    return Appointment.from_model(updated)


# ============================================================================
# Slot Availability
# ============================================================================

@router.get("/appointments/slots", response_model=list[SlotAvailability])
async def get_available_slots(
    repo: Annotated[AppointmentRepository, Depends(get_appointment_repository)],
    date_from: date,
    date_to: date | None = None,
    duration_minutes: int = 15,
) -> list[SlotAvailability]:
    """Get available appointment slots.

    Returns available time slots based on:
    - Business hours (from industry config)
    - Existing appointments
    - Slot duration

    Args:
        date_from: Start date for availability search
        date_to: End date for availability search (default: same as start)
        duration_minutes: Duration of appointment slots

    Returns:
        List of available time slots
    """
    from phone_agent.config import get_settings

    settings = get_settings()
    hours = settings.industry.hours

    # Default to single day if no end date
    if date_to is None:
        date_to = date_from

    slots: list[SlotAvailability] = []
    current_date = date_from

    while current_date <= date_to:
        # Get day of week
        day_name = current_date.strftime("%A").lower()
        day_hours = hours.get(day_name)

        if day_hours:
            # Parse hours (e.g., "08:00-18:00")
            try:
                start_str, end_str = day_hours.split("-")
                start_hour, start_min = map(int, start_str.split(":"))
                end_hour, end_min = map(int, end_str.split(":"))

                # Generate slots
                current_time = time(start_hour, start_min)
                end_time = time(end_hour, end_min)

                while current_time < end_time:
                    # Check if slot is available
                    is_available = await repo.check_slot_availability(
                        current_date, current_time, duration_minutes
                    )

                    if is_available:
                        slots.append(
                            SlotAvailability(
                                date=current_date,
                                time=current_time,
                                duration_minutes=duration_minutes,
                            )
                        )

                    # Move to next slot
                    dt_current = datetime.combine(current_date, current_time)
                    dt_next = dt_current + timedelta(minutes=duration_minutes)
                    current_time = dt_next.time()

            except (ValueError, AttributeError):
                pass

        # Move to next day
        current_date += timedelta(days=1)

    return slots


# ============================================================================
# Contact-based Queries
# ============================================================================

@router.get("/contacts/{contact_id}/appointments", response_model=list[Appointment])
async def get_contact_appointments(
    contact_id: UUID,
    repo: Annotated[AppointmentRepository, Depends(get_appointment_repository)],
    limit: int = Query(50, ge=1, le=200),
) -> list[Appointment]:
    """Get all appointments for a specific contact.

    Args:
        contact_id: UUID of the contact
        limit: Maximum number of results

    Returns:
        List of appointments for the contact
    """
    appointments = await repo.get_by_contact(contact_id, limit=limit)
    return [Appointment.from_model(a) for a in appointments]


@router.get("/contacts/{contact_id}/appointments/next", response_model=Appointment | None)
async def get_contact_next_appointment(
    contact_id: UUID,
    repo: Annotated[AppointmentRepository, Depends(get_appointment_repository)],
) -> Appointment | None:
    """Get the next upcoming appointment for a contact.

    Args:
        contact_id: UUID of the contact

    Returns:
        Next appointment or None
    """
    appointment = await repo.get_next_for_contact(contact_id)
    if appointment is None:
        return None
    return Appointment.from_model(appointment)
