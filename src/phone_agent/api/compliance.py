"""DSGVO Compliance API Endpoints.

Provides API endpoints for consent management, audit trails,
call recording access, and appointment rescheduling.

DSGVO Articles Implemented:
- Art. 5: Principles (audit trails for accountability)
- Art. 6: Lawfulness of processing (consent verification)
- Art. 7: Conditions for consent (consent management)
- Art. 15: Right of access (audit log queries)
- Art. 30: Records of processing activities (audit log)
"""

from __future__ import annotations

import csv
import io
from datetime import datetime, date, time, timedelta, timezone
from enum import Enum
from typing import Any, Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from itf_shared import get_logger

from phone_agent.db import get_db
from phone_agent.db.models.compliance import ConsentModel, AuditLogModel
from phone_agent.db.repositories.compliance import (
    ConsentRepository,
    AuditLogRepository,
)
from phone_agent.db.repositories.contacts import ContactRepository
from phone_agent.db.repositories.calls import CallRepository
from phone_agent.db.repositories.appointments import AppointmentRepository
from phone_agent.services.compliance_service import (
    ComplianceService,
    ConsentNotFoundError,
)
from phone_agent.integrations.sms.factory import get_sms_gateway
from phone_agent.integrations.sms.base import SMSMessage

log = get_logger(__name__)

router = APIRouter()


# ============================================================================
# Enums
# ============================================================================


class ConsentType(str, Enum):
    """Supported consent types."""

    PHONE_CONTACT = "phone_contact"
    SMS_CONTACT = "sms_contact"
    EMAIL_CONTACT = "email_contact"
    AI_PROCESSING = "ai_processing"
    VOICE_RECORDING = "voice_recording"
    DATA_SHARING = "data_sharing"
    MARKETING = "marketing"


class ConsentStatus(str, Enum):
    """Consent status values."""

    GRANTED = "granted"
    DENIED = "denied"
    WITHDRAWN = "withdrawn"
    EXPIRED = "expired"
    PENDING = "pending"


# ============================================================================
# Pydantic Schemas - Consent
# ============================================================================


class ConsentCreate(BaseModel):
    """Request to record consent."""

    consent_type: ConsentType
    granted_by: str = "phone_agent"
    duration_days: int | None = Field(
        None, description="Consent duration in days (None = indefinite)"
    )
    version: str = "1.0"
    legal_text: str | None = Field(
        None, description="Legal text shown to obtain consent"
    )
    notes: str | None = None
    reference_id: UUID | None = None
    reference_type: str | None = None


class Consent(BaseModel):
    """Consent response schema."""

    id: UUID
    contact_id: UUID
    consent_type: str
    status: str
    is_valid: bool
    granted_at: datetime | None
    expires_at: datetime | None
    withdrawn_at: datetime | None
    granted_by: str | None
    version: str
    industry: str | None
    reference_id: UUID | None
    reference_type: str | None
    notes: str | None
    created_at: datetime | None
    updated_at: datetime | None

    model_config = {"from_attributes": True}

    @classmethod
    def from_model(cls, model: ConsentModel) -> "Consent":
        """Create schema from ORM model."""
        return cls(
            id=model.id,
            contact_id=model.contact_id,
            consent_type=model.consent_type,
            status=model.status,
            is_valid=model.is_valid(),
            granted_at=model.granted_at,
            expires_at=model.expires_at,
            withdrawn_at=model.withdrawn_at,
            granted_by=model.granted_by,
            version=model.version,
            industry=model.industry,
            reference_id=model.reference_id,
            reference_type=model.reference_type,
            notes=model.notes,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )


class ConsentListResponse(BaseModel):
    """List of consents for a contact."""

    consents: list[Consent]
    contact_id: UUID
    active_count: int
    expired_count: int
    withdrawn_count: int


# ============================================================================
# Pydantic Schemas - Audit Log
# ============================================================================


class AuditLogEntry(BaseModel):
    """Audit log entry response."""

    id: UUID
    timestamp: datetime
    action: str
    action_category: str | None
    actor_id: str
    actor_type: str
    resource_type: str
    resource_id: str | None
    contact_id: UUID | None
    details: dict[str, Any]
    ip_address: str | None
    session_id: str | None
    industry: str | None
    checksum_valid: bool

    model_config = {"from_attributes": True}

    @classmethod
    def from_model(cls, model: AuditLogModel) -> "AuditLogEntry":
        """Create schema from ORM model."""
        return cls(
            id=model.id,
            timestamp=model.timestamp,
            action=model.action,
            action_category=model.action_category,
            actor_id=model.actor_id,
            actor_type=model.actor_type,
            resource_type=model.resource_type,
            resource_id=model.resource_id,
            contact_id=model.contact_id,
            details=model.details,
            ip_address=model.ip_address,
            session_id=model.session_id,
            industry=model.industry,
            checksum_valid=model.verify_checksum(),
        )


class AuditLogListResponse(BaseModel):
    """Paginated audit log response."""

    entries: list[AuditLogEntry]
    total: int
    page: int
    page_size: int


