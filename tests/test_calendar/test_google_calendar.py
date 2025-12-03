"""Tests for Google Calendar integration."""

from __future__ import annotations

import json
from datetime import date, datetime, time, timedelta
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from phone_agent.integrations.calendar.base import (
    AppointmentType,
    BookingRequest,
    SlotStatus,
)
from phone_agent.integrations.calendar.google import (
    GoogleCalendarError,
    GoogleCalendarIntegration,
)
from phone_agent.integrations.calendar.google_auth import (
    GoogleCalendarAuth,
    GoogleCalendarAuthError,
)
from phone_agent.integrations.calendar.google_models import (
    BusinessHours,
    build_google_event,
    format_event_description,
    format_event_summary,
    get_german_error_message,
)


# ============================================================================
# GoogleCalendarAuth Tests
# ============================================================================


class TestGoogleCalendarAuth:
    """Tests for GoogleCalendarAuth class."""

    def test_init_requires_credentials(self):
        """Test that initialization fails without credentials."""
        with pytest.raises(GoogleCalendarAuthError) as exc_info:
            GoogleCalendarAuth()

        assert "No Google Calendar credentials provided" in str(exc_info.value)
        assert exc_info.value.german_message is not None

    def test_init_with_credentials_file(self, mock_google_credentials, tmp_path):
        """Test initialization with credentials file path."""
        creds_file = tmp_path / "creds.json"
        creds_file.write_text('{"type": "service_account"}')

        auth = GoogleCalendarAuth(credentials_file=str(creds_file))
        assert auth._credentials_file == str(creds_file)

    def test_init_with_credentials_json(
        self, mock_google_credentials, sample_credentials_json
    ):
        """Test initialization with credentials JSON string."""
        auth = GoogleCalendarAuth(credentials_json=json.dumps(sample_credentials_json))
        assert auth._credentials_json is not None

    def test_get_credentials_from_json(
        self, mock_google_credentials, sample_credentials_json
    ):
        """Test loading credentials from JSON string."""
        auth = GoogleCalendarAuth(credentials_json=json.dumps(sample_credentials_json))
        creds = auth.get_credentials()

        assert creds is not None
        mock_google_credentials.from_service_account_info.assert_called_once()

    def test_get_calendar_service(
        self, mock_google_credentials, mock_calendar_service, sample_credentials_json
    ):
        """Test getting Calendar API service."""
        auth = GoogleCalendarAuth(credentials_json=json.dumps(sample_credentials_json))
        service = auth.get_calendar_service()

        assert service is not None

    def test_service_account_email(
        self, mock_google_credentials, sample_credentials_json
    ):
        """Test getting service account email."""
        auth = GoogleCalendarAuth(credentials_json=json.dumps(sample_credentials_json))
        email = auth.service_account_email

        assert email is not None


# ============================================================================
# BusinessHours Tests
# ============================================================================


class TestBusinessHours:
    """Tests for BusinessHours model."""

    def test_default_values(self):
        """Test default business hours."""
        hours = BusinessHours()

        assert hours.start == time(8, 0)
        assert hours.end == time(18, 0)
        assert hours.lunch_start == time(12, 0)
        assert hours.lunch_end == time(13, 0)
        assert hours.working_days == [0, 1, 2, 3, 4]

    def test_from_strings(self):
        """Test creating from string values."""
        hours = BusinessHours.from_strings(
            start="09:00",
            end="17:00",
            lunch_start="12:30",
            lunch_end="13:30",
            working_days=[0, 1, 2, 3],
        )

        assert hours.start == time(9, 0)
        assert hours.end == time(17, 0)
        assert hours.lunch_start == time(12, 30)
        assert hours.lunch_end == time(13, 30)
        assert hours.working_days == [0, 1, 2, 3]

    def test_is_working_day(self):
        """Test working day check."""
        hours = BusinessHours(working_days=[0, 1, 2, 3, 4])

        assert hours.is_working_day(0) is True  # Monday
        assert hours.is_working_day(4) is True  # Friday
        assert hours.is_working_day(5) is False  # Saturday
        assert hours.is_working_day(6) is False  # Sunday

    def test_is_lunch_time(self):
        """Test lunch time check."""
        hours = BusinessHours(lunch_start=time(12, 0), lunch_end=time(13, 0))

        assert hours.is_lunch_time(time(11, 59)) is False
        assert hours.is_lunch_time(time(12, 0)) is True
        assert hours.is_lunch_time(time(12, 30)) is True
        assert hours.is_lunch_time(time(13, 0)) is False

    def test_is_lunch_time_no_lunch(self):
        """Test lunch time check when no lunch break."""
        hours = BusinessHours(lunch_start=None, lunch_end=None)

        assert hours.is_lunch_time(time(12, 0)) is False


