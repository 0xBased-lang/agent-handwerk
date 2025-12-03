"""Test fixtures for Google Calendar integration tests."""

from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest


@pytest.fixture
def mock_google_credentials():
    """Mock Google service account credentials."""
    with patch("google.oauth2.service_account.Credentials") as mock:
        mock_creds = MagicMock()
        mock_creds.service_account_email = "test@test-project.iam.gserviceaccount.com"
        mock.from_service_account_file.return_value = mock_creds
        mock.from_service_account_info.return_value = mock_creds
        yield mock


@pytest.fixture
def mock_calendar_service(mock_google_credentials):
    """Mock Google Calendar API service."""
    with patch("googleapiclient.discovery.build") as mock_build:
        service = MagicMock()

        # Mock freebusy response - one busy slot at 9:00-9:30
        service.freebusy().query().execute.return_value = {
            "calendars": {
                "primary": {
                    "busy": [
                        {
                            "start": "2024-01-15T09:00:00+01:00",
                            "end": "2024-01-15T09:30:00+01:00",
                        }
                    ]
                }
            }
        }

        # Mock events insert
        service.events().insert().execute.return_value = {
            "id": "google_event_123",
            "htmlLink": "https://calendar.google.com/calendar/event?eid=abc123",
            "status": "confirmed",
        }

        # Mock events get
        service.events().get().execute.return_value = {
            "id": "google_event_123",
            "summary": "Termin: Max Mustermann",
            "description": "Test appointment",
            "start": {"dateTime": "2024-01-15T10:00:00+01:00", "timeZone": "Europe/Berlin"},
            "end": {"dateTime": "2024-01-15T10:15:00+01:00", "timeZone": "Europe/Berlin"},
        }

        # Mock events update
        service.events().update().execute.return_value = {
            "id": "google_event_123",
            "status": "confirmed",
        }

        # Mock events delete
        service.events().delete().execute.return_value = None

        mock_build.return_value = service
        yield service


@pytest.fixture
def sample_credentials_json():
    """Sample service account credentials JSON."""
    return {
        "type": "service_account",
        "project_id": "test-project",
        "private_key_id": "key123",
        "private_key": "-----BEGIN RSA PRIVATE KEY-----\nfake-key\n-----END RSA PRIVATE KEY-----\n",
        "client_email": "test@test-project.iam.gserviceaccount.com",
        "client_id": "123456789",
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
    }


@pytest.fixture
def google_calendar_auth(mock_google_credentials, sample_credentials_json):
    """Create GoogleCalendarAuth with mocked credentials."""
    import json
    from phone_agent.integrations.calendar.google_auth import GoogleCalendarAuth

    return GoogleCalendarAuth(credentials_json=json.dumps(sample_credentials_json))


@pytest.fixture
def google_calendar_integration(google_calendar_auth, mock_calendar_service):
    """Create GoogleCalendarIntegration with mocked service."""
    from phone_agent.integrations.calendar.google import GoogleCalendarIntegration
    from phone_agent.integrations.calendar.google_models import BusinessHours

    business_hours = BusinessHours.from_strings(
        start="08:00",
        end="18:00",
        lunch_start="12:00",
        lunch_end="13:00",
    )

    return GoogleCalendarIntegration(
        auth=google_calendar_auth,
        calendar_id="primary",
        timezone="Europe/Berlin",
        business_hours=business_hours,
        slot_duration_minutes=15,
    )


@pytest.fixture
def sample_booking_request():
    """Create a sample booking request."""
    from phone_agent.integrations.calendar.base import AppointmentType, BookingRequest

    return BookingRequest(
        slot_id=uuid4(),
        patient_id=uuid4(),
        patient_name="Max Mustermann",
        patient_phone="+49123456789",
        reason="Kontrolluntersuchung",
        appointment_type=AppointmentType.REGULAR,
    )
