"""Calendar Integration Factory.

Creates the appropriate calendar integration based on configuration.
Supports:
- local: Database-backed calendar (default)
- mock: Mock calendar for testing
- google: Google Calendar (future)
- outlook: Microsoft Outlook (future)
"""

from __future__ import annotations

from functools import lru_cache
from typing import TYPE_CHECKING

from itf_shared import get_logger

from phone_agent.config import get_settings
from phone_agent.integrations.calendar.base import CalendarIntegration
from phone_agent.integrations.calendar.local import LocalCalendarIntegration

if TYPE_CHECKING:
    from phone_agent.industry.gesundheit.scheduling import MockCalendarIntegration

log = get_logger(__name__)


# Singleton instance
_calendar_integration: CalendarIntegration | None = None


def get_calendar_integration() -> CalendarIntegration:
    """Get the configured calendar integration.

    Returns:
        Calendar integration instance based on config.
    """
    global _calendar_integration

    if _calendar_integration is not None:
        return _calendar_integration

    settings = get_settings()
    calendar_type = settings.integrations.calendar.type

    log.info("Initializing calendar integration", type=calendar_type)

    if calendar_type == "local":
        _calendar_integration = LocalCalendarIntegration(
            providers=[
                {"id": "default", "name": "Praxis"},
            ]
        )

    elif calendar_type == "mock":
        # Import mock from gesundheit module
        from phone_agent.industry.gesundheit.scheduling import MockCalendarIntegration

        # Create adapter to match CalendarIntegration interface
        _calendar_integration = _create_mock_adapter()

    elif calendar_type == "google":
        # Import Google Calendar integration
        from phone_agent.integrations.calendar.google import GoogleCalendarIntegration
        from phone_agent.integrations.calendar.google_auth import (
            GoogleCalendarAuth,
            GoogleCalendarAuthError,
        )
        from phone_agent.integrations.calendar.google_models import BusinessHours

        google_settings = settings.integrations.calendar.google

        # Check for credentials
        if not google_settings.credentials_file and not google_settings.credentials_json:
            log.warning(
                "Google Calendar credentials not configured, using local calendar"
            )
            _calendar_integration = LocalCalendarIntegration()
        else:
            try:
                # Create authentication
                auth = GoogleCalendarAuth(
                    credentials_file=google_settings.credentials_file or None,
                    credentials_json=google_settings.credentials_json or None,
                )

                # Create business hours from settings
                business_hours = BusinessHours.from_strings(
                    start=google_settings.business_hours_start,
                    end=google_settings.business_hours_end,
                    lunch_start=google_settings.lunch_start,
                    lunch_end=google_settings.lunch_end,
                    working_days=google_settings.working_days,
                )

                # Create integration
                _calendar_integration = GoogleCalendarIntegration(
                    auth=auth,
                    calendar_id=google_settings.calendar_id,
                    timezone=settings.integrations.calendar.timezone,
                    business_hours=business_hours,
                    slot_duration_minutes=google_settings.default_slot_duration,
                    max_retries=google_settings.max_retries,
                    retry_base_delay=google_settings.retry_base_delay,
                    cache_ttl_seconds=google_settings.cache_ttl_seconds,
                )

                log.info(
                    "Google Calendar integration initialized",
                    calendar_id=google_settings.calendar_id,
                )

            except GoogleCalendarAuthError as e:
                log.error(
                    "Failed to initialize Google Calendar",
                    error=str(e),
                )
                log.warning("Falling back to local calendar")
                _calendar_integration = LocalCalendarIntegration()

    elif calendar_type == "outlook":
        log.warning("Outlook Calendar integration not yet implemented, using local")
        _calendar_integration = LocalCalendarIntegration()

    else:
        log.warning(f"Unknown calendar type '{calendar_type}', using local")
        _calendar_integration = LocalCalendarIntegration()

    return _calendar_integration


def reset_calendar_integration() -> None:
    """Reset the calendar integration (for testing)."""
    global _calendar_integration
    _calendar_integration = None