# ============================================================================
# German Templates Tests
# ============================================================================


class TestGermanTemplates:
    """Tests for German locale templates."""

    def test_format_event_summary(self):
        """Test event summary formatting."""
        summary = format_event_summary("Max Mustermann")
        assert summary == "Termin: Max Mustermann"

    def test_format_event_description(self):
        """Test event description formatting."""
        description = format_event_description(
            reason="Kontrolluntersuchung",
            patient_name="Max Mustermann",
            phone="+49123456789",
            appointment_type="regular",
            appointment_id=uuid4(),
        )

        assert "Grund: Kontrolluntersuchung" in description
        assert "Patient: Max Mustermann" in description
        assert "Telefon: +49123456789" in description
        assert "Terminart: Regeltermin" in description
        assert "Telefonassistent" in description

    def test_get_german_error_message(self):
        """Test German error messages."""
        assert "nicht mehr verfügbar" in get_german_error_message("slot_unavailable")
        assert "Kalenderfehler" in get_german_error_message("calendar_error")
        assert "erfolgreich gebucht" in get_german_error_message("booking_success")

    def test_build_google_event(self):
        """Test building Google Calendar event payload."""
        start = datetime(2024, 1, 15, 10, 0)
        end = datetime(2024, 1, 15, 10, 15)

        event = build_google_event(
            summary="Termin: Max Mustermann",
            description="Test appointment",
            start_time=start,
            end_time=end,
            timezone="Europe/Berlin",
            location="Raum 1",
            appointment_id=uuid4(),
            patient_id=uuid4(),
            appointment_type="regular",
        )

        assert event["summary"] == "Termin: Max Mustermann"
        assert event["description"] == "Test appointment"
        assert event["location"] == "Raum 1"
        assert "Europe/Berlin" in event["start"]["timeZone"]
        assert "extendedProperties" in event
        assert event["extendedProperties"]["private"]["booked_via"] == "phone_agent"


# ============================================================================
# GoogleCalendarIntegration Tests
# ============================================================================


