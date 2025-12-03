"""Base calendar integration interface.

Defines the abstract interface for calendar integrations.
All calendar implementations (local, Google, Outlook, etc.) must implement this interface.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, date, time, timedelta
from enum import Enum
from typing import Any
from uuid import UUID, uuid4


class SlotStatus(str, Enum):
    """Status of appointment slots."""

    AVAILABLE = "available"
    BOOKED = "booked"
    BLOCKED = "blocked"
    RESERVED = "reserved"  # Temporarily held


class AppointmentType(str, Enum):
    """Types of appointments."""

    REGULAR = "regular"
    ACUTE = "acute"
    FOLLOWUP = "followup"
    PREVENTIVE = "preventive"
    CONSULTATION = "consultation"


@dataclass
class TimeSlot:
    """Available time slot for appointments."""

    id: UUID
    start: datetime
    end: datetime
    provider_id: str
    provider_name: str
    status: SlotStatus = SlotStatus.AVAILABLE
    appointment_type: AppointmentType = AppointmentType.REGULAR
    room: str | None = None
    notes: str | None = None

    @property
    def duration_minutes(self) -> int:
        """Get slot duration in minutes."""
        return int((self.end - self.start).total_seconds() / 60)

    @property
    def date(self) -> date:
        """Get the date of this slot."""
        return self.start.date()

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": str(self.id),
            "start": self.start.isoformat(),
            "end": self.end.isoformat(),
            "provider_id": self.provider_id,
            "provider_name": self.provider_name,
            "status": self.status.value,
            "appointment_type": self.appointment_type.value,
            "duration_minutes": self.duration_minutes,
            "room": self.room,
            "notes": self.notes,
        }


@dataclass
class BookingRequest:
    """Request to book an appointment."""

    slot_id: UUID
    patient_id: UUID
    patient_name: str
    patient_phone: str
    reason: str
    appointment_type: AppointmentType = AppointmentType.REGULAR
    notes: str | None = None
    send_confirmation: bool = True


@dataclass
class BookingResult:
    """Result of a booking operation."""

    success: bool
    appointment_id: UUID | None = None
    slot: TimeSlot | None = None
    message: str | None = None
    confirmation_sent: bool = False

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "success": self.success,
            "appointment_id": str(self.appointment_id) if self.appointment_id else None,
            "slot": self.slot.to_dict() if self.slot else None,
            "message": self.message,
            "confirmation_sent": self.confirmation_sent,
        }


class CalendarIntegration(ABC):
    """Abstract base class for calendar integrations.

    All calendar implementations must implement these methods:
    - get_available_slots: Retrieve available time slots
    - book_slot: Book an appointment
    - cancel_booking: Cancel an appointment
    - reschedule_booking: Move an appointment to a new slot
    """

    @abstractmethod
    async def get_available_slots(
        self,
        start_date: date,
        end_date: date,
        provider_id: str | None = None,
        appointment_type: AppointmentType | None = None,
        duration_minutes: int = 15,
    ) -> list[TimeSlot]:
        """Get available slots from calendar.

        Args:
            start_date: Start of date range
            end_date: End of date range
            provider_id: Filter by specific provider
            appointment_type: Filter by appointment type
            duration_minutes: Required slot duration

        Returns:
            List of available time slots
        """
        pass

    @abstractmethod
    async def book_slot(self, request: BookingRequest) -> BookingResult:
        """Book a slot in the calendar.

        Args:
            request: Booking request with patient and slot details

        Returns:
            Booking result with success status and appointment ID
        """
        pass

    @abstractmethod
    async def cancel_booking(
        self,
        appointment_id: UUID,
        reason: str,
    ) -> bool:
        """Cancel an appointment.

        Args:
            appointment_id: ID of the appointment to cancel
            reason: Cancellation reason

        Returns:
            True if cancelled successfully
        """
        pass

    @abstractmethod
    async def reschedule_booking(
        self,
        appointment_id: UUID,
        new_slot_id: UUID,
    ) -> BookingResult:
        """Reschedule an appointment to a new slot.

        Args:
            appointment_id: ID of the appointment to reschedule
            new_slot_id: ID of the new slot

        Returns:
            Booking result with new appointment details
        """
        pass

    async def get_next_available(
        self,
        provider_id: str | None = None,
        appointment_type: AppointmentType | None = None,
    ) -> TimeSlot | None:
        """Get the next available slot.

        Convenience method to find the soonest available appointment.

        Args:
            provider_id: Filter by specific provider
            appointment_type: Filter by appointment type

        Returns:
            Next available slot, or None if none available
        """
        today = date.today()
        end_date = today + timedelta(days=30)

        slots = await self.get_available_slots(
            start_date=today,
            end_date=end_date,
            provider_id=provider_id,
            appointment_type=appointment_type,
        )

        return slots[0] if slots else None

    async def check_availability(
        self,
        slot_id: UUID,
    ) -> bool:
        """Check if a specific slot is still available.

        Args:
            slot_id: Slot ID to check

        Returns:
            True if slot is available
        """
        # Default implementation - can be overridden for efficiency
        return True
