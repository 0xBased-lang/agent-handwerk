"""Healthcare-specific workflows and triage logic.

Implements telephone triage based on German ambulatory healthcare standards.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from itf_shared import get_logger

log = get_logger(__name__)


class TriageLevel(str, Enum):
    """Triage urgency levels for healthcare context."""

    AKUT = "akut"  # Emergency - call 112
    DRINGEND = "dringend"  # Same-day appointment needed
    NORMAL = "normal"  # Regular appointment
    BERATUNG = "beratung"  # Phone advice sufficient


@dataclass
class TriageResult:
    """Result of triage assessment."""

    level: TriageLevel
    reason: str
    action: str
    keywords_matched: list[str]
    confidence: float


# Keywords for triage classification
AKUT_KEYWORDS = [
    # Cardiovascular
    "brustschmerzen",
    "herzschmerzen",
    "herzinfarkt",
    "atemnot",
    "atembeschwerden",
    "kann nicht atmen",
    # Neurological
    "bewusstlos",
    "ohnmacht",
    "schlaganfall",
    "lähmung",
    "taubheit gesicht",
    "sprachstörung",
    # Trauma
    "starke blutung",
    "unfall",
    "sturz kopf",
    # Other emergencies
    "vergiftung",
    "allergischer schock",
    "anaphylaxie",
    "selbstmord",
    "suizid",
]

DRINGEND_KEYWORDS = [
    # Fever
    "hohes fieber",
    "fieber über 39",
    "fieber kind",
    # Pain
    "starke schmerzen",
    "unerträgliche schmerzen",
    "akute schmerzen",
    # Infections
    "infektion",
    "entzündung",
    "eiter",
    "geschwollen rot",
    # Acute symptoms
    "plötzlich verschlechtert",
    "seit heute morgen",
    "kann nicht arbeiten",
    "arbeitsunfähig",
    # Specific conditions
    "durchfall kind",
    "erbrechen kind",
    "asthma anfall",
]

NORMAL_KEYWORDS = [
    # Checkups
    "vorsorge",
    "check-up",
    "gesundheitscheck",
    "kontrolle",
    "kontrolltermin",
    # Routine
    "routineuntersuchung",
    "blutabnahme",
    "impfung",
    "impftermin",
    # Prescriptions
    "rezept",
    "wiederholungsrezept",
    "überweisung",
    # Chronic management
    "seit wochen",
    "seit monaten",
    "chronisch",
]

BERATUNG_KEYWORDS = [
    # Information
    "öffnungszeiten",
    "sprechzeiten",
    "adresse",
    "anfahrt",
    "parkplatz",
    # Administrative
    "termin absagen",
    "termin verschieben",
    "ergebnis abholen",
    "befund",
    # Questions
    "frage",
    "information",
    "wie lange",
]


def perform_triage(message: str) -> TriageResult:
    """Perform triage assessment based on patient message.

    Uses keyword matching and simple heuristics to classify urgency.
    For production, should be enhanced with LLM-based analysis.

    Args:
        message: Patient's description of their concern

    Returns:
        TriageResult with level, reason, and recommended action
    """
    message_lower = message.lower()
    matched_keywords: list[str] = []

    # Check for emergency keywords first
    for keyword in AKUT_KEYWORDS:
        if keyword in message_lower:
            matched_keywords.append(keyword)

    if matched_keywords:
        return TriageResult(
            level=TriageLevel.AKUT,
            reason=f"Notfall-Keywords erkannt: {', '.join(matched_keywords)}",
            action="Bitte rufen Sie sofort 112 an oder gehen Sie in die nächste Notaufnahme!",
            keywords_matched=matched_keywords,
            confidence=0.95,
        )

    # Check for urgent keywords
    matched_keywords = []
    for keyword in DRINGEND_KEYWORDS:
        if keyword in message_lower:
            matched_keywords.append(keyword)

    if matched_keywords:
        return TriageResult(
            level=TriageLevel.DRINGEND,
            reason=f"Dringende Symptome erkannt: {', '.join(matched_keywords)}",
            action="Ich werde versuchen, Ihnen heute noch einen Termin zu geben.",
            keywords_matched=matched_keywords,
            confidence=0.85,
        )

    # Check for advice/information keywords
    matched_keywords = []
    for keyword in BERATUNG_KEYWORDS:
        if keyword in message_lower:
            matched_keywords.append(keyword)

    if matched_keywords:
        return TriageResult(
            level=TriageLevel.BERATUNG,
            reason=f"Informationsanfrage erkannt: {', '.join(matched_keywords)}",
            action="Ich kann Ihnen hier direkt helfen.",
            keywords_matched=matched_keywords,
            confidence=0.80,
        )

    # Check for routine keywords
    matched_keywords = []
    for keyword in NORMAL_KEYWORDS:
        if keyword in message_lower:
            matched_keywords.append(keyword)

    if matched_keywords:
        return TriageResult(
            level=TriageLevel.NORMAL,
            reason=f"Routineanfrage erkannt: {', '.join(matched_keywords)}",
            action="Ich kann Ihnen gerne einen Termin anbieten.",
            keywords_matched=matched_keywords,
            confidence=0.75,
        )

    # Default to normal if no specific keywords matched
    return TriageResult(
        level=TriageLevel.NORMAL,
        reason="Keine spezifischen Keywords erkannt, normale Terminanfrage angenommen",
        action="Ich kann Ihnen gerne einen Termin anbieten. Können Sie mir Ihr Anliegen genauer beschreiben?",
        keywords_matched=[],
        confidence=0.50,
    )


async def get_time_of_day() -> str:
    """Get German greeting based on time of day."""
    from datetime import datetime

    hour = datetime.now().hour

    if hour < 11:
        return "Morgen"
    elif hour < 14:
        return "Mittag"
    elif hour < 18:
        return "Nachmittag"
    else:
        return "Abend"


def format_appointment_slots(slots: list[dict[str, Any]]) -> str:
    """Format available appointment slots for LLM prompt.

    Args:
        slots: List of slot dictionaries with date, time, duration

    Returns:
        Formatted string for prompt injection
    """
    if not slots:
        return "Leider sind aktuell keine freien Termine verfügbar."

    lines = []
    for slot in slots[:5]:  # Limit to 5 options
        date_str = slot.get("date", "")
        time_str = slot.get("time", "")
        lines.append(f"- {date_str} um {time_str} Uhr")

    return "\n".join(lines)