class TestGoogleCalendarIntegration:
    """Tests for GoogleCalendarIntegration class."""

    @pytest.mark.asyncio
    async def test_get_available_slots(self, google_calendar_integration):
        """Test getting available slots."""
        # Use a date in the past that we control for testing
        with patch("phone_agent.integrations.calendar.google.date") as mock_date:
            mock_date.today.return_value = date(2024, 1, 15)

            start = date(2024, 1, 15)
            end = date(2024, 1, 15)

            slots = await google_calendar_integration.get_available_slots(
                start_date=start,
                end_date=end,
                duration_minutes=15,
            )

            # Should have slots (exact count depends on business hours minus busy/lunch)
            assert isinstance(slots, list)
            for slot in slots:
                assert slot.status == SlotStatus.AVAILABLE

    @pytest.mark.asyncio
    async def test_get_available_slots_excludes_busy(self, google_calendar_integration):
        """Test that busy times are excluded from available slots."""
        with patch("phone_agent.integrations.calendar.google.date") as mock_date:
            mock_date.today.return_value = date(2024, 1, 15)

            slots = await google_calendar_integration.get_available_slots(
                start_date=date(2024, 1, 15),
                end_date=date(2024, 1, 15),
            )

            # The mock has 9:00-9:30 busy, so those slots should be excluded
            slot_times = [s.start.time() for s in slots]
            assert time(9, 0) not in slot_times
            assert time(9, 15) not in slot_times

    @pytest.mark.asyncio
    async def test_get_available_slots_excludes_lunch(self, google_calendar_integration):
        """Test that lunch break is excluded from available slots."""
        with patch("phone_agent.integrations.calendar.google.date") as mock_date:
            mock_date.today.return_value = date(2024, 1, 15)

            slots = await google_calendar_integration.get_available_slots(
                start_date=date(2024, 1, 15),
                end_date=date(2024, 1, 15),
            )

            # No slots during 12:00-13:00 lunch
            slot_times = [s.start.time() for s in slots]
            assert time(12, 0) not in slot_times
            assert time(12, 15) not in slot_times
            assert time(12, 30) not in slot_times
            assert time(12, 45) not in slot_times

    @pytest.mark.asyncio
    async def test_book_slot_success(
        self, google_calendar_integration, sample_booking_request
    ):
        """Test successful slot booking."""
        # Use future date for testing
        future_date = date.today() + timedelta(days=1)
        # Make sure it's not a weekend
        while future_date.weekday() >= 5:
            future_date = future_date + timedelta(days=1)

        slots = await google_calendar_integration.get_available_slots(
            start_date=future_date,
            end_date=future_date,
        )

        assert len(slots) > 0, f"No slots found for {future_date}"

        # Update booking request with actual slot ID
        sample_booking_request.slot_id = slots[0].id

        # Book the slot
        result = await google_calendar_integration.book_slot(sample_booking_request)

        assert result.success is True
        assert result.appointment_id is not None
        assert result.slot is not None
        assert "erfolgreich gebucht" in result.message

    @pytest.mark.asyncio
    async def test_book_slot_not_found(
        self, google_calendar_integration, sample_booking_request
    ):
        """Test booking with invalid slot ID."""
        # Use a random UUID that doesn't exist
        sample_booking_request.slot_id = uuid4()

        result = await google_calendar_integration.book_slot(sample_booking_request)

        assert result.success is False
        assert "nicht mehr verfügbar" in result.message

    @pytest.mark.asyncio
    async def test_cancel_booking(self, google_calendar_integration, sample_booking_request):
        """Test cancelling a booking."""
        # Use future date for testing
        future_date = date.today() + timedelta(days=1)
        while future_date.weekday() >= 5:
            future_date = future_date + timedelta(days=1)

        slots = await google_calendar_integration.get_available_slots(
            start_date=future_date,
            end_date=future_date,
        )

        assert len(slots) > 0, f"No slots found for {future_date}"

        sample_booking_request.slot_id = slots[0].id
        book_result = await google_calendar_integration.book_slot(sample_booking_request)

        assert book_result.success is True

        # Now cancel it
        cancelled = await google_calendar_integration.cancel_booking(
            appointment_id=book_result.appointment_id,
            reason="Patient requested cancellation",
        )

        assert cancelled is True

    @pytest.mark.asyncio
    async def test_cancel_nonexistent_booking(self, google_calendar_integration):
        """Test cancelling a booking that doesn't exist."""
        cancelled = await google_calendar_integration.cancel_booking(
            appointment_id=uuid4(),
            reason="Test cancellation",
        )

        assert cancelled is False

    @pytest.mark.asyncio
    async def test_reschedule_booking(
        self, google_calendar_integration, sample_booking_request
    ):
        """Test rescheduling a booking."""
        # Use future date for testing
        future_date = date.today() + timedelta(days=1)
        while future_date.weekday() >= 5:
            future_date = future_date + timedelta(days=1)

        slots = await google_calendar_integration.get_available_slots(
            start_date=future_date,
            end_date=future_date,
        )

        assert len(slots) >= 2, f"Need at least 2 slots for reschedule test, got {len(slots)}"

        # Book first slot
        sample_booking_request.slot_id = slots[0].id
        book_result = await google_calendar_integration.book_slot(sample_booking_request)

        assert book_result.success is True

        # Reschedule to second slot
        reschedule_result = await google_calendar_integration.reschedule_booking(
            appointment_id=book_result.appointment_id,
            new_slot_id=slots[1].id,
        )

        assert reschedule_result.success is True
        assert "umgebucht" in reschedule_result.message

    @pytest.mark.asyncio
    async def test_check_availability(self, google_calendar_integration):
        """Test checking slot availability."""
        # Use future date for testing
        future_date = date.today() + timedelta(days=1)
        while future_date.weekday() >= 5:
            future_date = future_date + timedelta(days=1)

        slots = await google_calendar_integration.get_available_slots(
            start_date=future_date,
            end_date=future_date,
        )

        if slots:
            is_available = await google_calendar_integration.check_availability(
                slots[0].id
            )
            assert is_available is True

    @pytest.mark.asyncio
    async def test_check_availability_unknown_slot(self, google_calendar_integration):
        """Test checking availability for unknown slot."""
        is_available = await google_calendar_integration.check_availability(uuid4())
        assert is_available is False


