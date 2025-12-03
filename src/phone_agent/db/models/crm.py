"""CRM ORM Models for Phone Agent.

Contains models for contact and company management:
- Contact: Individual patients/customers
- Company: Business entities (for B2B industries)
- ContactCompanyLink: Many-to-many relationship
"""
from __future__ import annotations

from datetime import datetime, date
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    String,
    Text,
    Integer,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    UniqueConstraint,
)
from sqlalchemy.dialects.sqlite import JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from phone_agent.db.base import Base, UUIDMixin, TimestampMixin, SoftDeleteMixin

if TYPE_CHECKING:
    from phone_agent.db.models.core import CallModel, AppointmentModel
    from phone_agent.db.models.compliance import ConsentModel, AuditLogModel


class ContactModel(Base, UUIDMixin, TimestampMixin, SoftDeleteMixin):
    """Contact (Patient/Customer) ORM model.

    Central CRM entity representing individuals who interact
    with the phone system. Used across all industries:
    - Healthcare: Patients
    - Handwerk: Customers
    - Freie Berufe: Clients/Leads
    """

    __tablename__ = "contacts"

    # Personal information
    first_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    last_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    salutation: Mapped[str | None] = mapped_column(
        String(20),
        nullable=True,
        comment="Herr, Frau, etc.",
    )

    # Contact methods
    phone_primary: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
    )
    phone_secondary: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
    )
    phone_mobile: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
    )
    email: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        index=True,
    )

    # Address
    street: Mapped[str | None] = mapped_column(String(255), nullable=True)
    street_number: Mapped[str | None] = mapped_column(String(20), nullable=True)
    zip_code: Mapped[str | None] = mapped_column(String(10), nullable=True, index=True)
    city: Mapped[str | None] = mapped_column(String(100), nullable=True)
    country: Mapped[str] = mapped_column(String(100), default="Germany", nullable=False)

    # Classification
    contact_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
        comment="patient, customer, lead, prospect",
    )
    source: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        comment="phone_agent, web, manual, import, referral",
    )
    industry: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
        comment="gesundheit, handwerk, freie_berufe, etc.",
    )

    # Healthcare-specific (nullable for non-healthcare)
    date_of_birth: Mapped[date | None] = mapped_column(
        Date,
        nullable=True,
    )
    insurance_type: Mapped[str | None] = mapped_column(
        String(20),
        nullable=True,
        comment="GKV, PKV, Privat, Selbstzahler",
    )
    insurance_number: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
    )

    # Handwerk-specific
    property_type: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        comment="residential, commercial, industrial",
    )

    # Preferences
    preferred_contact_method: Mapped[str | None] = mapped_column(
        String(20),
        nullable=True,
        comment="phone, sms, email",
    )
    preferred_contact_time: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        comment="morning, afternoon, evening",
    )
    preferred_language: Mapped[str] = mapped_column(
        String(10),
        default="de",
        nullable=False,
    )

    # Analytics counters (denormalized for performance)
    total_calls: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_appointments: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_no_shows: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Engagement tracking
    first_contact_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    last_contact_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        index=True,
    )
    last_appointment_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # External system IDs
    external_id: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        index=True,
        comment="ID in external PVS/CRM system",
    )

    # Notes
    notes: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    # Flexible metadata
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(
        JSON,
        nullable=True,
    )

    # Relationships
    calls: Mapped[list["CallModel"]] = relationship(
        back_populates="contact",
        lazy="dynamic",
    )
    appointments: Mapped[list["AppointmentModel"]] = relationship(
        back_populates="contact",
        lazy="dynamic",
    )
    consents: Mapped[list["ConsentModel"]] = relationship(
        back_populates="contact",
        lazy="selectin",
    )
    audit_logs: Mapped[list["AuditLogModel"]] = relationship(
        back_populates="contact",
        lazy="dynamic",
    )
    companies: Mapped[list["CompanyModel"]] = relationship(
        secondary="contact_company_links",
        back_populates="contacts",
        lazy="selectin",
    )

    # Indexes
    __table_args__ = (
        Index("ix_contacts_name", "last_name", "first_name"),
        Index("ix_contacts_industry_type", "industry", "contact_type"),
        UniqueConstraint("phone_primary", "industry", name="uq_contact_phone_industry"),
    )

    @property
    def full_name(self) -> str:
        """Get full name with optional salutation."""
        parts = []
        if self.salutation:
            parts.append(self.salutation)
        parts.append(self.first_name)
        parts.append(self.last_name)
        return " ".join(parts)

    def to_dict(self) -> dict[str, Any]:
        """Convert model to dictionary for API responses."""
        return {
            "id": str(self.id),
            "first_name": self.first_name,
            "last_name": self.last_name,
            "full_name": self.full_name,
            "salutation": self.salutation,
            "phone_primary": self.phone_primary,
            "phone_secondary": self.phone_secondary,
            "phone_mobile": self.phone_mobile,
            "email": self.email,
            "street": self.street,
            "street_number": self.street_number,
            "zip_code": self.zip_code,
            "city": self.city,
            "country": self.country,
            "contact_type": self.contact_type,
            "source": self.source,
            "industry": self.industry,
            "date_of_birth": self.date_of_birth.isoformat() if self.date_of_birth else None,
            "insurance_type": self.insurance_type,
            "preferred_contact_method": self.preferred_contact_method,
            "preferred_language": self.preferred_language,
            "total_calls": self.total_calls,
            "total_appointments": self.total_appointments,
            "last_contact_at": self.last_contact_at.isoformat() if self.last_contact_at else None,
            "external_id": self.external_id,
            "notes": self.notes,
            "metadata": self.metadata_json or {},
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "is_deleted": self.is_deleted,
        }


