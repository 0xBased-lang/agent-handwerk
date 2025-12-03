"""Base Email Gateway Interface.

Defines the abstract interface for email gateways.
All email implementations must implement this interface.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any
from uuid import UUID, uuid4


class EmailStatus(str, Enum):
    """Status of an email message."""

    PENDING = "pending"
    QUEUED = "queued"
    SENT = "sent"
    DELIVERED = "delivered"
    OPENED = "opened"
    CLICKED = "clicked"
    BOUNCED = "bounced"
    FAILED = "failed"
    SPAM = "spam"
    UNSUBSCRIBED = "unsubscribed"
    UNKNOWN = "unknown"


class EmailPriority(str, Enum):
    """Email priority levels."""

    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"


@dataclass
class EmailAttachment:
    """Email attachment."""

    filename: str
    content: bytes
    content_type: str = "application/octet-stream"
    content_id: str | None = None  # For inline images


@dataclass
class EmailMessage:
    """Email message to send."""

    to: str | list[str]  # Recipient email(s)
    subject: str
    body_text: str | None = None  # Plain text body
    body_html: str | None = None  # HTML body
    from_email: str | None = None  # Sender email
    from_name: str | None = None  # Sender display name
    reply_to: str | None = None
    cc: list[str] | None = None
    bcc: list[str] | None = None
    attachments: list[EmailAttachment] | None = None
    headers: dict[str, str] | None = None
    priority: EmailPriority = EmailPriority.NORMAL
    reference: str | None = None  # External reference ID
    template_id: str | None = None  # For template-based emails
    template_data: dict[str, Any] | None = None  # Template variables
    scheduled_at: datetime | None = None  # Schedule for later delivery
    tags: list[str] | None = None  # For categorization and tracking

    def __post_init__(self):
        """Normalize recipient list."""
        if isinstance(self.to, str):
            self.to = [self.to]

    @property
    def recipients(self) -> list[str]:
        """Get all recipients (to, cc, bcc)."""
        all_recipients = list(self.to)
        if self.cc:
            all_recipients.extend(self.cc)
        if self.bcc:
            all_recipients.extend(self.bcc)
        return all_recipients


@dataclass
class EmailResult:
    """Result of an email send operation."""

    success: bool
    message_id: str | None = None
    status: EmailStatus = EmailStatus.UNKNOWN
    provider: str = ""
    error_message: str | None = None
    error_code: str | None = None
    sent_at: datetime | None = None
    recipients_accepted: int = 0
    recipients_rejected: int = 0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "success": self.success,
            "message_id": self.message_id,
            "status": self.status.value,
            "provider": self.provider,
            "error_message": self.error_message,
            "error_code": self.error_code,
            "sent_at": self.sent_at.isoformat() if self.sent_at else None,
            "recipients_accepted": self.recipients_accepted,
            "recipients_rejected": self.recipients_rejected,
        }


class EmailGateway(ABC):
    """Abstract base class for email gateways.

    All email implementations must implement these methods:
    - send: Send a single email
    - send_bulk: Send multiple emails
    - get_status: Check delivery status (if supported)
    """

    @abstractmethod
    async def send(self, message: EmailMessage) -> EmailResult:
        """Send a single email message.

        Args:
            message: Email message to send

        Returns:
            Result with success status and message ID
        """
        pass

    async def send_bulk(self, messages: list[EmailMessage]) -> list[EmailResult]:
        """Send multiple email messages.

        Default implementation sends one by one.
        Override for batch optimization.

        Args:
            messages: List of messages to send

        Returns:
            List of results for each message
        """
        results = []
        for message in messages:
            result = await self.send(message)
            results.append(result)
        return results

    async def get_status(self, message_id: str) -> EmailStatus:
        """Check delivery status of a message.

        Not all providers support this. Default returns UNKNOWN.

        Args:
            message_id: Message ID from send result

        Returns:
            Current delivery status
        """
        return EmailStatus.UNKNOWN

    def validate_email(self, email: str) -> bool:
        """Basic email validation.

        Args:
            email: Email address to validate

        Returns:
            True if email format is valid
        """
        import re

        pattern = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
        return bool(re.match(pattern, email))

    def validate_message(self, message: EmailMessage) -> list[str]:
        """Validate email message.

        Args:
            message: Email message to validate

        Returns:
            List of validation errors (empty if valid)
        """
        errors = []

        # Check recipients
        if not message.to:
            errors.append("At least one recipient is required")
        else:
            for email in message.to:
                if not self.validate_email(email):
                    errors.append(f"Invalid recipient email: {email}")

        # Check CC/BCC
        if message.cc:
            for email in message.cc:
                if not self.validate_email(email):
                    errors.append(f"Invalid CC email: {email}")

        if message.bcc:
            for email in message.bcc:
                if not self.validate_email(email):
                    errors.append(f"Invalid BCC email: {email}")

        # Check subject
        if not message.subject:
            errors.append("Subject is required")

        # Check body
        if not message.body_text and not message.body_html:
            errors.append("Either text or HTML body is required")

        return errors


class MockEmailGateway(EmailGateway):
    """Mock email gateway for development and testing."""

    def __init__(self):
        """Initialize mock gateway."""
        self._sent_messages: list[dict[str, Any]] = []
        self._message_statuses: dict[str, EmailStatus] = {}

    async def send(self, message: EmailMessage) -> EmailResult:
        """Mock send - logs message and returns success."""
        from itf_shared import get_logger

        log = get_logger(__name__)

        # Validate message
        errors = self.validate_message(message)
        if errors:
            return EmailResult(
                success=False,
                status=EmailStatus.FAILED,
                provider="mock",
                error_message="; ".join(errors),
            )

        message_id = str(uuid4())

        log.info(
            "Mock email sent",
            message_id=message_id,
            to=message.to,
            subject=message.subject,
        )

        self._sent_messages.append(
            {
                "message_id": message_id,
                "to": message.to,
                "subject": message.subject,
                "body_text": message.body_text,
                "body_html": message.body_html,
                "sent_at": datetime.now(),
            }
        )

        self._message_statuses[message_id] = EmailStatus.SENT

        return EmailResult(
            success=True,
            message_id=message_id,
            status=EmailStatus.SENT,
            provider="mock",
            sent_at=datetime.now(),
            recipients_accepted=len(message.recipients),
        )

    async def get_status(self, message_id: str) -> EmailStatus:
        """Get mock message status."""
        return self._message_statuses.get(message_id, EmailStatus.UNKNOWN)

    def get_sent_messages(self) -> list[dict[str, Any]]:
        """Get list of all sent messages (for testing)."""
        return self._sent_messages.copy()

    def clear_sent_messages(self) -> None:
        """Clear sent messages list (for testing)."""
        self._sent_messages.clear()
        self._message_statuses.clear()

    def simulate_delivery(self, message_id: str) -> None:
        """Simulate message delivery (for testing)."""
        if message_id in self._message_statuses:
            self._message_statuses[message_id] = EmailStatus.DELIVERED

    def simulate_bounce(self, message_id: str) -> None:
        """Simulate message bounce (for testing)."""
        if message_id in self._message_statuses:
            self._message_statuses[message_id] = EmailStatus.BOUNCED

    def simulate_open(self, message_id: str) -> None:
        """Simulate message open (for testing)."""
        if message_id in self._message_statuses:
            self._message_statuses[message_id] = EmailStatus.OPENED