def _create_mock_adapter() -> CalendarIntegration:
    """Create adapter for MockCalendarIntegration.

    The MockCalendarIntegration from gesundheit/scheduling.py uses a slightly
    different interface. This creates an adapter to match the new interface.
    """
    from phone_agent.industry.gesundheit.scheduling import (
        MockCalendarIntegration as GesundheitMockCalendar,
        TimeSlot as GesundheitTimeSlot,
        SlotStatus as GesundheitSlotStatus,
        AppointmentType as GesundheitAppointmentType,
        Patient,
    )
    from phone_agent.integrations.calendar.base import (
        CalendarIntegration,
        TimeSlot,
        SlotStatus,
        AppointmentType,
        BookingRequest,
        BookingResult,
    )
    from datetime import date
    from uuid import UUID, uuid4

    class MockCalendarAdapter(CalendarIntegration):
        """Adapter for the gesundheit MockCalendarIntegration."""

        def __init__(self):
            self._mock = GesundheitMockCalendar()

        async def get_available_slots(
            self,
            start_date: date,
            end_date: date,
            provider_id: str | None = None,
            appointment_type: AppointmentType | None = None,
            duration_minutes: int = 15,
        ) -> list[TimeSlot]:
            # Convert appointment type
            mock_type = None
            if appointment_type:
                try:
                    mock_type = GesundheitAppointmentType(appointment_type.value)
                except ValueError:
                    pass

            mock_slots = await self._mock.get_available_slots(
                start_date=start_date,
                end_date=end_date,
                provider_id=provider_id,
                appointment_type=mock_type,
            )

            # Convert to new TimeSlot format
            return [
                TimeSlot(
                    id=s.id,
                    start=s.start,
                    end=s.end,
                    provider_id=s.provider_id,
                    provider_name=s.provider_name,
                    status=SlotStatus(s.status.value),
                    room=s.room,
                    notes=s.notes,
                )
                for s in mock_slots
            ]

        async def book_slot(self, request: BookingRequest) -> BookingResult:
            # Create mock patient - safely parse name
            name_parts = (request.patient_name or "").split()
            first_name = name_parts[0] if name_parts else "Patient"
            last_name = name_parts[-1] if len(name_parts) > 1 else ""

            patient = Patient(
                id=request.patient_id,
                first_name=first_name,
                last_name=last_name,
                date_of_birth=date(1980, 1, 1),  # Placeholder
                phone=request.patient_phone,
            )

            try:
                mock_type = GesundheitAppointmentType(request.appointment_type.value)
            except ValueError:
                mock_type = GesundheitAppointmentType.REGULAR

            try:
                appointment = await self._mock.book_slot(
                    slot_id=request.slot_id,
                    patient=patient,
                    reason=request.reason,
                    appointment_type=mock_type,
                )

                return BookingResult(
                    success=True,
                    appointment_id=appointment.id,
                    slot=TimeSlot(
                        id=appointment.slot.id,
                        start=appointment.slot.start,
                        end=appointment.slot.end,
                        provider_id=appointment.slot.provider_id,
                        provider_name=appointment.slot.provider_name,
                        status=SlotStatus.BOOKED,
                    ),
                    message="Termin erfolgreich gebucht.",
                )

            except ValueError as e:
                return BookingResult(
                    success=False,
                    message=str(e),
                )

        async def cancel_booking(
            self,
            appointment_id: UUID,
            reason: str,
        ) -> bool:
            return await self._mock.cancel_appointment(appointment_id, reason)

        async def reschedule_booking(
            self,
            appointment_id: UUID,
            new_slot_id: UUID,
        ) -> BookingResult:
            try:
                appointment = await self._mock.reschedule_appointment(
                    appointment_id=appointment_id,
                    new_slot_id=new_slot_id,
                )

                return BookingResult(
                    success=True,
                    appointment_id=appointment.id,
                    slot=TimeSlot(
                        id=appointment.slot.id,
                        start=appointment.slot.start,
                        end=appointment.slot.end,
                        provider_id=appointment.slot.provider_id,
                        provider_name=appointment.slot.provider_name,
                        status=SlotStatus.BOOKED,
                    ),
                    message="Termin erfolgreich umgebucht.",
                )

            except ValueError as e:
                return BookingResult(
                    success=False,
                    message=str(e),
                )

    return MockCalendarAdapter()
