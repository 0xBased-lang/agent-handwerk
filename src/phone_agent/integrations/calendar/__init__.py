"""Calendar Integration Module.

Provides calendar integration for appointment scheduling.
Supports:
- Local database-backed calendar (uses AppointmentRepository)
- Google Calendar (via Google Calendar API)
- Mock calendar for development/testing
- Extensible for external calendar systems (Outlook, etc.)
"""

from phone_agent.integrations.calendar.base import (
    AppointmentType,
    BookingRequest,
    BookingResult,
    CalendarIntegration,
    SlotStatus,
    TimeSlot,
)
from phone_agent.integrations.calendar.factory import (
    get_calendar_integration,
    reset_calendar_integration,
)
from phone_agent.integrations.calendar.local import LocalCalendarIntegration

# Google Calendar exports (lazy import to avoid dependency errors)
__all__ = [
    # Base classes
    "CalendarIntegration",
    "TimeSlot",
    "SlotStatus",
    "AppointmentType",
    "BookingRequest",
    "BookingResult",
    # Implementations
    "LocalCalendarIntegration",
    # Factory
    "get_calendar_integration",
    "reset_calendar_integration",
]


def __getattr__(name: str):
    """Lazy import for Google Calendar classes to avoid import errors when deps missing."""
    if name == "GoogleCalendarIntegration":
        from phone_agent.integrations.calendar.google import GoogleCalendarIntegration

        return GoogleCalendarIntegration
    if name == "GoogleCalendarAuth":
        from phone_agent.integrations.calendar.google_auth import GoogleCalendarAuth

        return GoogleCalendarAuth
    if name == "GoogleCalendarError":
        from phone_agent.integrations.calendar.google import GoogleCalendarError

        return GoogleCalendarError
    if name == "GoogleCalendarAuthError":
        from phone_agent.integrations.calendar.google_auth import GoogleCalendarAuthError

        return GoogleCalendarAuthError
    if name == "BusinessHours":
        from phone_agent.integrations.calendar.google_models import BusinessHours

        return BusinessHours
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
