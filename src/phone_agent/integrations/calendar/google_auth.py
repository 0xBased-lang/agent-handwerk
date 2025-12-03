"""Google Calendar Authentication Module.

Handles authentication for Google Calendar API using service accounts.
Service accounts are recommended for headless server-to-server communication.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from itf_shared import get_logger

log = get_logger(__name__)

# Default scopes for calendar access
CALENDAR_SCOPES = [
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/calendar.events",
]


class GoogleCalendarAuthError(Exception):
    """Authentication error for Google Calendar."""

    def __init__(self, message: str, german_message: str | None = None):
        super().__init__(message)
        self.german_message = german_message or "Verbindung zum Kalender fehlgeschlagen."


class GoogleCalendarAuth:
    """Manages Google Calendar API authentication.

    Supports service account authentication for headless operation.
    Service accounts are recommended for small healthcare practices
    as they don't require interactive OAuth2 consent flows.

    Usage:
        # From file
        auth = GoogleCalendarAuth(credentials_file="/path/to/credentials.json")

        # From JSON string (for environment variables)
        auth = GoogleCalendarAuth(credentials_json='{"type": "service_account", ...}')

        # Get authenticated service
        service = await auth.get_calendar_service()
    """

    def __init__(
        self,
        credentials_file: str | None = None,
        credentials_json: str | None = None,
        scopes: list[str] | None = None,
    ):
        """Initialize Google Calendar authentication.

        Args:
            credentials_file: Path to service account JSON file
            credentials_json: Service account JSON as string (for env vars)
            scopes: OAuth2 scopes (defaults to calendar access)

        Raises:
            GoogleCalendarAuthError: If no credentials provided
        """
        self._credentials_file = credentials_file
        self._credentials_json = credentials_json
        self._scopes = scopes or CALENDAR_SCOPES
        self._credentials = None
        self._service = None

        # Validate that at least one credential source is provided
        if not credentials_file and not credentials_json:
            raise GoogleCalendarAuthError(
                "No Google Calendar credentials provided. "
                "Set credentials_file or credentials_json.",
                german_message="Keine Google Kalender-Zugangsdaten konfiguriert.",
            )

    def _load_credentials(self) -> Any:
        """Load credentials from file or JSON string.

        Returns:
            Google Credentials object

        Raises:
            GoogleCalendarAuthError: If credentials cannot be loaded
        """
        try:
            from google.oauth2 import service_account

            if self._credentials_json:
                # Load from JSON string
                creds_data = json.loads(self._credentials_json)
                credentials = service_account.Credentials.from_service_account_info(
                    creds_data, scopes=self._scopes
                )
                log.debug("Loaded credentials from JSON string")

            elif self._credentials_file:
                # Load from file
                creds_path = Path(self._credentials_file)
                if not creds_path.exists():
                    raise GoogleCalendarAuthError(
                        f"Credentials file not found: {self._credentials_file}",
                        german_message="Kalender-Zugangsdaten nicht gefunden.",
                    )

                credentials = service_account.Credentials.from_service_account_file(
                    str(creds_path), scopes=self._scopes
                )
                log.debug("Loaded credentials from file", path=self._credentials_file)

            else:
                raise GoogleCalendarAuthError(
                    "No credentials source available",
                    german_message="Keine Kalender-Zugangsdaten verfügbar.",
                )

            return credentials

        except json.JSONDecodeError as e:
            raise GoogleCalendarAuthError(
                f"Invalid credentials JSON: {e}",
                german_message="Ungültige Kalender-Zugangsdaten.",
            ) from e
        except Exception as e:
            if isinstance(e, GoogleCalendarAuthError):
                raise
            raise GoogleCalendarAuthError(
                f"Failed to load credentials: {e}",
                german_message="Kalender-Authentifizierung fehlgeschlagen.",
            ) from e

    def get_credentials(self) -> Any:
        """Get valid credentials, loading if necessary.

        Returns:
            Google Credentials object
        """
        if self._credentials is None:
            self._credentials = self._load_credentials()
        return self._credentials

    def get_calendar_service(self) -> Any:
        """Get authenticated Calendar API service.

        Returns:
            Google Calendar API service resource

        Raises:
            GoogleCalendarAuthError: If service cannot be created
        """
        if self._service is not None:
            return self._service

        try:
            from googleapiclient.discovery import build

            credentials = self.get_credentials()
            self._service = build("calendar", "v3", credentials=credentials)
            log.info("Google Calendar service initialized successfully")
            return self._service

        except Exception as e:
            raise GoogleCalendarAuthError(
                f"Failed to create Calendar service: {e}",
                german_message="Kalender-Dienst konnte nicht gestartet werden.",
            ) from e

    def refresh_credentials(self) -> None:
        """Refresh credentials if needed.

        Service account credentials typically don't need refresh,
        but this method can be called to force re-authentication.
        """
        self._credentials = None
        self._service = None
        log.debug("Credentials cache cleared, will reload on next use")

    @property
    def service_account_email(self) -> str | None:
        """Get the service account email address.

        Useful for setting up calendar sharing permissions.

        Returns:
            Service account email or None if not loaded
        """
        try:
            credentials = self.get_credentials()
            return getattr(credentials, "service_account_email", None)
        except GoogleCalendarAuthError:
            return None
