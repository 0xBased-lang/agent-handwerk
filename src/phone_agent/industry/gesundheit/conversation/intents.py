"""Intent detection for healthcare conversations.

Provides keyword-based intent detection for German patient inputs.
"""

from __future__ import annotations

from phone_agent.industry.gesundheit.conversation.state import PatientIntent
from phone_agent.industry.gesundheit.triage import (
    TriageEngine,
    UrgencyLevel,
    get_triage_engine,
)


# Intent keywords (German)
INTENT_KEYWORDS: dict[PatientIntent, list[str]] = {
    PatientIntent.BOOK_APPOINTMENT: [
        "termin", "anmelden", "kommen", "vorbeikommen",
        "untersuchen", "praxis",
    ],
    PatientIntent.CANCEL_APPOINTMENT: [
        "absagen", "stornieren", "nicht kommen", "abmelden",
    ],
    PatientIntent.RESCHEDULE_APPOINTMENT: [
        "verschieben", "umbuchen", "anderen termin", "umbestellen",
        "verlegen", "neuen termin",
    ],
    PatientIntent.REQUEST_PRESCRIPTION: [
        "rezept", "medikament", "verschreibung",
    ],
    PatientIntent.REQUEST_PRESCRIPTION_REFILL: [
        "folgerezept", "nachbestellen", "wieder bestellen",
        "dasselbe medikament", "medikament geht aus", "brauche wieder",
    ],
    PatientIntent.LAB_RESULTS: [
        "labor", "befund", "ergebnis", "blut",
    ],
    PatientIntent.LAB_RESULTS_INQUIRY: [
        "laborwerte", "blutwerte", "ergebnisse abholen",
        "sind meine ergebnisse", "sind meine werte",
        "befund besprechen", "werte besprechen",
    ],
    PatientIntent.SPEAK_TO_STAFF: [
        "arzt sprechen", "assistentin", "rückruf", "mensch",
    ],
    PatientIntent.EMERGENCY: [
        "notfall", "dringend", "sofort", "schlecht",
        "brustschmerz", "atemnot", "bewusstlos",
    ],
}


class IntentDetector:
    """Detects patient intent from text input."""

    def __init__(self, triage_engine: TriageEngine | None = None):
        """Initialize intent detector.

        Args:
            triage_engine: Optional triage engine for emergency detection
        """
        self._triage = triage_engine or get_triage_engine()

    def detect(self, text: str) -> PatientIntent:
        """Detect intent from user text.

        Args:
            text: User input text (German)

        Returns:
            Detected intent or UNKNOWN
        """
        text_lower = text.lower()

        for intent, keywords in INTENT_KEYWORDS.items():
            for keyword in keywords:
                if keyword in text_lower:
                    return intent

        return PatientIntent.UNKNOWN

    def is_emergency(self, text: str) -> bool:
        """Check if text indicates an emergency.

        Uses triage engine for comprehensive assessment.

        Args:
            text: User input text

        Returns:
            True if emergency detected
        """
        result = self._triage.assess(symptoms=[], free_text=text)
        return result.urgency == UrgencyLevel.EMERGENCY

    def has_symptoms(self, text: str) -> bool:
        """Check if text contains symptom descriptions.

        Args:
            text: User input text

        Returns:
            True if symptoms mentioned
        """
        symptoms = self._triage.extract_symptoms_from_text(text)
        return len(symptoms) > 0

    def extract_symptoms(self, text: str) -> list[str]:
        """Extract symptom names from text.

        Args:
            text: User input text

        Returns:
            List of symptom names
        """
        symptoms = self._triage.extract_symptoms_from_text(text)
        return [s.name for s in symptoms]


# Singleton instance
_detector: IntentDetector | None = None


def get_intent_detector() -> IntentDetector:
    """Get singleton intent detector instance."""
    global _detector
    if _detector is None:
        _detector = IntentDetector()
    return _detector
