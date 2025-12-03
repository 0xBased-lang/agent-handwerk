"""Base SMS Gateway Interface.

Defines the abstract interface for SMS gateways.
All SMS implementations must implement this interface.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any
from uuid import UUID, uuid4


class SMSStatus(str, Enum):
    """Status of an SMS message."""

    PENDING = "pending"
    SENT = "sent"
    DELIVERED = "delivered"
    FAILED = "failed"
    UNKNOWN = "unknown"


@dataclass
class SMSMessage:
    """SMS message to send."""

    to: str  # Phone number in E.164 format (e.g., +491234567890)
    body: str  # Message text
    from_number: str | None = None  # Sender ID (optional)
    reference: str | None = None  # External reference ID
    scheduled_at: datetime | None = None  # Schedule for later delivery


@dataclass
class SMSResult:
    """Result of an SMS send operation."""

    success: bool
    message_id: str | None = None
    status: SMSStatus = SMSStatus.UNKNOWN
    provider: str = ""
    error_message: str | None = None
    sent_at: datetime | None = None
    cost: float | None = None  # Cost in EUR
    segments: int = 1  # Number of SMS segments

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "success": self.success,
            "message_id": self.message_id,
            "status": self.status.value,
            "provider": self.provider,
            "error_message": self.error_message,
            "sent_at": self.sent_at.isoformat() if self.sent_at else None,
            "cost": self.cost,
            "segments": self.segments,
        }


class SMSGateway(ABC):
    """Abstract base class for SMS gateways.

    All SMS implementations must implement these methods:
    - send: Send a single SMS
    - send_bulk: Send multiple SMS messages
    - get_status: Check delivery status
    """

    @abstractmethod
    async def send(self, message: SMSMessage) -> SMSResult:
        """Send a single SMS message.

        Args:
            message: SMS message to send

        Returns:
            Result with success status and message ID
        """
        pass

    async def send_bulk(self, messages: list[SMSMessage]) -> list[SMSResult]:
        """Send multiple SMS messages.

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

    @abstractmethod
    async def get_status(self, message_id: str) -> SMSStatus:
        """Check delivery status of a message.

        Args:
            message_id: Message ID from send result

        Returns:
            Current delivery status
        """
        pass

    def normalize_phone(self, phone: str) -> str:
        """Normalize phone number to E.164 format.

        Converts German phone numbers to international format.

        Args:
            phone: Phone number in any format

        Returns:
            Phone number in E.164 format (e.g., +491234567890)
        """
        # Remove spaces, dashes, and parentheses
        phone = "".join(c for c in phone if c.isdigit() or c == "+")

        # Handle German numbers
        if phone.startswith("0049"):
            phone = "+" + phone[2:]
        elif phone.startswith("49"):
            phone = "+" + phone
        elif phone.startswith("0"):
            phone = "+49" + phone[1:]
        elif not phone.startswith("+"):
            phone = "+49" + phone

        return phone

    def calculate_segments(self, text: str) -> int:
        """Calculate number of SMS segments for a message.

        Standard SMS: 160 chars (GSM-7) or 70 chars (Unicode)
        Concatenated: 153 chars (GSM-7) or 67 chars (Unicode) per segment

        Args:
            text: Message text

        Returns:
            Number of segments
        """
        # Check for non-GSM-7 characters
        gsm7_chars = set(
            "@£$¥èéùìòÇ\nØø\rÅåΔ_ΦΓΛΩΠΨΣΘΞ ÆæßÉ"
            '!"#¤%&\'()*+,-./0123456789:;<=>?'
            "¡ABCDEFGHIJKLMNOPQRSTUVWXYZÄÖÑÜ§"
            "¿abcdefghijklmnopqrstuvwxyzäöñüà"
        )

        is_gsm7 = all(c in gsm7_chars for c in text)

        if is_gsm7:
            if len(text) <= 160:
                return 1
            return (len(text) + 152) // 153
        else:
            if len(text) <= 70:
                return 1
            return (len(text) + 66) // 67


class MockSMSGateway(SMSGateway):
    """Mock SMS gateway for development and testing."""

    def __init__(self):
        """Initialize mock gateway."""
        self._sent_messages: list[dict[str, Any]] = []
        self._message_statuses: dict[str, SMSStatus] = {}

    async def send(self, message: SMSMessage) -> SMSResult:
        """Mock send - logs message and returns success."""
        from itf_shared import get_logger
        log = get_logger(__name__)

        message_id = str(uuid4())
        normalized_to = self.normalize_phone(message.to)

        log.info(
            "Mock SMS sent",
            message_id=message_id,
            to=normalized_to,
            body_length=len(message.body),
            segments=self.calculate_segments(message.body),
        )

        self._sent_messages.append({
            "message_id": message_id,
            "to": normalized_to,
            "body": message.body,
            "sent_at": datetime.now(),
        })

        self._message_statuses[message_id] = SMSStatus.SENT

        return SMSResult(
            success=True,
            message_id=message_id,
            status=SMSStatus.SENT,
            provider="mock",
            sent_at=datetime.now(),
            segments=self.calculate_segments(message.body),
        )

    async def get_status(self, message_id: str) -> SMSStatus:
        """Get mock message status."""
        return self._message_statuses.get(message_id, SMSStatus.UNKNOWN)

    def get_sent_messages(self) -> list[dict[str, Any]]:
        """Get list of all sent messages (for testing)."""
        return self._sent_messages.copy()

    def clear_sent_messages(self) -> None:
        """Clear sent messages list (for testing)."""
        self._sent_messages.clear()
        self._message_statuses.clear()
