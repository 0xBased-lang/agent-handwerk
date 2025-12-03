"""CRM (Contact Relationship Management) Endpoints.

Provides API endpoints for contact and company management.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from phone_agent.db import get_db
from phone_agent.db.models.crm import ContactModel, CompanyModel
from phone_agent.db.repositories.contacts import ContactRepository, CompanyRepository


router = APIRouter()


# ============================================================================
# Pydantic Schemas - Contacts
# ============================================================================

class ContactCreate(BaseModel):
    """Schema for creating a contact."""

    first_name: str
    last_name: str
    phone_primary: str
    phone_secondary: str | None = None
    phone_mobile: str | None = None
    email: str | None = None
    salutation: str | None = None
    street: str | None = None
    street_number: str | None = None
    zip_code: str | None = None
    city: str | None = None
    country: str = "Germany"
    contact_type: str = "patient"
    source: str = "phone_agent"
    industry: str = "gesundheit"
    date_of_birth: str | None = None
    insurance_type: str | None = None
    preferred_contact_method: str | None = None
    preferred_language: str = "de"
    notes: str | None = None
    external_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ContactUpdate(BaseModel):
    """Schema for updating a contact."""

    first_name: str | None = None
    last_name: str | None = None
    phone_primary: str | None = None
    phone_secondary: str | None = None
    phone_mobile: str | None = None
    email: str | None = None
    salutation: str | None = None
    street: str | None = None
    street_number: str | None = None
    zip_code: str | None = None
    city: str | None = None
    contact_type: str | None = None
    insurance_type: str | None = None
    preferred_contact_method: str | None = None
    notes: str | None = None
    metadata: dict[str, Any] | None = None


class Contact(BaseModel):
    """Contact schema for API responses."""

    id: UUID
    first_name: str
    last_name: str
    full_name: str
    salutation: str | None = None
    phone_primary: str
    phone_secondary: str | None = None
    phone_mobile: str | None = None
    email: str | None = None
    street: str | None = None
    street_number: str | None = None
    zip_code: str | None = None
    city: str | None = None
    country: str = "Germany"
    contact_type: str
    source: str | None = None
    industry: str
    date_of_birth: str | None = None
    insurance_type: str | None = None
    preferred_contact_method: str | None = None
    preferred_language: str = "de"
    total_calls: int = 0
    total_appointments: int = 0
    total_no_shows: int = 0
    last_contact_at: datetime | None = None
    external_id: str | None = None
    notes: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime | None = None
    is_deleted: bool = False

    model_config = {"from_attributes": True}

    @classmethod
    def from_model(cls, model: ContactModel) -> "Contact":
        """Create schema from ORM model."""
        return cls(
            id=model.id,
            first_name=model.first_name,
            last_name=model.last_name,
            full_name=model.full_name,
            salutation=model.salutation,
            phone_primary=model.phone_primary,
            phone_secondary=model.phone_secondary,
            phone_mobile=model.phone_mobile,
            email=model.email,
            street=model.street,
            street_number=model.street_number,
            zip_code=model.zip_code,
            city=model.city,
            country=model.country,
            contact_type=model.contact_type,
            source=model.source,
            industry=model.industry,
            date_of_birth=model.date_of_birth.isoformat() if model.date_of_birth else None,
            insurance_type=model.insurance_type,
            preferred_contact_method=model.preferred_contact_method,
            preferred_language=model.preferred_language,
            total_calls=model.total_calls,
            total_appointments=model.total_appointments,
            total_no_shows=model.total_no_shows,
            last_contact_at=model.last_contact_at,
            external_id=model.external_id,
            notes=model.notes,
            metadata=model.metadata_json or {},
            created_at=model.created_at,
            is_deleted=model.is_deleted,
        )


class ContactListResponse(BaseModel):
    """Paginated contact list response."""

    contacts: list[Contact]
    total: int
    page: int
    page_size: int


class ContactStats(BaseModel):
    """Contact statistics."""

    total_contacts: int
    new_this_week: int
    active_30_days: int
    by_type: dict[str, int]


# ============================================================================
# Pydantic Schemas - Companies
# ============================================================================

class CompanyCreate(BaseModel):
    """Schema for creating a company."""

    name: str
    legal_name: str | None = None
    tax_id: str | None = None
    street: str | None = None
    street_number: str | None = None
    zip_code: str | None = None
    city: str | None = None
    country: str = "Germany"
    phone: str | None = None
    email: str | None = None
    website: str | None = None
    industry: str | None = None
    company_type: str | None = None
    size: str | None = None
    external_id: str | None = None
    notes: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class CompanyUpdate(BaseModel):
    """Schema for updating a company."""

    name: str | None = None
    legal_name: str | None = None
    tax_id: str | None = None
    street: str | None = None
    zip_code: str | None = None
    city: str | None = None
    phone: str | None = None
    email: str | None = None
    website: str | None = None
    industry: str | None = None
    company_type: str | None = None
    notes: str | None = None


class Company(BaseModel):
    """Company schema for API responses."""

    id: UUID
    name: str
    legal_name: str | None = None
    tax_id: str | None = None
    street: str | None = None
    street_number: str | None = None
    zip_code: str | None = None
    city: str | None = None
    country: str = "Germany"
    phone: str | None = None
    email: str | None = None
    website: str | None = None
    industry: str | None = None
    company_type: str | None = None
    size: str | None = None
    total_contacts: int = 0
    total_service_calls: int = 0
    external_id: str | None = None
    notes: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime | None = None
    is_deleted: bool = False

    model_config = {"from_attributes": True}

    @classmethod
    def from_model(cls, model: CompanyModel) -> "Company":
        """Create schema from ORM model."""
        return cls(
            id=model.id,
            name=model.name,
            legal_name=model.legal_name,
            tax_id=model.tax_id,
            street=model.street,
            street_number=model.street_number,
            zip_code=model.zip_code,
            city=model.city,
            country=model.country,
            phone=model.phone,
            email=model.email,
            website=model.website,
            industry=model.industry,
            company_type=model.company_type,
            size=model.size,
            total_contacts=model.total_contacts,
            total_service_calls=model.total_service_calls,
            external_id=model.external_id,
            notes=model.notes,
            metadata=model.metadata_json or {},
            created_at=model.created_at,
            is_deleted=model.is_deleted,
        )


# ============================================================================
# Dependencies
# ============================================================================

async def get_contact_repository(
    session: Annotated[AsyncSession, Depends(get_db)]
) -> ContactRepository:
    """Get contact repository instance."""
    return ContactRepository(session)


async def get_company_repository(
    session: Annotated[AsyncSession, Depends(get_db)]
) -> CompanyRepository:
    """Get company repository instance."""
    return CompanyRepository(session)


# ============================================================================
# Contact Endpoints
# ============================================================================

@router.get("/crm/contacts", response_model=ContactListResponse)
async def list_contacts(
    repo: Annotated[ContactRepository, Depends(get_contact_repository)],
    industry: str | None = None,
    contact_type: str | None = None,
    search: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> ContactListResponse:
    """List contacts with optional filtering and search.

    Args:
        industry: Filter by industry
        contact_type: Filter by contact type (patient, customer, lead)
        search: Search term for name/phone/email
        page: Page number
        page_size: Results per page

    Returns:
        Paginated list of contacts
    """
    skip = (page - 1) * page_size

    if search:
        contacts = await repo.search_full_text(
            search, industry=industry, skip=skip, limit=page_size
        )
    elif contact_type:
        contacts = await repo.get_by_type(
            contact_type, industry=industry, skip=skip, limit=page_size
        )
    elif industry:
        contacts = await repo.get_by_industry(industry, skip=skip, limit=page_size)
    else:
        contacts = await repo.get_multi(skip=skip, limit=page_size)

    total = await repo.count()

    return ContactListResponse(
        contacts=[Contact.from_model(c) for c in contacts],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/crm/contacts/search")
async def search_contacts(
    repo: Annotated[ContactRepository, Depends(get_contact_repository)],
    q: str = Query(..., min_length=2),
    industry: str | None = None,
    limit: int = Query(20, ge=1, le=50),
) -> list[Contact]:
    """Search contacts by name, phone, or email.

    Args:
        q: Search query
        industry: Optional industry filter
        limit: Maximum results

    Returns:
        List of matching contacts
    """
    contacts = await repo.search_full_text(q, industry=industry, limit=limit)
    return [Contact.from_model(c) for c in contacts]


@router.get("/crm/contacts/by-phone")
async def find_contact_by_phone(
    repo: Annotated[ContactRepository, Depends(get_contact_repository)],
    phone: str,
    industry: str | None = None,
) -> Contact | None:
    """Find a contact by phone number.

    Args:
        phone: Phone number to search
        industry: Optional industry filter

    Returns:
        Contact or None
    """
    contact = await repo.find_by_phone(phone, industry=industry)
    if contact is None:
        return None
    return Contact.from_model(contact)


@router.get("/crm/contacts/stats", response_model=ContactStats)
async def get_contact_stats(
    repo: Annotated[ContactRepository, Depends(get_contact_repository)],
    industry: str | None = None,
) -> ContactStats:
    """Get contact statistics.

    Args:
        industry: Optional industry filter

    Returns:
        Contact statistics
    """
    stats = await repo.get_statistics(industry=industry)
    return ContactStats(**stats)


@router.get("/crm/contacts/recent")
async def get_recent_contacts(
    repo: Annotated[ContactRepository, Depends(get_contact_repository)],
    days: int = Query(7, ge=1, le=30),
    industry: str | None = None,
    limit: int = Query(50, ge=1, le=100),
) -> list[Contact]:
    """Get contacts with recent activity.

    Args:
        days: Number of days to look back
        industry: Optional industry filter
        limit: Maximum results

    Returns:
        List of recently active contacts
    """
    contacts = await repo.get_recent_contacts(days=days, industry=industry, limit=limit)
    return [Contact.from_model(c) for c in contacts]


@router.get("/crm/contacts/inactive")
async def get_inactive_contacts(
    repo: Annotated[ContactRepository, Depends(get_contact_repository)],
    days: int = Query(90, ge=30, le=365),
    industry: str | None = None,
    limit: int = Query(50, ge=1, le=100),
) -> list[Contact]:
    """Get contacts without recent activity.

    Args:
        days: Inactivity threshold in days
        industry: Optional industry filter
        limit: Maximum results

    Returns:
        List of inactive contacts
    """
    contacts = await repo.get_inactive_contacts(days=days, industry=industry, limit=limit)
    return [Contact.from_model(c) for c in contacts]


@router.get("/crm/contacts/leads")
async def get_leads(
    repo: Annotated[ContactRepository, Depends(get_contact_repository)],
    industry: str | None = None,
    limit: int = Query(50, ge=1, le=100),
) -> list[Contact]:
    """Get all leads and prospects.

    Args:
        industry: Optional industry filter
        limit: Maximum results

    Returns:
        List of lead contacts
    """
    contacts = await repo.get_leads(industry=industry, limit=limit)
    return [Contact.from_model(c) for c in contacts]


@router.get("/crm/contacts/{contact_id}", response_model=Contact)
async def get_contact(
    contact_id: UUID,
    repo: Annotated[ContactRepository, Depends(get_contact_repository)],
) -> Contact:
    """Get a specific contact by ID.

    Args:
        contact_id: Contact UUID

    Returns:
        Contact details

    Raises:
        HTTPException: If contact not found
    """
    contact = await repo.get(contact_id)
    if contact is None:
        raise HTTPException(status_code=404, detail="Contact not found")
    return Contact.from_model(contact)


@router.get("/crm/contacts/{contact_id}/timeline")
async def get_contact_timeline(
    contact_id: UUID,
    repo: Annotated[ContactRepository, Depends(get_contact_repository)],
) -> dict[str, Any]:
    """Get contact with interaction timeline.

    Args:
        contact_id: Contact UUID

    Returns:
        Contact with calls, appointments, and consents

    Raises:
        HTTPException: If contact not found
    """
    contact = await repo.get_with_timeline(contact_id)
    if contact is None:
        raise HTTPException(status_code=404, detail="Contact not found")

    return {
        "contact": Contact.from_model(contact),
        "calls": [c.to_dict() for c in contact.calls[:50]],
        "appointments": [a.to_dict() for a in contact.appointments[:50]],
        "consents": [c.to_dict() for c in contact.consents],
    }


@router.post("/crm/contacts", response_model=Contact, status_code=201)
async def create_contact(
    data: ContactCreate,
    repo: Annotated[ContactRepository, Depends(get_contact_repository)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Contact:
    """Create a new contact.

    Args:
        data: Contact creation data

    Returns:
        Created contact

    Raises:
        HTTPException: If phone number already exists
    """
    # Check for existing contact with same phone
    existing = await repo.find_by_phone(data.phone_primary, industry=data.industry)
    if existing:
        raise HTTPException(
            status_code=409,
            detail="Contact with this phone number already exists",
        )

    contact = ContactModel(
        id=uuid4(),
        first_name=data.first_name,
        last_name=data.last_name,
        phone_primary=data.phone_primary,
        phone_secondary=data.phone_secondary,
        phone_mobile=data.phone_mobile,
        email=data.email,
        salutation=data.salutation,
        street=data.street,
        street_number=data.street_number,
        zip_code=data.zip_code,
        city=data.city,
        country=data.country,
        contact_type=data.contact_type,
        source=data.source,
        industry=data.industry,
        insurance_type=data.insurance_type,
        preferred_contact_method=data.preferred_contact_method,
        preferred_language=data.preferred_language,
        notes=data.notes,
        external_id=data.external_id,
    )
    contact.metadata_json = data.metadata

    # Parse date_of_birth if provided
    if data.date_of_birth:
        from datetime import datetime
        contact.date_of_birth = datetime.fromisoformat(data.date_of_birth).date()

    created = await repo.create(contact)
    await db.commit()

    return Contact.from_model(created)


@router.patch("/crm/contacts/{contact_id}", response_model=Contact)
async def update_contact(
    contact_id: UUID,
    data: ContactUpdate,
    repo: Annotated[ContactRepository, Depends(get_contact_repository)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Contact:
    """Update a contact.

    Args:
        contact_id: Contact UUID
        data: Update data

    Returns:
        Updated contact

    Raises:
        HTTPException: If contact not found
    """
    contact = await repo.get(contact_id)
    if contact is None:
        raise HTTPException(status_code=404, detail="Contact not found")

    update_data = data.model_dump(exclude_unset=True)

    # Handle metadata separately
    if "metadata" in update_data:
        update_data["metadata_json"] = update_data.pop("metadata")

    updated = await repo.update(contact_id, update_data)
    await db.commit()

    return Contact.from_model(updated)


@router.delete("/crm/contacts/{contact_id}")
async def delete_contact(
    contact_id: UUID,
    repo: Annotated[ContactRepository, Depends(get_contact_repository)],
    db: Annotated[AsyncSession, Depends(get_db)],
    soft: bool = Query(True, description="Soft delete (default) or hard delete"),
) -> dict[str, str]:
    """Delete a contact.

    Args:
        contact_id: Contact UUID
        soft: If True, soft delete; if False, permanently delete

    Returns:
        Deletion status

    Raises:
        HTTPException: If contact not found
    """
    contact = await repo.get(contact_id)
    if contact is None:
        raise HTTPException(status_code=404, detail="Contact not found")

    if soft:
        await repo.soft_delete(contact_id)
    else:
        await repo.delete(contact_id)

    await db.commit()

    return {"status": "deleted", "soft_delete": soft}


# ============================================================================
# Company Endpoints
# ============================================================================

@router.get("/crm/companies", response_model=list[Company])
async def list_companies(
    repo: Annotated[CompanyRepository, Depends(get_company_repository)],
    search: str | None = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
) -> list[Company]:
    """List companies with optional search.

    Args:
        search: Search term for company name
        skip: Pagination offset
        limit: Maximum results

    Returns:
        List of companies
    """
    if search:
        companies = await repo.search_by_name(search, skip=skip, limit=limit)
    else:
        companies = await repo.get_multi(skip=skip, limit=limit)

    return [Company.from_model(c) for c in companies]


@router.get("/crm/companies/{company_id}", response_model=Company)
async def get_company(
    company_id: UUID,
    repo: Annotated[CompanyRepository, Depends(get_company_repository)],
) -> Company:
    """Get a specific company by ID.

    Args:
        company_id: Company UUID

    Returns:
        Company details

    Raises:
        HTTPException: If company not found
    """
    company = await repo.get(company_id)
    if company is None:
        raise HTTPException(status_code=404, detail="Company not found")
    return Company.from_model(company)


@router.get("/crm/companies/{company_id}/contacts", response_model=list[Contact])
async def get_company_contacts(
    company_id: UUID,
    repo: Annotated[CompanyRepository, Depends(get_company_repository)],
) -> list[Contact]:
    """Get all contacts for a company.

    Args:
        company_id: Company UUID

    Returns:
        List of contacts associated with the company

    Raises:
        HTTPException: If company not found
    """
    company = await repo.get_with_contacts(company_id)
    if company is None:
        raise HTTPException(status_code=404, detail="Company not found")

    return [Contact.from_model(c) for c in company.contacts]


@router.post("/crm/companies", response_model=Company, status_code=201)
async def create_company(
    data: CompanyCreate,
    repo: Annotated[CompanyRepository, Depends(get_company_repository)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Company:
    """Create a new company.

    Args:
        data: Company creation data

    Returns:
        Created company

    Raises:
        HTTPException: If tax ID already exists
    """
    # Check for existing company with same tax ID
    if data.tax_id:
        existing = await repo.find_by_tax_id(data.tax_id)
        if existing:
            raise HTTPException(
                status_code=409,
                detail="Company with this tax ID already exists",
            )

    company = CompanyModel(
        id=uuid4(),
        name=data.name,
        legal_name=data.legal_name,
        tax_id=data.tax_id,
        street=data.street,
        street_number=data.street_number,
        zip_code=data.zip_code,
        city=data.city,
        country=data.country,
        phone=data.phone,
        email=data.email,
        website=data.website,
        industry=data.industry,
        company_type=data.company_type,
        size=data.size,
        external_id=data.external_id,
        notes=data.notes,
    )
    company.metadata_json = data.metadata

    created = await repo.create(company)
    await db.commit()

    return Company.from_model(created)


@router.patch("/crm/companies/{company_id}", response_model=Company)
async def update_company(
    company_id: UUID,
    data: CompanyUpdate,
    repo: Annotated[CompanyRepository, Depends(get_company_repository)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Company:
    """Update a company.

    Args:
        company_id: Company UUID
        data: Update data

    Returns:
        Updated company

    Raises:
        HTTPException: If company not found
    """
    company = await repo.get(company_id)
    if company is None:
        raise HTTPException(status_code=404, detail="Company not found")

    update_data = data.model_dump(exclude_unset=True)
    updated = await repo.update(company_id, update_data)
    await db.commit()

    return Company.from_model(updated)


@router.delete("/crm/companies/{company_id}")
async def delete_company(
    company_id: UUID,
    repo: Annotated[CompanyRepository, Depends(get_company_repository)],
    db: Annotated[AsyncSession, Depends(get_db)],
    soft: bool = Query(True, description="Soft delete (default) or hard delete"),
) -> dict[str, str]:
    """Delete a company.

    Args:
        company_id: Company UUID
        soft: If True, soft delete; if False, permanently delete

    Returns:
        Deletion status

    Raises:
        HTTPException: If company not found
    """
    company = await repo.get(company_id)
    if company is None:
        raise HTTPException(status_code=404, detail="Company not found")

    if soft:
        await repo.soft_delete(company_id)
    else:
        await repo.delete(company_id)

    await db.commit()

    return {"status": "deleted", "soft_delete": soft}
