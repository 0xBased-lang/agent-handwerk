"""Advanced healthcare triage system.

Implements intelligent symptom assessment based on German ambulatory
healthcare guidelines (KBV Bereitschaftsdienst-Triage).

Features:
- Multi-symptom analysis
- Risk scoring
- Emergency detection
- Urgency classification
- Recommended actions
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class SymptomCategory(str, Enum):
    """Categories of symptoms for triage assessment."""

    CARDIOVASCULAR = "cardiovascular"
    RESPIRATORY = "respiratory"
    NEUROLOGICAL = "neurological"
    GASTROINTESTINAL = "gastrointestinal"
    MUSCULOSKELETAL = "musculoskeletal"
    DERMATOLOGICAL = "dermatological"
    PSYCHIATRIC = "psychiatric"
    UROLOGICAL = "urological"
    GYNECOLOGICAL = "gynecological"
    PEDIATRIC = "pediatric"
    GENERAL = "general"


class UrgencyLevel(str, Enum):
    """Urgency levels following German triage standards."""

    EMERGENCY = "emergency"        # Sofort: 112 rufen
    VERY_URGENT = "very_urgent"    # Sehr dringend: < 10 min
    URGENT = "urgent"              # Dringend: < 30 min
    STANDARD = "standard"          # Normal: < 90 min
    NON_URGENT = "non_urgent"      # Nicht dringend: Regeltermin


@dataclass
class Symptom:
    """Individual symptom with attributes."""

    name: str
    category: SymptomCategory
    severity: int  # 1-10
    duration_hours: float | None = None
    is_new: bool = True
    is_worsening: bool = False
    associated_symptoms: list[str] = field(default_factory=list)

    # Risk modifiers
    fever: bool = False
    fever_temp: float | None = None
    pain_level: int | None = None  # 1-10

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "name": self.name,
            "category": self.category.value,
            "severity": self.severity,
            "duration_hours": self.duration_hours,
            "is_new": self.is_new,
            "is_worsening": self.is_worsening,
            "associated_symptoms": self.associated_symptoms,
            "fever": self.fever,
            "fever_temp": self.fever_temp,
            "pain_level": self.pain_level,
        }


@dataclass
class PatientContext:
    """Patient information for triage context."""

    age: int | None = None
    gender: str | None = None
    is_pregnant: bool = False

    # Pre-existing conditions
    chronic_conditions: list[str] = field(default_factory=list)
    allergies: list[str] = field(default_factory=list)
    medications: list[str] = field(default_factory=list)

    # Risk factors
    is_diabetic: bool = False
    is_immunocompromised: bool = False
    has_heart_condition: bool = False

    def calculate_risk_multiplier(self) -> float:
        """Calculate risk multiplier based on patient factors."""
        multiplier = 1.0

        # Age risk
        if self.age is not None:
            if self.age < 2 or self.age > 75:
                multiplier *= 1.5
            elif self.age > 65:
                multiplier *= 1.2

        # Pregnancy risk
        if self.is_pregnant:
            multiplier *= 1.3

        # Chronic conditions
        if self.is_diabetic:
            multiplier *= 1.2
        if self.is_immunocompromised:
            multiplier *= 1.5
        if self.has_heart_condition:
            multiplier *= 1.3

        return min(multiplier, 2.5)  # Cap at 2.5x


@dataclass
class TriageResult:
    """Result of triage assessment."""

    urgency: UrgencyLevel
    risk_score: float  # 0-100
    primary_concern: str
    recommended_action: str
    max_wait_minutes: int | None
    requires_callback: bool = False
    requires_doctor: bool = False
    emergency_symptoms: list[str] = field(default_factory=list)
    assessment_notes: list[str] = field(default_factory=list)
    timestamp: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "urgency": self.urgency.value,
            "risk_score": self.risk_score,
            "primary_concern": self.primary_concern,
            "recommended_action": self.recommended_action,
            "max_wait_minutes": self.max_wait_minutes,
            "requires_callback": self.requires_callback,
            "requires_doctor": self.requires_doctor,
            "emergency_symptoms": self.emergency_symptoms,
            "assessment_notes": self.assessment_notes,
            "timestamp": self.timestamp.isoformat(),
        }


# Emergency symptom patterns (always escalate)
EMERGENCY_PATTERNS: dict[str, list[str]] = {
    "chest_pain": [
        "brustschmerz", "brustdruck", "engegefühl brust",
        "herzschmerz", "stechen brust", "brennen brust",
    ],
    "breathing_difficulty": [
        "atemnot", "kurzatmig", "kann nicht atmen",
        "luftnot", "ersticken", "atemprobleme",
    ],
    "stroke_symptoms": [
        "lähmung", "taubheit gesicht", "arm schwäche",
        "sprachstörung", "verwirrung plötzlich", "sehen verschwommen",
    ],
    "severe_bleeding": [
        "starke blutung", "blut nicht stoppen",
        "große wunde", "viel blut",
    ],
    "unconsciousness": [
        "bewusstlos", "ohnmacht", "nicht ansprechbar",
        "zusammengebrochen",
    ],
    "severe_allergic": [
        "allergischer schock", "anaphylaxie", "geschwollene zunge",
        "kann nicht schlucken", "ausschlag ganzer körper",
    ],
    "severe_pain": [
        "unerträgliche schmerzen", "stärkste schmerzen",
        "schlimmste schmerzen meines lebens",
    ],
}

# Urgent symptom patterns (same-day appointment)
URGENT_PATTERNS: dict[str, list[str]] = {
    "high_fever": [
        "hohes fieber", "über 39 grad", "fieber kind",
        "schüttelfrost", "fieber seit tagen",
    ],
    "acute_pain": [
        "starke schmerzen", "akute schmerzen",
        "plötzliche schmerzen",
    ],
    "vomiting": [
        "erbrechen", "kann nichts bei mir behalten",
        "übelkeit stark",
    ],
    "injury": [
        "verletzung", "unfall", "sturz", "gebrochen",
    ],
    "infection_signs": [
        "eitrig", "entzündet", "geschwollen rot",
        "heiß und rot",
    ],
}

# German symptom synonyms for NLU
SYMPTOM_SYNONYMS: dict[str, list[str]] = {
    "kopfschmerzen": ["kopfweh", "schädel brummt", "migräne"],
    "bauchschmerzen": ["bauchweh", "magenschmerzen", "unterleibsschmerzen"],
    "rückenschmerzen": ["rücken tut weh", "kreuzschmerzen", "hexenschuss"],
    "halsschmerzen": ["halsweh", "schluckbeschwerden", "kratzen im hals"],
    "husten": ["huste", "hustenreiz", "reizhusten", "auswurf"],
    "schnupfen": ["erkältung", "nase verstopft", "laufende nase"],
    "schwindel": ["benommen", "gleichgewichtsstörung", "alles dreht sich"],
    "müdigkeit": ["erschöpft", "keine energie", "matt", "abgeschlagen"],
    "fieber": ["temperatur", "erhöhte temperatur", "fiebert"],
    "durchfall": ["dünnpfiff", "magendarm", "weicher stuhl"],
    "verstopfung": ["kein stuhlgang", "harter stuhl"],
    "schlafstörung": ["kann nicht schlafen", "wache auf", "schlaflos"],
    "angst": ["panik", "unruhig", "ängstlich", "besorgt"],
    "depression": ["traurig", "niedergeschlagen", "hoffnungslos", "antriebslos"],
}


class TriageEngine:
    """Intelligent triage engine for symptom assessment."""

    def __init__(self):
        """Initialize triage engine."""
        self._emergency_patterns = EMERGENCY_PATTERNS
        self._urgent_patterns = URGENT_PATTERNS
        self._symptom_synonyms = SYMPTOM_SYNONYMS

    def assess(
        self,
        symptoms: list[Symptom],
        patient: PatientContext | None = None,
        free_text: str | None = None,
    ) -> TriageResult:
        """
        Perform triage assessment.

        Args:
            symptoms: List of symptoms reported
            patient: Patient context if available
            free_text: Free-text description for NLU analysis

        Returns:
            TriageResult with urgency and recommendations
        """
        patient = patient or PatientContext()
        emergency_found: list[str] = []
        assessment_notes: list[str] = []

        # Check free text for emergency patterns
        if free_text:
            text_lower = free_text.lower()
            for pattern_name, keywords in self._emergency_patterns.items():
                for keyword in keywords:
                    if keyword in text_lower:
                        emergency_found.append(f"{pattern_name}: {keyword}")

        # If emergency found, return immediately
        if emergency_found:
            return TriageResult(
                urgency=UrgencyLevel.EMERGENCY,
                risk_score=100.0,
                primary_concern=emergency_found[0].split(":")[0],
                recommended_action="Bitte rufen Sie sofort den Notruf 112 an oder lassen Sie sich in die nächste Notaufnahme bringen.",
                max_wait_minutes=0,
                requires_callback=False,
                requires_doctor=True,
                emergency_symptoms=emergency_found,
                assessment_notes=["Notfall erkannt - sofortige medizinische Hilfe erforderlich"],
            )

        # Calculate base risk score from symptoms
        base_score = 0.0
        primary_concern = "Allgemeine Beschwerden"

        if symptoms:
            # Weight by severity
            severity_scores = [s.severity for s in symptoms]
            base_score = sum(severity_scores) / len(severity_scores) * 10

            # Find most severe symptom
            most_severe = max(symptoms, key=lambda s: s.severity)
            primary_concern = most_severe.name

            # Add modifiers
            for symptom in symptoms:
                if symptom.is_worsening:
                    base_score += 10
                    assessment_notes.append(f"{symptom.name} verschlechtert sich")

                if symptom.fever and symptom.fever_temp:
                    if symptom.fever_temp >= 39.5:
                        base_score += 20
                        assessment_notes.append(f"Hohes Fieber: {symptom.fever_temp}°C")
                    elif symptom.fever_temp >= 38.5:
                        base_score += 10

                if symptom.pain_level and symptom.pain_level >= 8:
                    base_score += 15
                    assessment_notes.append(f"Starke Schmerzen: {symptom.pain_level}/10")

                if symptom.duration_hours and symptom.duration_hours > 72:
                    base_score += 5
                    assessment_notes.append("Symptome bestehen seit über 3 Tagen")

        # Check urgent patterns in free text
        urgent_found = False
        if free_text:
            text_lower = free_text.lower()
            for pattern_name, keywords in self._urgent_patterns.items():
                for keyword in keywords:
                    if keyword in text_lower:
                        urgent_found = True
                        base_score += 15
                        assessment_notes.append(f"Dringend: {pattern_name}")
                        break
                if urgent_found:
                    break

        # Apply patient risk multiplier
        risk_multiplier = patient.calculate_risk_multiplier()
        final_score = min(base_score * risk_multiplier, 99.0)  # Cap below emergency

        if risk_multiplier > 1.0:
            assessment_notes.append(f"Risikopatient (Faktor: {risk_multiplier:.1f})")

        # Determine urgency level
        urgency, max_wait, action = self._determine_urgency(final_score, urgent_found)

        return TriageResult(
            urgency=urgency,
            risk_score=round(final_score, 1),
            primary_concern=primary_concern,
            recommended_action=action,
            max_wait_minutes=max_wait,
            requires_callback=urgency in [UrgencyLevel.URGENT, UrgencyLevel.VERY_URGENT],
            requires_doctor=final_score >= 50,
            emergency_symptoms=[],
            assessment_notes=assessment_notes,
        )

    def _determine_urgency(
        self,
        score: float,
        urgent_pattern: bool,
    ) -> tuple[UrgencyLevel, int | None, str]:
        """Determine urgency level from risk score."""

        if score >= 80:
            return (
                UrgencyLevel.VERY_URGENT,
                10,
                "Bitte kommen Sie umgehend in die Praxis. Wir informieren den Arzt.",
            )

        if score >= 60 or urgent_pattern:
            return (
                UrgencyLevel.URGENT,
                30,
                "Wir geben Ihnen einen dringenden Termin für heute. Bitte kommen Sie so bald wie möglich.",
            )

        if score >= 40:
            return (
                UrgencyLevel.STANDARD,
                90,
                "Wir können Ihnen einen Termin für heute oder morgen anbieten.",
            )

        return (
            UrgencyLevel.NON_URGENT,
            None,
            "Für Ihre Beschwerden können wir einen regulären Termin vereinbaren.",
        )

    def extract_symptoms_from_text(self, text: str) -> list[Symptom]:
        """
        Extract symptoms from free-text description using NLU.

        Args:
            text: Patient's description in German

        Returns:
            List of identified symptoms
        """
        text_lower = text.lower()
        found_symptoms: list[Symptom] = []

        # Check for known symptoms and synonyms
        for canonical, synonyms in self._symptom_synonyms.items():
            all_terms = [canonical] + synonyms
            for term in all_terms:
                if term in text_lower:
                    # Determine category
                    category = self._categorize_symptom(canonical)

                    # Estimate severity from context
                    severity = self._estimate_severity(text_lower, term)

                    found_symptoms.append(Symptom(
                        name=canonical,
                        category=category,
                        severity=severity,
                        is_worsening="schlimmer" in text_lower or "verschlechtert" in text_lower,
                    ))
                    break  # Only add once per canonical symptom

        # Check for fever with temperature
        import re
        temp_match = re.search(r'(\d{2}[,\.]\d)\s*(?:grad|°)', text_lower)
        if temp_match:
            temp = float(temp_match.group(1).replace(',', '.'))
            # Add fever symptom if not already present
            fever_exists = any(s.name == "fieber" for s in found_symptoms)
            if not fever_exists and temp >= 37.5:
                found_symptoms.append(Symptom(
                    name="fieber",
                    category=SymptomCategory.GENERAL,
                    severity=min(int((temp - 36) * 2), 10),
                    fever=True,
                    fever_temp=temp,
                ))
            elif fever_exists:
                for s in found_symptoms:
                    if s.name == "fieber":
                        s.fever = True
                        s.fever_temp = temp

        # Check for pain level
        pain_match = re.search(r'schmerz(?:en)?.*?(\d{1,2})(?:\s*von\s*10|\s*/\s*10)?', text_lower)
        if pain_match:
            pain_level = int(pain_match.group(1))
            for s in found_symptoms:
                if "schmerz" in s.name:
                    s.pain_level = min(pain_level, 10)

        return found_symptoms

    def _categorize_symptom(self, symptom: str) -> SymptomCategory:
        """Categorize symptom by body system."""
        categories = {
            SymptomCategory.NEUROLOGICAL: ["kopfschmerzen", "schwindel", "migräne"],
            SymptomCategory.GASTROINTESTINAL: ["bauchschmerzen", "durchfall", "verstopfung", "übelkeit"],
            SymptomCategory.RESPIRATORY: ["husten", "schnupfen", "atemnot", "halsschmerzen"],
            SymptomCategory.MUSCULOSKELETAL: ["rückenschmerzen", "gelenkschmerzen"],
            SymptomCategory.PSYCHIATRIC: ["angst", "depression", "schlafstörung"],
            SymptomCategory.CARDIOVASCULAR: ["herzrasen", "brustschmerzen"],
        }

        for category, symptoms in categories.items():
            if symptom in symptoms:
                return category

        return SymptomCategory.GENERAL

    def _estimate_severity(self, text: str, symptom_term: str) -> int:
        """Estimate symptom severity from context."""
        # Look for severity modifiers near the symptom
        severe_words = ["stark", "heftig", "schlimm", "extrem", "unerträglich"]
        mild_words = ["leicht", "bisschen", "etwas", "wenig"]

        # Default severity
        severity = 5

        for word in severe_words:
            if word in text:
                severity = 8
                break

        for word in mild_words:
            if word in text:
                severity = 3
                break

        return severity


# Singleton instance
_triage_engine: TriageEngine | None = None


def get_triage_engine() -> TriageEngine:
    """Get or create triage engine singleton."""
    global _triage_engine
    if _triage_engine is None:
        _triage_engine = TriageEngine()
    return _triage_engine