class CompanyModel(Base, UUIDMixin, TimestampMixin, SoftDeleteMixin):
    """Company/Organization ORM model.

    Represents business entities for B2B relationships,
    primarily used in Handwerk and Freie Berufe industries.
    """

    __tablename__ = "companies"

    # Company identification
    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True,
    )
    legal_name: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        comment="Official registered name",
    )
    tax_id: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        comment="Steuernummer / USt-IdNr",
    )

    # Address
    street: Mapped[str | None] = mapped_column(String(255), nullable=True)
    street_number: Mapped[str | None] = mapped_column(String(20), nullable=True)
    zip_code: Mapped[str | None] = mapped_column(String(10), nullable=True, index=True)
    city: Mapped[str | None] = mapped_column(String(100), nullable=True)
    country: Mapped[str] = mapped_column(String(100), default="Germany", nullable=False)

    # Contact info
    phone: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        index=True,
    )
    email: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )
    website: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    # Classification
    industry: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        comment="Company's industry sector",
    )
    company_type: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        comment="commercial, residential, public, etc.",
    )
    size: Mapped[str | None] = mapped_column(
        String(20),
        nullable=True,
        comment="small, medium, large, enterprise",
    )

    # Analytics
    total_contacts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_service_calls: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # External system ID
    external_id: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        index=True,
    )

    # Notes
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Flexible metadata
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(
        JSON,
        nullable=True,
    )

    # Relationships
    contacts: Mapped[list["ContactModel"]] = relationship(
        secondary="contact_company_links",
        back_populates="companies",
        lazy="selectin",
    )

    def to_dict(self) -> dict[str, Any]:
        """Convert model to dictionary for API responses."""
        return {
            "id": str(self.id),
            "name": self.name,
            "legal_name": self.legal_name,
            "tax_id": self.tax_id,
            "street": self.street,
            "street_number": self.street_number,
            "zip_code": self.zip_code,
            "city": self.city,
            "country": self.country,
            "phone": self.phone,
            "email": self.email,
            "website": self.website,
            "industry": self.industry,
            "company_type": self.company_type,
            "size": self.size,
            "total_contacts": self.total_contacts,
            "external_id": self.external_id,
            "notes": self.notes,
            "metadata": self.metadata_json or {},
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "is_deleted": self.is_deleted,
        }


class ContactCompanyLinkModel(Base, UUIDMixin, TimestampMixin):
    """Contact-Company association table.

    Links contacts to companies with role information.
    Supports many-to-many relationships.
    """

    __tablename__ = "contact_company_links"

    # Foreign keys
    contact_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("contacts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    company_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Role information
    role: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        comment="owner, manager, employee, contact_person",
    )
    job_title: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )
    is_primary: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
        comment="Primary contact for this company",
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )

    # Unique constraint
    __table_args__ = (
        UniqueConstraint("contact_id", "company_id", name="uq_contact_company"),
        Index("ix_link_company_primary", "company_id", "is_primary"),
    )

    def to_dict(self) -> dict[str, Any]:
        """Convert model to dictionary for API responses."""
        return {
            "id": str(self.id),
            "contact_id": str(self.contact_id),
            "company_id": str(self.company_id),
            "role": self.role,
            "job_title": self.job_title,
            "is_primary": self.is_primary,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