class AuditIntegrityResponse(BaseModel):
    """Audit log integrity check response."""

    verified: bool
    total_checked: int
    valid_count: int
    invalid_count: int
    invalid_entries: list[str]
    broken_chains: list[dict[str, Any]]


# ============================================================================
# Pydantic Schemas - Recordings
# ============================================================================


class RecordingResponse(BaseModel):
    """Call recording access response."""

    call_id: UUID
    recording_url: str | None
    transcript: str | None
    duration_seconds: int | None
    recorded_at: datetime | None
    consent_verified: bool
    access_expires_at: datetime


# ============================================================================
# Pydantic Schemas - Reschedule
# ============================================================================


class RescheduleRequest(BaseModel):
    """Request to reschedule appointment."""

    new_date: date
    new_time: time
    reason: str | None = None
    notify_patient: bool = True


class RescheduleResponse(BaseModel):
    """Appointment reschedule response."""

    appointment_id: UUID
    previous_datetime: datetime
    new_datetime: datetime
    status: str
    notification_sent: bool
    audit_log_id: UUID


# ============================================================================
# Dependencies
# ============================================================================


async def get_consent_repository(
    session: Annotated[AsyncSession, Depends(get_db)],
) -> ConsentRepository:
    """Get consent repository instance."""
    return ConsentRepository(session)


async def get_audit_repository(
    session: Annotated[AsyncSession, Depends(get_db)],
) -> AuditLogRepository:
    """Get audit log repository instance."""
    return AuditLogRepository(session)


async def get_contact_repository(
    session: Annotated[AsyncSession, Depends(get_db)],
) -> ContactRepository:
    """Get contact repository instance."""
    return ContactRepository(session)


async def get_call_repository(
    session: Annotated[AsyncSession, Depends(get_db)],
) -> CallRepository:
    """Get call repository instance."""
    return CallRepository(session)


async def get_appointment_repository(
    session: Annotated[AsyncSession, Depends(get_db)],
) -> AppointmentRepository:
    """Get appointment repository instance."""
    return AppointmentRepository(session)


async def get_compliance_service(
    consent_repo: Annotated[ConsentRepository, Depends(get_consent_repository)],
    audit_repo: Annotated[AuditLogRepository, Depends(get_audit_repository)],
) -> ComplianceService:
    """Get compliance service instance."""
    return ComplianceService(consent_repo, audit_repo)


def get_client_ip(request: Request) -> str | None:
    """Extract client IP from request."""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client:
        return request.client.host
    return None


# ============================================================================
# Consent Management Endpoints
# ============================================================================


