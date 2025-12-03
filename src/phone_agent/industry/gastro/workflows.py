"""Gastro-specific workflows and triage logic.

Implements reservation handling based on German restaurant industry standards.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from itf_shared import get_logger

log = get_logger(__name__)


class RequestType(str, Enum):
    """Types of guest requests."""

    RESERVATION = "reservation"  # New reservation
    MODIFICATION = "modification"  # Change existing reservation
    CANCELLATION = "cancellation"  # Cancel reservation
    INFORMATION = "information"  # Menu, hours, directions
    COMPLAINT = "complaint"  # Service issues
    GROUP_BOOKING = "group_booking"  # Large party (>8)


class ServicePeriod(str, Enum):
    """Restaurant service periods."""

    LUNCH = "lunch"  # 11:30-14:30
    DINNER = "dinner"  # 17:30-22:00
    SUNDAY = "sunday"  # 11:30-21:00 (continuous)
    CLOSED = "closed"  # Montag


@dataclass
class RequestResult:
    """Result of request classification."""

    request_type: RequestType
    reason: str
    action: str
    keywords_matched: list[str]
    confidence: float
    requires_callback: bool = False
    priority: int = 2  # 1=high, 2=normal, 3=low


# Keywords for request classification
RESERVATION_KEYWORDS = [
    # Direct reservation requests
    "reservieren",
    "reservierung",
    "tisch",
    "platz",
    "buchen",
    "buchung",
    # Party size indicators
    "personen",
    "gäste",
    "zu zweit",
    "zu dritt",
    "zu viert",
    # Time indicators
    "heute abend",
    "morgen",
    "am wochenende",
    "nächste woche",
    "samstag",
    "sonntag",
]

MODIFICATION_KEYWORDS = [
    # Change requests
    "ändern",
    "änderung",
    "verschieben",
    "umbuchen",
    "andere uhrzeit",
    "anderer tag",
    # Person changes
    "mehr personen",
    "weniger personen",
    "doch zu",
    # Existing booking reference
    "meine reservierung",
    "unsere buchung",
    "hatte reserviert",
]

CANCELLATION_KEYWORDS = [
    # Cancel requests
    "absagen",
    "stornieren",
    "stornierung",
    "nicht kommen",
    "können nicht",
    "müssen absagen",
    "leider absagen",
    # Reasons often given
    "krank",
    "dazwischen",
    "verhindert",
]

INFORMATION_KEYWORDS = [
    # Menu
    "speisekarte",
    "menü",
    "was gibt es",
    "tagesgericht",
    "vegetarisch",
    "vegan",
    # Hours
    "öffnungszeiten",
    "geöffnet",
    "wann auf",
    "wie lange",
    # Location
    "adresse",
    "wo seid ihr",
    "anfahrt",
    "parkplatz",
    "parken",
    # Payment
    "kartenzahlung",
    "bar",
    "gutschein",
]

GROUP_BOOKING_KEYWORDS = [
    # Large parties
    "große gruppe",
    "viele personen",
    "firmenessen",
    "weihnachtsfeier",
    "geburtstag feiern",
    "jubiläum",
    "hochzeit",
    "gruppe",
    "gesellschaft",
]

COMPLAINT_KEYWORDS = [
    # Issues
    "beschwerde",
    "unzufrieden",
    "problem",
    "enttäuscht",
    "ärgerlich",
    "nicht okay",
    "schlecht",
    "kalt",
    "lange gewartet",
]


def classify_request(message: str) -> RequestResult:
    """Classify guest request based on message content.

    Uses keyword matching and simple heuristics to classify request type.
    For production, should be enhanced with LLM-based analysis.

    Args:
        message: Guest's message/request

    Returns:
        RequestResult with type, reason, and recommended action
    """
    message_lower = message.lower()
    matched_keywords: list[str] = []

    # Check for complaints first (high priority)
    for keyword in COMPLAINT_KEYWORDS:
        if keyword in message_lower:
            matched_keywords.append(keyword)

    if matched_keywords:
        return RequestResult(
            request_type=RequestType.COMPLAINT,
            reason=f"Beschwerde erkannt: {', '.join(matched_keywords)}",
            action="Ich verbinde Sie mit unserem Restaurantleiter.",
            keywords_matched=matched_keywords,
            confidence=0.90,
            requires_callback=True,
            priority=1,
        )

    # Check for group bookings (special handling)
    matched_keywords = []
    for keyword in GROUP_BOOKING_KEYWORDS:
        if keyword in message_lower:
            matched_keywords.append(keyword)

    if matched_keywords:
        return RequestResult(
            request_type=RequestType.GROUP_BOOKING,
            reason=f"Gruppenanfrage erkannt: {', '.join(matched_keywords)}",
            action="Für größere Gruppen empfehle ich ein Gespräch mit unserem Restaurantleiter.",
            keywords_matched=matched_keywords,
            confidence=0.85,
            requires_callback=True,
            priority=2,
        )

    # Check for cancellations
    matched_keywords = []
    for keyword in CANCELLATION_KEYWORDS:
        if keyword in message_lower:
            matched_keywords.append(keyword)

    if matched_keywords:
        return RequestResult(
            request_type=RequestType.CANCELLATION,
            reason=f"Stornierung erkannt: {', '.join(matched_keywords)}",
            action="Ich kann Ihre Reservierung stornieren. Unter welchem Namen war gebucht?",
            keywords_matched=matched_keywords,
            confidence=0.85,
            priority=2,
        )

    # Check for modifications
    matched_keywords = []
    for keyword in MODIFICATION_KEYWORDS:
        if keyword in message_lower:
            matched_keywords.append(keyword)

    if matched_keywords:
        return RequestResult(
            request_type=RequestType.MODIFICATION,
            reason=f"Änderungswunsch erkannt: {', '.join(matched_keywords)}",
            action="Gerne ändere ich Ihre Reservierung. Unter welchem Namen war gebucht?",
            keywords_matched=matched_keywords,
            confidence=0.80,
            priority=2,
        )

    # Check for information requests
    matched_keywords = []
    for keyword in INFORMATION_KEYWORDS:
        if keyword in message_lower:
            matched_keywords.append(keyword)

    if matched_keywords:
        return RequestResult(
            request_type=RequestType.INFORMATION,
            reason=f"Informationsanfrage erkannt: {', '.join(matched_keywords)}",
            action="Ich helfe Ihnen gerne mit der Information.",
            keywords_matched=matched_keywords,
            confidence=0.80,
            priority=3,
        )

    # Check for new reservations (most common)
    matched_keywords = []
    for keyword in RESERVATION_KEYWORDS:
        if keyword in message_lower:
            matched_keywords.append(keyword)

    if matched_keywords:
        return RequestResult(
            request_type=RequestType.RESERVATION,
            reason=f"Reservierungsanfrage erkannt: {', '.join(matched_keywords)}",
            action="Sehr gerne! Für wann und wie viele Personen darf ich reservieren?",
            keywords_matched=matched_keywords,
            confidence=0.85,
            priority=2,
        )

    # Default to reservation if no specific keywords matched
    return RequestResult(
        request_type=RequestType.RESERVATION,
        reason="Keine spezifischen Keywords erkannt, Reservierungsanfrage angenommen",
        action="Guten Tag! Möchten Sie einen Tisch reservieren?",
        keywords_matched=[],
        confidence=0.50,
        priority=2,
    )


def get_service_period(hour: int, weekday: int) -> ServicePeriod:
    """Determine service period based on time and day.

    Args:
        hour: Hour of day (0-23)
        weekday: Day of week (0=Monday, 6=Sunday)

    Returns:
        ServicePeriod enum value
    """
    # Monday = closed
    if weekday == 0:
        return ServicePeriod.CLOSED

    # Sunday = continuous service
    if weekday == 6:
        if 11 <= hour < 21:
            return ServicePeriod.SUNDAY
        return ServicePeriod.CLOSED

    # Tuesday-Saturday = split service
    if 11 <= hour < 15:
        return ServicePeriod.LUNCH
    elif 17 <= hour < 22:
        return ServicePeriod.DINNER

    return ServicePeriod.CLOSED


async def get_time_of_day() -> str:
    """Get German greeting based on time of day."""
    from datetime import datetime

    hour = datetime.now().hour

    if hour < 11:
        return "Morgen"
    elif hour < 14:
        return "Mittag"
    elif hour < 18:
        return "Tag"
    else:
        return "Abend"


def extract_party_size(message: str) -> int | None:
    """Extract party size from message.

    Args:
        message: Guest message to parse

    Returns:
        Number of guests or None if not found
    """
    import re

    message_lower = message.lower()

    # Direct number patterns
    patterns = [
        r"(\d+)\s*personen",
        r"für\s*(\d+)",
        r"(\d+)\s*gäste",
        r"(\d+)\s*leute",
        r"tisch\s*für\s*(\d+)",
    ]

    for pattern in patterns:
        match = re.search(pattern, message_lower)
        if match:
            return int(match.group(1))

    # German word numbers - use word boundary regex to avoid false positives
    # (e.g., "reservieren" should not match "vier")
    word_numbers = {
        r"\bzwei\b": 2, r"\bzweit\b": 2, r"\bzu\s+zweit\b": 2,
        r"\bdrei\b": 3, r"\bdritt\b": 3, r"\bzu\s+dritt\b": 3,
        r"\bvier\b": 4, r"\bviert\b": 4, r"\bzu\s+viert\b": 4,
        r"\bfünf\b": 5, r"\bfünft\b": 5, r"\bzu\s+fünft\b": 5,
        r"\bsechs\b": 6, r"\bsechst\b": 6, r"\bzu\s+sechst\b": 6,
        r"\bsieben\b": 7, r"\bsiebt\b": 7, r"\bzu\s+siebt\b": 7,
        r"\bacht\b": 8, r"\bzu\s+acht\b": 8,
        r"\bneun\b": 9, r"\bneunt\b": 9, r"\bzu\s+neunt\b": 9,
        r"\bzehn\b": 10, r"\bzehnt\b": 10, r"\bzu\s+zehnt\b": 10,
    }

    for pattern, num in word_numbers.items():
        if re.search(pattern, message_lower):
            return num

    return None


def extract_date_time(message: str) -> dict[str, Any]:
    """Extract date and time from message.

    Args:
        message: Guest message to parse

    Returns:
        Dict with date and time fields (may be partial)
    """
    import re
    from datetime import datetime, timedelta

    message_lower = message.lower()
    result: dict[str, Any] = {}
    today = datetime.now()

    # Time patterns
    time_patterns = [
        r"um\s*(\d{1,2})\s*(?:uhr|:)",
        r"(\d{1,2})\s*uhr",
        r"(\d{1,2}):(\d{2})",
    ]

    for pattern in time_patterns:
        match = re.search(pattern, message_lower)
        if match:
            hour = int(match.group(1))
            if 10 <= hour <= 22:  # Valid restaurant hours
                result["time"] = f"{hour:02d}:00"
                break

    # Relative date words
    if "heute" in message_lower:
        result["date"] = today.strftime("%Y-%m-%d")
    elif "morgen" in message_lower:
        result["date"] = (today + timedelta(days=1)).strftime("%Y-%m-%d")
    elif "übermorgen" in message_lower:
        result["date"] = (today + timedelta(days=2)).strftime("%Y-%m-%d")

    # Weekday names
    weekdays = {
        "montag": 0, "dienstag": 1, "mittwoch": 2,
        "donnerstag": 3, "freitag": 4, "samstag": 5, "sonntag": 6,
    }

    for day_name, day_num in weekdays.items():
        if day_name in message_lower:
            days_ahead = day_num - today.weekday()
            if days_ahead <= 0:
                days_ahead += 7
            result["date"] = (today + timedelta(days=days_ahead)).strftime("%Y-%m-%d")
            break

    return result


def format_available_slots(slots: list[dict[str, Any]]) -> str:
    """Format available reservation slots for LLM prompt.

    Args:
        slots: List of slot dictionaries with date, time

    Returns:
        Formatted string for prompt injection
    """
    if not slots:
        return "Leider sind aktuell keine freien Tische verfügbar."

    lines = []
    for slot in slots[:5]:  # Limit to 5 options
        date_str = slot.get("date", "")
        time_str = slot.get("time", "")
        capacity = slot.get("capacity", "")
        if capacity:
            lines.append(f"- {date_str} um {time_str} Uhr (bis {capacity} Personen)")
        else:
            lines.append(f"- {date_str} um {time_str} Uhr")

    return "\n".join(lines)
