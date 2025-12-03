"""Advanced job triage system for Handwerk.

Implements intelligent job assessment based on:
- Multi-category issue detection
- Risk scoring with customer context
- Emergency pattern recognition
- German NLU for problem extraction
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
import re

# Import shared enums from workflows for consistency
from phone_agent.industry.handwerk.workflows import (
    TradeCategory,
    UrgencyLevel,
)


@dataclass
class JobIssue:
    """Individual job issue with attributes."""

    description: str
    category: TradeCategory
    severity: int  # 1-10
    location: str | None = None
    duration_hours: float | None = None
    is_recurring: bool = False
    affects_safety: bool = False
    affects_habitability: bool = False
    property_damage_risk: bool = False
    customer_attempted_fix: bool = False

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "description": self.description,
            "category": self.category.value,
            "severity": self.severity,
            "location": self.location,
            "duration_hours": self.duration_hours,
            "is_recurring": self.is_recurring,
            "affects_safety": self.affects_safety,
            "affects_habitability": self.affects_habitability,
            "property_damage_risk": self.property_damage_risk,
            "customer_attempted_fix": self.customer_attempted_fix,
        }


@dataclass
class CustomerContext:
    """Customer information for triage context."""

    property_type: str | None = None  # "apartment", "house", "commercial"
    is_renter: bool = False
    is_owner: bool = True
    has_small_children: bool = False
    has_elderly: bool = False
    has_disabled: bool = False
    floor_level: int | None = None  # For accessibility
    has_pets: bool = False
    # Commercial flag for business customers
    is_commercial: bool = False
    # Alternative naming (is_elderly alias)
    is_elderly: bool | None = None

    def __post_init__(self):
        """Handle alternative parameter names."""
        # Support both is_elderly and has_elderly
        if self.is_elderly is not None:
            self.has_elderly = self.is_elderly

    def calculate_risk_multiplier(self) -> float:
        """Calculate risk multiplier based on customer factors."""
        multiplier = 1.0

        # Vulnerable occupants increase priority
        if self.has_small_children:
            multiplier *= 1.3
        if self.has_elderly:
            multiplier *= 1.2
        if self.has_disabled:
            multiplier *= 1.2

        # Commercial customers may have higher urgency for business impact
        if self.is_commercial:
            multiplier *= 1.1

        # High floor without elevator is more urgent for some issues
        if self.floor_level and self.floor_level > 3:
            multiplier *= 1.1

        return min(multiplier, 2.0)  # Cap at 2x


@dataclass
class TriageResult:
    """Result of triage assessment."""

    urgency: UrgencyLevel
    risk_score: float  # 0-100
    primary_issue: str
    category: TradeCategory
    recommended_action: str
    max_response_hours: int | None
    requires_immediate_callback: bool = False
    requires_emergency_dispatch: bool = False
    safety_instructions: list[str] = field(default_factory=list)
    assessment_notes: list[str] = field(default_factory=list)
    timestamp: datetime = field(default_factory=datetime.now)

    @property
    def is_emergency(self) -> bool:
        """Check if this is an emergency requiring immediate response."""
        return self.urgency in [UrgencyLevel.EMERGENCY, UrgencyLevel.SICHERHEIT]

    @property
    def trade_category(self) -> TradeCategory:
        """Alias for category (for backward compatibility)."""
        return self.category

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "urgency": self.urgency.value,
            "risk_score": self.risk_score,
            "primary_issue": self.primary_issue,
            "category": self.category.value,
            "recommended_action": self.recommended_action,
            "max_response_hours": self.max_response_hours,
            "requires_immediate_callback": self.requires_immediate_callback,
            "requires_emergency_dispatch": self.requires_emergency_dispatch,
            "safety_instructions": self.safety_instructions,
            "assessment_notes": self.assessment_notes,
            "timestamp": self.timestamp.isoformat(),
            "is_emergency": self.is_emergency,
        }


# Emergency patterns (always escalate immediately)
EMERGENCY_PATTERNS: dict[str, list[str]] = {
    "gas_leak": [
        "gasgeruch", "gasleck", "gas riecht", "gasaustritt", "gas strömt",
        "riecht nach gas", "zischen gas", "gaswarnmelder",
    ],
    "water_main_break": [
        "wasserrohrbruch", "rohr geplatzt", "rohr ist geplatzt", "wasser spritzt",
        "hauptleitung", "überschwemmung", "wasser läuft unkontrolliert",
    ],
    "electrical_fire": [
        "kabel brennt", "steckdose raucht", "elektrobrand", "kurzschluss",
        "funken sprühen", "qualm steckdose", "brandgeruch elektrik",
        "kurzschluss mit funken", "brennt am stromkasten",
    ],
    "structural_danger": [
        "decke stürzt", "einsturz", "riss wand groß",
        "statik gefahr", "wand bewegt",
    ],
    "locked_in_danger": [
        "kind eingesperrt", "baby allein", "herd an eingesperrt",
        "person eingeschlossen gefahr", "hilfe eingesperrt",
    ],
}

# Very urgent patterns (response < 2 hours)
VERY_URGENT_PATTERNS: dict[str, list[str]] = {
    "no_heating_cold": [
        "keine heizung", "heizung aus", "frieren", "kalt wohnung",
        "heizung komplett ausgefallen", "heizung ist ausgefallen",
        "heizung ausgefallen", "eiskalt", "heizung defekt",
    ],
    "major_water_leak": [
        "wasser tropft stark", "großes leck", "überschwemmt",
        "keller unter wasser",
    ],
    "no_power": [
        "kein strom komplett", "stromausfall haus",
        "fi lässt sich nicht einschalten",
    ],
    "locked_out": [
        "ausgesperrt", "schlüssel drinnen", "tür zugefallen",
        "nicht mehr reinkommen",
    ],
}

# Urgent patterns (same day)
URGENT_PATTERNS: dict[str, list[str]] = {
    "toilet_blocked": [
        "toilette verstopft", "wc verstopft", "klo geht nicht",
        "abfluss verstopft", "komplett verstopft",
    ],
    "no_hot_water": [
        "kein warmwasser", "boiler kaputt", "therme defekt",
        "durchlauferhitzer funktioniert nicht",
    ],
    "heating_problems": [
        "heizung funktioniert nicht richtig", "heizung macht geräusche",
        "heizkörper wird nicht warm",
    ],
    "electrical_issues": [
        "steckdose funktioniert nicht", "sicherung fliegt raus",
        "fi schalter",
    ],
}

# German issue synonyms for NLU
ISSUE_SYNONYMS: dict[str, list[str]] = {
    "verstopfung": ["verstopft", "dicht", "geht nicht ab", "staut"],
    "undicht": ["tropft", "leckt", "feucht", "nass", "wasser kommt raus"],
    "defekt": ["kaputt", "funktioniert nicht", "geht nicht", "ausgefallen"],
    "geräusch": ["macht lärm", "quietscht", "brummt", "klopft", "pfeift"],
    "geruch": ["stinkt", "riecht", "geruch", "gestank"],
}

# Category detection keywords (using TradeCategory from workflows.py)
CATEGORY_KEYWORDS: dict[TradeCategory, list[str]] = {
    TradeCategory.SHK: [
        # Sanitär (Plumbing)
        "wasser", "rohr", "abfluss", "toilette", "wc", "waschbecken",
        "spüle", "siphon", "wasserhahn", "armatur", "dusche", "badewanne",
        # Heizung (Heating)
        "heizung", "heizkörper", "therme", "gastherme", "kessel",
        "brenner", "thermostat", "warmwasser", "boiler", "fußbodenheizung",
        # Klima (Climate)
        "klima", "klimaanlage", "lüftung", "belüftung", "kühlung",
    ],
    TradeCategory.ELEKTRO: [
        "strom", "steckdose", "schalter", "licht", "lampe", "sicherung",
        "fi", "kabel", "leitung", "elektrisch",
    ],
    TradeCategory.SCHLOSSER: [
        "schlüssel", "schloss", "tür", "ausgesperrt", "eingesperrt",
        "aufschließen", "zylinder", "schließanlage",
    ],
    TradeCategory.DACHDECKER: [
        "dach", "ziegel", "dachrinne", "regenrinne", "schornstein",
        "dachfenster", "dachstuhl", "undicht dach",
    ],
    TradeCategory.MALER: [
        "streichen", "farbe", "tapete", "wand", "anstrich",
        "lackieren", "schimmel wand",
    ],
    TradeCategory.TISCHLER: [
        "holz", "möbel", "schrank", "tür holz", "fenster holz",
        "parkett", "laminat", "treppe",
    ],
    TradeCategory.BAU: [
        "beton", "maurer", "estrich", "fundament", "mauer",
        "putz", "fassade",
    ],
}


class TriageEngine:
    """Intelligent triage engine for job assessment."""

    def __init__(self):
        """Initialize triage engine."""
        self._emergency_patterns = EMERGENCY_PATTERNS
        self._very_urgent_patterns = VERY_URGENT_PATTERNS
        self._urgent_patterns = URGENT_PATTERNS
        self._issue_synonyms = ISSUE_SYNONYMS
        self._category_keywords = CATEGORY_KEYWORDS

    def assess(
        self,
        issues: list[JobIssue],
        customer: CustomerContext | None = None,
        free_text: str | None = None,
    ) -> TriageResult:
        """
        Perform triage assessment.

        Args:
            issues: List of issues reported
            customer: Customer context if available
            free_text: Free-text description for NLU analysis

        Returns:
            TriageResult with urgency and recommendations
        """
        customer = customer or CustomerContext()
        emergency_found: list[str] = []
        safety_instructions: list[str] = []
        assessment_notes: list[str] = []

        # Check free text for emergency patterns
        if free_text:
            text_lower = free_text.lower()

            # Check emergency patterns
            for pattern_name, keywords in self._emergency_patterns.items():
                for keyword in keywords:
                    if keyword in text_lower:
                        emergency_found.append(f"{pattern_name}: {keyword}")

            # Add safety instructions for emergencies
            if "gas" in text_lower:
                safety_instructions.append(
                    "Verlassen Sie sofort das Gebäude! Keine Lichtschalter betätigen!"
                )
            if "wasserrohrbruch" in text_lower or "rohr geplatzt" in text_lower:
                safety_instructions.append(
                    "Drehen Sie den Hauptwasserhahn zu!"
                )
            if "kabel brennt" in text_lower or "steckdose raucht" in text_lower:
                safety_instructions.append(
                    "Schalten Sie die Hauptsicherung aus! Berühren Sie nichts!"
                )

        # If emergency found, return immediately
        if emergency_found:
            category = self._detect_category(free_text or "")
            return TriageResult(
                urgency=UrgencyLevel.SICHERHEIT,
                risk_score=100.0,
                primary_issue=emergency_found[0].split(":")[0],
                category=category,
                recommended_action="NOTFALL! Sofortige Maßnahmen erforderlich. Techniker wird umgehend entsandt.",
                max_response_hours=0,
                requires_immediate_callback=True,
                requires_emergency_dispatch=True,
                safety_instructions=safety_instructions,
                assessment_notes=["Notfall erkannt - sofortige Reaktion erforderlich"],
            )

        # Check very urgent patterns
        very_urgent_found = False
        if free_text:
            text_lower = free_text.lower()
            for pattern_name, keywords in self._very_urgent_patterns.items():
                for keyword in keywords:
                    if keyword in text_lower:
                        very_urgent_found = True
                        assessment_notes.append(f"Sehr dringend: {pattern_name}")
                        break
                if very_urgent_found:
                    break

        if very_urgent_found:
            category = self._detect_category(free_text or "")
            return TriageResult(
                urgency=UrgencyLevel.DRINGEND,
                risk_score=85.0,
                primary_issue=assessment_notes[0] if assessment_notes else "Dringendes Problem",
                category=category,
                recommended_action="Sehr dringend! Techniker wird innerhalb von 2 Stunden entsandt.",
                max_response_hours=2,
                requires_immediate_callback=True,
                requires_emergency_dispatch=False,
                safety_instructions=safety_instructions,
                assessment_notes=assessment_notes,
            )

        # Check urgent patterns
        urgent_found = False
        if free_text:
            text_lower = free_text.lower()
            for pattern_name, keywords in self._urgent_patterns.items():
                for keyword in keywords:
                    if keyword in text_lower:
                        urgent_found = True
                        assessment_notes.append(f"Dringend: {pattern_name}")
                        break
                if urgent_found:
                    break

        # Calculate base risk score from issues
        base_score = 0.0
        primary_issue = "Allgemeine Anfrage"
        category = TradeCategory.ALLGEMEIN

        # If free text was analyzed, assign base score based on patterns found
        if very_urgent_found:
            base_score = 40.0
        elif urgent_found:
            base_score = 30.0
        elif free_text:
            # Minimum base score when analyzing free text
            base_score = 20.0

        if issues:
            # Weight by severity
            severity_scores = [i.severity for i in issues]
            base_score += sum(severity_scores) / len(severity_scores) * 10

            # Find most severe issue
            most_severe = max(issues, key=lambda i: i.severity)
            primary_issue = most_severe.description
            category = most_severe.category

            # Add modifiers
            for issue in issues:
                if issue.affects_safety:
                    base_score += 20
                    assessment_notes.append(f"Sicherheitsrelevant: {issue.description}")
                if issue.affects_habitability:
                    base_score += 15
                    assessment_notes.append("Beeinträchtigt Wohnbarkeit")
                if issue.property_damage_risk:
                    base_score += 10
                    assessment_notes.append("Gefahr von Sachschäden")
                if issue.is_recurring:
                    base_score += 5
                    assessment_notes.append("Wiederkehrendes Problem")

        # Detect category from free text if not from issues
        if category == TradeCategory.ALLGEMEIN and free_text:
            category = self._detect_category(free_text)

        # Apply customer risk multiplier
        risk_multiplier = customer.calculate_risk_multiplier()
        final_score = min(base_score * risk_multiplier, 99.0)

        if risk_multiplier > 1.0:
            assessment_notes.append(f"Risikohaushalt (Faktor: {risk_multiplier:.1f})")

        # Determine urgency level
        if urgent_found or final_score >= 70:
            urgency = UrgencyLevel.DRINGEND
            max_hours = 8
            action = "Dringender Einsatz heute erforderlich."
        elif final_score >= 50:
            urgency = UrgencyLevel.NORMAL
            max_hours = 72
            action = "Termin in den nächsten 1-3 Tagen möglich."
        else:
            urgency = UrgencyLevel.ROUTINE
            max_hours = None
            action = "Flexibler Termin nach Vereinbarung."

        return TriageResult(
            urgency=urgency,
            risk_score=round(final_score, 1),
            primary_issue=primary_issue,
            category=category,
            recommended_action=action,
            max_response_hours=max_hours,
            requires_immediate_callback=urgency == UrgencyLevel.DRINGEND,
            requires_emergency_dispatch=False,
            safety_instructions=safety_instructions,
            assessment_notes=assessment_notes,
        )

    def _detect_category(self, text: str) -> TradeCategory:
        """Detect issue category from text."""
        text_lower = text.lower()

        best_category = TradeCategory.ALLGEMEIN
        best_count = 0

        for category, keywords in self._category_keywords.items():
            count = sum(1 for keyword in keywords if keyword in text_lower)
            if count > best_count:
                best_count = count
                best_category = category

        return best_category

    def extract_issues_from_text(self, text: str) -> list[JobIssue]:
        """
        Extract job issues from free-text description using NLU.

        Args:
            text: Customer's description in German

        Returns:
            List of identified issues
        """
        text_lower = text.lower()
        found_issues: list[JobIssue] = []

        # Detect category
        category = self._detect_category(text)

        # Extract issue characteristics
        severity = self._estimate_severity(text_lower)
        affects_safety = any(
            keyword in text_lower
            for keywords in self._emergency_patterns.values()
            for keyword in keywords
        )
        affects_habitability = any(
            word in text_lower
            for word in ["unbewohnbar", "nicht nutzbar", "kein wasser", "keine heizung", "kein strom"]
        )
        property_damage_risk = any(
            word in text_lower
            for word in ["wasserschaden", "schimmel", "feucht", "nass werden"]
        )

        # Try to extract location
        location = self._extract_location(text_lower)

        # Create issue
        found_issues.append(JobIssue(
            description=text[:200],  # Truncate long descriptions
            category=category,
            severity=severity,
            location=location,
            affects_safety=affects_safety,
            affects_habitability=affects_habitability,
            property_damage_risk=property_damage_risk,
        ))

        return found_issues

    def _estimate_severity(self, text: str) -> int:
        """Estimate issue severity from context."""
        # Default severity
        severity = 5

        # High severity indicators
        high_words = [
            "dringend", "notfall", "sofort", "gefährlich",
            "komplett", "total", "gar nicht", "überhaupt nicht",
        ]
        for word in high_words:
            if word in text:
                severity = 8
                break

        # Low severity indicators
        low_words = [
            "manchmal", "ab und zu", "leicht", "bisschen",
            "klein", "gelegentlich",
        ]
        for word in low_words:
            if word in text:
                severity = 3
                break

        return severity

    def _extract_location(self, text: str) -> str | None:
        """Extract location from text."""
        locations = [
            "küche", "bad", "badezimmer", "wohnzimmer", "schlafzimmer",
            "keller", "dachboden", "flur", "garten", "garage",
            "toilette", "gäste-wc", "waschküche", "heizungsraum",
        ]

        for location in locations:
            if location in text:
                return location.capitalize()

        # Try to extract floor
        floor_match = re.search(r'(\d+)\.\s*(etage|stock|og|obergeschoss)', text)
        if floor_match:
            return f"{floor_match.group(1)}. Etage"

        return None


# Singleton instance
_triage_engine: TriageEngine | None = None


def get_triage_engine() -> TriageEngine:
    """Get or create triage engine singleton."""
    global _triage_engine
    if _triage_engine is None:
        _triage_engine = TriageEngine()
    return _triage_engine
