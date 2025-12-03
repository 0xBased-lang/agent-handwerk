"""Handwerk (Trades) API endpoints."""
from __future__ import annotations

from datetime import date, datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

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
