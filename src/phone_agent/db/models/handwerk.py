"""Handwerk (Trades) specific ORM Models.

Contains models specific to craftsman/trades business operations:
- JobModel: Service requests and work orders
- QuoteModel: Cost estimates and quotes

These extend the generic appointment/contact models for trade-specific functionality.
"""
from __future__ import annotations

from datetime import datetime, date, time
from typing import TYPE_CHECKING, Any
from uuid import UUID
from decimal import Decimal

from sqlalchemy import (
    String,
    Text,
    Integer,
    Boolean,
    Date,
    Time,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
)
from sqlalchemy.dialects.sqlite import JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from phone_agent.db.base import Base, UUIDMixin, TimestampMixin, SoftDeleteMixin

if TYPE_CHECKING:
    from phone_agent.db.models.crm import ContactModel
    from phone_agent.db.models.core import AppointmentModel, CallModel
    from phone_agent.db.models.elektro import ConversationTranscriptModel


# Enums as string constants for database storage
class JobStatus:
    """Job status values."""
    REQUESTED = "requested"      # Customer called, job created
    QUOTED = "quoted"            # Quote sent to customer
    ACCEPTED = "accepted"        # Customer accepted quote
    SCHEDULED = "scheduled"      # Appointment scheduled
    IN_PROGRESS = "in_progress"  # Technician on site
    COMPLETED = "completed"      # Work finished
    CANCELLED = "cancelled"      # Job cancelled
    ON_HOLD = "on_hold"          # Waiting for parts/info


class JobUrgency:
    """Job urgency levels (from triage)."""
    NOTFALL = "notfall"          # Emergency (gas leak, etc.)
    DRINGEND = "dringend"        # Urgent (same day)
    NORMAL = "normal"            # Normal (within days)
    ROUTINE = "routine"          # Routine (flexible scheduling)


class TradeCategory:
    """Trade/service categories."""
    SHK = "shk"                  # Sanitär, Heizung, Klima
    ELEKTRO = "elektro"          # Electrical
    SCHLOSSER = "schlosser"      # Locksmith
    DACHDECKER = "dachdecker"    # Roofing
    MALER = "maler"              # Painting
    TISCHLER = "tischler"        # Carpentry
    BAU = "bau"                  # Construction
    ALLGEMEIN = "allgemein"      # General


class PropertyType:
    """Property types for job location."""
    RESIDENTIAL = "residential"
    COMMERCIAL = "commercial"
    INDUSTRIAL = "industrial"


class QuoteStatus:
    """Quote status values."""
    DRAFT = "draft"              # Being prepared
    SENT = "sent"                # Sent to customer
    ACCEPTED = "accepted"        # Customer accepted
    REJECTED = "rejected"        # Customer rejected
    EXPIRED = "expired"          # Validity period passed
    REVISED = "revised"          # New version created


