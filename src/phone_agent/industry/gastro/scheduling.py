"""Gastro scheduling service.

Manages restaurant reservations, table allocation, and availability.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, time as dt_time
from enum import Enum
from typing import Any
import uuid


class TableStatus(str, Enum):
    """Status of a restaurant table."""

    AVAILABLE = "available"
    RESERVED = "reserved"
    OCCUPIED = "occupied"
    BLOCKED = "blocked"  # Maintenance, reserved for VIP


class ReservationStatus(str, Enum):
    """Status of a reservation."""

    CONFIRMED = "confirmed"
    PENDING = "pending"  # Awaiting confirmation
    CANCELLED = "cancelled"
    NO_SHOW = "no_show"
    COMPLETED = "completed"
    SEATED = "seated"


@dataclass
class Table:
    """A restaurant table."""

    id: str
    name: str  # e.g., "Tisch 1", "Terrasse 3"
    capacity: int
    min_guests: int = 1
    location: str = "indoor"  # indoor, terrace, window, private
    is_combinable: bool = True  # Can be combined with adjacent tables
    notes: str | None = None


@dataclass
class TimeSlot:
    """A reservation time slot."""

    start_time: dt_time
    end_time: dt_time
    service_period: str  # lunch, dinner, sunday


@dataclass
class Reservation:
    """A restaurant reservation."""

    id: str
    guest_name: str
    phone: str
    email: str | None
    party_size: int
    date: str  # YYYY-MM-DD
    time: str  # HH:MM
    duration_minutes: int = 90
    table_ids: list[str] = field(default_factory=list)
    status: ReservationStatus = ReservationStatus.CONFIRMED
    special_requests: list[str] = field(default_factory=list)
    occasion: str | None = None
    notes: str | None = None
    deposit_paid: bool = False
    created_at: datetime = field(default_factory=datetime.now)
    confirmed_at: datetime | None = None
    reminder_sent: bool = False

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "guest_name": self.guest_name,
            "phone": self.phone,
            "email": self.email,
            "party_size": self.party_size,
            "date": self.date,
            "time": self.time,
            "duration_minutes": self.duration_minutes,
            "table_ids": self.table_ids,
            "status": self.status.value,
            "special_requests": self.special_requests,
            "occasion": self.occasion,
            "notes": self.notes,
            "deposit_paid": self.deposit_paid,
            "created_at": self.created_at.isoformat(),
            "confirmed_at": self.confirmed_at.isoformat() if self.confirmed_at else None,
            "reminder_sent": self.reminder_sent,
        }


@dataclass
class AvailabilitySlot:
    """An available slot for reservation."""

    date: str
    time: str
    capacity: int
    table_ids: list[str]
    is_peak: bool = False
    notes: str | None = None


class SchedulingService:
    """Service for managing restaurant reservations."""

    def __init__(self):
        """Initialize scheduling service."""
        self._tables: dict[str, Table] = {}
        self._reservations: dict[str, Reservation] = {}
        self._default_duration = 90  # minutes
        self._buffer_minutes = 15  # Between reservations

        # Service hours (weekday -> list of TimeSlot)
        self._service_hours = {
            0: [],  # Monday - closed
            1: [  # Tuesday
                TimeSlot(dt_time(11, 30), dt_time(14, 30), "lunch"),
                TimeSlot(dt_time(17, 30), dt_time(22, 0), "dinner"),
            ],
            2: [  # Wednesday
                TimeSlot(dt_time(11, 30), dt_time(14, 30), "lunch"),
                TimeSlot(dt_time(17, 30), dt_time(22, 0), "dinner"),
            ],
            3: [  # Thursday
                TimeSlot(dt_time(11, 30), dt_time(14, 30), "lunch"),
                TimeSlot(dt_time(17, 30), dt_time(22, 0), "dinner"),
            ],
            4: [  # Friday
                TimeSlot(dt_time(11, 30), dt_time(14, 30), "lunch"),
                TimeSlot(dt_time(17, 30), dt_time(22, 0), "dinner"),
            ],
            5: [  # Saturday
                TimeSlot(dt_time(11, 30), dt_time(14, 30), "lunch"),
                TimeSlot(dt_time(17, 30), dt_time(22, 0), "dinner"),
            ],
            6: [  # Sunday
                TimeSlot(dt_time(11, 30), dt_time(21, 0), "sunday"),
            ],
        }

        # Peak times (higher demand)
        self._peak_times = [
            (4, dt_time(19, 0), dt_time(21, 0)),  # Friday dinner
            (5, dt_time(18, 30), dt_time(21, 30)),  # Saturday dinner
            (6, dt_time(12, 0), dt_time(14, 0)),  # Sunday lunch
        ]

        self._init_default_tables()

    def _init_default_tables(self) -> None:
        """Initialize default table layout."""
        default_tables = [
            Table("t1", "Tisch 1", capacity=2, location="window"),
            Table("t2", "Tisch 2", capacity=2, location="window"),
            Table("t3", "Tisch 3", capacity=4, location="indoor"),
            Table("t4", "Tisch 4", capacity=4, location="indoor"),
            Table("t5", "Tisch 5", capacity=6, location="indoor"),
            Table("t6", "Tisch 6", capacity=6, location="indoor"),
            Table("t7", "Tisch 7", capacity=8, location="indoor", is_combinable=False),
            Table("t8", "Terrasse 1", capacity=4, location="terrace"),
            Table("t9", "Terrasse 2", capacity=4, location="terrace"),
            Table("t10", "Terrasse 3", capacity=6, location="terrace"),
            Table("p1", "Separee", capacity=12, location="private", is_combinable=False),
        ]

        for table in default_tables:
            self._tables[table.id] = table

    def find_available_slots(
        self,
        party_size: int,
        date: str,
        preferred_time: str | None = None,
        location_preference: str | None = None,
    ) -> list[AvailabilitySlot]:
        """
        Find available reservation slots.

        Args:
            party_size: Number of guests
            date: Date to check (YYYY-MM-DD)
            preferred_time: Preferred time (HH:MM), optional
            location_preference: Preferred location (indoor, terrace, etc.)

        Returns:
            List of available slots
        """
        try:
            check_date = datetime.strptime(date, "%Y-%m-%d")
        except ValueError:
            return []

        weekday = check_date.weekday()
        service_slots = self._service_hours.get(weekday, [])

        if not service_slots:
            return []  # Restaurant closed

        available: list[AvailabilitySlot] = []

        for service_slot in service_slots:
            # Generate time slots every 30 minutes during service
            current = datetime.combine(check_date.date(), service_slot.start_time)
            end = datetime.combine(check_date.date(), service_slot.end_time)

            # Reserve last 90 minutes for existing guests
            end = end - timedelta(minutes=90)

            while current < end:
                time_str = current.strftime("%H:%M")

                # Find available tables
                available_tables = self._find_tables_for_slot(
                    party_size=party_size,
                    date=date,
                    time=time_str,
                    location_preference=location_preference,
                )

                if available_tables:
                    is_peak = self._is_peak_time(weekday, current.time())
                    total_capacity = sum(self._tables[tid].capacity for tid in available_tables)

                    available.append(AvailabilitySlot(
                        date=date,
                        time=time_str,
                        capacity=total_capacity,
                        table_ids=available_tables,
                        is_peak=is_peak,
                    ))

                current += timedelta(minutes=30)

        # Sort by proximity to preferred time if specified
        if preferred_time and available:
            try:
                pref = datetime.strptime(preferred_time, "%H:%M").time()
                available.sort(key=lambda s: abs(
                    datetime.strptime(s.time, "%H:%M").time().hour * 60 +
                    datetime.strptime(s.time, "%H:%M").time().minute -
                    (pref.hour * 60 + pref.minute)
                ))
            except ValueError:
                pass

        return available

    def _find_tables_for_slot(
        self,
        party_size: int,
        date: str,
        time: str,
        location_preference: str | None = None,
    ) -> list[str]:
        """Find suitable tables for a slot."""
        # Get all reservations for this date/time
        reserved_table_ids = set()

        for res in self._reservations.values():
            if res.date != date or res.status in [
                ReservationStatus.CANCELLED,
                ReservationStatus.NO_SHOW,
            ]:
                continue

            # Check time overlap
            res_start = datetime.strptime(f"{res.date} {res.time}", "%Y-%m-%d %H:%M")
            res_end = res_start + timedelta(minutes=res.duration_minutes + self._buffer_minutes)

            check_time = datetime.strptime(f"{date} {time}", "%Y-%m-%d %H:%M")
            check_end = check_time + timedelta(minutes=self._default_duration)

            if res_start < check_end and check_time < res_end:
                reserved_table_ids.update(res.table_ids)

        # Find available tables
        available_tables: list[Table] = []
        for table in self._tables.values():
            if table.id in reserved_table_ids:
                continue

            if location_preference and table.location != location_preference:
                continue

            if table.capacity >= party_size and table.min_guests <= party_size:
                available_tables.append(table)

        # Sort by best fit (smallest capacity that fits)
        available_tables.sort(key=lambda t: t.capacity)

        # Return first suitable table(s)
        for table in available_tables:
            if table.capacity >= party_size:
                return [table.id]

        # Handle table combining for large parties
        combined_tables = self._find_combinable_tables(
            party_size=party_size,
            available_tables=available_tables,
            location_preference=location_preference,
        )
        if combined_tables:
            return combined_tables

        return []

    def _find_combinable_tables(
        self,
        party_size: int,
        available_tables: list[Table],
        location_preference: str | None = None,
    ) -> list[str]:
        """
        Find a combination of tables that can accommodate a large party.

        Uses a greedy algorithm to find the smallest set of combinable tables
        that together have enough capacity for the party.

        Args:
            party_size: Number of guests
            available_tables: List of available tables
            location_preference: Preferred location (prioritizes same location)

        Returns:
            List of table IDs if a valid combination found, empty list otherwise
        """
        # Filter to combinable tables only
        combinable = [t for t in available_tables if t.is_combinable]

        if not combinable:
            return []

        # Group tables by location for better combinations
        tables_by_location: dict[str, list[Table]] = {}
        for table in combinable:
            loc = table.location
            if loc not in tables_by_location:
                tables_by_location[loc] = []
            tables_by_location[loc].append(table)

        # Try to find combination in preferred location first
        if location_preference and location_preference in tables_by_location:
            result = self._find_table_combination(
                tables_by_location[location_preference], party_size
            )
            if result:
                return result

        # Try each location, preferring locations with more capacity
        locations = sorted(
            tables_by_location.keys(),
            key=lambda loc: sum(t.capacity for t in tables_by_location[loc]),
            reverse=True,
        )

        for location in locations:
            result = self._find_table_combination(
                tables_by_location[location], party_size
            )
            if result:
                return result

        # Last resort: combine tables across locations
        all_combinable = sorted(combinable, key=lambda t: t.capacity, reverse=True)
        return self._find_table_combination(all_combinable, party_size)

    def _find_table_combination(
        self,
        tables: list[Table],
        party_size: int,
    ) -> list[str]:
        """
        Find the smallest combination of tables that fits the party.

        Uses a greedy approach: start with largest tables and add
        smaller ones until capacity is met.

        Args:
            tables: List of tables to consider
            party_size: Number of guests

        Returns:
            List of table IDs if combination found, empty list otherwise
        """
        if not tables:
            return []

        # Sort by capacity descending for greedy selection
        sorted_tables = sorted(tables, key=lambda t: t.capacity, reverse=True)

        selected: list[str] = []
        total_capacity = 0

        for table in sorted_tables:
            selected.append(table.id)
            total_capacity += table.capacity

            if total_capacity >= party_size:
                return selected

        # Not enough capacity even with all tables
        return []

    def _is_peak_time(self, weekday: int, check_time: dt_time) -> bool:
        """Check if time is during peak hours."""
        for peak_weekday, start, end in self._peak_times:
            if weekday == peak_weekday and start <= check_time <= end:
                return True
        return False

    def create_reservation(
        self,
        guest_name: str,
        phone: str,
        party_size: int,
        date: str,
        time: str,
        email: str | None = None,
        special_requests: list[str] | None = None,
        occasion: str | None = None,
        notes: str | None = None,
    ) -> Reservation | None:
        """
        Create a new reservation.

        Args:
            guest_name: Name of the guest
            phone: Contact phone number
            party_size: Number of guests
            date: Reservation date
            time: Reservation time
            email: Optional email address
            special_requests: List of special requests
            occasion: Special occasion if any
            notes: Additional notes

        Returns:
            Created Reservation or None if no availability
        """
        # Find available tables
        slots = self.find_available_slots(party_size, date, time)

        # Find exact match or closest
        matching_slot = None
        for slot in slots:
            if slot.time == time:
                matching_slot = slot
                break

        if not matching_slot and slots:
            matching_slot = slots[0]  # Use closest available

        if not matching_slot:
            return None

        # Create reservation
        reservation = Reservation(
            id=str(uuid.uuid4())[:8],
            guest_name=guest_name,
            phone=phone,
            email=email,
            party_size=party_size,
            date=date,
            time=matching_slot.time,
            table_ids=matching_slot.table_ids,
            status=ReservationStatus.CONFIRMED,
            special_requests=special_requests or [],
            occasion=occasion,
            notes=notes,
            confirmed_at=datetime.now(),
        )

        self._reservations[reservation.id] = reservation
        return reservation

    def cancel_reservation(self, reservation_id: str) -> bool:
        """Cancel a reservation by ID."""
        if reservation_id not in self._reservations:
            return False

        self._reservations[reservation_id].status = ReservationStatus.CANCELLED
        return True

    def find_reservation(
        self,
        guest_name: str | None = None,
        phone: str | None = None,
        date: str | None = None,
    ) -> Reservation | None:
        """Find a reservation by guest details."""
        for res in self._reservations.values():
            if res.status == ReservationStatus.CANCELLED:
                continue

            name_match = not guest_name or guest_name.lower() in res.guest_name.lower()
            phone_match = not phone or phone in res.phone
            date_match = not date or res.date == date

            if name_match and phone_match and date_match:
                return res

        return None

    def get_reservations_for_date(self, date: str) -> list[Reservation]:
        """Get all reservations for a specific date."""
        return [
            res for res in self._reservations.values()
            if res.date == date and res.status not in [
                ReservationStatus.CANCELLED,
                ReservationStatus.NO_SHOW,
            ]
        ]

    def mark_no_show(self, reservation_id: str) -> bool:
        """Mark a reservation as no-show."""
        if reservation_id not in self._reservations:
            return False

        self._reservations[reservation_id].status = ReservationStatus.NO_SHOW
        return True

    def mark_seated(self, reservation_id: str) -> bool:
        """Mark a reservation as seated (guest arrived)."""
        if reservation_id not in self._reservations:
            return False

        self._reservations[reservation_id].status = ReservationStatus.SEATED
        return True

    def modify_reservation(
        self,
        reservation_id: str,
        new_date: str | None = None,
        new_time: str | None = None,
        new_party_size: int | None = None,
    ) -> Reservation | None:
        """Modify an existing reservation."""
        if reservation_id not in self._reservations:
            return None

        res = self._reservations[reservation_id]
        date = new_date or res.date
        time = new_time or res.time
        party_size = new_party_size or res.party_size

        # Check availability for new parameters
        slots = self.find_available_slots(party_size, date, time)

        if not slots:
            return None

        # Update reservation
        res.date = date
        res.time = slots[0].time
        res.party_size = party_size
        res.table_ids = slots[0].table_ids

        return res


# Singleton instance
_scheduling_service: SchedulingService | None = None


def get_scheduling_service() -> SchedulingService:
    """Get or create scheduling service singleton."""
    global _scheduling_service
    if _scheduling_service is None:
        _scheduling_service = SchedulingService()
    return _scheduling_service
