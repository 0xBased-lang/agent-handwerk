"""Recall campaign API endpoints.

Provides two sets of endpoints:
1. Original in-memory gesundheit industry service (legacy)
2. Database-backed RecallService for production campaigns

The database-backed endpoints are prefixed with /db/ and use
SQLAlchemy models for persistence.
"""
from __future__ import annotations

from datetime import date
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from phone_agent.industry.gesundheit import (
    get_recall_service,
    RecallType,
    RecallStatus,
    ContactMethod,
)
from phone_agent.db import get_db_context
from phone_agent.services.recall_service import RecallService, RecallServiceError


# Alias for cleaner code
get_session = get_db_context


router = APIRouter(prefix="/recall")


class CampaignCreate(BaseModel):
    """Request model for creating a campaign."""

    name: str | None = Field(default=None, description="Campaign name")
    recall_type: str = Field(..., description="Type of recall campaign")
    description: str = Field(default="", description="Campaign description")
    target_age_min: int | None = Field(default=None, ge=0, le=120)
    target_age_max: int | None = Field(default=None, ge=0, le=120)
    target_gender: str | None = Field(default=None, description="M, F, or None for all")
    target_conditions: list[str] = Field(default_factory=list)
    max_attempts: int = Field(default=3, ge=1, le=10)
    days_between_attempts: int = Field(default=3, ge=1, le=30)
    phone_script: str = Field(default="", description="Custom phone script")
    sms_template: str = Field(default="", description="Custom SMS template")


class CampaignResponse(BaseModel):
    """Response model for campaign."""

    id: str
    name: str
    recall_type: str
    description: str
    active: bool
    target_age_min: int | None
    target_age_max: int | None
    max_attempts: int
    days_between_attempts: int


class PatientAdd(BaseModel):
    """Request model for adding a patient to a campaign."""

    patient_id: str = Field(..., description="Patient ID")
    first_name: str = Field(..., description="First name")
    last_name: str = Field(..., description="Last name")
    phone: str = Field(..., description="Phone number")
    email: str | None = Field(default=None, description="Email address")
    priority: int = Field(default=5, ge=0, le=10, description="Priority (0-10)")


class RecallPatientResponse(BaseModel):
    """Response model for recall patient."""

    id: str
    patient_id: str
    campaign_id: str
    first_name: str
    last_name: str
    phone: str
    status: str
    attempts: int
    priority: int


class AttemptComplete(BaseModel):
    """Request model for completing an attempt."""

    outcome: str = Field(..., description="Outcome status")
    transcript: str | None = Field(default=None, description="Call transcript")
    notes: str | None = Field(default=None, description="Additional notes")
    appointment_id: str | None = Field(default=None, description="Scheduled appointment ID")


class CampaignStats(BaseModel):
    """Response model for campaign statistics."""

    campaign_id: str
    campaign_name: str
    total_patients: int
    status_breakdown: dict[str, int]
    total_attempts: int
    appointments_made: int
    success_rate: float


@router.post("/campaigns", response_model=CampaignResponse)
async def create_campaign(request: CampaignCreate) -> CampaignResponse:
    """
    Create a new recall campaign.

    Uses built-in templates for common campaign types:
    - preventive: Check-up reminders
    - vaccination: Flu, COVID, etc.
    - chronic: DMP quarterly follow-ups
    - no_show: Missed appointment follow-up
    - lab_results: Lab result discussions
    """
    service = get_recall_service()

    try:
        recall_type = RecallType(request.recall_type)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid recall type: {request.recall_type}",
        )

    campaign = service.create_campaign(
        recall_type=recall_type,
        name=request.name,
        description=request.description,
        target_age_min=request.target_age_min,
        target_age_max=request.target_age_max,
        target_gender=request.target_gender,
        target_conditions=request.target_conditions,
        max_attempts=request.max_attempts,
        days_between_attempts=request.days_between_attempts,
    )

    # Update custom templates if provided
    if request.phone_script:
        campaign.phone_script = request.phone_script
    if request.sms_template:
        campaign.sms_template = request.sms_template

    return CampaignResponse(
        id=str(campaign.id),
        name=campaign.name,
        recall_type=campaign.recall_type.value,
        description=campaign.description,
        active=campaign.active,
        target_age_min=campaign.target_age_min,
        target_age_max=campaign.target_age_max,
        max_attempts=campaign.max_attempts,
        days_between_attempts=campaign.days_between_attempts,
    )


