"""Google Calendar Data Models.

Contains data structures specific to Google Calendar integration,
including business hours configuration and event ID mappings.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, time
from typing import Any
from uuid import UUID


@dataclass
class BusinessHours:
    """Business hours configuration for slot generation.

    Defines when the practice is open and available for appointments.
    """

    start: time = field(default_factory=lambda: time(8, 0))
    end: time = field(default_factory=lambda: time(18, 0))
    lunch_start: time | None = field(default_factory=lambda: time(12, 0))
    lunch_end: time | None = field(default_factory=lambda: time(13, 0))
    working_days: list[int] = field(default_factory=lambda: [0, 1, 2, 3, 4])

    @classmethod
    def from_strings(
        cls,
        start: str = "08:00",
        end: str = "18:00",
        lunch_start: str | None = "12:00",
        lunch_end: str | None = "13:00",
        working_days: list[int] | None = None,
    ) -> "BusinessHours":
        """Create BusinessHours from string time values.

        Args:
            start: Start time as HH:MM
            end: End time as HH:MM
            lunch_start: Lunch start as HH:MM (optional)
            lunch_end: Lunch end as HH:MM (optional)
            working_days: List of weekday indices (0=Monday, 6=Sunday)

        Returns:
            BusinessHours instance
        """

        def parse_time(t: str | None) -> time | None:
            if not t:
                return None
            parts = t.split(":")
            return time(int(parts[0]), int(parts[1]))

        return cls(
            start=parse_time(start) or time(8, 0),
            end=parse_time(end) or time(18, 0),
            lunch_start=parse_time(lunch_start),
            lunch_end=parse_time(lunch_end),
            working_days=working_days or [0, 1, 2, 3, 4],
        )

    def is_working_day(self, weekday: int) -> bool:
        """Check if a weekday is a working day.

        Args:
            weekday: Day of week (0=Monday, 6=Sunday)

        Returns:
            True if it's a working day
        """
        return weekday in self.working_days

    def is_lunch_time(self, t: time) -> bool:
        """Check if a time falls within lunch break.

        Args:
            t: Time to check

        Returns:
            True if during lunch break
        """
        if self.lunch_start is None or self.lunch_end is None:
            return False
        return self.lunch_start <= t < self.lunch_end


@dataclass
class GoogleEventMapping:
    """Mapping between internal appointment IDs and Google event IDs.

    Used to track the relationship between Phone Agent appointments
    and their corresponding Google Calendar events.
    """

    appointment_id: UUID
    google_event_id: str
    calendar_id: str
    created_at: datetime = field(default_factory=datetime.now)
    patient_id: UUID | None = None
    appointment_type: str | None = None


# German locale templates for calendar events
GERMAN_TEMPLATES = {
    "event_summary": "Termin: {patient_name}",
    "event_description": """Grund: {reason}
Patient: {patient_name}
Telefon: {phone}
Terminart: {appointment_type}

Gebucht via: Telefonassistent
Buchungs-ID: {appointment_id}""",
    "cancellation_note": "Storniert am {date}: {reason}",
    "reschedule_note": "Umgebucht von {old_time} auf {new_time}",
    "appointment_types": {
        "regular": "Regeltermin",
        "acute": "Akutsprechstunde",
        "followup": "Wiedervorstellung",
        "preventive": "Vorsorge",
        "consultation": "Beratung",
    },
    "error_messages": {
        "slot_unavailable": "Dieser Termin ist leider nicht mehr verfügbar.",
        "calendar_error": "Es ist ein Kalenderfehler aufgetreten. Bitte versuchen Sie es erneut.",
        "authentication_error": "Verbindung zum Kalender fehlgeschlagen.",
        "rate_limit": "Zu viele Anfragen. Bitte warten Sie einen Moment.",
        "event_not_found": "Termin nicht gefunden.",
        "booking_success": "Termin erfolgreich gebucht.",
        "cancel_success": "Termin erfolgreich storniert.",
        "reschedule_success": "Termin erfolgreich umgebucht.",
    },
}


def format_event_summary(patient_name: str) -> str:
    """Format event summary (title) in German.

    Args:
        patient_name: Patient's name

    Returns:
        Formatted event summary
    """
    return GERMAN_TEMPLATES["event_summary"].format(patient_name=patient_name)


def format_event_description(
    reason: str,
    patient_name: str,
    phone: str,
    appointment_type: str,
    appointment_id: UUID,
) -> str:
    """Format event description in German.

    Args:
        reason: Appointment reason
        patient_name: Patient's name
        phone: Patient's phone number
        appointment_type: Type of appointment
        appointment_id: Internal appointment ID

    Returns:
        Formatted event description
    """
    # Translate appointment type to German
    type_german = GERMAN_TEMPLATES["appointment_types"].get(
        appointment_type, appointment_type
    )

    return GERMAN_TEMPLATES["event_description"].format(
        reason=reason,
        patient_name=patient_name,
        phone=phone,
        appointment_type=type_german,
        appointment_id=str(appointment_id),
    )


def get_german_error_message(error_type: str) -> str:
    """Get German error message for an error type.

    Args:
        error_type: Error type key

    Returns:
        German error message
    """
    return GERMAN_TEMPLATES["error_messages"].get(
        error_type, "Ein Fehler ist aufgetreten."
    )


def build_google_event(
    summary: str,
    description: str,
    start_time: datetime,
    end_time: datetime,
    timezone: str = "Europe/Berlin",
    location: str | None = None,
    appointment_id: UUID | None = None,
    patient_id: UUID | None = None,
    appointment_type: str | None = None,
) -> dict[str, Any]:
    """Build a Google Calendar event payload.

    Args:
        summary: Event title
        description: Event description
        start_time: Start datetime
        end_time: End datetime
        timezone: Timezone string
        location: Optional location
        appointment_id: Optional internal appointment ID
        patient_id: Optional patient ID
        appointment_type: Optional appointment type

    Returns:
        Google Calendar event dict
    """
    event: dict[str, Any] = {
        "summary": summary,
        "description": description,
        "start": {
            "dateTime": start_time.isoformat(),
            "timeZone": timezone,
        },
        "end": {
            "dateTime": end_time.isoformat(),
            "timeZone": timezone,
        },
        "reminders": {
            "useDefault": False,
            "overrides": [
                {"method": "popup", "minutes": 60},
            ],
        },
    }

    if location:
        event["location"] = location

    # Store internal IDs in extended properties for later lookup
    extended_properties: dict[str, Any] = {"private": {"booked_via": "phone_agent"}}

    if appointment_id:
        extended_properties["private"]["phone_agent_id"] = str(appointment_id)
    if patient_id:
        extended_properties["private"]["patient_id"] = str(patient_id)
    if appointment_type:
        extended_properties["private"]["appointment_type"] = appointment_type

    event["extendedProperties"] = extended_properties

    return event
