"""Local database-backed calendar integration.

Uses the AppointmentRepository to manage appointments in the local database.
This is the default implementation for standalone deployments.
"""

from __future__ import annotations

from datetime import datetime, date, time, timedelta
from typing import Any
from uuid import UUID, uuid4

from itf_shared import get_logger

from phone_agent.db.session import get_db_context
from phone_agent.db.repositories.appointments import AppointmentRepository
from phone_agent.db.models import AppointmentModel
from phone_agent.api.appointments import AppointmentStatus
from phone_agent.integrations.calendar.base import (
    CalendarIntegration,
    TimeSlot,
    SlotStatus,
    AppointmentType,
    BookingRequest,
    BookingResult,
)

log = get_logger(__name__)


class LocalCalendarIntegration(CalendarIntegration):
    """Local database-backed calendar integration.

    Uses the Phone Agent database to store and retrieve appointments.
    Generates available slots based on business hours configuration.
    """

    def __init__(
        self,
        business_hours_start: time = time(8, 0),
        business_hours_end: time = time(18, 0),
        lunch_start: time = time(12, 0),
        lunch_end: time = time(13, 0),
        slot_duration_minutes: int = 15,
        providers: list[dict[str, str]] | None = None,
    ):
        """Initialize local calendar integration.

        Args:
            business_hours_start: Start of business hours
            business_hours_end: End of business hours
            lunch_start: Start of lunch break
            lunch_end: End of lunch break
            slot_duration_minutes: Default slot duration
            providers: List of provider dicts with 'id' and 'name' keys
        """
        self.business_hours_start = business_hours_start
        self.business_hours_end = business_hours_end
        self.lunch_start = lunch_start
        self.lunch_end = lunch_end
        self.slot_duration_minutes = slot_duration_minutes

        # Default providers if not specified
        self.providers = providers or [
            {"id": "default", "name": "Praxis"},
        ]

        # Cache for generated slots (slot_id -> TimeSlot)
        self._slot_cache: dict[UUID, TimeSlot] = {}

    def _generate_slots_for_day(
        self,
        day: date,
        provider_id: str,
        provider_name: str,
        duration_minutes: int,
    ) -> list[TimeSlot]:
        """Generate available slots for a single day.

        Args:
            day: Date to generate slots for
            provider_id: Provider ID
            provider_name: Provider display name
            duration_minutes: Slot duration

        Returns:
            List of time slots for the day
        """
        slots = []

        # Skip weekends
        if day.weekday() >= 5:
            return slots

        # Skip past dates
        if day < date.today():
            return slots

        current_time = datetime.combine(day, self.business_hours_start)
        end_time = datetime.combine(day, self.business_hours_end)

        # If today, skip past times
        now = datetime.now()
        if day == date.today() and current_time < now:
            # Round up to next slot boundary
            minutes_since_start = (now - current_time).total_seconds() / 60
            slots_passed = int(minutes_since_start / duration_minutes) + 1
            current_time = current_time + timedelta(minutes=slots_passed * duration_minutes)

        while current_time + timedelta(minutes=duration_minutes) <= end_time:
            slot_time = current_time.time()

            # Skip lunch break
            if self.lunch_start <= slot_time < self.lunch_end:
                current_time = datetime.combine(day, self.lunch_end)
                continue

            slot = TimeSlot(
                id=uuid4(),
                start=current_time,
                end=current_time + timedelta(minutes=duration_minutes),
                provider_id=provider_id,
                provider_name=provider_name,
                status=SlotStatus.AVAILABLE,
            )

            slots.append(slot)
            self._slot_cache[slot.id] = slot

            current_time = current_time + timedelta(minutes=duration_minutes)

        return slots

    async def _get_booked_slots(
        self,
        start_date: date,
        end_date: date,
        provider_id: str | None = None,
    ) -> set[tuple[date, time, str]]:
        """Get set of already-booked time slots.

        Returns set of (date, time, provider_id) tuples that are booked.
        """
        booked = set()

        try:
            async with get_db_context() as db:
                repo = AppointmentRepository(db)

                # Get all appointments in range
                appointments = await repo.find_many(
                    start_date__gte=datetime.combine(start_date, time.min),
                    start_date__lte=datetime.combine(end_date, time.max),
                )

                for appt in appointments:
                    # Skip cancelled appointments
                    if appt.status == AppointmentStatus.CANCELLED.value:
                        continue

                    if provider_id and appt.provider_id != provider_id:
                        continue

                    booked.add((
                        appt.start_date.date(),
                        appt.start_date.time(),
                        appt.provider_id or "default",
                    ))

        except Exception as e:
            log.error("Failed to get booked slots", error=str(e))

        return booked

    async def get_available_slots(
        self,
        start_date: date,
        end_date: date,
        provider_id: str | None = None,
        appointment_type: AppointmentType | None = None,
        duration_minutes: int = 15,
    ) -> list[TimeSlot]:
        """Get available slots from local calendar.

        Generates slots based on business hours and filters out booked ones.
        """
        duration = duration_minutes or self.slot_duration_minutes
        all_slots = []

        # Get booked slots to filter
        booked = await self._get_booked_slots(start_date, end_date, provider_id)

        # Generate slots for each day and provider
        current_date = start_date
        while current_date <= end_date:
            for provider in self.providers:
                if provider_id and provider["id"] != provider_id:
                    continue

                day_slots = self._generate_slots_for_day(
                    day=current_date,
                    provider_id=provider["id"],
                    provider_name=provider["name"],
                    duration_minutes=duration,
                )

                # Filter out booked slots
                for slot in day_slots:
                    key = (slot.start.date(), slot.start.time(), slot.provider_id)
                    if key not in booked:
                        all_slots.append(slot)

            current_date = current_date + timedelta(days=1)

        return all_slots

    async def book_slot(self, request: BookingRequest) -> BookingResult:
        """Book a slot in the local calendar.

        Creates an appointment in the database.
        """
        # Check if slot exists and is available
        slot = self._slot_cache.get(request.slot_id)
        if not slot:
            return BookingResult(
                success=False,
                message="Slot not found. It may have expired.",
            )

        if slot.status != SlotStatus.AVAILABLE:
            return BookingResult(
                success=False,
                message="Slot is no longer available.",
            )

        try:
            async with get_db_context() as db:
                repo = AppointmentRepository(db)

                # Check for conflicts
                existing = await repo.find_one(
                    start_date=slot.start,
                    provider_id=slot.provider_id,
                    status__ne=AppointmentStatus.CANCELLED.value,
                )

                if existing:
                    return BookingResult(
                        success=False,
                        message="This time slot has already been booked.",
                    )

                # Create appointment
                appointment = AppointmentModel(
                    id=uuid4(),
                    contact_id=request.patient_id,
                    start_date=slot.start,
                    end_date=slot.end,
                    provider_id=slot.provider_id,
                    provider_name=slot.provider_name,
                    appointment_type=request.appointment_type.value,
                    status=AppointmentStatus.SCHEDULED.value,
                    reason=request.reason,
                    notes=request.notes,
                )

                await repo.create(appointment)

                # Mark slot as booked
                slot.status = SlotStatus.BOOKED

                log.info(
                    "Appointment booked",
                    appointment_id=str(appointment.id),
                    slot_start=slot.start.isoformat(),
                    patient_id=str(request.patient_id),
                )

                return BookingResult(
                    success=True,
                    appointment_id=appointment.id,
                    slot=slot,
                    message="Termin erfolgreich gebucht.",
                    confirmation_sent=False,  # SMS will be handled separately
                )

        except Exception as e:
            log.error("Failed to book slot", error=str(e))
            return BookingResult(
                success=False,
                message=f"Booking failed: {str(e)}",
            )

    async def cancel_booking(
        self,
        appointment_id: UUID,
        reason: str,
    ) -> bool:
        """Cancel an appointment in the local calendar."""
        try:
            async with get_db_context() as db:
                repo = AppointmentRepository(db)

                appointment = await repo.find_by_id(appointment_id)
                if not appointment:
                    log.warning("Appointment not found for cancellation", id=str(appointment_id))
                    return False

                await repo.update(appointment_id, {
                    "status": AppointmentStatus.CANCELLED.value,
                    "cancellation_reason": reason,
                })

                log.info(
                    "Appointment cancelled",
                    appointment_id=str(appointment_id),
                    reason=reason,
                )

                return True

        except Exception as e:
            log.error("Failed to cancel appointment", error=str(e))
            return False

    async def reschedule_booking(
        self,
        appointment_id: UUID,
        new_slot_id: UUID,
    ) -> BookingResult:
        """Reschedule an appointment to a new slot."""
        # Get new slot
        new_slot = self._slot_cache.get(new_slot_id)
        if not new_slot:
            return BookingResult(
                success=False,
                message="New slot not found.",
            )

        if new_slot.status != SlotStatus.AVAILABLE:
            return BookingResult(
                success=False,
                message="New slot is not available.",
            )

        try:
            async with get_db_context() as db:
                repo = AppointmentRepository(db)

                # Get existing appointment
                old_appointment = await repo.find_by_id(appointment_id)
                if not old_appointment:
                    return BookingResult(
                        success=False,
                        message="Original appointment not found.",
                    )

                # Cancel old appointment
                await repo.update(appointment_id, {
                    "status": AppointmentStatus.RESCHEDULED.value,
                    "notes": f"{old_appointment.notes or ''}\nRescheduled from {old_appointment.start_date.isoformat()}",
                })

                # Create new appointment
                new_appointment = AppointmentModel(
                    id=uuid4(),
                    contact_id=old_appointment.contact_id,
                    start_date=new_slot.start,
                    end_date=new_slot.end,
                    provider_id=new_slot.provider_id,
                    provider_name=new_slot.provider_name,
                    appointment_type=old_appointment.appointment_type,
                    status=AppointmentStatus.SCHEDULED.value,
                    reason=old_appointment.reason,
                    notes=f"Umgebucht von {old_appointment.start_date.strftime('%d.%m.%Y %H:%M')}",
                )

                await repo.create(new_appointment)

                # Mark new slot as booked
                new_slot.status = SlotStatus.BOOKED

                log.info(
                    "Appointment rescheduled",
                    old_id=str(appointment_id),
                    new_id=str(new_appointment.id),
                    new_time=new_slot.start.isoformat(),
                )

                return BookingResult(
                    success=True,
                    appointment_id=new_appointment.id,
                    slot=new_slot,
                    message="Termin erfolgreich umgebucht.",
                )

        except Exception as e:
            log.error("Failed to reschedule appointment", error=str(e))
            return BookingResult(
                success=False,
                message=f"Rescheduling failed: {str(e)}",
            )

    async def check_availability(self, slot_id: UUID) -> bool:
        """Check if a specific slot is still available."""
        slot = self._slot_cache.get(slot_id)
        if not slot:
            return False

        if slot.status != SlotStatus.AVAILABLE:
            return False

        # Double-check against database
        try:
            async with get_db_context() as db:
                repo = AppointmentRepository(db)
                existing = await repo.find_one(
                    start_date=slot.start,
                    provider_id=slot.provider_id,
                    status__ne=AppointmentStatus.CANCELLED.value,
                )
                return existing is None

        except Exception:
            return False