@router.post("/campaigns/{campaign_id}/patients", response_model=RecallPatientResponse)
async def add_patient(campaign_id: str, request: PatientAdd) -> RecallPatientResponse:
    """Add a patient to a recall campaign."""
    service = get_recall_service()

    try:
        patient = service.add_patient_to_campaign(
            campaign_id=UUID(campaign_id),
            patient_id=UUID(request.patient_id),
            first_name=request.first_name,
            last_name=request.last_name,
            phone=request.phone,
            email=request.email,
            priority=request.priority,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    return RecallPatientResponse(
        id=str(patient.id),
        patient_id=str(patient.patient_id),
        campaign_id=str(patient.campaign_id),
        first_name=patient.first_name,
        last_name=patient.last_name,
        phone=patient.phone,
        status=patient.status.value,
        attempts=patient.attempts,
        priority=patient.priority,
    )


@router.get("/campaigns/{campaign_id}/next-patient", response_model=RecallPatientResponse | None)
async def get_next_patient(campaign_id: str) -> RecallPatientResponse | None:
    """Get the next patient to contact in a campaign."""
    service = get_recall_service()

    patient = service.get_next_patient(UUID(campaign_id))

    if not patient:
        return None

    return RecallPatientResponse(
        id=str(patient.id),
        patient_id=str(patient.patient_id),
        campaign_id=str(patient.campaign_id),
        first_name=patient.first_name,
        last_name=patient.last_name,
        phone=patient.phone,
        status=patient.status.value,
        attempts=patient.attempts,
        priority=patient.priority,
    )


@router.post("/patients/{recall_patient_id}/start-attempt")
async def start_attempt(
    recall_patient_id: str,
    method: str = Query(default="phone", description="Contact method"),
) -> dict[str, Any]:
    """Start a recall attempt for a patient."""
    service = get_recall_service()

    try:
        contact_method = ContactMethod(method)
    except ValueError:
        contact_method = ContactMethod.PHONE

    try:
        attempt = service.start_attempt(
            recall_patient_id=UUID(recall_patient_id),
            method=contact_method,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    return attempt.to_dict()


@router.post("/attempts/{attempt_id}/complete")
async def complete_attempt(
    attempt_id: str,
    request: AttemptComplete,
) -> dict[str, Any]:
    """Complete a recall attempt with outcome."""
    service = get_recall_service()

    try:
        outcome = RecallStatus(request.outcome)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid outcome: {request.outcome}",
        )

    try:
        attempt = service.complete_attempt(
            attempt_id=UUID(attempt_id),
            outcome=outcome,
            transcript=request.transcript,
            notes=request.notes,
            appointment_id=UUID(request.appointment_id) if request.appointment_id else None,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    return attempt.to_dict()


@router.get("/campaigns/{campaign_id}/stats", response_model=CampaignStats)
async def get_campaign_stats(campaign_id: str) -> CampaignStats:
    """Get statistics for a campaign."""
    service = get_recall_service()

    try:
        stats = service.get_campaign_stats(UUID(campaign_id))
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    return CampaignStats(**stats)


@router.get("/campaigns/{campaign_id}/script")
async def get_phone_script(
    campaign_id: str,
    first_name: str = Query(..., description="Patient first name"),
    last_name: str = Query(..., description="Patient last name"),
    practice_name: str = Query(default="Dr. Mustermann", description="Practice name"),
) -> dict[str, str]:
    """Get personalized phone script for a patient."""
    service = get_recall_service()

    from phone_agent.industry.gesundheit.recall import RecallPatient
    from uuid import uuid4

    # Create a temporary patient object for script generation
    patient = RecallPatient(
        id=uuid4(),
        patient_id=uuid4(),
        campaign_id=UUID(campaign_id),
        first_name=first_name,
        last_name=last_name,
        phone="",
    )

    script = service.get_phone_script(
        campaign_id=UUID(campaign_id),
        patient=patient,
        practice_name=practice_name,
    )

    if not script:
        raise HTTPException(status_code=404, detail="Campaign not found")

    return {"script": script}


@router.get("/types")
async def get_recall_types() -> list[dict[str, str]]:
    """Get available recall campaign types."""
    return [
        {"value": rt.value, "name": rt.name}
        for rt in RecallType
    ]


@router.get("/statuses")
async def get_recall_statuses() -> list[dict[str, str]]:
    """Get available recall statuses."""
    return [
        {"value": rs.value, "name": rs.name}
        for rs in RecallStatus
    ]


# =============================================================================
# Database-backed Campaign Endpoints (Production)
# =============================================================================

class DBCampaignCreate(BaseModel):
    """Request model for creating a database-backed campaign."""

    name: str = Field(..., description="Campaign name")
    campaign_type: str = Field(..., description="Type: vorsorge, impfung, kontrolle, wartung")
    industry: str = Field(default="gesundheit", description="Industry vertical")
    start_date: date = Field(..., description="Campaign start date")
    end_date: date | None = Field(default=None, description="Campaign end date")
    description: str | None = Field(default=None, description="Campaign description")
    target_criteria: dict[str, Any] | None = Field(default=None, description="Targeting criteria JSON")
    max_attempts: int = Field(default=3, ge=1, le=10, description="Maximum call attempts")
    call_interval_hours: int = Field(default=24, ge=1, le=168, description="Hours between retries")
    priority: int = Field(default=5, ge=1, le=10, description="Campaign priority")
    call_script: str | None = Field(default=None, description="Call script template")
    sms_template: str | None = Field(default=None, description="SMS follow-up template")


class DBCampaignUpdate(BaseModel):
    """Request model for updating a campaign."""

    name: str | None = None
    description: str | None = None
    end_date: date | None = None
    target_criteria: dict[str, Any] | None = None
    max_attempts: int | None = Field(default=None, ge=1, le=10)
    call_interval_hours: int | None = Field(default=None, ge=1, le=168)
    priority: int | None = Field(default=None, ge=1, le=10)
    call_script: str | None = None
    sms_template: str | None = None


class DBCampaignResponse(BaseModel):
    """Response model for database-backed campaign."""

    id: str
    name: str
    campaign_type: str
    industry: str
    status: str
    start_date: str
    end_date: str | None
    description: str | None
    max_attempts: int
    call_interval_hours: int
    priority: int
    total_contacts: int
    contacts_called: int
    contacts_reached: int
    appointments_booked: int
    progress_percent: float
    reach_rate: float
    conversion_rate: float
    created_at: str | None
    updated_at: str | None


class DBContactAdd(BaseModel):
    """Request model for adding a contact to a campaign."""

    contact_id: str = Field(..., description="CRM contact UUID")
    phone_number: str = Field(..., description="Phone number to call")
    contact_name: str | None = Field(default=None, description="Contact name")
    priority: int = Field(default=5, ge=1, le=10, description="Contact priority")
    custom_data: dict[str, Any] | None = Field(default=None, description="Custom personalization data")


class DBContactBulkAdd(BaseModel):
    """Request model for bulk adding contacts."""

    contacts: list[DBContactAdd] = Field(..., description="List of contacts to add")


class DBContactResponse(BaseModel):
    """Response model for campaign contact."""

    id: str
    campaign_id: str
    contact_id: str
    status: str
    priority: int
    attempts: int
    max_attempts: int
    next_attempt_at: str | None
    last_attempt_at: str | None
    last_call_result: str | None
    outcome: str | None
    phone_number: str
    contact_name: str | None
    can_attempt: bool
    created_at: str | None


class DBAttemptRecord(BaseModel):
    """Request model for recording a call attempt."""

    result: str = Field(..., description="Call result: answered, voicemail, no_answer, busy, failed")
    duration: int | None = Field(default=None, description="Call duration in seconds")
    call_id: str | None = Field(default=None, description="Reference to call record")
    notes: str | None = Field(default=None, description="Call notes")


class DBConversionRecord(BaseModel):
    """Request model for recording a conversion."""

    outcome: str = Field(..., description="Outcome: appointment_booked, callback_requested, declined")
    appointment_id: str | None = Field(default=None, description="Appointment reference")
    notes: str | None = Field(default=None, description="Notes")


# Campaign CRUD Endpoints

@router.post("/campaigns/db", response_model=DBCampaignResponse, tags=["DB Campaigns"])
async def create_db_campaign(request: DBCampaignCreate) -> DBCampaignResponse:
    """Create a new database-backed recall campaign."""
    async with get_session() as session:
        service = RecallService(session)

        campaign = await service.create_campaign(
            name=request.name,
            campaign_type=request.campaign_type,
            industry=request.industry,
            start_date=request.start_date,
            end_date=request.end_date,
            description=request.description,
            target_criteria=request.target_criteria,
            max_attempts=request.max_attempts,
            call_interval_hours=request.call_interval_hours,
            priority=request.priority,
            call_script=request.call_script,
            sms_template=request.sms_template,
        )

        return DBCampaignResponse(**campaign.to_dict())


@router.get("/campaigns/db", response_model=list[DBCampaignResponse], tags=["DB Campaigns"])
async def list_db_campaigns(
    status: str | None = Query(default=None, description="Filter by status"),
    industry: str | None = Query(default=None, description="Filter by industry"),
    campaign_type: str | None = Query(default=None, description="Filter by type"),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> list[DBCampaignResponse]:
    """List all database-backed campaigns."""
    async with get_session() as session:
        service = RecallService(session)

        campaigns = await service.list_campaigns(
            status=status,
            industry=industry,
            campaign_type=campaign_type,
            limit=limit,
            offset=offset,
        )

        return [DBCampaignResponse(**c.to_dict()) for c in campaigns]


@router.get("/campaigns/db/{campaign_id}", response_model=DBCampaignResponse, tags=["DB Campaigns"])
async def get_db_campaign(campaign_id: str) -> DBCampaignResponse:
    """Get a specific campaign by ID."""
    async with get_session() as session:
        service = RecallService(session)

        campaign = await service.get_campaign(UUID(campaign_id))
        if not campaign:
            raise HTTPException(status_code=404, detail="Campaign not found")

        return DBCampaignResponse(**campaign.to_dict())


@router.put("/campaigns/db/{campaign_id}", response_model=DBCampaignResponse, tags=["DB Campaigns"])
async def update_db_campaign(
    campaign_id: str,
    request: DBCampaignUpdate,
) -> DBCampaignResponse:
    """Update a campaign."""
    async with get_session() as session:
        service = RecallService(session)

        updates = request.model_dump(exclude_unset=True)
        campaign = await service.update_campaign(UUID(campaign_id), **updates)

        if not campaign:
            raise HTTPException(status_code=404, detail="Campaign not found")

        return DBCampaignResponse(**campaign.to_dict())


@router.delete("/campaigns/db/{campaign_id}", tags=["DB Campaigns"])
async def delete_db_campaign(campaign_id: str) -> dict[str, Any]:
    """Delete a campaign and all related data."""
    async with get_session() as session:
        service = RecallService(session)

        success = await service.delete_campaign(UUID(campaign_id))
        if not success:
            raise HTTPException(status_code=404, detail="Campaign not found")

        return {"deleted": True, "campaign_id": campaign_id}


# Campaign Status Management

@router.post("/campaigns/db/{campaign_id}/activate", response_model=DBCampaignResponse, tags=["DB Campaigns"])
async def activate_db_campaign(campaign_id: str) -> DBCampaignResponse:
    """Activate a draft campaign."""
    async with get_session() as session:
        service = RecallService(session)

        try:
            campaign = await service.activate_campaign(UUID(campaign_id))
            if not campaign:
                raise HTTPException(status_code=404, detail="Campaign not found")
            return DBCampaignResponse(**campaign.to_dict())
        except RecallServiceError as e:
            raise HTTPException(status_code=400, detail=str(e))


@router.post("/campaigns/db/{campaign_id}/pause", response_model=DBCampaignResponse, tags=["DB Campaigns"])
async def pause_db_campaign(campaign_id: str) -> DBCampaignResponse:
    """Pause an active campaign."""
    async with get_session() as session:
        service = RecallService(session)

        try:
            campaign = await service.pause_campaign(UUID(campaign_id))
            if not campaign:
                raise HTTPException(status_code=404, detail="Campaign not found")
            return DBCampaignResponse(**campaign.to_dict())
        except RecallServiceError as e:
            raise HTTPException(status_code=400, detail=str(e))


@router.post("/campaigns/db/{campaign_id}/resume", response_model=DBCampaignResponse, tags=["DB Campaigns"])
async def resume_db_campaign(campaign_id: str) -> DBCampaignResponse:
    """Resume a paused campaign."""
    async with get_session() as session:
        service = RecallService(session)

        try:
            campaign = await service.resume_campaign(UUID(campaign_id))
            if not campaign:
                raise HTTPException(status_code=404, detail="Campaign not found")
            return DBCampaignResponse(**campaign.to_dict())
        except RecallServiceError as e:
            raise HTTPException(status_code=400, detail=str(e))


@router.post("/campaigns/db/{campaign_id}/complete", response_model=DBCampaignResponse, tags=["DB Campaigns"])
async def complete_db_campaign(campaign_id: str) -> DBCampaignResponse:
    """Mark a campaign as completed."""
    async with get_session() as session:
        service = RecallService(session)

        campaign = await service.complete_campaign(UUID(campaign_id))
        if not campaign:
            raise HTTPException(status_code=404, detail="Campaign not found")

        return DBCampaignResponse(**campaign.to_dict())


# Contact Management Endpoints

@router.post("/campaigns/db/{campaign_id}/contacts", response_model=DBContactResponse, tags=["DB Campaign Contacts"])
async def add_campaign_contact(
    campaign_id: str,
    request: DBContactAdd,
) -> DBContactResponse:
    """Add a single contact to a campaign."""
    async with get_session() as session:
        service = RecallService(session)

        try:
            contact = await service.add_contact(
                campaign_id=UUID(campaign_id),
                contact_id=UUID(request.contact_id),
                phone_number=request.phone_number,
                contact_name=request.contact_name,
                priority=request.priority,
                custom_data=request.custom_data,
            )
            return DBContactResponse(**contact.to_dict())
        except RecallServiceError as e:
            raise HTTPException(status_code=404, detail=str(e))


@router.post("/campaigns/db/{campaign_id}/contacts/bulk", tags=["DB Campaign Contacts"])
async def add_campaign_contacts_bulk(
    campaign_id: str,
    request: DBContactBulkAdd,
) -> dict[str, Any]:
    """Add multiple contacts to a campaign."""
    async with get_session() as session:
        service = RecallService(session)

        contacts_data = [
            {
                "contact_id": UUID(c.contact_id),
                "phone_number": c.phone_number,
                "contact_name": c.contact_name,
                "priority": c.priority,
                "custom_data": c.custom_data,
            }
            for c in request.contacts
        ]

        try:
            added = await service.add_contacts_bulk(UUID(campaign_id), contacts_data)
            return {"added": added, "campaign_id": campaign_id}
        except RecallServiceError as e:
            raise HTTPException(status_code=404, detail=str(e))


@router.get("/campaigns/db/{campaign_id}/contacts", response_model=list[DBContactResponse], tags=["DB Campaign Contacts"])
async def list_campaign_contacts(
    campaign_id: str,
    status: str | None = Query(default=None, description="Filter by status"),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> list[DBContactResponse]:
    """List contacts in a campaign."""
    async with get_session() as session:
        service = RecallService(session)

        contacts = await service.get_campaign_contacts(
            campaign_id=UUID(campaign_id),
            status=status,
            limit=limit,
            offset=offset,
        )

        return [DBContactResponse(**c.to_dict()) for c in contacts]


@router.get("/contacts/db/{contact_id}", response_model=DBContactResponse, tags=["DB Campaign Contacts"])
async def get_campaign_contact(contact_id: str) -> DBContactResponse:
    """Get a specific campaign contact."""
    async with get_session() as session:
        service = RecallService(session)

        contact = await service.get_contact(UUID(contact_id))
        if not contact:
            raise HTTPException(status_code=404, detail="Contact not found")

        return DBContactResponse(**contact.to_dict())


@router.delete("/contacts/db/{contact_id}", tags=["DB Campaign Contacts"])
async def remove_campaign_contact(contact_id: str) -> dict[str, Any]:
    """Remove a contact from a campaign."""
    async with get_session() as session:
        service = RecallService(session)

        success = await service.remove_contact(UUID(contact_id))
        if not success:
            raise HTTPException(status_code=404, detail="Contact not found")

        return {"removed": True, "contact_id": contact_id}


@router.post("/contacts/db/{contact_id}/opt-out", response_model=DBContactResponse, tags=["DB Campaign Contacts"])
async def opt_out_campaign_contact(contact_id: str) -> DBContactResponse:
    """Mark a contact as opted out."""
    async with get_session() as session:
        service = RecallService(session)

        contact = await service.opt_out_contact(UUID(contact_id))
        if not contact:
            raise HTTPException(status_code=404, detail="Contact not found")

        return DBContactResponse(**contact.to_dict())


# Call Tracking Endpoints

@router.get("/contacts/db/due", response_model=list[DBContactResponse], tags=["DB Call Scheduling"])
async def get_contacts_to_call(
    campaign_id: str | None = Query(default=None, description="Filter by campaign"),
    limit: int = Query(default=10, ge=1, le=50),
) -> list[DBContactResponse]:
    """Get contacts that are due for calling."""
    async with get_session() as session:
        service = RecallService(session)

        campaign_uuid = UUID(campaign_id) if campaign_id else None
        contacts = await service.get_contacts_to_call(limit=limit, campaign_id=campaign_uuid)

        return [DBContactResponse(**c.to_dict()) for c in contacts]


@router.post("/contacts/db/{contact_id}/attempt", response_model=DBContactResponse, tags=["DB Call Scheduling"])
async def record_call_attempt(
    contact_id: str,
    request: DBAttemptRecord,
) -> DBContactResponse:
    """Record a call attempt result."""
    async with get_session() as session:
        service = RecallService(session)

        call_uuid = UUID(request.call_id) if request.call_id else None
        contact = await service.record_call_attempt(
            contact_id=UUID(contact_id),
            result=request.result,
            duration=request.duration,
            call_id=call_uuid,
            notes=request.notes,
        )

        if not contact:
            raise HTTPException(status_code=404, detail="Contact not found")

        return DBContactResponse(**contact.to_dict())


@router.post("/contacts/db/{contact_id}/convert", response_model=DBContactResponse, tags=["DB Call Scheduling"])
async def record_conversion(
    contact_id: str,
    request: DBConversionRecord,
) -> DBContactResponse:
    """Record a successful conversion."""
    async with get_session() as session:
        service = RecallService(session)

        appointment_uuid = UUID(request.appointment_id) if request.appointment_id else None
        contact = await service.record_conversion(
            contact_id=UUID(contact_id),
            outcome=request.outcome,
            appointment_id=appointment_uuid,
            notes=request.notes,
        )

        if not contact:
            raise HTTPException(status_code=404, detail="Contact not found")

        return DBContactResponse(**contact.to_dict())


# Statistics Endpoints

@router.get("/campaigns/db/{campaign_id}/stats", tags=["DB Campaigns"])
async def get_db_campaign_stats(campaign_id: str) -> dict[str, Any]:
    """Get comprehensive campaign statistics."""
    async with get_session() as session:
        service = RecallService(session)

        stats = await service.get_campaign_stats(UUID(campaign_id))
        if not stats:
            raise HTTPException(status_code=404, detail="Campaign not found")

        return stats
