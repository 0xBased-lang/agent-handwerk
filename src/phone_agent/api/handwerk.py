"""Handwerk (Trades) API endpoints."""
from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from phone_agent.db import get_db
from phone_agent.db.models import (
    AppointmentModel,
    ContactModel,
    JobModel,
    QuoteModel,
)
from phone_agent.db.models.handwerk import (
    JobStatus,
    JobUrgency,
    TradeCategory as DBTradeCategory,
    QuoteStatus,
)

from phone_agent.industry.handwerk import (
    # Triage
    get_triage_engine,
    TradeCategory,
    UrgencyLevel,
    JobIssue,
    CustomerContext,
    # Scheduling
    get_scheduling_service,
    JobType,
    TimeSlot,
    SchedulingPreferences,
    Customer,
    # Follow-up
    get_followup_service,
    FollowUpType,
    FollowUpStatus,
    # Technician
    get_technician_matcher,
    TechnicianQualification,
)


router = APIRouter(prefix="/handwerk", tags=["Handwerk"])


# ====================
# Request/Response Models
# ====================

class IssueInput(BaseModel):
    """Input model for a job issue."""

    description: str = Field(..., description="Issue description in German")
    category: str = Field(default="allgemein", description="Trade category")
    severity: int = Field(ge=1, le=10, default=5, description="Severity (1-10)")
    is_recurring: bool = Field(default=False, description="Is this a recurring issue")
    affects_safety: bool = Field(default=False, description="Does this affect safety")


class CustomerContextInput(BaseModel):
    """Input model for customer context."""

    is_commercial: bool = Field(default=False, description="Commercial customer")
    is_elderly: bool = Field(default=False, description="Elderly or vulnerable person")
    has_children: bool = Field(default=False, description="Has small children at home")
    property_type: str = Field(default="residential", description="Property type")
    has_maintenance_contract: bool = Field(default=False, description="Has maintenance contract")


class TriageRequest(BaseModel):
    """Request model for triage assessment."""

    free_text: str | None = Field(default=None, description="Customer's description in German")
    issues: list[IssueInput] = Field(default_factory=list, description="List of issues")
    customer: CustomerContextInput | None = Field(default=None, description="Customer context")


class TriageResponse(BaseModel):
    """Response model for triage assessment."""

    urgency: str
    urgency_display: str
    risk_score: float
    primary_concern: str
    recommended_action: str
    trade_category: str
    is_emergency: bool
    max_wait_hours: int | None
    requires_specialist: bool
    requires_permit: bool
    assessment_notes: list[str]
    extracted_issues: list[dict[str, Any]]


# Urgency level display names (German)
URGENCY_DISPLAY = {
    UrgencyLevel.SICHERHEIT: "Sicherheitsgefährdung - Sofort Notdienst",
    UrgencyLevel.DRINGEND: "Dringend - Heute noch",
    UrgencyLevel.NORMAL: "Normal - Innerhalb 1-3 Tagen",
    UrgencyLevel.ROUTINE: "Routine - Flexibler Termin",
}


# ====================
# Triage Endpoints
# ====================

@router.post("/triage", response_model=TriageResponse)
async def assess_triage(request: TriageRequest) -> TriageResponse:
    """
    Perform job triage assessment.

    Analyzes reported issues and customer context to determine urgency level
    and recommended action. Supports both structured issues and
    free-text description in German.
    """
    engine = get_triage_engine()

    # Convert input issues
    issues: list[JobIssue] = []
    for issue in request.issues:
        try:
            category = TradeCategory(issue.category)
        except ValueError:
            category = TradeCategory.ALLGEMEIN

        issues.append(JobIssue(
            description=issue.description,
            category=category,
            severity=issue.severity,
            is_recurring=issue.is_recurring,
            affects_safety=issue.affects_safety,
        ))

    # Convert customer context
    customer = None
    if request.customer:
        customer = CustomerContext(
            is_commercial=request.customer.is_commercial,
            is_elderly=request.customer.is_elderly,
            has_children=request.customer.has_children,
            property_type=request.customer.property_type,
            has_maintenance_contract=request.customer.has_maintenance_contract,
        )

    # Extract issues from free text if provided
    extracted = []
    if request.free_text:
        extracted = engine.extract_issues_from_text(request.free_text)
        issues.extend(extracted)

    # Perform triage
    result = engine.assess(
        issues=issues,
        customer=customer,
        free_text=request.free_text,
    )

    return TriageResponse(
        urgency=result.urgency.value,
        urgency_display=URGENCY_DISPLAY.get(result.urgency, result.urgency.value),
        risk_score=result.risk_score,
        primary_concern=result.primary_concern,
        recommended_action=result.recommended_action,
        trade_category=result.trade_category.value if result.trade_category else "allgemein",
        is_emergency=result.is_emergency,
        max_wait_hours=result.max_wait_hours,
        requires_specialist=result.requires_specialist,
        requires_permit=result.requires_permit,
        assessment_notes=result.assessment_notes,
        extracted_issues=[i.to_dict() for i in extracted],
    )


