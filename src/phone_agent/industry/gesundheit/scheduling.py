"""Healthcare appointment scheduling system.

Intelligent scheduling with:
- Multi-provider calendar integration
- Urgency-aware slot allocation
- Patient preference matching
- Conflict resolution
- Appointment reminders
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, date, time, timedelta
from enum import Enum
from typing import Any, AsyncIterator
from uuid import UUID, uuid4
import asyncio


class AppointmentType(str, Enum):
    """Types of medical appointments."""

    ACUTE = "acute"                    # Akutsprechstunde
    REGULAR = "regular"                # Regeltermin
    FOLLOWUP = "followup"              # Wiedervorstellung
    PREVENTIVE = "preventive"          # Vorsorge
    VACCINATION = "vaccination"        # Impfung
    CHECKUP = "checkup"                # Check-up
    SPECIALIST = "specialist"          # Facharzt
    LAB = "lab"                        # Labor
    IMAGING = "imaging"                # Bildgebung


class SlotStatus(str, Enum):
    """Status of appointment slots."""

    AVAILABLE = "available"
    BOOKED = "booked"
    BLOCKED = "blocked"
    RESERVED = "reserved"  # Temporarily held


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
class Patient:
    """Patient information for scheduling."""

    id: UUID
    first_name: str
    last_name: str
    date_of_birth: date
    phone: str
    email: str | None = None
    insurance_number: str | None = None
    insurance_type: str = "GKV"  # GKV or PKV
    preferred_provider: str | None = None
    preferred_times: list[str] = field(default_factory=list)  # "morning", "afternoon"
    language: str = "de"
    notes: str | None = None

    @property
    def full_name(self) -> str:
        """Get full name."""
        return f"{self.first_name} {self.last_name}"

    @property
    def age(self) -> int:
        """Calculate age."""
        today = date.today()
        return today.year - self.date_of_birth.year - (
            (today.month, today.day) < (self.date_of_birth.month, self.date_of_birth.day)
        )


@dataclass
class Appointment:
    """Scheduled appointment."""

    id: UUID
    patient_id: UUID
    patient_name: str
    slot: TimeSlot
    reason: str
    appointment_type: AppointmentType
    urgency_level: str | None = None
    created_at: datetime = field(default_factory=datetime.now)
    created_by: str = "phone_agent"
    confirmed: bool = False
    reminder_sent: bool = False
    notes: str | None = None
    cancellation_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": str(self.id),
            "patient_id": str(self.patient_id),
            "patient_name": self.patient_name,
            "slot": self.slot.to_dict(),
            "reason": self.reason,
            "appointment_type": self.appointment_type.value,
            "urgency_level": self.urgency_level,
            "created_at": self.created_at.isoformat(),
            "created_by": self.created_by,
            "confirmed": self.confirmed,
            "reminder_sent": self.reminder_sent,
            "notes": self.notes,
            "cancellation_reason": self.cancellation_reason,
        }


@dataclass
class SchedulingPreferences:
    """Preferences for appointment scheduling."""

    preferred_date: date | None = None
    preferred_time: str | None = None  # "morning", "afternoon", "evening"
    preferred_provider: str | None = None
    urgency_max_wait_hours: int | None = None
    appointment_type: AppointmentType = AppointmentType.REGULAR
    duration_minutes: int = 15
    flexible_date: bool = True
    flexible_provider: bool = True


class CalendarIntegration:
    """Base class for calendar integrations."""

    async def get_available_slots(
        self,
        start_date: date,
        end_date: date,
        provider_id: str | None = None,
        appointment_type: AppointmentType | None = None,
    ) -> list[TimeSlot]:
        """Get available slots from calendar."""
        raise NotImplementedError

    async def book_slot(
        self,
        slot_id: UUID,
        patient: Patient,
        reason: str,
    ) -> Appointment:
        """Book a slot in the calendar."""
        raise NotImplementedError

    async def cancel_appointment(
        self,
        appointment_id: UUID,
        reason: str,
    ) -> bool:
        """Cancel an appointment."""
        raise NotImplementedError

    async def reschedule_appointment(
        self,
        appointment_id: UUID,
        new_slot_id: UUID,
    ) -> Appointment:
        """Reschedule an appointment to a new slot."""
        raise NotImplementedError


class MockCalendarIntegration(CalendarIntegration):
    """Mock calendar integration for development/testing."""

    def __init__(self):
        """Initialize mock calendar."""
        self._slots: dict[UUID, TimeSlot] = {}
        self._appointments: dict[UUID, Appointment] = {}
        self._generate_mock_slots()

    def _generate_mock_slots(self):
        """Generate mock available slots for next 2 weeks."""
        providers = [
            ("dr-mueller", "Dr. Müller"),
            ("dr-schmidt", "Dr. Schmidt"),
            ("dr-weber", "Dr. Weber"),
        ]

        today = date.today()

        for day_offset in range(14):
            current_date = today + timedelta(days=day_offset)

            # Skip weekends
            if current_date.weekday() >= 5:
                continue

            for provider_id, provider_name in providers:
                # Morning slots (8:00 - 12:00)
                for hour in range(8, 12):
                    for minute in [0, 15, 30, 45]:
                        start = datetime.combine(current_date, time(hour, minute))
                        slot = TimeSlot(
                            id=uuid4(),
                            start=start,
                            end=start + timedelta(minutes=15),
                            provider_id=provider_id,
                            provider_name=provider_name,
                        )
                        self._slots[slot.id] = slot

                # Afternoon slots (14:00 - 18:00)
                for hour in range(14, 18):
                    for minute in [0, 15, 30, 45]:
                        start = datetime.combine(current_date, time(hour, minute))
                        slot = TimeSlot(
                            id=uuid4(),
                            start=start,
                            end=start + timedelta(minutes=15),
                            provider_id=provider_id,
                            provider_name=provider_name,
                        )
                        self._slots[slot.id] = slot

    async def get_available_slots(
        self,
        start_date: date,
        end_date: date,
        provider_id: str | None = None,
        appointment_type: AppointmentType | None = None,
    ) -> list[TimeSlot]:
        """Get available slots from mock calendar."""
        slots = []

        for slot in self._slots.values():
            slot_date = slot.start.date()

            # Check date range
            if slot_date < start_date or slot_date > end_date:
                continue

            # Check availability
            if slot.status != SlotStatus.AVAILABLE:
                continue

            # Check provider filter
            if provider_id and slot.provider_id != provider_id:
                continue

            # Check if slot is in the future
            if slot.start <= datetime.now():
                continue

            slots.append(slot)

        # Sort by datetime
        slots.sort(key=lambda s: s.start)

        return slots

    async def book_slot(
        self,
        slot_id: UUID,
        patient: Patient,
        reason: str,
        appointment_type: AppointmentType = AppointmentType.REGULAR,
    ) -> Appointment:
        """Book a slot in the mock calendar."""
        if slot_id not in self._slots:
            raise ValueError(f"Slot {slot_id} not found")

        slot = self._slots[slot_id]

        if slot.status != SlotStatus.AVAILABLE:
            raise ValueError(f"Slot {slot_id} is not available")

        # Mark slot as booked
        slot.status = SlotStatus.BOOKED

        # Create appointment
        appointment = Appointment(
            id=uuid4(),
            patient_id=patient.id,
            patient_name=patient.full_name,
            slot=slot,
            reason=reason,
            appointment_type=appointment_type,
        )

        self._appointments[appointment.id] = appointment

        return appointment

    async def cancel_appointment(
        self,
        appointment_id: UUID,
        reason: str,
    ) -> bool:
        """Cancel an appointment in the mock calendar."""
        if appointment_id not in self._appointments:
            return False

        appointment = self._appointments[appointment_id]

        # Mark slot as available again
        appointment.slot.status = SlotStatus.AVAILABLE

        # Update appointment
        appointment.cancellation_reason = reason

        # Remove from appointments
        del self._appointments[appointment_id]

        return True

    async def reschedule_appointment(
        self,
        appointment_id: UUID,
        new_slot_id: UUID,
    ) -> Appointment:
        """Reschedule an appointment to a new slot."""
        if appointment_id not in self._appointments:
            raise ValueError(f"Appointment {appointment_id} not found")

        if new_slot_id not in self._slots:
            raise ValueError(f"Slot {new_slot_id} not found")

        old_appointment = self._appointments[appointment_id]
        new_slot = self._slots[new_slot_id]

        if new_slot.status != SlotStatus.AVAILABLE:
            raise ValueError(f"Slot {new_slot_id} is not available")

        # Release old slot
        old_appointment.slot.status = SlotStatus.AVAILABLE

        # Book new slot
        new_slot.status = SlotStatus.BOOKED

        # Create new appointment
        new_appointment = Appointment(
            id=uuid4(),
            patient_id=old_appointment.patient_id,
            patient_name=old_appointment.patient_name,
            slot=new_slot,
            reason=old_appointment.reason,
            appointment_type=old_appointment.appointment_type,
            urgency_level=old_appointment.urgency_level,
            notes=f"Umgebucht von {old_appointment.slot.start.strftime('%d.%m.%Y %H:%M')}",
        )

        # Update records
        del self._appointments[appointment_id]
        self._appointments[new_appointment.id] = new_appointment

        return new_appointment


class SchedulingService:
    """Intelligent appointment scheduling service."""

    def __init__(self, calendar: CalendarIntegration | None = None):
        """Initialize scheduling service."""
        self._calendar = calendar or MockCalendarIntegration()

    async def find_slots(
        self,
        preferences: SchedulingPreferences,
        limit: int = 5,
    ) -> list[TimeSlot]:
        """
        Find available slots matching preferences.

        Args:
            preferences: Scheduling preferences
            limit: Maximum number of slots to return

        Returns:
            List of matching slots, sorted by relevance
        """
        # Determine date range
        start_date = preferences.preferred_date or date.today()
        if preferences.urgency_max_wait_hours:
            hours = preferences.urgency_max_wait_hours
            end_date = start_date + timedelta(hours=hours)
        else:
            end_date = start_date + timedelta(days=14)

        # Get available slots
        slots = await self._calendar.get_available_slots(
            start_date=start_date,
            end_date=end_date,
            provider_id=preferences.preferred_provider if not preferences.flexible_provider else None,
            appointment_type=preferences.appointment_type,
        )

        # Score and sort slots
        scored_slots = [
            (slot, self._score_slot(slot, preferences))
            for slot in slots
        ]
        scored_slots.sort(key=lambda x: x[1], reverse=True)

        # Return top slots
        return [slot for slot, score in scored_slots[:limit]]

    def _score_slot(self, slot: TimeSlot, preferences: SchedulingPreferences) -> float:
        """Score a slot based on preference matching."""
        score = 100.0

        # Time preference matching
        if preferences.preferred_time:
            slot_hour = slot.start.hour
            if preferences.preferred_time == "morning" and slot_hour >= 12:
                score -= 20
            elif preferences.preferred_time == "afternoon" and slot_hour < 12:
                score -= 20
            elif preferences.preferred_time == "evening" and slot_hour < 16:
                score -= 20

        # Date preference matching
        if preferences.preferred_date:
            days_diff = abs((slot.start.date() - preferences.preferred_date).days)
            score -= days_diff * 10

        # Provider preference matching
        if preferences.preferred_provider:
            if slot.provider_id != preferences.preferred_provider:
                score -= 15

        # Prefer earlier slots for urgent appointments
        if preferences.urgency_max_wait_hours:
            hours_until = (slot.start - datetime.now()).total_seconds() / 3600
            if hours_until < preferences.urgency_max_wait_hours:
                score += 20

        return max(score, 0)

    async def book_appointment(
        self,
        slot_id: UUID,
        patient: Patient,
        reason: str,
        appointment_type: AppointmentType = AppointmentType.REGULAR,
        urgency_level: str | None = None,
    ) -> Appointment:
        """
        Book an appointment.

        Args:
            slot_id: ID of the slot to book
            patient: Patient information
            reason: Reason for appointment
            appointment_type: Type of appointment
            urgency_level: Urgency level from triage

        Returns:
            Created appointment
        """
        appointment = await self._calendar.book_slot(
            slot_id=slot_id,
            patient=patient,
            reason=reason,
            appointment_type=appointment_type,
        )

        appointment.urgency_level = urgency_level

        return appointment

    async def cancel_appointment(
        self,
        appointment_id: UUID,
        reason: str,
    ) -> bool:
        """
        Cancel an appointment.

        Args:
            appointment_id: ID of the appointment to cancel
            reason: Reason for cancellation

        Returns:
            True if cancelled successfully
        """
        return await self._calendar.cancel_appointment(appointment_id, reason)

    async def reschedule_appointment(
        self,
        appointment_id: UUID,
        new_slot_id: UUID,
    ) -> Appointment:
        """
        Reschedule an appointment.

        Args:
            appointment_id: ID of the appointment to reschedule
            new_slot_id: ID of the new slot

        Returns:
            Updated appointment
        """
        return await self._calendar.reschedule_appointment(
            appointment_id=appointment_id,
            new_slot_id=new_slot_id,
        )

    def format_slot_for_speech(self, slot: TimeSlot, language: str = "de") -> str:
        """
        Format a slot for speech output.

        Args:
            slot: Time slot
            language: Language code

        Returns:
            Human-readable slot description
        """
        if language == "de":
            # German date/time format
            weekdays = ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"]
            day_name = weekdays[slot.start.weekday()]
            date_str = slot.start.strftime("%d.%m.")
            time_str = slot.start.strftime("%H:%M")

            return f"{day_name}, den {date_str} um {time_str} Uhr bei {slot.provider_name}"

        # English fallback
        return f"{slot.start.strftime('%A, %B %d at %H:%M')} with {slot.provider_name}"

    def format_slots_for_speech(
        self,
        slots: list[TimeSlot],
        language: str = "de",
        max_slots: int = 3,
    ) -> str:
        """
        Format multiple slots for speech output.

        Args:
            slots: List of time slots
            language: Language code
            max_slots: Maximum slots to include

        Returns:
            Human-readable slot options
        """
        if not slots:
            if language == "de":
                return "Leider habe ich aktuell keine freien Termine gefunden."
            return "I couldn't find any available appointments."

        slots = slots[:max_slots]

        if language == "de":
            if len(slots) == 1:
                return f"Ich kann Ihnen folgenden Termin anbieten: {self.format_slot_for_speech(slots[0], language)}"

            options = [
                f"Option {i+1}: {self.format_slot_for_speech(slot, language)}"
                for i, slot in enumerate(slots)
            ]
            return "Ich kann Ihnen folgende Termine anbieten:\n" + "\n".join(options)

        # English fallback
        options = [self.format_slot_for_speech(slot, language) for slot in slots]
        return "Available appointments:\n" + "\n".join(options)


# Singleton instance
_scheduling_service: SchedulingService | None = None


def get_scheduling_service() -> SchedulingService:
    """Get or create scheduling service singleton."""
    global _scheduling_service
    if _scheduling_service is None:
        _scheduling_service = SchedulingService()
    return _scheduling_service