@router.post(
    "/contacts/{contact_id}/consent",
    response_model=Consent,
    status_code=201,
    tags=["Compliance"],
)
async def record_consent(
    contact_id: UUID,
    data: ConsentCreate,
    request: Request,
    service: Annotated[ComplianceService, Depends(get_compliance_service)],
    contact_repo: Annotated[ContactRepository, Depends(get_contact_repository)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> Consent:
    """Record patient consent for a specific purpose.

    DSGVO Reference: Art. 7 - Conditions for consent

    Args:
        contact_id: Contact UUID
        data: Consent creation data

    Returns:
        Created consent record
    """
    # Verify contact exists
    contact = await contact_repo.get(contact_id)
    if contact is None:
        raise HTTPException(status_code=404, detail="Contact not found")

    try:
        consent = await service.record_consent_with_audit(
            contact_id=contact_id,
            consent_type=data.consent_type.value,
            granted_by=data.granted_by,
            actor_id="api",
            actor_type="system",
            ip_address=get_client_ip(request),
            version=data.version,
            duration_days=data.duration_days,
            legal_text=data.legal_text,
            reference_id=data.reference_id,
            reference_type=data.reference_type,
            notes=data.notes,
            industry=contact.industry or "gesundheit",
        )

        await session.commit()
        return Consent.from_model(consent)

    except Exception as e:
        await session.rollback()
        log.exception("Failed to record consent")
        raise HTTPException(status_code=500, detail="Failed to record consent") from e


@router.get(
    "/contacts/{contact_id}/consent",
    response_model=ConsentListResponse,
    tags=["Compliance"],
)
async def get_consent_status(
    contact_id: UUID,
    request: Request,
    consent_repo: Annotated[ConsentRepository, Depends(get_consent_repository)],
    service: Annotated[ComplianceService, Depends(get_compliance_service)],
    contact_repo: Annotated[ContactRepository, Depends(get_contact_repository)],
    consent_type: ConsentType | None = None,
    include_expired: bool = False,
) -> ConsentListResponse:
    """Get consent status for a contact.

    DSGVO Reference: Art. 15 - Right of access

    Args:
        contact_id: Contact UUID
        consent_type: Optional filter by consent type
        include_expired: Include expired consents

    Returns:
        List of consent records
    """
    # Verify contact exists
    contact = await contact_repo.get(contact_id)
    if contact is None:
        raise HTTPException(status_code=404, detail="Contact not found")

    # Log access
    await service.log_data_access(
        actor_id="api",
        resource_type="consent",
        resource_id=None,
        contact_id=contact_id,
        action="consent_status_viewed",
        ip_address=get_client_ip(request),
        industry=contact.industry or "gesundheit",
    )

    # Get consents
    if include_expired:
        consents = await consent_repo.get_by_contact(contact_id)
    else:
        consents = await consent_repo.get_active_consents(contact_id)

    # Filter by type if specified
    if consent_type:
        consents = [c for c in consents if c.consent_type == consent_type.value]

    # Count by status
    counts = await consent_repo.count_by_contact(contact_id)

    return ConsentListResponse(
        consents=[Consent.from_model(c) for c in consents],
        contact_id=contact_id,
        active_count=counts.get("granted", 0),
        expired_count=counts.get("expired", 0),
        withdrawn_count=counts.get("withdrawn", 0),
    )


@router.delete(
    "/contacts/{contact_id}/consent",
    tags=["Compliance"],
)
async def revoke_consent(
    contact_id: UUID,
    consent_type: ConsentType,
    request: Request,
    service: Annotated[ComplianceService, Depends(get_compliance_service)],
    contact_repo: Annotated[ContactRepository, Depends(get_contact_repository)],
    session: Annotated[AsyncSession, Depends(get_db)],
    notes: str | None = None,
) -> dict[str, Any]:
    """Revoke (withdraw) consent for a specific purpose.

    DSGVO Reference: Art. 7(3) - Right to withdraw consent

    Args:
        contact_id: Contact UUID
        consent_type: Type of consent to revoke
        notes: Optional notes about revocation

    Returns:
        Status message
    """
    # Verify contact exists
    contact = await contact_repo.get(contact_id)
    if contact is None:
        raise HTTPException(status_code=404, detail="Contact not found")

    try:
        consent = await service.revoke_consent_with_audit(
            contact_id=contact_id,
            consent_type=consent_type.value,
            actor_id="api",
            actor_type="system",
            ip_address=get_client_ip(request),
            notes=notes,
            industry=contact.industry or "gesundheit",
        )

        await session.commit()

        return {
            "status": "withdrawn",
            "consent_id": str(consent.id),
            "consent_type": consent_type.value,
            "withdrawn_at": consent.withdrawn_at.isoformat() if consent.withdrawn_at else None,
        }

    except ConsentNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except Exception as e:
        await session.rollback()
        log.exception("Failed to revoke consent")
        raise HTTPException(status_code=500, detail="Failed to revoke consent") from e


# ============================================================================
# Audit Trail Endpoints
# ============================================================================


@router.get(
    "/audit-log",
    response_model=AuditLogListResponse,
    tags=["Compliance"],
)
async def query_audit_log(
    request: Request,
    audit_repo: Annotated[AuditLogRepository, Depends(get_audit_repository)],
    service: Annotated[ComplianceService, Depends(get_compliance_service)],
    start_date: datetime | None = None,
    end_date: datetime | None = None,
    actor_id: str | None = None,
    action: str | None = None,
    action_category: str | None = None,
    resource_type: str | None = None,
    contact_id: UUID | None = None,
    industry: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
) -> AuditLogListResponse:
    """Query audit log entries with filters.

    DSGVO Reference: Art. 30 - Records of processing activities

    Args:
        start_date: Start of date range
        end_date: End of date range
        actor_id: Filter by actor
        action: Filter by action
        action_category: Filter by category
        resource_type: Filter by resource type
        contact_id: Filter by contact
        industry: Filter by industry
        page: Page number
        page_size: Results per page

    Returns:
        Paginated audit log entries
    """
    # Default date range if not specified (use timezone-aware UTC)
    if start_date is None:
        start_date = datetime.now(timezone.utc) - timedelta(days=30)
    if end_date is None:
        end_date = datetime.now(timezone.utc)

    skip = (page - 1) * page_size

    # Log this access (meta-audit)
    await service.log_data_access(
        actor_id="api",
        resource_type="audit_log",
        resource_id=None,
        contact_id=contact_id,
        action="audit_log_queried",
        ip_address=get_client_ip(request),
        details={
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "filters": {
                "actor_id": actor_id,
                "action": action,
                "resource_type": resource_type,
            },
        },
    )

    # Get entries
    entries = await audit_repo.get_by_date_range(
        start=start_date,
        end=end_date,
        actor_id=actor_id,
        action=action,
        action_category=action_category,
        resource_type=resource_type,
        contact_id=contact_id,
        industry=industry,
        skip=skip,
        limit=page_size,
    )

    # Get total count
    total = await audit_repo.count_with_filters(
        start=start_date,
        end=end_date,
        actor_id=actor_id,
        action=action,
        action_category=action_category,
        resource_type=resource_type,
        contact_id=contact_id,
        industry=industry,
    )

    return AuditLogListResponse(
        entries=[AuditLogEntry.from_model(e) for e in entries],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get(
    "/audit-log/export",
    tags=["Compliance"],
)
async def export_audit_log(
    request: Request,
    audit_repo: Annotated[AuditLogRepository, Depends(get_audit_repository)],
    service: Annotated[ComplianceService, Depends(get_compliance_service)],
    format: str = Query("json", pattern="^(json|csv)$"),
    start_date: datetime | None = None,
    end_date: datetime | None = None,
    contact_id: UUID | None = None,
) -> Response:
    """Export audit log for compliance reporting.

    Args:
        format: Export format (json or csv)
        start_date: Start of date range
        end_date: End of date range
        contact_id: Optional contact filter

    Returns:
        JSON or CSV file download
    """
    # Default date range (use timezone-aware UTC)
    if start_date is None:
        start_date = datetime.now(timezone.utc) - timedelta(days=30)
    if end_date is None:
        end_date = datetime.now(timezone.utc)

    # Log export request
    await service.log_data_access(
        actor_id="api",
        resource_type="audit_log",
        resource_id=None,
        contact_id=contact_id,
        action="audit_log_exported",
        ip_address=get_client_ip(request),
        details={"format": format},
    )

    # Get entries
    entries = await audit_repo.get_by_date_range(
        start=start_date,
        end=end_date,
        contact_id=contact_id,
        limit=10000,  # Max export size
    )

    if format == "json":
        import json

        content = json.dumps(
            [e.to_dict() for e in entries],
            indent=2,
            ensure_ascii=False,
            default=str,
        )
        return Response(
            content=content,
            media_type="application/json",
            headers={
                "Content-Disposition": f"attachment; filename=audit_log_{datetime.now(timezone.utc).strftime('%Y%m%d')}.json"
            },
        )
    else:  # CSV
        output = io.StringIO()
        writer = csv.writer(output)

        # Header
        writer.writerow([
            "id",
            "timestamp",
            "action",
            "action_category",
            "actor_id",
            "actor_type",
            "resource_type",
            "resource_id",
            "contact_id",
            "ip_address",
            "industry",
            "checksum_valid",
        ])

        # Rows
        for entry in entries:
            writer.writerow([
                str(entry.id),
                entry.timestamp.isoformat(),
                entry.action,
                entry.action_category,
                entry.actor_id,
                entry.actor_type,
                entry.resource_type,
                entry.resource_id,
                str(entry.contact_id) if entry.contact_id else "",
                entry.ip_address or "",
                entry.industry or "",
                entry.verify_checksum(),
            ])

        content = output.getvalue()
        return Response(
            content=content,
            media_type="text/csv",
            headers={
                "Content-Disposition": f"attachment; filename=audit_log_{datetime.now(timezone.utc).strftime('%Y%m%d')}.csv"
            },
        )


@router.get(
    "/audit-log/integrity",
    response_model=AuditIntegrityResponse,
    tags=["Compliance"],
)
async def verify_audit_integrity(
    request: Request,
    audit_repo: Annotated[AuditLogRepository, Depends(get_audit_repository)],
    service: Annotated[ComplianceService, Depends(get_compliance_service)],
    sample_size: int = Query(100, ge=10, le=1000),
) -> AuditIntegrityResponse:
    """Verify audit log chain integrity.

    Checks checksum chain for tamper detection.

    Args:
        sample_size: Number of entries to verify

    Returns:
        Integrity verification result
    """
    # Log integrity check
    await service.log_data_access(
        actor_id="api",
        resource_type="audit_log",
        resource_id=None,
        contact_id=None,
        action="audit_integrity_verified",
        ip_address=get_client_ip(request),
        details={"sample_size": sample_size},
    )

    result = await audit_repo.verify_chain_integrity(sample_size)

    return AuditIntegrityResponse(**result)


# ============================================================================
# Call Recording Access Endpoints
# ============================================================================


@router.get(
    "/calls/{call_id}/recording",
    response_model=RecordingResponse,
    tags=["Compliance"],
)
async def access_call_recording(
    call_id: UUID,
    request: Request,
    call_repo: Annotated[CallRepository, Depends(get_call_repository)],
    service: Annotated[ComplianceService, Depends(get_compliance_service)],
    reason: str = Query(..., min_length=10, description="Reason for accessing recording"),
) -> RecordingResponse:
    """Access call recording with consent verification.

    DSGVO Reference: Art. 6 - Lawfulness of processing

    Workflow:
    1. Verify the call exists
    2. Get contact_id from call
    3. Check contact has valid VOICE_RECORDING consent
    4. Log the access to audit trail
    5. Return recording URL/transcript

    Args:
        call_id: Call UUID
        reason: Reason for accessing recording (required, min 10 chars)

    Returns:
        Recording details with consent status
    """
    # Get call
    call = await call_repo.get(call_id)
    if call is None:
        raise HTTPException(status_code=404, detail="Call not found")

    # Check consent if contact exists
    consent_verified = True
    if call.contact_id:
        contact_uuid = UUID(call.contact_id) if isinstance(call.contact_id, str) else call.contact_id
        allowed, deny_reason = await service.verify_consent_for_recording_access(
            contact_id=contact_uuid,
            actor_id="api",
            ip_address=get_client_ip(request),
        )
        if not allowed:
            raise HTTPException(
                status_code=403,
                detail=f"Access denied: {deny_reason}"
            )
        consent_verified = True

    # Log the access
    await service.log_data_access(
        actor_id="api",
        resource_type="call_recording",
        resource_id=str(call_id),
        contact_id=UUID(call.contact_id) if call.contact_id else None,
        action="recording_accessed",
        ip_address=get_client_ip(request),
        details={"reason": reason},
    )

    # Calculate access expiry (URL valid for 1 hour)
    access_expires_at = datetime.now(timezone.utc) + timedelta(hours=1)

    return RecordingResponse(
        call_id=call_id,
        recording_url=call.recording_url if hasattr(call, "recording_url") else None,
        transcript=call.transcript if hasattr(call, "transcript") else None,
        duration_seconds=call.duration_seconds if hasattr(call, "duration_seconds") else None,
        recorded_at=call.started_at if hasattr(call, "started_at") else None,
        consent_verified=consent_verified,
        access_expires_at=access_expires_at,
    )


# ============================================================================
# Appointment Rescheduling Endpoints
# ============================================================================


@router.post(
    "/appointments/{appointment_id}/reschedule",
    response_model=RescheduleResponse,
    tags=["Compliance"],
)
async def reschedule_appointment(
    appointment_id: UUID,
    data: RescheduleRequest,
    request: Request,
    appointment_repo: Annotated[AppointmentRepository, Depends(get_appointment_repository)],
    service: Annotated[ComplianceService, Depends(get_compliance_service)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> RescheduleResponse:
    """Reschedule an appointment with full audit trail.

    DSGVO Reference: Art. 5(1)(e) - Storage limitation

    Workflow:
    1. Verify appointment exists and is reschedulable
    2. Check for slot conflicts at new time
    3. Store old date/time for audit
    4. Update appointment
    5. Log to audit trail with before/after details
    6. Optionally send notification (if consent exists)

    Args:
        appointment_id: Appointment UUID
        data: Reschedule request data

    Returns:
        Reschedule confirmation with audit ID
    """
    # Get appointment
    appointment = await appointment_repo.get(appointment_id)
    if appointment is None:
        raise HTTPException(status_code=404, detail="Appointment not found")

    # Check if reschedulable
    if appointment.status in ("completed", "cancelled", "no_show"):
        raise HTTPException(
            status_code=400,
            detail=f"Cannot reschedule appointment with status: {appointment.status}"
        )

    # Store previous values
    previous_date = appointment.date
    previous_time = appointment.time
    previous_datetime = datetime.combine(previous_date, previous_time)

    # Create new datetime
    new_datetime = datetime.combine(data.new_date, data.new_time)

    # Check for conflicts at new time
    conflicts = await appointment_repo.check_slot_availability(
        provider_id=appointment.provider_id,
        date=data.new_date,
        time=data.new_time,
        duration_minutes=appointment.duration_minutes,
        exclude_id=appointment_id,
    )

    if not conflicts:  # conflicts returns True if available
        raise HTTPException(
            status_code=409,
            detail="Time slot not available - conflict with existing appointment"
        )

    # Update appointment
    appointment.date = data.new_date
    appointment.time = data.new_time
    appointment.status = "rescheduled"
    if data.reason:
        appointment.notes = f"{appointment.notes or ''}\nRescheduled: {data.reason}".strip()

    await session.flush()

    # Create audit log entry
    contact_id = UUID(appointment.contact_id) if appointment.contact_id else None
    audit_entry = await service.log_data_access(
        actor_id="api",
        resource_type="appointment",
        resource_id=str(appointment_id),
        contact_id=contact_id,
        action="appointment_rescheduled",
        ip_address=get_client_ip(request),
        details={
            "previous_datetime": previous_datetime.isoformat(),
            "new_datetime": new_datetime.isoformat(),
            "reason": data.reason,
            "notify_patient": data.notify_patient,
        },
    )

    await session.commit()

    # Send notification if requested and consent exists
    notification_sent = False
    if data.notify_patient and contact_id:
        # Check SMS consent
        has_sms_consent = await service.verify_consent(contact_id, "sms_contact")
        if has_sms_consent:
            try:
                # Get contact phone number
                contact_repo = ContactRepository(session)
                contact = await contact_repo.get(contact_id)

                if contact and contact.phone_primary:
                    # Format dates in German style
                    date_str = data.new_date.strftime("%d.%m.%Y")
                    time_str = data.new_time.strftime("%H:%M")

                    # Build notification message
                    message_body = (
                        f"Terminänderung\n\n"
                        f"Guten Tag{' ' + contact.first_name if contact.first_name else ''},\n"
                        f"Ihr Termin wurde verschoben auf:\n"
                        f"{date_str} um {time_str} Uhr\n\n"
                        f"Bei Rückfragen rufen Sie uns bitte an.\n"
                        f"Vielen Dank!"
                    )

                    # Send SMS
                    gateway = get_sms_gateway()
                    sms_message = SMSMessage(
                        to=contact.phone_primary,
                        body=message_body,
                        reference=f"reschedule_{appointment_id}",
                    )
                    result = await gateway.send(sms_message)

                    if result.success:
                        notification_sent = True
                        log.info(
                            "Reschedule notification sent",
                            appointment_id=str(appointment_id),
                            contact_id=str(contact_id),
                            message_id=result.message_id,
                        )
                    else:
                        log.error(
                            "Failed to send reschedule notification",
                            appointment_id=str(appointment_id),
                            contact_id=str(contact_id),
                            error=result.error_message,
                        )
                else:
                    log.warning(
                        "Cannot send notification - contact has no phone",
                        contact_id=str(contact_id),
                    )
            except Exception as e:
                log.error(
                    "Error sending reschedule notification",
                    appointment_id=str(appointment_id),
                    contact_id=str(contact_id),
                    error=str(e),
                )
        else:
            log.info(
                "No SMS consent for reschedule notification",
                contact_id=str(contact_id),
            )

    return RescheduleResponse(
        appointment_id=appointment_id,
        previous_datetime=previous_datetime,
        new_datetime=new_datetime,
        status="rescheduled",
        notification_sent=notification_sent,
        audit_log_id=audit_entry.id,
    )


# ============================================================================
# DSGVO Data Subject Rights (Art. 15-22)
# ============================================================================


class DataAccessRequest(BaseModel):
    """Request for data access (Art. 15 DSGVO)."""

    contact_id: UUID = Field(..., description="Contact/Patient ID")
    format: str = Field(default="json", description="Export format: json or csv")
    include_audit_logs: bool = Field(default=True, description="Include audit trail")
    include_calls: bool = Field(default=True, description="Include call records")
    include_appointments: bool = Field(default=True, description="Include appointments")
    include_consents: bool = Field(default=True, description="Include consent history")
    include_sms: bool = Field(default=True, description="Include SMS messages")


class DataAccessResponse(BaseModel):
    """Response for data access request."""

    request_id: UUID
    contact_id: UUID
    generated_at: datetime
    format: str
    data: dict[str, Any] | None = None
    download_url: str | None = None


class ErasureRequest(BaseModel):
    """Request for data erasure (Art. 17 DSGVO)."""

    contact_id: UUID = Field(..., description="Contact/Patient ID")
    reason: str | None = Field(None, description="Reason for erasure request")
    verify_legal_holds: bool = Field(default=True, description="Check for legal retention requirements")


class ErasureResponse(BaseModel):
    """Response for erasure request."""

    request_id: UUID
    contact_id: UUID
    status: str  # "completed", "partial", "denied", "pending"
    erased_records: dict[str, int]
    retained_records: dict[str, int]
    retention_reasons: list[str]
    completed_at: datetime | None = None


class PortabilityRequest(BaseModel):
    """Request for data portability (Art. 20 DSGVO)."""

    contact_id: UUID = Field(..., description="Contact/Patient ID")
    format: str = Field(default="json", description="Export format: json")


class PortabilityResponse(BaseModel):
    """Response for data portability request."""

    request_id: UUID
    contact_id: UUID
    format: str
    generated_at: datetime
    file_size_bytes: int
    download_url: str | None = None
    data: dict[str, Any] | None = None


@router.post(
    "/compliance/data-access",
    response_model=DataAccessResponse,
    summary="Request data access (Art. 15 DSGVO)",
    description="""
    Submit a request for access to all personal data held about a contact.

    DSGVO Article 15 - Right of access by the data subject:
    The data subject shall have the right to obtain confirmation as to whether
    personal data are being processed and access to the personal data.

    Returns all personal data in requested format (JSON or CSV).
    """
)
async def request_data_access(
    request: Request,
    data: DataAccessRequest,
    session: AsyncSession = Depends(get_db),
) -> DataAccessResponse:
    """Process data access request under Art. 15 DSGVO."""
    request_id = uuid4()

    # Log the access request
    service = ComplianceService(session)
    await service.log_data_access(
        actor_id="api",
        resource_type="data_access_request",
        resource_id=str(request_id),
        contact_id=data.contact_id,
        action="data_access_requested",
        ip_address=get_client_ip(request),
        details={"format": data.format, "request_id": str(request_id)},
    )

    # Gather all data
    export_data: dict[str, Any] = {
        "request_id": str(request_id),
        "contact_id": str(data.contact_id),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "data_categories": [],
    }

    # Get contact information
    contact_repo = ContactRepository(session)
    contact = await contact_repo.get(data.contact_id)

    if not contact:
        raise HTTPException(status_code=404, detail="Contact not found")

    export_data["personal_data"] = {
        "first_name": contact.first_name,
        "last_name": contact.last_name,
        "phone_primary": contact.phone_primary,
        "phone_secondary": contact.phone_secondary,
        "email": contact.email,
        "date_of_birth": contact.date_of_birth.isoformat() if contact.date_of_birth else None,
        "address": contact.address,
        "city": contact.city,
        "postal_code": contact.postal_code,
        "notes": contact.notes,
        "created_at": contact.created_at.isoformat() if contact.created_at else None,
    }
    export_data["data_categories"].append("personal_data")

    # Get consent history
    if data.include_consents:
        consent_repo = ConsentRepository(session)
        consents = await consent_repo.get_by_contact(data.contact_id)
        export_data["consents"] = [c.to_dict() for c in consents]
        export_data["data_categories"].append("consents")

    # Get call records
    if data.include_calls:
        call_repo = CallRepository(session)
        calls = await call_repo.get_by_contact(data.contact_id, limit=1000)
        export_data["calls"] = [
            {
                "id": str(c.id),
                "direction": c.direction,
                "status": c.status,
                "duration": c.duration,
                "created_at": c.created_at.isoformat() if c.created_at else None,
                "summary": c.summary,
            }
            for c in calls
        ]
        export_data["data_categories"].append("calls")

    # Get appointments
    if data.include_appointments:
        appt_repo = AppointmentRepository(session)
        appointments = await appt_repo.get_by_contact(data.contact_id, limit=1000)
        export_data["appointments"] = [a.to_dict() for a in appointments]
        export_data["data_categories"].append("appointments")

    # Get audit logs
    if data.include_audit_logs:
        audit_repo = AuditLogRepository(session)
        logs = await audit_repo.get_by_contact(data.contact_id, limit=1000)
        export_data["audit_logs"] = [l.to_dict() for l in logs]
        export_data["data_categories"].append("audit_logs")

    # Get SMS messages
    if data.include_sms:
        try:
            from phone_agent.db.repositories.sms import SMSRepository
            sms_repo = SMSRepository(session)
            messages = await sms_repo.get_by_contact(data.contact_id, limit=1000)
            export_data["sms_messages"] = [m.to_dict() for m in messages]
            export_data["data_categories"].append("sms_messages")
        except Exception:
            pass  # SMS module may not exist

    await session.commit()

    return DataAccessResponse(
        request_id=request_id,
        contact_id=data.contact_id,
        generated_at=datetime.now(timezone.utc),
        format=data.format,
        data=export_data,
    )


@router.post(
    "/compliance/data-erasure",
    response_model=ErasureResponse,
    summary="Request data erasure (Art. 17 DSGVO)",
    description="""
    Submit a request for erasure of all personal data (Right to be forgotten).

    DSGVO Article 17 - Right to erasure:
    The data subject shall have the right to obtain erasure of personal data
    without undue delay where certain grounds apply.

    Note: Some data may be retained due to legal requirements (e.g., medical records
    for 10 years under German law). Retained data will be anonymized where possible.
    """
)
async def request_data_erasure(
    request: Request,
    data: ErasureRequest,
    session: AsyncSession = Depends(get_db),
) -> ErasureResponse:
    """Process data erasure request under Art. 17 DSGVO."""
    request_id = uuid4()

    # Log the erasure request
    service = ComplianceService(session)
    await service.log_data_access(
        actor_id="api",
        resource_type="data_erasure_request",
        resource_id=str(request_id),
        contact_id=data.contact_id,
        action="data_erasure_requested",
        ip_address=get_client_ip(request),
        details={"reason": data.reason, "request_id": str(request_id)},
    )

    # Check contact exists
    contact_repo = ContactRepository(session)
    contact = await contact_repo.get(data.contact_id)

    if not contact:
        raise HTTPException(status_code=404, detail="Contact not found")

    erased_records: dict[str, int] = {}
    retained_records: dict[str, int] = {}
    retention_reasons: list[str] = []

    # Check for legal holds (medical records = 10 years)
    if data.verify_legal_holds:
        # Check for recent medical appointments (within 10 years)
        appt_repo = AppointmentRepository(session)
        recent_cutoff = datetime.now(timezone.utc) - timedelta(days=10 * 365)

        appointments = await appt_repo.get_by_contact(data.contact_id, limit=1000)
        medical_appointments = [
            a for a in appointments
            if a.created_at and a.created_at > recent_cutoff
        ]

        if medical_appointments:
            retained_records["appointments"] = len(medical_appointments)
            retention_reasons.append(
                f"§ 630f BGB: {len(medical_appointments)} Termine müssen für 10 Jahre aufbewahrt werden"
            )

    # Anonymize contact data (keep structure but remove PII)
    original_data = {
        "first_name": contact.first_name,
        "last_name": contact.last_name,
        "phone_primary": contact.phone_primary,
        "email": contact.email,
    }

    contact.first_name = "[GELÖSCHT]"
    contact.last_name = "[GELÖSCHT]"
    contact.phone_primary = None
    contact.phone_secondary = None
    contact.email = None
    contact.date_of_birth = None
    contact.address = None
    contact.city = None
    contact.postal_code = None
    contact.notes = "[DATEN GELÖSCHT - Art. 17 DSGVO]"

    erased_records["personal_data"] = 1

    # Delete SMS messages (no legal retention requirement)
    try:
        from phone_agent.db.models.sms import SMSMessageModel
        from sqlalchemy import delete as sql_delete

        sms_result = await session.execute(
            sql_delete(SMSMessageModel).where(SMSMessageModel.contact_id == data.contact_id)
        )
        erased_records["sms_messages"] = sms_result.rowcount
    except Exception:
        pass

    # Anonymize call transcripts (keep call records for statistics)
    try:
        from phone_agent.db.models import CallModel
        from sqlalchemy import update

        call_result = await session.execute(
            update(CallModel)
            .where(CallModel.contact_id == data.contact_id)
            .values(transcript=None, summary="[GELÖSCHT]")
        )
        erased_records["call_transcripts"] = call_result.rowcount
    except Exception:
        pass

    # Withdraw all consents
    consent_repo = ConsentRepository(session)
    consents = await consent_repo.get_by_contact(data.contact_id)
    for consent in consents:
        if consent.status == "granted":
            consent.withdraw(notes="Art. 17 DSGVO - Löschantrag")
    erased_records["consents_withdrawn"] = len(consents)

    # Log the completed erasure
    await service.log_data_access(
        actor_id="api",
        resource_type="data_erasure_completed",
        resource_id=str(request_id),
        contact_id=data.contact_id,
        action="data_erasure_completed",
        ip_address=get_client_ip(request),
        details={
            "erased": erased_records,
            "retained": retained_records,
            "retention_reasons": retention_reasons,
        },
    )

    await session.commit()

    return ErasureResponse(
        request_id=request_id,
        contact_id=data.contact_id,
        status="completed" if not retained_records else "partial",
        erased_records=erased_records,
        retained_records=retained_records,
        retention_reasons=retention_reasons,
        completed_at=datetime.now(timezone.utc),
    )


@router.post(
    "/compliance/data-portability",
    response_model=PortabilityResponse,
    summary="Request data portability (Art. 20 DSGVO)",
    description="""
    Request personal data in a portable, machine-readable format.

    DSGVO Article 20 - Right to data portability:
    The data subject shall have the right to receive personal data in a
    structured, commonly used and machine-readable format.

    Returns all data provided by the data subject in JSON format.
    """
)
async def request_data_portability(
    request: Request,
    data: PortabilityRequest,
    session: AsyncSession = Depends(get_db),
) -> PortabilityResponse:
    """Process data portability request under Art. 20 DSGVO."""
    request_id = uuid4()

    # Log the portability request
    service = ComplianceService(session)
    await service.log_data_access(
        actor_id="api",
        resource_type="data_portability_request",
        resource_id=str(request_id),
        contact_id=data.contact_id,
        action="data_portability_requested",
        ip_address=get_client_ip(request),
        details={"format": data.format, "request_id": str(request_id)},
    )

    # Get contact
    contact_repo = ContactRepository(session)
    contact = await contact_repo.get(data.contact_id)

    if not contact:
        raise HTTPException(status_code=404, detail="Contact not found")

    # Build portable data package (only data provided by data subject)
    portable_data = {
        "meta": {
            "format": "DSGVO_Art20_Export",
            "version": "1.0",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "contact_id": str(data.contact_id),
        },
        "personal_information": {
            "first_name": contact.first_name,
            "last_name": contact.last_name,
            "phone_primary": contact.phone_primary,
            "phone_secondary": contact.phone_secondary,
            "email": contact.email,
            "date_of_birth": contact.date_of_birth.isoformat() if contact.date_of_birth else None,
            "address": contact.address,
            "city": contact.city,
            "postal_code": contact.postal_code,
        },
        "consents": [],
        "appointments": [],
    }

    # Get consents (user-provided)
    consent_repo = ConsentRepository(session)
    consents = await consent_repo.get_by_contact(data.contact_id)
    portable_data["consents"] = [
        {
            "type": c.consent_type,
            "status": c.status,
            "granted_at": c.granted_at.isoformat() if c.granted_at else None,
        }
        for c in consents
    ]

    # Get appointments (user-initiated)
    appt_repo = AppointmentRepository(session)
    appointments = await appt_repo.get_by_contact(data.contact_id, limit=1000)
    portable_data["appointments"] = [
        {
            "date": a.date.isoformat() if a.date else None,
            "time": a.time.isoformat() if a.time else None,
            "type": a.appointment_type,
            "status": a.status,
            "reason": a.reason,
        }
        for a in appointments
    ]

    await session.commit()

    # Calculate size
    import json
    json_str = json.dumps(portable_data, ensure_ascii=False)
    file_size = len(json_str.encode('utf-8'))

    return PortabilityResponse(
        request_id=request_id,
        contact_id=data.contact_id,
        format=data.format,
        generated_at=datetime.now(timezone.utc),
        file_size_bytes=file_size,
        data=portable_data,
    )


@router.get(
    "/compliance/data-subject-rights",
    summary="Get data subject rights information (DSGVO Art. 15-22)",
    description="Returns information about available data subject rights in German and English."
)
async def get_data_subject_rights_info(
    language: str = Query(default="de", description="Language: de or en"),
) -> dict[str, Any]:
    """Get information about DSGVO data subject rights."""
    from phone_agent.industry.gesundheit.compliance import get_data_protection_service

    service = get_data_protection_service()
    rights_info = service.get_data_subject_rights_info(language)

    return {
        "language": language,
        "rights": rights_info,
        "endpoints": {
            "data_access": {
                "method": "POST",
                "path": "/api/v1/compliance/data-access",
                "description": "Request access to all personal data (Art. 15)",
            },
            "data_erasure": {
                "method": "POST",
                "path": "/api/v1/compliance/data-erasure",
                "description": "Request erasure of personal data (Art. 17)",
            },
            "data_portability": {
                "method": "POST",
                "path": "/api/v1/compliance/data-portability",
                "description": "Request data in portable format (Art. 20)",
            },
        },
    }