@router.post("/triage/extract-issues")
async def extract_issues(text: str = Query(..., description="German text to analyze")) -> list[dict[str, Any]]:
    """
    Extract job issues from free-text description.

    Analyzes German text to identify mentioned problems and their categories.
    """
    engine = get_triage_engine()
    issues = engine.extract_issues_from_text(text)
    return [i.to_dict() for i in issues]


@router.get("/triage/categories")
async def get_trade_categories() -> list[dict[str, str]]:
    """Get available trade categories."""
    return [
        {"value": cat.value, "name": cat.name}
        for cat in TradeCategory
    ]


@router.get("/urgency-levels")
async def get_urgency_levels() -> list[dict[str, Any]]:
    """Get urgency levels with descriptions."""
    return [
        {
            "value": level.value,
            "name": level.name,
            "display": URGENCY_DISPLAY.get(level, level.value),
        }
        for level in UrgencyLevel
    ]


# ====================
# Follow-up Campaign Endpoints
# ====================

class CampaignCreateRequest(BaseModel):
    """Request model for creating a follow-up campaign."""

    followup_type: str = Field(..., description="Type of follow-up campaign")
    name: str | None = Field(default=None, description="Campaign name")
    description: str | None = Field(default=None, description="Campaign description")
    target_trade_category: str | None = Field(default=None, description="Target trade category")
    max_attempts: int = Field(default=3, ge=1, le=10, description="Maximum contact attempts")
    days_between_attempts: int = Field(default=3, ge=1, le=30, description="Days between attempts")


class CustomerAddRequest(BaseModel):
    """Request model for adding a customer to a campaign."""

    customer_id: str = Field(..., description="Customer UUID")
    first_name: str = Field(..., description="First name")
    last_name: str = Field(..., description="Last name")
    phone: str = Field(..., description="Phone number")
    company_name: str | None = Field(default=None, description="Company name")
    email: str | None = Field(default=None, description="Email address")
    address: str | None = Field(default=None, description="Service address")
    last_service_date: date | None = Field(default=None, description="Last service date")
    last_service_type: str | None = Field(default=None, description="Last service type")
    equipment_info: str | None = Field(default=None, description="Equipment details")
    priority: int = Field(default=5, ge=0, le=10, description="Priority level")


@router.post("/followup/campaigns")
async def create_campaign(request: CampaignCreateRequest) -> dict[str, Any]:
    """
    Create a new follow-up campaign.

    Supports maintenance reminders, quote follow-ups, seasonal campaigns, and more.
    """
    service = get_followup_service()

    try:
        followup_type = FollowUpType(request.followup_type)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid follow-up type: {request.followup_type}"
        )

    trade_category = None
    if request.target_trade_category:
        try:
            trade_category = TradeCategory(request.target_trade_category)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid trade category: {request.target_trade_category}"
            )

    campaign = service.create_campaign(
        followup_type=followup_type,
        name=request.name,
        target_trade_category=trade_category,
        max_attempts=request.max_attempts,
        days_between_attempts=request.days_between_attempts,
    )

    return campaign.to_dict()


