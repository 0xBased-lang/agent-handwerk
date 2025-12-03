"""SMS Message ORM Model for Phone Agent.

Stores SMS message records with delivery tracking for appointment
confirmations, reminders, and notifications.

Supports multiple providers (Twilio, sipgate) with unified status tracking.
"""
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID

from sqlalchemy import (
    String,
    Text,
    Integer,
    Float,
    DateTime,
    ForeignKey,
    Index,
)
from sqlalchemy.dialects.sqlite import JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from phone_agent.db.base import Base, UUIDMixin, TimestampMixin

if TYPE_CHECKING:
    from phone_agent.db.models.crm import ContactModel
    from phone_agent.db.models.core import AppointmentModel


class SMSMessageModel(Base, UUIDMixin, TimestampMixin):
    """SMS message record ORM model.

    Stores all SMS messages with delivery tracking including:
    - Message content and recipients
    - Provider information (Twilio, sipgate)
    - Delivery status updates from webhooks
    - Cost and segment information
    - Links to appointments and contacts
    """

    __tablename__ = "sms_messages"

    # Recipient information
    to_number: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
        comment="Recipient phone number in E.164 format",
    )
    from_number: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        comment="Sender phone number or ID",
    )

    # Message content
    body: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="SMS message body",
    )
    segments: Mapped[int] = mapped_column(
        Integer,
        default=1,
        nullable=False,
        comment="Number of SMS segments",
    )

    # Provider information
    provider: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
        comment="SMS provider: twilio, sipgate, mock",
    )
    provider_message_id: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        index=True,
        comment="External message ID from provider",
    )

    # Status tracking
    status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="pending",
        index=True,
        comment="pending, queued, sent, delivered, failed, undelivered",
    )
    error_code: Mapped[str | None] = mapped_column(
        String(20),
        nullable=True,
        comment="Provider error code if failed",
    )
    error_message: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Error description if failed",
    )

    # Timing
    queued_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="When message was queued for sending",
    )
    sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="When message was sent to carrier",
    )
    delivered_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="When message was delivered to recipient",
    )
    failed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="When message delivery failed",
    )

    # Cost tracking
    cost: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
        comment="Message cost in EUR",
    )
    cost_currency: Mapped[str] = mapped_column(
        String(3),
        default="EUR",
        nullable=False,
    )

    # Message type and reference
    message_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="notification",
        index=True,
        comment="confirmation, reminder, cancellation, notification, marketing",
    )
    reference: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        index=True,
        comment="External reference ID for correlation",
    )

    # Retry tracking - use Python defaults for non-persisted instances
    retry_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        insert_default=0,
        nullable=False,
        comment="Number of send attempts",
    )
    max_retries: Mapped[int] = mapped_column(
        Integer,
        default=3,
        insert_default=3,
        nullable=False,
        comment="Maximum retry attempts",
    )
    next_retry_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Next retry attempt time",
    )

    # Linked entities
    appointment_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("appointments.id"),
        nullable=True,
        index=True,
        comment="Linked appointment UUID",
    )
    contact_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("contacts.id"),
        nullable=True,
        index=True,
        comment="Linked contact UUID",
    )
    call_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("calls.id"),
        nullable=True,
        index=True,
        comment="Linked call UUID",
    )

    # Webhook tracking
    webhook_received: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
        comment="Number of status webhooks received",
    )
    last_webhook_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Last webhook received timestamp",
    )

    # Flexible metadata
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(
        JSON,
        nullable=True,
        comment="Additional message metadata",
    )

    # Relationships
    contact: Mapped["ContactModel | None"] = relationship(
        lazy="selectin",
    )

    # Indexes for common queries
    __table_args__ = (
        Index("ix_sms_messages_status_provider", "status", "provider"),
        Index("ix_sms_messages_created_status", "created_at", "status"),
        Index("ix_sms_messages_to_number_created", "to_number", "created_at"),
        Index("ix_sms_messages_retry", "status", "next_retry_at"),
    )

    def to_dict(self) -> dict[str, Any]:
        """Convert model to dictionary for API responses."""
        return {
            "id": str(self.id),
            "to_number": self.to_number,
            "from_number": self.from_number,
            "body": self.body,
            "segments": self.segments,
            "provider": self.provider,
            "provider_message_id": self.provider_message_id,
            "status": self.status,
            "error_code": self.error_code,
            "error_message": self.error_message,
            "queued_at": self.queued_at.isoformat() if self.queued_at else None,
            "sent_at": self.sent_at.isoformat() if self.sent_at else None,
            "delivered_at": self.delivered_at.isoformat() if self.delivered_at else None,
            "failed_at": self.failed_at.isoformat() if self.failed_at else None,
            "cost": self.cost,
            "cost_currency": self.cost_currency,
            "message_type": self.message_type,
            "reference": self.reference,
            "retry_count": self.retry_count,
            "max_retries": self.max_retries,
            "appointment_id": self.appointment_id,
            "contact_id": str(self.contact_id) if self.contact_id else None,
            "call_id": self.call_id,
            "webhook_received": self.webhook_received,
            "metadata": self.metadata_json or {},
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

    def mark_queued(self) -> None:
        """Mark message as queued for sending."""
        self.status = "queued"
        self.queued_at = datetime.now()

    def mark_sent(self, provider_message_id: str | None = None) -> None:
        """Mark message as sent to carrier."""
        self.status = "sent"
        self.sent_at = datetime.now()
        if provider_message_id:
            self.provider_message_id = provider_message_id

    def mark_delivered(self) -> None:
        """Mark message as delivered to recipient."""
        self.status = "delivered"
        self.delivered_at = datetime.now()

    def mark_failed(
        self,
        error_code: str | None = None,
        error_message: str | None = None,
    ) -> None:
        """Mark message as failed."""
        self.status = "failed"
        self.failed_at = datetime.now()
        self.error_code = error_code
        self.error_message = error_message

    def mark_undelivered(
        self,
        error_code: str | None = None,
        error_message: str | None = None,
    ) -> None:
        """Mark message as undelivered (sent but not received)."""
        self.status = "undelivered"
        self.failed_at = datetime.now()
        self.error_code = error_code
        self.error_message = error_message

    def can_retry(self) -> bool:
        """Check if message can be retried."""
        return (
            self.status in ("failed", "undelivered")
            and self.retry_count < self.max_retries
        )

    def increment_retry(self, next_retry_delay_seconds: int = 60) -> None:
        """Increment retry count and schedule next retry."""
        self.retry_count += 1
        self.status = "pending"
        self.next_retry_at = datetime.now() + timedelta(seconds=next_retry_delay_seconds)

    def record_webhook(self) -> None:
        """Record that a webhook was received."""
        self.webhook_received += 1
        self.last_webhook_at = datetime.now()


# Import timedelta at module level
from datetime import timedelta