# ============================================================================
# Factory Tests
# ============================================================================


class TestCalendarFactory:
    """Tests for calendar factory with Google type."""

    def test_factory_returns_local_without_google_credentials(self):
        """Test that factory falls back to local without Google credentials."""
        from phone_agent.integrations.calendar.factory import (
            get_calendar_integration,
            reset_calendar_integration,
        )
        from phone_agent.integrations.calendar.local import LocalCalendarIntegration

        # Reset any existing singleton
        reset_calendar_integration()

        # With default settings (no google credentials), should use local
        with patch("phone_agent.integrations.calendar.factory.get_settings") as mock_settings:
            mock_settings.return_value.integrations.calendar.type = "google"
            mock_settings.return_value.integrations.calendar.google.credentials_file = ""
            mock_settings.return_value.integrations.calendar.google.credentials_json = ""

            calendar = get_calendar_integration()

            # Should fall back to local
            assert isinstance(calendar, LocalCalendarIntegration)

        # Clean up
        reset_calendar_integration()

    def test_factory_creates_google_integration_with_credentials(
        self, mock_google_credentials, mock_calendar_service, sample_credentials_json
    ):
        """Test that factory creates GoogleCalendarIntegration with credentials."""
        from phone_agent.integrations.calendar.factory import (
            get_calendar_integration,
            reset_calendar_integration,
        )
        from phone_agent.integrations.calendar.google import GoogleCalendarIntegration

        # Reset any existing singleton
        reset_calendar_integration()

        # Mock settings with Google credentials
        with patch("phone_agent.integrations.calendar.factory.get_settings") as mock_settings:
            settings = MagicMock()
            settings.integrations.calendar.type = "google"
            settings.integrations.calendar.timezone = "Europe/Berlin"
            settings.integrations.calendar.google.credentials_file = ""
            settings.integrations.calendar.google.credentials_json = json.dumps(
                sample_credentials_json
            )
            settings.integrations.calendar.google.calendar_id = "primary"
            settings.integrations.calendar.google.business_hours_start = "08:00"
            settings.integrations.calendar.google.business_hours_end = "18:00"
            settings.integrations.calendar.google.lunch_start = "12:00"
            settings.integrations.calendar.google.lunch_end = "13:00"
            settings.integrations.calendar.google.working_days = [0, 1, 2, 3, 4]
            settings.integrations.calendar.google.default_slot_duration = 15
            settings.integrations.calendar.google.max_retries = 3
            settings.integrations.calendar.google.retry_base_delay = 1.0
            settings.integrations.calendar.google.cache_ttl_seconds = 30
            mock_settings.return_value = settings

            calendar = get_calendar_integration()

            assert isinstance(calendar, GoogleCalendarIntegration)

        # Clean up
        reset_calendar_integration()
