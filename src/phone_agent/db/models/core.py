"""Core ORM Models for Phone Agent.

Contains the fundamental models for call and appointment tracking.
These models persist the data that was previously stored in-memory.
"""
from __future__ import annotations

from datetime import datetime, date, time
from typing import TYPE_CHECKING, Any
from uuid import UUID

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
)
from sqlalchemy.dialects.sqlite import JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from phone_agent.db.base import Base, UUIDMixin, TimestampMixin

if TYPE_CHECKING:
    from phone_agent.db.models.crm import ContactModel


class CallModel(Base, UUIDMixin, TimestampMixin):
    """Call record ORM model.

    Stores all inbound and outbound call data including:
    - Call metadata (direction, status, participants)
    - Timing information (start, end, duration)
    - AI-generated content (transcript, summary)
    - Triage results and linked appointments
    """

    __tablename__ = "calls"

    # Call identification
    direction: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        index=True,
        comment="inbound or outbound",
    )
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        index=True,
        comment="incoming, ringing, active, on_hold, completed, missed, failed",
    )

    # Participants
    caller_id: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
        comment="Caller phone number",
    )
    callee_id: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="Callee phone number",
    )

    # Timing
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
    )
    ended_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    duration_seconds: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )

    # AI-generated content
    transcript: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Full call transcript",
    )
    summary: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="AI-generated call summary",
    )

    # Triage and outcomes
    triage_result: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        comment="Triage urgency level",
    )
    appointment_id: Mapped[str | None] = mapped_column(
        String(36),
        nullable=True,
        comment="Linked appointment UUID",
    )

    # Transfer information
    transferred: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )
    transfer_to: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        comment="Transfer destination",
    )
    transfer_reason: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    # Flexible metadata
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(
        JSON,
        nullable=True,
        comment="Additional call metadata",
    )

    # CRM link
    contact_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("contacts.id"),
        nullable=True,
        index=True,
    )

    # Relationships
    contact: Mapped["ContactModel | None"] = relationship(
        back_populates="calls",
        lazy="selectin",
    )

    # Indexes for common queries
    __table_args__ = (
        Index("ix_calls_started_at_desc", started_at.desc()),
        Index("ix_calls_caller_status", "caller_id", "status"),
    )

    def to_dict(self) -> dict[str, Any]:
        """Convert model to dictionary for API responses."""
        return {
            "id": str(self.id),
            "direction": self.direction,
            "status": self.status,
            "caller_id": self.caller_id,
            "callee_id": self.callee_id,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "ended_at": self.ended_at.isoformat() if self.ended_at else None,
            "duration_seconds": self.duration_seconds,
            "transcript": self.transcript,
            "summary": self.summary,
            "triage_result": self.triage_result,
            "appointment_id": self.appointment_id,
            "transferred": self.transferred,
            "transfer_to": self.transfer_to,
            "metadata": self.metadata_json or {},
            "contact_id": str(self.contact_id) if self.contact_id else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class AppointmentModel(Base, UUIDMixin, TimestampMixin):
    """Appointment record ORM model.

    Stores appointment scheduling data including:
    - Patient/customer information
    - Scheduled date and time
    - Appointment type and status
    - Reminder tracking
    """

    __tablename__ = "appointments"

    # Patient/customer info (denormalized for quick access)
    patient_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    patient_phone: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
    )
    patient_email: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    # Scheduling
    appointment_date: Mapped[date] = mapped_column(
        Date,
        nullable=False,
        index=True,
    )
    appointment_time: Mapped[time] = mapped_column(
        Time,
        nullable=False,
    )
    duration_minutes: Mapped[int] = mapped_column(
        Integer,
        default=15,
        nullable=False,
    )

    # Classification
    type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
        comment="consultation, checkup, followup, emergency, vaccination, etc.",
    )
    status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
        comment="scheduled, confirmed, cancelled, completed, no_show",
    )

    # Provider (for multi-provider practices)
    provider_id: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        index=True,
    )
    provider_name: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    # Notes and reason
    reason: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Reason for appointment",
    )
    notes: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Additional notes",
    )

    # Reminder tracking
    reminder_sent: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )
    reminder_sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # Confirmation
    confirmed: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )
    confirmed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # Source tracking
    created_by: Mapped[str] = mapped_column(
        String(100),
        default="phone_agent",
        nullable=False,
        comment="phone_agent, web, manual, pvs_sync",
    )

    # Link to originating call
    call_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("calls.id"),
        nullable=True,
    )

    # CRM link
    contact_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("contacts.id"),
        nullable=True,
        index=True,
    )

    # Flexible metadata
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(
        JSON,
        nullable=True,
    )

    # Relationships
    contact: Mapped["ContactModel | None"] = relationship(
        back_populates="appointments",
        lazy="selectin",
    )

    # Indexes
    __table_args__ = (
        Index("ix_appointments_date_status", "appointment_date", "status"),
        Index("ix_appointments_provider_date", "provider_id", "appointment_date"),
    )

    def to_dict(self) -> dict[str, Any]:
        """Convert model to dictionary for API responses."""
        return {
            "id": str(self.id),
            "patient_name": self.patient_name,
            "patient_phone": self.patient_phone,
            "patient_email": self.patient_email,
            "appointment_date": self.appointment_date.isoformat() if self.appointment_date else None,
            "appointment_time": self.appointment_time.isoformat() if self.appointment_time else None,
            "duration_minutes": self.duration_minutes,
            "type": self.type,
            "status": self.status,
            "provider_id": self.provider_id,
            "provider_name": self.provider_name,
            "reason": self.reason,
            "notes": self.notes,
            "reminder_sent": self.reminder_sent,
            "confirmed": self.confirmed,
            "created_by": self.created_by,
            "call_id": self.call_id,
            "contact_id": str(self.contact_id) if self.contact_id else None,
            "metadata": self.metadata_json or {},
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
