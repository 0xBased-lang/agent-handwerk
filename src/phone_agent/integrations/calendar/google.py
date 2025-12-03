"""Google Calendar Integration.

Implements CalendarIntegration interface for Google Calendar API.
Provides appointment booking, cancellation, and rescheduling for
German healthcare practices.
"""

from __future__ import annotations

import asyncio
from datetime import date, datetime, time, timedelta, timezone
from typing import Any
from uuid import UUID, uuid4

from itf_shared import get_logger

from phone_agent.integrations.calendar.base import (
    AppointmentType,
    BookingRequest,
    BookingResult,
    CalendarIntegration,
    SlotStatus,
    TimeSlot,
)
from phone_agent.integrations.calendar.google_auth import (
    GoogleCalendarAuth,
    GoogleCalendarAuthError,
)
from phone_agent.integrations.calendar.google_models import (
    BusinessHours,
    GoogleEventMapping,
    build_google_event,
    format_event_description,
    format_event_summary,
    get_german_error_message,
)

log = get_logger(__name__)


class GoogleCalendarError(Exception):
    """Google Calendar operation error."""

    def __init__(self, message: str, german_message: str | None = None):
        super().__init__(message)
        self.german_message = german_message or get_german_error_message("calendar_error")


class GoogleCalendarIntegration(CalendarIntegration):
    """Google Calendar implementation of CalendarIntegration.

    Provides:
    - FreeBusy queries for availability checking
    - Event creation for booking appointments
    - Event deletion for cancellations
    - Event updates for rescheduling
    - German locale support for all event text
    - Retry logic with exponential backoff
    - Simple in-memory caching for freeBusy results

    Usage:
        auth = GoogleCalendarAuth(credentials_file="/path/to/creds.json")
        calendar = GoogleCalendarIntegration(
            auth=auth,
            calendar_id="practice@domain.com",
        )

        # Get available slots
        slots = await calendar.get_available_slots(
            start_date=date.today(),
            end_date=date.today() + timedelta(days=7),
        )

        # Book a slot
        result = await calendar.book_slot(booking_request)
    """

    def __init__(
        self,
        auth: GoogleCalendarAuth,
        calendar_id: str = "primary",
        timezone: str = "Europe/Berlin",
        business_hours: BusinessHours | None = None,
        slot_duration_minutes: int = 15,
        max_retries: int = 3,
        retry_base_delay: float = 1.0,
        cache_ttl_seconds: int = 30,
    ):
        """Initialize Google Calendar integration.

        Args:
            auth: Google Calendar authentication handler
            calendar_id: Calendar ID or email address
            timezone: Timezone for appointments
            business_hours: Business hours configuration
            slot_duration_minutes: Default appointment duration
            max_retries: Max retry attempts for API calls
            retry_base_delay: Base delay for exponential backoff
            cache_ttl_seconds: Cache TTL for freeBusy results
        """
        self._auth = auth
        self._calendar_id = calendar_id
        self._timezone = timezone
        self._business_hours = business_hours or BusinessHours()
        self._slot_duration_minutes = slot_duration_minutes
        self._max_retries = max_retries
        self._retry_base_delay = retry_base_delay
        self._cache_ttl_seconds = cache_ttl_seconds

        # Cache for slot lookups and freeBusy results
        self._slot_cache: dict[UUID, TimeSlot] = {}
        self._event_mappings: dict[UUID, GoogleEventMapping] = {}
        self._freebusy_cache: dict[str, tuple[datetime, list[dict[str, str]]]] = {}

    async def _execute_with_retry(
        self, operation: str, func: Any, *args: Any, **kwargs: Any
    ) -> Any:
        """Execute a function with exponential backoff retry.

        Args:
            operation: Operation name for logging
            func: Function to execute
            *args: Positional arguments for func
            **kwargs: Keyword arguments for func

        Returns:
            Function result

        Raises:
            GoogleCalendarError: If all retries fail
        """
        last_error = None

        for attempt in range(self._max_retries):
            try:
                # Execute the function
                result = func(*args, **kwargs)

                # Handle Google API request objects
                if hasattr(result, "execute"):
                    result = result.execute()

                return result

            except Exception as e:
                last_error = e
                error_str = str(e)

                # Check for rate limit errors (429)
                if "429" in error_str or "Rate Limit" in error_str:
                    delay = self._retry_base_delay * (2**attempt)
                    log.warning(
                        "Rate limited, retrying",
                        operation=operation,
                        attempt=attempt + 1,
                        delay=delay,
                    )
                    await asyncio.sleep(delay)
                    continue

                # Check for transient errors
                if any(code in error_str for code in ["500", "502", "503", "504"]):
                    delay = self._retry_base_delay * (2**attempt)
                    log.warning(
                        "Transient error, retrying",
                        operation=operation,
                        attempt=attempt + 1,
                        error=error_str,
                    )
                    await asyncio.sleep(delay)
                    continue

                # Non-retryable error
                raise GoogleCalendarError(
                    f"{operation} failed: {e}",
                    german_message=get_german_error_message("calendar_error"),
                ) from e

        raise GoogleCalendarError(
            f"{operation} failed after {self._max_retries} retries: {last_error}",
            german_message=get_german_error_message("calendar_error"),
        )

    async def _get_freebusy(
        self, start: datetime, end: datetime
    ) -> list[dict[str, str]]:
        """Get busy periods from Google Calendar.

        Uses caching to reduce API calls.

        Args:
            start: Start of query range
            end: End of query range

        Returns:
            List of busy periods with 'start' and 'end' keys
        """
        cache_key = f"{start.isoformat()}_{end.isoformat()}"

        # Check cache (use UTC for consistent timezone comparison)
        if cache_key in self._freebusy_cache:
            cached_time, cached_data = self._freebusy_cache[cache_key]
            if (datetime.now(timezone.utc) - cached_time).total_seconds() < self._cache_ttl_seconds:
                return cached_data

        try:
            service = self._auth.get_calendar_service()

            body = {
                "timeMin": start.isoformat() + "Z" if start.tzinfo is None else start.isoformat(),
                "timeMax": end.isoformat() + "Z" if end.tzinfo is None else end.isoformat(),
                "timeZone": self._timezone,
                "items": [{"id": self._calendar_id}],
            }

            result = await self._execute_with_retry(
                "freebusy.query",
                service.freebusy().query,
                body=body,
            )

            busy_periods = result.get("calendars", {}).get(
                self._calendar_id, {}
            ).get("busy", [])

            # Cache the result (store UTC timestamp for consistent comparison)
            self._freebusy_cache[cache_key] = (datetime.now(timezone.utc), busy_periods)

            return busy_periods

        except GoogleCalendarAuthError as e:
            raise GoogleCalendarError(
                f"Authentication failed: {e}",
                german_message=e.german_message,
            ) from e

    def _is_slot_busy(
        self, slot_start: datetime, slot_end: datetime, busy_periods: list[dict[str, str]]
    ) -> bool:
        """Check if a slot overlaps with any busy period.

        Args:
            slot_start: Slot start time
            slot_end: Slot end time
            busy_periods: List of busy periods

        Returns:
            True if slot overlaps with any busy period
        """
        for period in busy_periods:
            busy_start = datetime.fromisoformat(period["start"].replace("Z", "+00:00"))
            busy_end = datetime.fromisoformat(period["end"].replace("Z", "+00:00"))

            # Remove timezone for comparison if needed
            if busy_start.tzinfo and slot_start.tzinfo is None:
                busy_start = busy_start.replace(tzinfo=None)
                busy_end = busy_end.replace(tzinfo=None)

            # Check for overlap
            if slot_start < busy_end and slot_end > busy_start:
                return True

        return False

    def _generate_slots_for_day(
        self, day: date, duration_minutes: int, busy_periods: list[dict[str, str]]
    ) -> list[TimeSlot]:
        """Generate available slots for a single day.

        Args:
            day: Date to generate slots for
            duration_minutes: Slot duration
            busy_periods: Busy periods to exclude

        Returns:
            List of available time slots
        """
        slots = []

        # Skip non-working days
        if not self._business_hours.is_working_day(day.weekday()):
            return slots

        # Skip past dates
        if day < date.today():
            return slots

        current_time = datetime.combine(day, self._business_hours.start)
        end_time = datetime.combine(day, self._business_hours.end)

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
            if self._business_hours.is_lunch_time(slot_time):
                if self._business_hours.lunch_end:
                    current_time = datetime.combine(day, self._business_hours.lunch_end)
                else:
                    current_time = current_time + timedelta(minutes=duration_minutes)
                continue

            slot_end = current_time + timedelta(minutes=duration_minutes)

            # Check if slot is busy
            if not self._is_slot_busy(current_time, slot_end, busy_periods):
                slot = TimeSlot(
                    id=uuid4(),
                    start=current_time,
                    end=slot_end,
                    provider_id="default",
                    provider_name="Praxis",
                    status=SlotStatus.AVAILABLE,
                )
                slots.append(slot)
                self._slot_cache[slot.id] = slot

            current_time = current_time + timedelta(minutes=duration_minutes)

        return slots

    async def get_available_slots(
        self,
        start_date: date,
        end_date: date,
        provider_id: str | None = None,
        appointment_type: AppointmentType | None = None,
        duration_minutes: int = 15,
    ) -> list[TimeSlot]:
        """Get available slots from Google Calendar.

        Queries Google Calendar freeBusy API and generates available
        slots based on business hours minus busy periods.

        Args:
            start_date: Start of date range
            end_date: End of date range
            provider_id: Not used (single calendar)
            appointment_type: Not used (all slots same type)
            duration_minutes: Required slot duration

        Returns:
            List of available time slots
        """
        duration = duration_minutes or self._slot_duration_minutes

        # Get busy periods from Google Calendar
        start_dt = datetime.combine(start_date, time.min)
        end_dt = datetime.combine(end_date, time.max)

        try:
            busy_periods = await self._get_freebusy(start_dt, end_dt)
        except GoogleCalendarError:
            log.warning("Failed to get freeBusy, generating slots without busy check")
            busy_periods = []

        # Generate slots for each day
        all_slots = []
        current_date = start_date
        while current_date <= end_date:
            day_slots = self._generate_slots_for_day(
                day=current_date,
                duration_minutes=duration,
                busy_periods=busy_periods,
            )
            all_slots.extend(day_slots)
            current_date = current_date + timedelta(days=1)

        log.info(
            "Generated available slots",
            start=start_date.isoformat(),
            end=end_date.isoformat(),
            count=len(all_slots),
        )

        return all_slots

    async def book_slot(self, request: BookingRequest) -> BookingResult:
        """Book a slot by creating a Google Calendar event.

        Args:
            request: Booking request with patient and slot details

        Returns:
            Booking result with success status
        """
        # Get slot from cache
        slot = self._slot_cache.get(request.slot_id)
        if not slot:
            return BookingResult(
                success=False,
                message=get_german_error_message("slot_unavailable"),
            )

        if slot.status != SlotStatus.AVAILABLE:
            return BookingResult(
                success=False,
                message=get_german_error_message("slot_unavailable"),
            )

        try:
            service = self._auth.get_calendar_service()

            # Generate appointment ID
            appointment_id = uuid4()

            # Build event
            event = build_google_event(
                summary=format_event_summary(request.patient_name),
                description=format_event_description(
                    reason=request.reason,
                    patient_name=request.patient_name,
                    phone=request.patient_phone,
                    appointment_type=request.appointment_type.value,
                    appointment_id=appointment_id,
                ),
                start_time=slot.start,
                end_time=slot.end,
                timezone=self._timezone,
                location=slot.room,
                appointment_id=appointment_id,
                patient_id=request.patient_id,
                appointment_type=request.appointment_type.value,
            )

            # Create event in Google Calendar
            result = await self._execute_with_retry(
                "events.insert",
                service.events().insert,
                calendarId=self._calendar_id,
                body=event,
            )

            google_event_id = result.get("id")

            # Store mapping
            self._event_mappings[appointment_id] = GoogleEventMapping(
                appointment_id=appointment_id,
                google_event_id=google_event_id,
                calendar_id=self._calendar_id,
                patient_id=request.patient_id,
                appointment_type=request.appointment_type.value,
            )

            # Update slot status
            slot.status = SlotStatus.BOOKED

            # Clear freeBusy cache
            self._freebusy_cache.clear()

            log.info(
                "Appointment booked in Google Calendar",
                appointment_id=str(appointment_id),
                google_event_id=google_event_id,
                start=slot.start.isoformat(),
            )

            return BookingResult(
                success=True,
                appointment_id=appointment_id,
                slot=slot,
                message=get_german_error_message("booking_success"),
                confirmation_sent=False,
            )

        except GoogleCalendarAuthError as e:
            log.error("Authentication failed during booking", error=str(e))
            return BookingResult(
                success=False,
                message=e.german_message,
            )
        except GoogleCalendarError as e:
            log.error("Google Calendar error during booking", error=str(e))
            return BookingResult(
                success=False,
                message=e.german_message,
            )
        except Exception as e:
            log.error("Unexpected error during booking", error=str(e))
            return BookingResult(
                success=False,
                message=get_german_error_message("calendar_error"),
            )

    async def cancel_booking(
        self,
        appointment_id: UUID,
        reason: str,
    ) -> bool:
        """Cancel an appointment by deleting the Google Calendar event.

        Args:
            appointment_id: ID of the appointment to cancel
            reason: Cancellation reason

        Returns:
            True if cancelled successfully
        """
        mapping = self._event_mappings.get(appointment_id)
        if not mapping:
            log.warning(
                "No Google event mapping found for appointment",
                appointment_id=str(appointment_id),
            )
            return False

        try:
            service = self._auth.get_calendar_service()

            await self._execute_with_retry(
                "events.delete",
                service.events().delete,
                calendarId=mapping.calendar_id,
                eventId=mapping.google_event_id,
            )

            # Remove mapping
            del self._event_mappings[appointment_id]

            # Clear freeBusy cache
            self._freebusy_cache.clear()

            log.info(
                "Appointment cancelled in Google Calendar",
                appointment_id=str(appointment_id),
                google_event_id=mapping.google_event_id,
                reason=reason,
            )

            return True

        except Exception as e:
            log.error(
                "Failed to cancel appointment",
                appointment_id=str(appointment_id),
                error=str(e),
            )
            return False

    async def reschedule_booking(
        self,
        appointment_id: UUID,
        new_slot_id: UUID,
    ) -> BookingResult:
        """Reschedule an appointment by updating the Google Calendar event.

        Args:
            appointment_id: ID of the appointment to reschedule
            new_slot_id: ID of the new slot

        Returns:
            Booking result with new appointment details
        """
        # Get event mapping
        mapping = self._event_mappings.get(appointment_id)
        if not mapping:
            return BookingResult(
                success=False,
                message=get_german_error_message("event_not_found"),
            )

        # Get new slot
        new_slot = self._slot_cache.get(new_slot_id)
        if not new_slot:
            return BookingResult(
                success=False,
                message=get_german_error_message("slot_unavailable"),
            )

        if new_slot.status != SlotStatus.AVAILABLE:
            return BookingResult(
                success=False,
                message=get_german_error_message("slot_unavailable"),
            )

        try:
            service = self._auth.get_calendar_service()

            # Get existing event
            existing_event = await self._execute_with_retry(
                "events.get",
                service.events().get,
                calendarId=mapping.calendar_id,
                eventId=mapping.google_event_id,
            )

            # Update event times
            existing_event["start"] = {
                "dateTime": new_slot.start.isoformat(),
                "timeZone": self._timezone,
            }
            existing_event["end"] = {
                "dateTime": new_slot.end.isoformat(),
                "timeZone": self._timezone,
            }

            # Add reschedule note to description
            old_description = existing_event.get("description", "")
            reschedule_note = f"\n\nUmgebucht am {datetime.now().strftime('%d.%m.%Y %H:%M')}"
            existing_event["description"] = old_description + reschedule_note

            # Update event
            await self._execute_with_retry(
                "events.update",
                service.events().update,
                calendarId=mapping.calendar_id,
                eventId=mapping.google_event_id,
                body=existing_event,
            )

            # Update slot status
            new_slot.status = SlotStatus.BOOKED

            # Clear freeBusy cache
            self._freebusy_cache.clear()

            log.info(
                "Appointment rescheduled in Google Calendar",
                appointment_id=str(appointment_id),
                new_start=new_slot.start.isoformat(),
            )

            return BookingResult(
                success=True,
                appointment_id=appointment_id,
                slot=new_slot,
                message=get_german_error_message("reschedule_success"),
            )

        except Exception as e:
            log.error(
                "Failed to reschedule appointment",
                appointment_id=str(appointment_id),
                error=str(e),
            )
            return BookingResult(
                success=False,
                message=get_german_error_message("calendar_error"),
            )

    async def check_availability(self, slot_id: UUID) -> bool:
        """Check if a specific slot is still available.

        Args:
            slot_id: Slot ID to check

        Returns:
            True if slot is available
        """
        slot = self._slot_cache.get(slot_id)
        if not slot:
            return False

        if slot.status != SlotStatus.AVAILABLE:
            return False

        # Double-check with Google Calendar
        try:
            busy_periods = await self._get_freebusy(slot.start, slot.end)
            return not self._is_slot_busy(slot.start, slot.end, busy_periods)
        except GoogleCalendarError:
            # If we can't check, assume it's still available
            return True
