"""Email Message ORM Model for Phone Agent.

Stores email message records with delivery tracking for appointment
confirmations, reminders, and notifications.

Supports multiple providers (SMTP, SendGrid) with unified status tracking.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Any
from uuid import UUID

from sqlalchemy import (
    String,
    Text,
    Integer,
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


class EmailMessageModel(Base, UUIDMixin, TimestampMixin):
    """Email message record ORM model.

    Stores all email messages with delivery tracking including:
    - Message content and recipients
    - Provider information (SMTP, SendGrid)
    - Delivery status updates from webhooks
    - Open and click tracking (SendGrid)
    - Links to appointments and contacts
    """

    __tablename__ = "email_messages"

    # Recipient information
    to_email: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True,
        comment="Primary recipient email address",
    )
    to_emails_json: Mapped[list[str] | None] = mapped_column(
        JSON,
        nullable=True,
        comment="All recipient emails (to, cc, bcc)",
    )
    from_email: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        comment="Sender email address",
    )
    from_name: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        comment="Sender display name",
    )
    reply_to: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        comment="Reply-to email address",
    )

    # Message content
    subject: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
        comment="Email subject",
    )
    body_text: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Plain text body",
    )
    body_html: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="HTML body",
    )
    has_attachments: Mapped[bool] = mapped_column(
        default=False,
        nullable=False,
        comment="Whether email has attachments",
    )

    # Provider information
    provider: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
        comment="Email provider: smtp, sendgrid, mock",
    )
    provider_message_id: Mapped[str | None] = mapped_column(
        String(255),
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
        comment="pending, queued, sent, delivered, opened, clicked, bounced, failed",
    )
    error_code: Mapped[str | None] = mapped_column(
        String(50),
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
        comment="When message was sent",
    )
    delivered_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="When message was delivered",
    )
    opened_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="When message was first opened",
    )
    clicked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="When message link was first clicked",
    )
    bounced_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="When message bounced",
    )
    failed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="When message delivery failed",
    )

    # Engagement tracking
    open_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
        comment="Number of times email was opened",
    )
    click_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
        comment="Number of link clicks",
    )
    last_opened_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Last time email was opened",
    )
    last_clicked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Last time link was clicked",
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
    tags_json: Mapped[list[str] | None] = mapped_column(
        JSON,
        nullable=True,
        comment="Tags for categorization",
    )

    # Retry tracking
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
        Index("ix_email_messages_status_provider", "status", "provider"),
        Index("ix_email_messages_created_status", "created_at", "status"),
        Index("ix_email_messages_to_email_created", "to_email", "created_at"),
        Index("ix_email_messages_retry", "status", "next_retry_at"),
    )

    def to_dict(self) -> dict[str, Any]:
        """Convert model to dictionary for API responses."""
        return {
            "id": str(self.id),
            "to_email": self.to_email,
            "to_emails": self.to_emails_json,
            "from_email": self.from_email,
            "from_name": self.from_name,
            "subject": self.subject,
            "has_attachments": self.has_attachments,
            "provider": self.provider,
            "provider_message_id": self.provider_message_id,
            "status": self.status,
            "error_code": self.error_code,
            "error_message": self.error_message,
            "queued_at": self.queued_at.isoformat() if self.queued_at else None,
            "sent_at": self.sent_at.isoformat() if self.sent_at else None,
            "delivered_at": self.delivered_at.isoformat() if self.delivered_at else None,
            "opened_at": self.opened_at.isoformat() if self.opened_at else None,
            "clicked_at": self.clicked_at.isoformat() if self.clicked_at else None,
            "bounced_at": self.bounced_at.isoformat() if self.bounced_at else None,
            "open_count": self.open_count,
            "click_count": self.click_count,
            "message_type": self.message_type,
            "reference": self.reference,
            "tags": self.tags_json,
            "retry_count": self.retry_count,
            "appointment_id": self.appointment_id,
            "contact_id": str(self.contact_id) if self.contact_id else None,
            "webhook_received": self.webhook_received,
            "metadata": self.metadata_json or {},
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

    def mark_queued(self) -> None:
        """Mark message as queued for sending."""
        self.status = "queued"
        self.queued_at = datetime.now(timezone.utc)

    def mark_sent(self, provider_message_id: str | None = None) -> None:
        """Mark message as sent."""
        self.status = "sent"
        self.sent_at = datetime.now(timezone.utc)
        if provider_message_id:
            self.provider_message_id = provider_message_id

    def mark_delivered(self) -> None:
        """Mark message as delivered."""
        self.status = "delivered"
        self.delivered_at = datetime.now(timezone.utc)

    def mark_opened(self) -> None:
        """Mark message as opened."""
        if self.opened_at is None:
            self.opened_at = datetime.now(timezone.utc)
        self.open_count += 1
        self.last_opened_at = datetime.now(timezone.utc)
        if self.status in ("sent", "delivered"):
            self.status = "opened"

    def mark_clicked(self) -> None:
        """Mark message as clicked."""
        if self.clicked_at is None:
            self.clicked_at = datetime.now(timezone.utc)
        self.click_count += 1
        self.last_clicked_at = datetime.now(timezone.utc)
        if self.status in ("sent", "delivered", "opened"):
            self.status = "clicked"

    def mark_bounced(
        self,
        error_code: str | None = None,
        error_message: str | None = None,
    ) -> None:
        """Mark message as bounced."""
        self.status = "bounced"
        self.bounced_at = datetime.now(timezone.utc)
        self.error_code = error_code
        self.error_message = error_message

    def mark_failed(
        self,
        error_code: str | None = None,
        error_message: str | None = None,
    ) -> None:
        """Mark message as failed."""
        self.status = "failed"
        self.failed_at = datetime.now(timezone.utc)
        self.error_code = error_code
        self.error_message = error_message

    def can_retry(self) -> bool:
        """Check if message can be retried."""
        return (
            self.status in ("failed", "bounced")
            and self.retry_count < self.max_retries
        )

    def increment_retry(self, next_retry_delay_seconds: int = 60) -> None:
        """Increment retry count and schedule next retry."""
        self.retry_count += 1
        self.status = "pending"
        self.next_retry_at = datetime.now(timezone.utc) + timedelta(seconds=next_retry_delay_seconds)

    def record_webhook(self) -> None:
        """Record that a webhook was received."""
        self.webhook_received += 1
        self.last_webhook_at = datetime.now(timezone.utc)