class JobModel(Base, UUIDMixin, TimestampMixin, SoftDeleteMixin):
    """Service job/work order ORM model.

    Represents a service request from a customer, tracking the full lifecycle
    from initial call through completion and invoicing.
    """

    __tablename__ = "jobs"

    # Job identification
    job_number: Mapped[str] = mapped_column(
        String(50),
        unique=True,
        nullable=False,
        index=True,
        comment="Human-readable job number (e.g., JOB-2024-0001)",
    )

    # Job details
    title: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="Brief description of the job",
    )
    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Detailed description of work needed",
    )

    # Classification
    trade_category: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
        comment="Trade type: shk, elektro, schlosser, etc.",
    )
    urgency: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
        default=JobUrgency.NORMAL,
        comment="Urgency level from triage: notfall, dringend, normal, routine",
    )
    status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
        default=JobStatus.REQUESTED,
        comment="Current job status",
    )

    # Location
    address_street: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )
    address_number: Mapped[str | None] = mapped_column(
        String(20),
        nullable=True,
    )
    address_zip: Mapped[str | None] = mapped_column(
        String(10),
        nullable=True,
    )
    address_city: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )
    property_type: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        comment="residential, commercial, industrial",
    )
    access_notes: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Access instructions, parking info, etc.",
    )

    # Scheduling preferences
    preferred_date: Mapped[date | None] = mapped_column(
        Date,
        nullable=True,
        comment="Customer's preferred date",
    )
    preferred_time_window: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        comment="Time window: frueh, vormittag, mittag, nachmittag, spaet, abend",
    )

    # Actual scheduling (linked to appointment)
    scheduled_date: Mapped[date | None] = mapped_column(
        Date,
        nullable=True,
        index=True,
    )
    scheduled_time: Mapped[time | None] = mapped_column(
        Time,
        nullable=True,
    )
    estimated_duration_minutes: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        default=60,
    )

    # Completion tracking
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="When technician started work",
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="When work was completed",
    )

    # Financials
    estimated_cost: Mapped[Decimal | None] = mapped_column(
        Numeric(10, 2),
        nullable=True,
        comment="Estimated cost before work",
    )
    actual_cost: Mapped[Decimal | None] = mapped_column(
        Numeric(10, 2),
        nullable=True,
        comment="Actual cost after completion",
    )
    is_paid: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )
    paid_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # Notes
    customer_notes: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Notes from customer about the job",
    )
    technician_notes: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Notes from technician after work",
    )
    internal_notes: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Internal office notes",
    )

    # Materials/parts tracking
    materials_json: Mapped[dict[str, Any] | None] = mapped_column(
        JSON,
        nullable=True,
        comment="Materials used: [{name, quantity, cost}]",
    )

    # Foreign keys
    contact_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("contacts.id"),
        nullable=True,
        index=True,
        comment="Customer who requested the job",
    )
    technician_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("contacts.id"),
        nullable=True,
        index=True,
        comment="Assigned technician",
    )
    appointment_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("appointments.id"),
        nullable=True,
        comment="Linked appointment for scheduling",
    )
    call_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("calls.id"),
        nullable=True,
        comment="Originating phone call",
    )

    # Flexible metadata
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(
        JSON,
        nullable=True,
    )

    # Relationships
    contact: Mapped["ContactModel | None"] = relationship(
        "ContactModel",
        foreign_keys=[contact_id],
        lazy="selectin",
    )
    technician: Mapped["ContactModel | None"] = relationship(
        "ContactModel",
        foreign_keys=[technician_id],
        lazy="selectin",
    )
    quotes: Mapped[list["QuoteModel"]] = relationship(
        back_populates="job",
        lazy="selectin",
    )
    transcript: Mapped["ConversationTranscriptModel | None"] = relationship(
        "ConversationTranscriptModel",
        back_populates="job",
        uselist=False,
        lazy="selectin",
    )

    # Indexes
    __table_args__ = (
        Index("ix_jobs_status_date", "status", "scheduled_date"),
        Index("ix_jobs_urgency_status", "urgency", "status"),
        Index("ix_jobs_trade_status", "trade_category", "status"),
    )

    def to_dict(self) -> dict[str, Any]:
        """Convert model to dictionary for API responses."""
        return {
            "id": str(self.id),
            "job_number": self.job_number,
            "title": self.title,
            "description": self.description,
            "trade_category": self.trade_category,
            "urgency": self.urgency,
            "status": self.status,
            "address": {
                "street": self.address_street,
                "number": self.address_number,
                "zip": self.address_zip,
                "city": self.address_city,
            },
            "property_type": self.property_type,
            "access_notes": self.access_notes,
            "preferred_date": self.preferred_date.isoformat() if self.preferred_date else None,
            "preferred_time_window": self.preferred_time_window,
            "scheduled_date": self.scheduled_date.isoformat() if self.scheduled_date else None,
            "scheduled_time": self.scheduled_time.isoformat() if self.scheduled_time else None,
            "estimated_duration_minutes": self.estimated_duration_minutes,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "estimated_cost": float(self.estimated_cost) if self.estimated_cost else None,
            "actual_cost": float(self.actual_cost) if self.actual_cost else None,
            "is_paid": self.is_paid,
            "customer_notes": self.customer_notes,
            "technician_notes": self.technician_notes,
            "materials": self.materials_json or [],
            "contact_id": str(self.contact_id) if self.contact_id else None,
            "technician_id": str(self.technician_id) if self.technician_id else None,
            "appointment_id": str(self.appointment_id) if self.appointment_id else None,
            "call_id": str(self.call_id) if self.call_id else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class QuoteModel(Base, UUIDMixin, TimestampMixin, SoftDeleteMixin):
    """Quote/cost estimate ORM model.

    Represents a formal cost estimate sent to a customer for a job.
    Supports versioning (multiple quotes per job) and line items.
    """

    __tablename__ = "quotes"

    # Quote identification
    quote_number: Mapped[str] = mapped_column(
        String(50),
        unique=True,
        nullable=False,
        index=True,
        comment="Human-readable quote number (e.g., QUO-2024-0001)",
    )
    version: Mapped[int] = mapped_column(
        Integer,
        default=1,
        nullable=False,
        comment="Version number for revised quotes",
    )

    # Status
    status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
        default=QuoteStatus.DRAFT,
        comment="draft, sent, accepted, rejected, expired, revised",
    )

    # Validity
    valid_from: Mapped[date] = mapped_column(
        Date,
        nullable=False,
    )
    valid_until: Mapped[date] = mapped_column(
        Date,
        nullable=False,
        comment="Quote expiration date",
    )

    # Line items (stored as JSON for flexibility)
    items_json: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON,
        nullable=False,
        default=list,
        comment="Line items: [{description, quantity, unit, unit_price, total}]",
    )

    # Totals
    subtotal: Mapped[Decimal] = mapped_column(
        Numeric(10, 2),
        nullable=False,
        default=0,
    )
    tax_rate: Mapped[Decimal] = mapped_column(
        Numeric(5, 2),
        nullable=False,
        default=19.0,
        comment="Tax rate percentage (e.g., 19.0 for 19% MwSt)",
    )
    tax_amount: Mapped[Decimal] = mapped_column(
        Numeric(10, 2),
        nullable=False,
        default=0,
    )
    discount_amount: Mapped[Decimal] = mapped_column(
        Numeric(10, 2),
        nullable=False,
        default=0,
    )
    total: Mapped[Decimal] = mapped_column(
        Numeric(10, 2),
        nullable=False,
        default=0,
    )

    # Terms and conditions
    payment_terms: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Payment terms and conditions",
    )
    notes: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Additional notes on the quote",
    )

    # Tracking timestamps
    sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    viewed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="When customer viewed the quote",
    )
    accepted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    rejected_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    rejection_reason: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    # Foreign keys
    job_id: Mapped[UUID] = mapped_column(
        ForeignKey("jobs.id"),
        nullable=False,
        index=True,
    )
    contact_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("contacts.id"),
        nullable=True,
        index=True,
    )
    created_by_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("contacts.id"),
        nullable=True,
        comment="Staff member who created the quote",
    )

    # Flexible metadata
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(
        JSON,
        nullable=True,
    )

    # Relationships
    job: Mapped["JobModel"] = relationship(
        back_populates="quotes",
        lazy="selectin",
    )
    contact: Mapped["ContactModel | None"] = relationship(
        "ContactModel",
        foreign_keys=[contact_id],
        lazy="selectin",
    )

    # Indexes
    __table_args__ = (
        Index("ix_quotes_status_valid", "status", "valid_until"),
        Index("ix_quotes_job_version", "job_id", "version"),
    )

    def to_dict(self) -> dict[str, Any]:
        """Convert model to dictionary for API responses."""
        return {
            "id": str(self.id),
            "quote_number": self.quote_number,
            "version": self.version,
            "status": self.status,
            "valid_from": self.valid_from.isoformat() if self.valid_from else None,
            "valid_until": self.valid_until.isoformat() if self.valid_until else None,
            "items": self.items_json or [],
            "subtotal": float(self.subtotal) if self.subtotal else 0,
            "tax_rate": float(self.tax_rate) if self.tax_rate else 19.0,
            "tax_amount": float(self.tax_amount) if self.tax_amount else 0,
            "discount_amount": float(self.discount_amount) if self.discount_amount else 0,
            "total": float(self.total) if self.total else 0,
            "payment_terms": self.payment_terms,
            "notes": self.notes,
            "sent_at": self.sent_at.isoformat() if self.sent_at else None,
            "viewed_at": self.viewed_at.isoformat() if self.viewed_at else None,
            "accepted_at": self.accepted_at.isoformat() if self.accepted_at else None,
            "rejected_at": self.rejected_at.isoformat() if self.rejected_at else None,
            "rejection_reason": self.rejection_reason,
            "job_id": str(self.job_id) if self.job_id else None,
            "contact_id": str(self.contact_id) if self.contact_id else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

    def calculate_totals(self) -> None:
        """Calculate subtotal, tax, and total from line items."""
        self.subtotal = Decimal("0")
        for item in self.items_json or []:
            item_total = Decimal(str(item.get("total", 0)))
            self.subtotal += item_total

        self.tax_amount = (self.subtotal * self.tax_rate / Decimal("100")).quantize(Decimal("0.01"))
        self.total = self.subtotal + self.tax_amount - self.discount_amount