@router.post("/followup/campaigns/{campaign_id}/customers")
async def add_customer_to_campaign(
    campaign_id: str,
    request: CustomerAddRequest,
) -> dict[str, Any]:
    """Add a customer to a follow-up campaign."""
    service = get_followup_service()

    try:
        campaign_uuid = UUID(campaign_id)
        customer_uuid = UUID(request.customer_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid UUID format")

    try:
        customer = service.add_customer_to_campaign(
            campaign_id=campaign_uuid,
            customer_id=customer_uuid,
            first_name=request.first_name,
            last_name=request.last_name,
            phone=request.phone,
            company_name=request.company_name,
            email=request.email,
            address=request.address,
            last_service_date=request.last_service_date,
            last_service_type=request.last_service_type,
            equipment_info=request.equipment_info,
            priority=request.priority,
        )
        return customer.to_dict()
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/followup/campaigns/{campaign_id}/next-customer")
async def get_next_customer(campaign_id: str) -> dict[str, Any] | None:
    """Get next customer to contact in a campaign."""
    service = get_followup_service()

    try:
        campaign_uuid = UUID(campaign_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid campaign ID")

    customer = service.get_next_customer(campaign_id=campaign_uuid)
    if customer:
        return customer.to_dict()
    return None


@router.get("/followup/campaigns/{campaign_id}/stats")
async def get_campaign_stats(campaign_id: str) -> dict[str, Any]:
    """Get statistics for a follow-up campaign."""
    service = get_followup_service()

    try:
        campaign_uuid = UUID(campaign_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid campaign ID")

    try:
        stats = service.get_campaign_stats(campaign_uuid)
        return stats
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/followup/types")
async def get_followup_types() -> list[dict[str, str]]:
    """Get available follow-up campaign types."""
    return [
        {"value": ft.value, "name": ft.name}
        for ft in FollowUpType
    ]


@router.get("/followup/seasonal-recommendations")
async def get_seasonal_recommendations(
    month: int | None = Query(default=None, ge=1, le=12, description="Month (1-12)")
) -> list[dict[str, Any]]:
    """Get recommended seasonal campaigns for a month."""
    service = get_followup_service()
    recommendations = service.get_seasonal_campaigns_for_month(month)
    return recommendations


# ====================
# Scheduling Endpoints
# ====================

class SlotSearchRequest(BaseModel):
    """Request model for searching available slots."""

    job_type: str = Field(default="reparatur", description="Type of job")
    trade_category: str | None = Field(default=None, description="Trade category")
    urgency_max_wait_hours: int | None = Field(default=None, description="Max wait hours for urgent jobs")
    preferred_days: list[int] | None = Field(default=None, description="Preferred weekdays (0=Mon)")
    preferred_time_of_day: str | None = Field(default=None, description="vormittags/nachmittags")


class ServiceCallCreateRequest(BaseModel):
    """Request model for creating a service call."""

    slot_id: str = Field(..., description="Selected time slot ID")
    customer_id: str = Field(..., description="Customer UUID")
    first_name: str = Field(..., description="First name")
    last_name: str = Field(..., description="Last name")
    phone: str = Field(..., description="Phone number")
    street: str = Field(..., description="Street address")
    zip_code: str = Field(..., description="ZIP code")
    city: str = Field(..., description="City")
    problem_description: str = Field(..., description="Description of the problem")
    job_type: str = Field(default="reparatur", description="Type of job")
    access_info: str | None = Field(default=None, description="Access instructions")


@router.post("/scheduling/search-slots")
async def search_slots(request: SlotSearchRequest, limit: int = Query(default=5, ge=1, le=20)) -> list[dict[str, Any]]:
    """Search for available time slots."""
    service = get_scheduling_service()

    try:
        job_type = JobType(request.job_type)
    except ValueError:
        job_type = JobType.REPARATUR

    trade_category = None
    if request.trade_category:
        try:
            trade_category = TradeCategory(request.trade_category)
        except ValueError:
            pass

    prefs = SchedulingPreferences(
        job_type=job_type,
        trade_category=trade_category,
        urgency_max_wait_hours=request.urgency_max_wait_hours,
        preferred_days=request.preferred_days,
        preferred_time_of_day=request.preferred_time_of_day,
    )

    slots = service.find_slots(prefs, limit=limit)
    return [slot.to_dict() for slot in slots]


@router.post("/scheduling/book")
async def book_service_call(request: ServiceCallCreateRequest) -> dict[str, Any]:
    """Book a service call."""
    service = get_scheduling_service()

    try:
        slot_uuid = UUID(request.slot_id)
        customer_uuid = UUID(request.customer_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid UUID format")

    try:
        job_type = JobType(request.job_type)
    except ValueError:
        job_type = JobType.REPARATUR

    # Find the slot
    slot = service.get_slot_by_id(slot_uuid)
    if not slot:
        raise HTTPException(status_code=404, detail="Time slot not found")

    customer = Customer(
        id=customer_uuid,
        first_name=request.first_name,
        last_name=request.last_name,
        phone=request.phone,
        street=request.street,
        zip_code=request.zip_code,
        city=request.city,
    )

    service_call = service.book_service_call(
        slot=slot,
        customer=customer,
        problem_description=request.problem_description,
        job_type=job_type,
        access_info=request.access_info,
    )

    return service_call.to_dict()


@router.get("/scheduling/job-types")
async def get_job_types() -> list[dict[str, str]]:
    """Get available job types."""
    return [
        {"value": jt.value, "name": jt.name}
        for jt in JobType
    ]


# ====================
# Technician Endpoints
# ====================

class TechnicianSearchRequest(BaseModel):
    """Request model for searching technicians."""

    trade_category: str = Field(..., description="Required trade category")
    urgency: str = Field(default="normal", description="Urgency level")
    required_certifications: list[str] = Field(default_factory=list, description="Required certifications")
    location_zip: str | None = Field(default=None, description="Customer ZIP code")


@router.post("/technicians/search")
async def search_technicians(request: TechnicianSearchRequest, limit: int = Query(default=5, ge=1, le=20)) -> list[dict[str, Any]]:
    """Search for available technicians matching job requirements."""
    matcher = get_technician_matcher()

    try:
        trade_category = TradeCategory(request.trade_category)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid trade category: {request.trade_category}")

    try:
        urgency = UrgencyLevel(request.urgency)
    except ValueError:
        urgency = UrgencyLevel.NORMAL

    matches = matcher.find_matches(
        trade_category=trade_category,
        urgency=urgency,
        required_certifications=request.required_certifications,
        limit=limit,
    )

    return [m.to_dict() for m in matches]


@router.get("/technicians/qualifications")
async def get_technician_qualifications() -> list[dict[str, str]]:
    """Get available technician qualification levels."""
    return [
        {"value": q.value, "name": q.name}
        for q in TechnicianQualification
    ]


# ====================
# Service Call Management Endpoints
# ====================

class ServiceCallStatusUpdate(BaseModel):
    """Request model for updating service call status."""

    status: str = Field(..., description="New status: scheduled, en_route, arrived, in_progress, completed, cancelled")
    notes: str | None = Field(default=None, description="Status update notes")
    technician_notes: str | None = Field(default=None, description="Technician notes")
    parts_used: list[str] | None = Field(default=None, description="List of parts used")
    completion_time_minutes: int | None = Field(default=None, ge=0, description="Actual time spent")


@router.get("/service-calls/{service_call_id}")
async def get_service_call(service_call_id: str) -> dict[str, Any]:
    """Get details of a specific service call."""
    service = get_scheduling_service()

    try:
        call_uuid = UUID(service_call_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid service call ID")

    service_call = service.get_service_call_by_id(call_uuid)
    if not service_call:
        raise HTTPException(status_code=404, detail="Service call not found")

    return service_call.to_dict()


@router.patch("/service-calls/{service_call_id}")
async def update_service_call(
    service_call_id: str,
    update: ServiceCallStatusUpdate,
) -> dict[str, Any]:
    """Update service call status.

    Supports status transitions:
    - scheduled -> en_route, cancelled
    - en_route -> arrived, cancelled
    - arrived -> in_progress
    - in_progress -> completed
    """
    service = get_scheduling_service()

    try:
        call_uuid = UUID(service_call_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid service call ID")

    try:
        updated = service.update_service_call_status(
            service_call_id=call_uuid,
            status=update.status,
            notes=update.notes,
            technician_notes=update.technician_notes,
            parts_used=update.parts_used,
            completion_time_minutes=update.completion_time_minutes,
        )
        return updated.to_dict()
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ====================
# Customer History Endpoints
# ====================

@router.get("/customers/{customer_id}/history")
async def get_customer_history(
    customer_id: str,
    limit: int = Query(default=20, ge=1, le=100),
) -> dict[str, Any]:
    """Get service history for a customer.

    Returns:
        - List of past service calls
        - Equipment records
        - Follow-up campaigns
        - Total service statistics
    """
    service = get_scheduling_service()
    followup_service = get_followup_service()

    try:
        customer_uuid = UUID(customer_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid customer ID")

    # Get service call history
    service_calls = service.get_customer_service_calls(customer_uuid, limit=limit)

    # Get follow-up campaign participation
    campaigns = followup_service.get_customer_campaigns(customer_uuid)

    # Calculate statistics
    total_calls = len(service_calls)
    completed_calls = sum(1 for c in service_calls if c.status == "completed")
    total_spent_minutes = sum(
        c.completion_time_minutes or 0
        for c in service_calls
        if c.status == "completed"
    )

    return {
        "customer_id": customer_id,
        "statistics": {
            "total_service_calls": total_calls,
            "completed_calls": completed_calls,
            "total_service_time_minutes": total_spent_minutes,
            "first_service_date": service_calls[-1].scheduled_date.isoformat() if service_calls else None,
            "last_service_date": service_calls[0].scheduled_date.isoformat() if service_calls else None,
        },
        "service_calls": [c.to_dict() for c in service_calls],
        "campaigns": [c.to_dict() for c in campaigns],
    }


# ====================
# Equipment Tracking Endpoints
# ====================

class EquipmentCreateRequest(BaseModel):
    """Request model for adding equipment."""

    equipment_type: str = Field(..., description="Type of equipment (e.g., heizung, klimaanlage)")
    manufacturer: str | None = Field(default=None, description="Manufacturer name")
    model: str | None = Field(default=None, description="Model number")
    serial_number: str | None = Field(default=None, description="Serial number")
    installation_date: date | None = Field(default=None, description="Installation date")
    warranty_expiry: date | None = Field(default=None, description="Warranty expiry date")
    maintenance_interval_months: int | None = Field(default=None, ge=1, le=60, description="Maintenance interval")
    location: str | None = Field(default=None, description="Location in property")
    notes: str | None = Field(default=None, description="Additional notes")


class EquipmentUpdateRequest(BaseModel):
    """Request model for updating equipment."""

    last_maintenance_date: date | None = Field(default=None, description="Last maintenance date")
    next_maintenance_date: date | None = Field(default=None, description="Next scheduled maintenance")
    condition: str | None = Field(default=None, description="Current condition: good, fair, poor, needs_repair")
    notes: str | None = Field(default=None, description="Additional notes")
    is_active: bool | None = Field(default=None, description="Whether equipment is still in use")


@router.get("/customers/{customer_id}/equipment")
async def get_customer_equipment(customer_id: str) -> list[dict[str, Any]]:
    """Get all equipment registered for a customer."""
    service = get_scheduling_service()

    try:
        customer_uuid = UUID(customer_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid customer ID")

    equipment = service.get_customer_equipment(customer_uuid)
    return [e.to_dict() for e in equipment]


@router.post("/customers/{customer_id}/equipment")
async def add_customer_equipment(
    customer_id: str,
    request: EquipmentCreateRequest,
) -> dict[str, Any]:
    """Register new equipment for a customer."""
    service = get_scheduling_service()

    try:
        customer_uuid = UUID(customer_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid customer ID")

    equipment = service.add_customer_equipment(
        customer_id=customer_uuid,
        equipment_type=request.equipment_type,
        manufacturer=request.manufacturer,
        model=request.model,
        serial_number=request.serial_number,
        installation_date=request.installation_date,
        warranty_expiry=request.warranty_expiry,
        maintenance_interval_months=request.maintenance_interval_months,
        location=request.location,
        notes=request.notes,
    )

    return equipment.to_dict()


@router.patch("/customers/{customer_id}/equipment/{equipment_id}")
async def update_customer_equipment(
    customer_id: str,
    equipment_id: str,
    request: EquipmentUpdateRequest,
) -> dict[str, Any]:
    """Update equipment details."""
    service = get_scheduling_service()

    try:
        customer_uuid = UUID(customer_id)
        equipment_uuid = UUID(equipment_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid UUID format")

    try:
        equipment = service.update_equipment(
            customer_id=customer_uuid,
            equipment_id=equipment_uuid,
            last_maintenance_date=request.last_maintenance_date,
            next_maintenance_date=request.next_maintenance_date,
            condition=request.condition,
            notes=request.notes,
            is_active=request.is_active,
        )
        return equipment.to_dict()
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/customers/{customer_id}/equipment/maintenance-due")
async def get_maintenance_due(
    customer_id: str,
    days_ahead: int = Query(default=30, ge=1, le=365),
) -> list[dict[str, Any]]:
    """Get equipment that needs maintenance within specified days."""
    service = get_scheduling_service()

    try:
        customer_uuid = UUID(customer_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid customer ID")

    equipment = service.get_equipment_needing_maintenance(
        customer_id=customer_uuid,
        days_ahead=days_ahead,
    )

    return [e.to_dict() for e in equipment]


# ====================
# Calendar Endpoints (Database-backed)
# ====================

class CalendarEntry(BaseModel):
    """Calendar entry for display."""
    id: str
    type: str  # job, appointment
    title: str
    customer_name: str | None = None
    address: str | None = None
    date: date
    time: str | None = None
    duration_minutes: int = 60
    status: str
    urgency: str | None = None
    trade_category: str | None = None


@router.get("/calendar")
async def get_calendar(
    start_date: date = Query(..., description="Start date (inclusive)"),
    end_date: date = Query(..., description="End date (inclusive)"),
    technician_id: str | None = Query(default=None, description="Filter by technician"),
    trade_category: str | None = Query(default=None, description="Filter by trade"),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Get calendar entries for a date range.

    Returns jobs and appointments grouped by date.
    """
    # Build job query
    job_query = select(JobModel).where(
        and_(
            JobModel.scheduled_date >= start_date,
            JobModel.scheduled_date <= end_date,
            JobModel.is_deleted == False,
        )
    )

    if technician_id:
        try:
            tech_uuid = UUID(technician_id)
            job_query = job_query.where(JobModel.technician_id == tech_uuid)
        except ValueError:
            pass

    if trade_category:
        job_query = job_query.where(JobModel.trade_category == trade_category)

    job_query = job_query.order_by(JobModel.scheduled_date, JobModel.scheduled_time)

    result = await db.execute(job_query)
    jobs = result.scalars().all()

    # Group by date
    entries_by_date: dict[str, list[dict]] = {}
    for job in jobs:
        date_str = job.scheduled_date.isoformat() if job.scheduled_date else "unscheduled"
        if date_str not in entries_by_date:
            entries_by_date[date_str] = []

        # Get customer name
        customer_name = None
        if job.contact:
            customer_name = f"{job.contact.first_name} {job.contact.last_name}"

        entries_by_date[date_str].append({
            "id": str(job.id),
            "type": "job",
            "job_number": job.job_number,
            "title": job.title,
            "customer_name": customer_name,
            "address": f"{job.address_street} {job.address_number or ''}, {job.address_zip} {job.address_city}" if job.address_street else None,
            "date": job.scheduled_date.isoformat() if job.scheduled_date else None,
            "time": job.scheduled_time.strftime("%H:%M") if job.scheduled_time else None,
            "duration_minutes": job.estimated_duration_minutes or 60,
            "status": job.status,
            "urgency": job.urgency,
            "trade_category": job.trade_category,
        })

    return {
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "total_entries": sum(len(v) for v in entries_by_date.values()),
        "entries_by_date": entries_by_date,
    }


@router.get("/calendar/{date_str}")
async def get_day_schedule(
    date_str: str,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Get detailed schedule for a specific day."""
    try:
        target_date = date.fromisoformat(date_str)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD")

    # Get jobs for the day
    job_query = select(JobModel).where(
        and_(
            JobModel.scheduled_date == target_date,
            JobModel.is_deleted == False,
        )
    ).order_by(JobModel.scheduled_time)

    result = await db.execute(job_query)
    jobs = result.scalars().all()

    schedule = []
    for job in jobs:
        customer_name = None
        customer_phone = None
        if job.contact:
            customer_name = f"{job.contact.first_name} {job.contact.last_name}"
            customer_phone = job.contact.phone

        schedule.append({
            "id": str(job.id),
            "job_number": job.job_number,
            "title": job.title,
            "description": job.description,
            "customer": {
                "name": customer_name,
                "phone": customer_phone,
            },
            "address": {
                "street": job.address_street,
                "number": job.address_number,
                "zip": job.address_zip,
                "city": job.address_city,
            },
            "time": job.scheduled_time.strftime("%H:%M") if job.scheduled_time else None,
            "duration_minutes": job.estimated_duration_minutes or 60,
            "status": job.status,
            "urgency": job.urgency,
            "trade_category": job.trade_category,
            "technician_id": str(job.technician_id) if job.technician_id else None,
            "access_notes": job.access_notes,
            "customer_notes": job.customer_notes,
        })

    return {
        "date": target_date.isoformat(),
        "weekday": target_date.strftime("%A"),
        "total_jobs": len(schedule),
        "schedule": schedule,
    }


# ====================
# Jobs API (Database-backed)
# ====================

class JobCreateRequest(BaseModel):
    """Request model for creating a job."""
    title: str = Field(..., description="Job title/summary")
    description: str | None = Field(default=None, description="Detailed description")
    trade_category: str = Field(default="allgemein", description="Trade category")
    urgency: str = Field(default="normal", description="Urgency level")

    # Customer
    contact_id: str | None = Field(default=None, description="Existing customer UUID")
    customer_name: str | None = Field(default=None, description="Customer name (if new)")
    customer_phone: str | None = Field(default=None, description="Customer phone (if new)")

    # Location
    address_street: str | None = None
    address_number: str | None = None
    address_zip: str | None = None
    address_city: str | None = None
    property_type: str | None = None
    access_notes: str | None = None

    # Scheduling preferences
    preferred_date: date | None = None
    preferred_time_window: str | None = None

    # Notes
    customer_notes: str | None = None


class JobUpdateRequest(BaseModel):
    """Request model for updating a job."""
    title: str | None = None
    description: str | None = None
    status: str | None = None
    urgency: str | None = None
    technician_id: str | None = None
    scheduled_date: date | None = None
    scheduled_time: str | None = None  # HH:MM format
    estimated_duration_minutes: int | None = None
    estimated_cost: float | None = None
    actual_cost: float | None = None
    technician_notes: str | None = None
    internal_notes: str | None = None


def _generate_job_number() -> str:
    """Generate a unique job number."""
    now = datetime.now()
    return f"JOB-{now.year}-{now.strftime('%m%d%H%M%S')}"


@router.post("/jobs")
async def create_job(
    request: JobCreateRequest,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Create a new job/service request."""
    # Generate job number
    job_number = _generate_job_number()

    # Handle contact
    contact_id = None
    if request.contact_id:
        try:
            contact_id = UUID(request.contact_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid contact_id format")

    # Create job
    job = JobModel(
        id=uuid4(),
        job_number=job_number,
        title=request.title,
        description=request.description,
        trade_category=request.trade_category,
        urgency=request.urgency,
        status=JobStatus.REQUESTED,
        contact_id=contact_id,
        address_street=request.address_street,
        address_number=request.address_number,
        address_zip=request.address_zip,
        address_city=request.address_city,
        property_type=request.property_type,
        access_notes=request.access_notes,
        preferred_date=request.preferred_date,
        preferred_time_window=request.preferred_time_window,
        customer_notes=request.customer_notes,
    )

    db.add(job)
    await db.commit()
    await db.refresh(job)

    return job.to_dict()


@router.get("/jobs")
async def list_jobs(
    status: str | None = Query(default=None, description="Filter by status"),
    urgency: str | None = Query(default=None, description="Filter by urgency"),
    trade_category: str | None = Query(default=None, description="Filter by trade"),
    from_date: date | None = Query(default=None, description="Scheduled from date"),
    to_date: date | None = Query(default=None, description="Scheduled to date"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """List jobs with optional filters."""
    query = select(JobModel).where(JobModel.is_deleted == False)

    if status:
        query = query.where(JobModel.status == status)
    if urgency:
        query = query.where(JobModel.urgency == urgency)
    if trade_category:
        query = query.where(JobModel.trade_category == trade_category)
    if from_date:
        query = query.where(JobModel.scheduled_date >= from_date)
    if to_date:
        query = query.where(JobModel.scheduled_date <= to_date)

    query = query.order_by(JobModel.created_at.desc()).offset(offset).limit(limit)

    result = await db.execute(query)
    jobs = result.scalars().all()

    return {
        "jobs": [j.to_dict() for j in jobs],
        "count": len(jobs),
        "offset": offset,
        "limit": limit,
    }


@router.get("/jobs/{job_id}")
async def get_job(
    job_id: str,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Get detailed job information."""
    try:
        job_uuid = UUID(job_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid job ID")

    result = await db.execute(
        select(JobModel).where(
            and_(JobModel.id == job_uuid, JobModel.is_deleted == False)
        )
    )
    job = result.scalar_one_or_none()

    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    job_dict = job.to_dict()

    # Include quotes if any
    if job.quotes:
        job_dict["quotes"] = [q.to_dict() for q in job.quotes]

    return job_dict


@router.patch("/jobs/{job_id}")
async def update_job(
    job_id: str,
    request: JobUpdateRequest,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Update a job."""
    try:
        job_uuid = UUID(job_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid job ID")

    result = await db.execute(
        select(JobModel).where(
            and_(JobModel.id == job_uuid, JobModel.is_deleted == False)
        )
    )
    job = result.scalar_one_or_none()

    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    # Update fields
    if request.title is not None:
        job.title = request.title
    if request.description is not None:
        job.description = request.description
    if request.status is not None:
        job.status = request.status
        # Track completion
        if request.status == JobStatus.COMPLETED:
            job.completed_at = datetime.now()
        elif request.status == JobStatus.IN_PROGRESS:
            job.started_at = datetime.now()
    if request.urgency is not None:
        job.urgency = request.urgency
    if request.technician_id is not None:
        try:
            job.technician_id = UUID(request.technician_id)
        except ValueError:
            pass
    if request.scheduled_date is not None:
        job.scheduled_date = request.scheduled_date
    if request.scheduled_time is not None:
        from datetime import time as time_type
        try:
            parts = request.scheduled_time.split(":")
            job.scheduled_time = time_type(int(parts[0]), int(parts[1]))
        except (ValueError, IndexError):
            pass
    if request.estimated_duration_minutes is not None:
        job.estimated_duration_minutes = request.estimated_duration_minutes
    if request.estimated_cost is not None:
        job.estimated_cost = Decimal(str(request.estimated_cost))
    if request.actual_cost is not None:
        job.actual_cost = Decimal(str(request.actual_cost))
    if request.technician_notes is not None:
        job.technician_notes = request.technician_notes
    if request.internal_notes is not None:
        job.internal_notes = request.internal_notes

    await db.commit()
    await db.refresh(job)

    return job.to_dict()


@router.delete("/jobs/{job_id}")
async def delete_job(
    job_id: str,
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """Soft delete a job."""
    try:
        job_uuid = UUID(job_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid job ID")

    result = await db.execute(
        select(JobModel).where(
            and_(JobModel.id == job_uuid, JobModel.is_deleted == False)
        )
    )
    job = result.scalar_one_or_none()

    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    job.is_deleted = True
    job.deleted_at = datetime.now()
    await db.commit()

    return {"message": "Job deleted", "id": job_id}


# ====================
# Quotes API (Database-backed)
# ====================

class QuoteLineItem(BaseModel):
    """Quote line item."""
    description: str
    quantity: float = 1.0
    unit: str = "Stück"
    unit_price: float
    total: float | None = None


class QuoteCreateRequest(BaseModel):
    """Request model for creating a quote."""
    job_id: str = Field(..., description="Job UUID")
    items: list[QuoteLineItem] = Field(..., description="Line items")
    valid_days: int = Field(default=30, ge=1, le=90, description="Validity in days")
    tax_rate: float = Field(default=19.0, description="Tax rate percentage")
    discount_amount: float = Field(default=0, description="Discount amount")
    payment_terms: str | None = None
    notes: str | None = None


def _generate_quote_number() -> str:
    """Generate a unique quote number."""
    now = datetime.now()
    return f"QUO-{now.year}-{now.strftime('%m%d%H%M%S')}"


@router.post("/quotes")
async def create_quote(
    request: QuoteCreateRequest,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Create a quote for a job."""
    try:
        job_uuid = UUID(request.job_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid job_id format")

    # Verify job exists
    result = await db.execute(
        select(JobModel).where(JobModel.id == job_uuid)
    )
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    # Calculate totals
    items_json = []
    subtotal = Decimal("0")
    for item in request.items:
        item_total = Decimal(str(item.quantity)) * Decimal(str(item.unit_price))
        items_json.append({
            "description": item.description,
            "quantity": item.quantity,
            "unit": item.unit,
            "unit_price": item.unit_price,
            "total": float(item_total),
        })
        subtotal += item_total

    tax_rate = Decimal(str(request.tax_rate))
    tax_amount = (subtotal * tax_rate / Decimal("100")).quantize(Decimal("0.01"))
    discount = Decimal(str(request.discount_amount))
    total = subtotal + tax_amount - discount

    # Create quote
    quote = QuoteModel(
        id=uuid4(),
        quote_number=_generate_quote_number(),
        job_id=job_uuid,
        contact_id=job.contact_id,
        status=QuoteStatus.DRAFT,
        valid_from=date.today(),
        valid_until=date.today() + timedelta(days=request.valid_days),
        items_json=items_json,
        subtotal=subtotal,
        tax_rate=tax_rate,
        tax_amount=tax_amount,
        discount_amount=discount,
        total=total,
        payment_terms=request.payment_terms,
        notes=request.notes,
    )

    db.add(quote)

    # Update job status
    if job.status == JobStatus.REQUESTED:
        job.status = JobStatus.QUOTED

    await db.commit()
    await db.refresh(quote)

    return quote.to_dict()


@router.get("/quotes/{quote_id}")
async def get_quote(
    quote_id: str,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Get quote details."""
    try:
        quote_uuid = UUID(quote_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid quote ID")

    result = await db.execute(
        select(QuoteModel).where(
            and_(QuoteModel.id == quote_uuid, QuoteModel.is_deleted == False)
        )
    )
    quote = result.scalar_one_or_none()

    if not quote:
        raise HTTPException(status_code=404, detail="Quote not found")

    return quote.to_dict()


@router.patch("/quotes/{quote_id}/status")
async def update_quote_status(
    quote_id: str,
    status: str = Query(..., description="New status: sent, accepted, rejected"),
    rejection_reason: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Update quote status."""
    try:
        quote_uuid = UUID(quote_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid quote ID")

    result = await db.execute(
        select(QuoteModel).where(
            and_(QuoteModel.id == quote_uuid, QuoteModel.is_deleted == False)
        )
    )
    quote = result.scalar_one_or_none()

    if not quote:
        raise HTTPException(status_code=404, detail="Quote not found")

    # Update status and timestamps
    quote.status = status
    now = datetime.now()

    if status == QuoteStatus.SENT:
        quote.sent_at = now
    elif status == QuoteStatus.ACCEPTED:
        quote.accepted_at = now
        # Update job status
        if quote.job:
            quote.job.status = JobStatus.ACCEPTED
    elif status == QuoteStatus.REJECTED:
        quote.rejected_at = now
        quote.rejection_reason = rejection_reason

    await db.commit()
    await db.refresh(quote)

    return quote.to_dict()


@router.get("/jobs/{job_id}/quotes")
async def list_job_quotes(
    job_id: str,
    db: AsyncSession = Depends(get_db),
) -> list[dict[str, Any]]:
    """List all quotes for a job."""
    try:
        job_uuid = UUID(job_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid job ID")

    result = await db.execute(
        select(QuoteModel).where(
            and_(
                QuoteModel.job_id == job_uuid,
                QuoteModel.is_deleted == False,
            )
        ).order_by(QuoteModel.created_at.desc())
    )
    quotes = result.scalars().all()

    return [q.to_dict() for q in quotes]


# ====================
# Dashboard/Stats Endpoints
# ====================

@router.get("/dashboard/stats")
async def get_dashboard_stats(
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Get dashboard statistics for Handwerker demo."""
    today = date.today()
    week_start = today - timedelta(days=today.weekday())
    week_end = week_start + timedelta(days=6)

    # Count jobs by status
    jobs_result = await db.execute(
        select(JobModel).where(JobModel.is_deleted == False)
    )
    jobs = jobs_result.scalars().all()

    status_counts = {}
    urgency_counts = {}
    today_jobs = 0
    week_jobs = 0

    for job in jobs:
        # Status counts
        status_counts[job.status] = status_counts.get(job.status, 0) + 1
        # Urgency counts
        urgency_counts[job.urgency] = urgency_counts.get(job.urgency, 0) + 1
        # Today's jobs
        if job.scheduled_date == today:
            today_jobs += 1
        # This week's jobs
        if job.scheduled_date and week_start <= job.scheduled_date <= week_end:
            week_jobs += 1

    return {
        "date": today.isoformat(),
        "jobs": {
            "total": len(jobs),
            "today": today_jobs,
            "this_week": week_jobs,
            "by_status": status_counts,
            "by_urgency": urgency_counts,
        },
        "quick_actions": [
            {"label": "Neuer Auftrag", "endpoint": "POST /handwerk/jobs"},
            {"label": "Kalender heute", "endpoint": f"GET /handwerk/calendar/{today.isoformat()}"},
            {"label": "Offene Notfälle", "endpoint": "GET /handwerk/jobs?urgency=notfall&status=requested"},
        ],
    }
