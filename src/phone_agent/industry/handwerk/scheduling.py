"""Service call scheduling for Handwerk.

Implements:
- Time window based scheduling (2-4 hour windows)
- Technician integration
- Customer preference matching
- German time formatting
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, date, time, timedelta
from enum import Enum
from typing import Any
from uuid import UUID, uuid4


class JobType(str, Enum):
    """Types of service calls."""

    NOTFALL = "notfall"               # Emergency call-out
    REPARATUR = "reparatur"           # Repair
    INSTALLATION = "installation"     # New installation
    WARTUNG = "wartung"               # Maintenance
    INSPEKTION = "inspektion"         # Inspection
    BERATUNG = "beratung"             # Consultation
    KOSTENVORANSCHLAG = "kostenvoranschlag"  # Quote/Estimate


class TimeWindow(str, Enum):
    """Standard time windows."""

    FRUEH = "frueh"           # 07:00-10:00
    VORMITTAG = "vormittag"   # 08:00-12:00
    MITTAG = "mittag"         # 11:00-14:00
    NACHMITTAG = "nachmittag" # 13:00-17:00
    SPAET = "spaet"           # 16:00-19:00
    ABEND = "abend"           # 18:00-20:00 (emergency only)


class SlotStatus(str, Enum):
    """Status of time slots."""

    AVAILABLE = "available"
    BOOKED = "booked"
    BLOCKED = "blocked"
    RESERVED = "reserved"


# Time window definitions
TIME_WINDOWS: dict[TimeWindow, tuple[time, time]] = {
    TimeWindow.FRUEH: (time(7, 0), time(10, 0)),
    TimeWindow.VORMITTAG: (time(8, 0), time(12, 0)),
    TimeWindow.MITTAG: (time(11, 0), time(14, 0)),
    TimeWindow.NACHMITTAG: (time(13, 0), time(17, 0)),
    TimeWindow.SPAET: (time(16, 0), time(19, 0)),
    TimeWindow.ABEND: (time(18, 0), time(20, 0)),
}

# German names for time windows
TIME_WINDOW_NAMES: dict[TimeWindow, str] = {
    TimeWindow.FRUEH: "Früh (7-10 Uhr)",
    TimeWindow.VORMITTAG: "Vormittags (8-12 Uhr)",
    TimeWindow.MITTAG: "Mittags (11-14 Uhr)",
    TimeWindow.NACHMITTAG: "Nachmittags (13-17 Uhr)",
    TimeWindow.SPAET: "Spätnachmittags (16-19 Uhr)",
    TimeWindow.ABEND: "Abends (18-20 Uhr)",
}


@dataclass
class Customer:
    """Customer information for scheduling."""

    id: UUID
    first_name: str
    last_name: str
    phone: str
    email: str | None = None

    # Address
    street: str = ""
    house_number: str = ""
    zip_code: str = ""
    city: str = ""
    floor: int | None = None
    apartment: str | None = None

    # Access info
    access_notes: str | None = None  # "Schlüssel bei Nachbar", "Tor-Code 1234"
    contact_on_site: str | None = None  # Person to contact if different
    contact_phone: str | None = None

    # Property info
    property_type: str = "apartment"  # "apartment", "house", "commercial"
    is_owner: bool = True

    # Coordinates for routing
    latitude: float | None = None
    longitude: float | None = None

    @property
    def full_name(self) -> str:
        """Get full name."""
        return f"{self.first_name} {self.last_name}"

    @property
    def full_address(self) -> str:
        """Get full address."""
        addr = f"{self.street} {self.house_number}"
        if self.apartment:
            addr += f", {self.apartment}"
        if self.floor is not None:
            # Floor 0 is ground floor (EG in German), others are upper floors (OG)
            floor_str = "EG" if self.floor == 0 else f"{self.floor}. OG"
            addr += f", {floor_str}"
        addr += f"\n{self.zip_code} {self.city}"
        return addr

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": str(self.id),
            "full_name": self.full_name,
            "phone": self.phone,
            "email": self.email,
            "full_address": self.full_address,
            "property_type": self.property_type,
            "access_notes": self.access_notes,
        }


@dataclass
class TimeSlot:
    """Available time slot for service calls."""

    id: UUID
    date: date
    window: TimeWindow
    technician_id: UUID | None = None
    technician_name: str | None = None
    status: SlotStatus = SlotStatus.AVAILABLE
    job_type: JobType = JobType.REPARATUR
    notes: str | None = None

    @property
    def start_time(self) -> time:
        """Get start time of window."""
        return TIME_WINDOWS[self.window][0]

    @property
    def end_time(self) -> time:
        """Get end time of window."""
        return TIME_WINDOWS[self.window][1]

    @property
    def window_name(self) -> str:
        """Get German name of time window."""
        return TIME_WINDOW_NAMES[self.window]

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": str(self.id),
            "date": self.date.isoformat(),
            "window": self.window.value,
            "window_name": self.window_name,
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat(),
            "technician_id": str(self.technician_id) if self.technician_id else None,
            "technician_name": self.technician_name,
            "status": self.status.value,
            "job_type": self.job_type.value,
        }


@dataclass
class ServiceCall:
    """Scheduled service call."""

    id: UUID
    customer_id: UUID
    customer_name: str
    customer_phone: str
    slot: TimeSlot
    job_description: str
    job_type: JobType
    address: str
    estimated_duration_minutes: int = 60
    technician_id: UUID | None = None
    technician_name: str | None = None

    # Status
    created_at: datetime = field(default_factory=datetime.now)
    created_by: str = "phone_agent"
    confirmed: bool = False
    reminder_sent: bool = False
    sms_sent: bool = False

    # Outcome
    status: str = "scheduled"  # scheduled, in_progress, completed, cancelled, no_show
    cancellation_reason: str | None = None
    completion_notes: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": str(self.id),
            "customer_id": str(self.customer_id),
            "customer_name": self.customer_name,
            "customer_phone": self.customer_phone,
            "slot": self.slot.to_dict(),
            "job_description": self.job_description,
            "job_type": self.job_type.value,
            "address": self.address,
            "estimated_duration_minutes": self.estimated_duration_minutes,
            "technician_id": str(self.technician_id) if self.technician_id else None,
            "technician_name": self.technician_name,
            "created_at": self.created_at.isoformat(),
            "confirmed": self.confirmed,
            "status": self.status,
        }


@dataclass
class SchedulingPreferences:
    """Preferences for scheduling service calls."""

    preferred_date: date | None = None
    preferred_window: TimeWindow | None = None
    urgency_max_wait_hours: int | None = None
    job_type: JobType = JobType.REPARATUR
    estimated_duration_minutes: int = 60
    flexible_date: bool = True
    flexible_window: bool = True
    preferred_technician_id: UUID | None = None


class MockCalendar:
    """Mock calendar for development/testing."""

    def __init__(self):
        """Initialize mock calendar."""
        self._slots: dict[UUID, TimeSlot] = {}
        self._service_calls: dict[UUID, ServiceCall] = {}
        self._generate_mock_slots()

    def _generate_mock_slots(self):
        """Generate mock available slots for next 2 weeks."""
        from phone_agent.industry.handwerk.technician import (
            MockTechnicianPool,
        )

        pool = MockTechnicianPool()
        technicians = pool.technicians

        today = date.today()

        for day_offset in range(14):
            current_date = today + timedelta(days=day_offset)

            # Skip Sundays
            if current_date.weekday() == 6:
                continue

            # Saturday only vormittag
            if current_date.weekday() == 5:
                windows = [TimeWindow.VORMITTAG]
            else:
                windows = [
                    TimeWindow.FRUEH,
                    TimeWindow.VORMITTAG,
                    TimeWindow.NACHMITTAG,
                    TimeWindow.SPAET,
                ]

            for tech in technicians:
                for window in windows:
                    slot = TimeSlot(
                        id=uuid4(),
                        date=current_date,
                        window=window,
                        technician_id=tech.id,
                        technician_name=tech.name,
                    )
                    self._slots[slot.id] = slot

    async def get_available_slots(
        self,
        start_date: date,
        end_date: date,
        window: TimeWindow | None = None,
        technician_id: UUID | None = None,
    ) -> list[TimeSlot]:
        """Get available slots."""
        slots = []

        for slot in self._slots.values():
            # Check date range
            if slot.date < start_date or slot.date > end_date:
                continue

            # Check availability
            if slot.status != SlotStatus.AVAILABLE:
                continue

            # Check window filter
            if window and slot.window != window:
                continue

            # Check technician filter
            if technician_id and slot.technician_id != technician_id:
                continue

            # Skip past slots
            if slot.date == date.today():
                now = datetime.now().time()
                if slot.start_time <= now:
                    continue

            slots.append(slot)

        # Sort by date and window
        slots.sort(key=lambda s: (s.date, s.start_time))

        return slots

    async def book_slot(
        self,
        slot_id: UUID,
        customer: Customer,
        job_description: str,
        job_type: JobType = JobType.REPARATUR,
        estimated_duration: int = 60,
    ) -> ServiceCall:
        """Book a slot."""
        if slot_id not in self._slots:
            raise ValueError(f"Slot {slot_id} not found")

        slot = self._slots[slot_id]

        if slot.status != SlotStatus.AVAILABLE:
            raise ValueError(f"Slot {slot_id} is not available")

        # Mark slot as booked
        slot.status = SlotStatus.BOOKED
        slot.job_type = job_type

        # Create service call
        service_call = ServiceCall(
            id=uuid4(),
            customer_id=customer.id,
            customer_name=customer.full_name,
            customer_phone=customer.phone,
            slot=slot,
            job_description=job_description,
            job_type=job_type,
            address=customer.full_address,
            estimated_duration_minutes=estimated_duration,
            technician_id=slot.technician_id,
            technician_name=slot.technician_name,
        )

        self._service_calls[service_call.id] = service_call

        return service_call

    async def cancel_service_call(
        self,
        service_call_id: UUID,
        reason: str,
    ) -> bool:
        """Cancel a service call."""
        if service_call_id not in self._service_calls:
            return False

        service_call = self._service_calls[service_call_id]

        # Release the slot
        service_call.slot.status = SlotStatus.AVAILABLE

        # Update service call
        service_call.status = "cancelled"
        service_call.cancellation_reason = reason

        return True


class SchedulingService:
    """Service call scheduling service."""

    def __init__(self, calendar: MockCalendar | None = None):
        """Initialize scheduling service."""
        self._calendar = calendar or MockCalendar()

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
            window=preferences.preferred_window if not preferences.flexible_window else None,
            technician_id=preferences.preferred_technician_id,
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

        # Date preference
        if preferences.preferred_date:
            days_diff = abs((slot.date - preferences.preferred_date).days)
            score -= days_diff * 10

        # Window preference
        if preferences.preferred_window:
            if slot.window != preferences.preferred_window:
                score -= 15

        # Technician preference
        if preferences.preferred_technician_id:
            if slot.technician_id != preferences.preferred_technician_id:
                score -= 10

        # Prefer earlier slots for urgent jobs
        if preferences.urgency_max_wait_hours:
            hours_until = (
                datetime.combine(slot.date, slot.start_time) - datetime.now()
            ).total_seconds() / 3600
            if hours_until < preferences.urgency_max_wait_hours:
                score += 20

        return max(score, 0)

    async def book_service_call(
        self,
        slot_id: UUID,
        customer: Customer,
        job_description: str,
        job_type: JobType = JobType.REPARATUR,
        estimated_duration: int = 60,
    ) -> ServiceCall:
        """
        Book a service call.

        Args:
            slot_id: ID of the slot to book
            customer: Customer information
            job_description: Description of the job
            job_type: Type of service call
            estimated_duration: Estimated duration in minutes

        Returns:
            Created service call
        """
        return await self._calendar.book_slot(
            slot_id=slot_id,
            customer=customer,
            job_description=job_description,
            job_type=job_type,
            estimated_duration=estimated_duration,
        )

    async def cancel_service_call(
        self,
        service_call_id: UUID,
        reason: str,
    ) -> bool:
        """
        Cancel a service call.

        Args:
            service_call_id: ID of the service call to cancel
            reason: Reason for cancellation

        Returns:
            True if cancelled successfully
        """
        return await self._calendar.cancel_service_call(service_call_id, reason)

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
            weekdays = [
                "Montag", "Dienstag", "Mittwoch", "Donnerstag",
                "Freitag", "Samstag", "Sonntag"
            ]
            day_name = weekdays[slot.date.weekday()]
            date_str = slot.date.strftime("%d.%m.")

            # Format time window
            window_str = TIME_WINDOW_NAMES[slot.window]

            tech_str = ""
            if slot.technician_name:
                tech_str = f" mit {slot.technician_name}"

            return f"{day_name}, den {date_str}, {window_str}{tech_str}"

        # English fallback
        return f"{slot.date.strftime('%A, %B %d')}, {slot.window_name}"

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

    def format_confirmation_for_speech(
        self,
        service_call: ServiceCall,
        language: str = "de",
    ) -> str:
        """Format service call confirmation for speech."""
        if language == "de":
            slot_str = self.format_slot_for_speech(service_call.slot, language)
            return (
                f"Ihr Termin ist bestätigt für {slot_str}.\n"
                f"Unser Monteur ruft Sie etwa 30 Minuten vor Ankunft an.\n"
                f"Sie erhalten eine SMS-Bestätigung."
            )

        return f"Your appointment is confirmed for {self.format_slot_for_speech(service_call.slot, language)}."


# Singleton instance
_scheduling_service: SchedulingService | None = None


def get_scheduling_service() -> SchedulingService:
    """Get or create scheduling service singleton."""
    global _scheduling_service
    if _scheduling_service is None:
        _scheduling_service = SchedulingService()
    return _scheduling_service
