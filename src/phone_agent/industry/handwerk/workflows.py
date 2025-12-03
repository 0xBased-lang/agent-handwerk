"""Handwerk (Trades) basic triage workflows.

Simple keyword-based job classification for quick urgency assessment.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


class UrgencyLevel(str, Enum):
    """Urgency levels for job requests."""

    # German names (primary)
    SICHERHEIT = "sicherheit"   # Safety-critical: Gas leak, electrical fire
    DRINGEND = "dringend"        # Urgent: Same day (heating failure, blocked toilet)
    NORMAL = "normal"            # Standard: 1-3 days (repairs, installations)
    ROUTINE = "routine"          # Routine: Flexible (maintenance, inspections)

    # English aliases (for advanced triage compatibility)
    EMERGENCY = "emergency"         # Same as SICHERHEIT
    VERY_URGENT = "very_urgent"     # < 2 hours response
    URGENT = "urgent"               # Same day response
    STANDARD = "standard"           # 1-3 days


class TradeCategory(str, Enum):
    """Trade categories (Gewerke)."""

    SHK = "shk"                  # Sanitär, Heizung, Klima
    ELEKTRO = "elektro"          # Electrical
    SCHLOSSER = "schlosser"      # Locksmith
    DACHDECKER = "dachdecker"    # Roofing
    MALER = "maler"              # Painting
    TISCHLER = "tischler"        # Carpentry
    BAU = "bau"                  # Construction
    ALLGEMEIN = "allgemein"      # General (German)
    GENERAL = "general"          # General (English alias)


@dataclass
class TriageResult:
    """Result of basic triage assessment."""

    level: UrgencyLevel
    category: TradeCategory
    confidence: float
    matched_keywords: list[str]
    recommended_action: str

    @property
    def urgency(self) -> UrgencyLevel:
        """Alias for level (compatibility)."""
        return self.level

    @property
    def trade_category(self) -> TradeCategory:
        """Alias for category (compatibility)."""
        return self.category

    @property
    def is_emergency(self) -> bool:
        """Check if this is an emergency."""
        return self.level == UrgencyLevel.SICHERHEIT

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "level": self.level.value,
            "category": self.category.value,
            "confidence": self.confidence,
            "matched_keywords": self.matched_keywords,
            "recommended_action": self.recommended_action,
        }


# Safety-critical keywords (SICHERHEIT) - always escalate
SICHERHEIT_KEYWORDS: list[str] = [
    # Gas emergencies
    "gasgeruch", "gasleck", "gas riecht", "gasaustritt", "gas strömt",
    "riecht nach gas", "nach gas", "zischen gas", "gaswarnmelder", "gasalarm",
    # Water main emergencies
    "wasserrohrbruch", "rohr geplatzt", "rohr ist geplatzt", "wasser spritzt",
    "hauptleitung geplatzt", "überschwemmung akut",
    # Electrical emergencies
    "kabel brennt", "stromschlag", "kurzschluss gefahr", "kurzschluss mit funken",
    "steckdose raucht", "elektrobrand", "funken sprühen", "brennt am stromkasten",
    "kabel schmilzt", "brandgeruch steckdose", "kurzschluss",
    # Structural emergencies
    "decke stürzt", "einsturz", "wand bricht",
    # Safety-critical lockouts
    "kind eingesperrt", "baby allein", "herd an eingesperrt",
    "person eingeschlossen gefahr",
]

# Urgent keywords (DRINGEND) - same day service
DRINGEND_KEYWORDS: list[str] = [
    # Plumbing urgent
    "toilette verstopft", "wc verstopft", "klo verstopft", "komplett verstopft",
    "abfluss verstopft", "rohrverstopfung",
    "wasser tropft stark", "undicht stark",
    "kein wasser", "wasserhahn kaputt",
    # Heating urgent
    "heizung ausgefallen", "heizung defekt", "keine heizung",
    "heizkessel kaputt", "kalt in wohnung", "frieren",
    "kein warmwasser", "warmwasser kaputt", "boiler defekt",
    "therme defekt", "durchlauferhitzer kaputt",
    # Locksmith urgent
    "ausgesperrt", "schlüssel vergessen", "tür klemmt",
    "schloss kaputt", "einbruch", "aufgebrochen",
    "schlüssel abgebrochen", "nicht aufschließen",
    # Electrical urgent
    "strom weg", "kein strom", "sicherung raus",
    "fi schalter", "stromausfall teilweise",
    # General urgent
    "dringend", "notfall", "sofort", "heute noch",
    "schnellstmöglich", "eilig",
]

# Normal keywords (NORMAL) - 1-3 days
NORMAL_KEYWORDS: list[str] = [
    # General repairs
    "reparatur", "reparieren", "defekt", "kaputt",
    "funktioniert nicht", "geht nicht", "macht geräusche",
    # Installations
    "einbauen", "installieren", "montieren", "anschließen",
    "austauschen", "erneuern", "ersetzen",
    # Specific issues
    "tropft", "undicht", "leckt", "klemmt",
    "wackelt", "locker", "quietscht",
    # Projects
    "umbauen", "renovieren", "sanieren",
]

# Routine keywords (ROUTINE) - flexible scheduling
ROUTINE_KEYWORDS: list[str] = [
    # Maintenance
    "wartung", "inspektion", "überprüfung", "kontrolle",
    "service", "pflege", "reinigung",
    # Quotes and consultations
    "kostenvoranschlag", "angebot", "preisanfrage",
    "beratung", "frage", "information",
    "besichtigung", "aufmaß",
    # Preventive
    "vorsorge", "check", "prüfung",
]

# Trade category keywords
SHK_KEYWORDS: list[str] = [
    "heizung", "sanitär", "wasser", "rohr", "abfluss",
    "klima", "lüftung", "warmwasser", "boiler", "therme",
    "heizkörper", "badezimmer", "dusche", "wasserhahn",
    "toilette", "wc", "waschbecken", "spüle", "siphon",
    "gastherme", "ölheizung", "wärmepumpe", "fußbodenheizung",
]

ELEKTRO_KEYWORDS: list[str] = [
    "strom", "elektrik", "elektrisch", "steckdose", "schalter",
    "sicherung", "kabel", "lampe", "licht", "fi-schalter",
    "zähler", "kurzschluss", "elektriker", "leitung",
    "verteilung", "sicherungskasten", "dimmer",
]

SCHLOSSER_KEYWORDS: list[str] = [
    "schlüssel", "schloss", "tür", "eingesperrt", "ausgesperrt",
    "aufschließen", "schließanlage", "tresor", "zylinder",
    "sicherheitsschloss", "türöffnung", "schlüsseldienst",
]

DACHDECKER_KEYWORDS: list[str] = [
    "dach", "ziegel", "dachrinne", "undicht dach", "sturm dach",
    "dachfenster", "schornstein", "dachstuhl", "dachziegel",
    "flachdach", "dachpappe", "regenrinne", "fallrohr",
]

MALER_KEYWORDS: list[str] = [
    "streichen", "tapete", "farbe", "anstrich", "lackieren",
    "schimmel wand", "feuchtigkeit wand", "tapezieren",
    "putz", "verputzen", "spachteln", "grundierung",
]

TISCHLER_KEYWORDS: list[str] = [
    "holz", "möbel", "schrank", "tür holz", "fenster holz",
    "treppe holz", "parkett", "laminat", "einbauschrank",
    "küche montage", "zimmertür",
]

BAU_KEYWORDS: list[str] = [
    "wand", "decke", "boden", "treppe", "fenster",
    "fassade", "putz", "beton", "maurer", "estrich",
    "fundament", "mauer", "ziegel",
]

# Recommended actions for each urgency level
URGENCY_ACTIONS: dict[UrgencyLevel, str] = {
    UrgencyLevel.SICHERHEIT: "NOTFALL! Sofortige Maßnahmen erforderlich. Bei Gasgeruch: Gebäude verlassen, 112 rufen!",
    UrgencyLevel.DRINGEND: "Dringender Einsatz heute noch erforderlich. Techniker wird schnellstmöglich geschickt.",
    UrgencyLevel.NORMAL: "Regulärer Termin in den nächsten 1-3 Tagen möglich.",
    UrgencyLevel.ROUTINE: "Flexibler Termin möglich. Wir finden einen passenden Zeitraum.",
}


def detect_trade_category(text: str) -> TradeCategory:
    """
    Detect trade category from text.

    Args:
        text: Input text in German

    Returns:
        Detected trade category
    """
    text_lower = text.lower()

    category_keywords = [
        (TradeCategory.SHK, SHK_KEYWORDS),
        (TradeCategory.ELEKTRO, ELEKTRO_KEYWORDS),
        (TradeCategory.SCHLOSSER, SCHLOSSER_KEYWORDS),
        (TradeCategory.DACHDECKER, DACHDECKER_KEYWORDS),
        (TradeCategory.MALER, MALER_KEYWORDS),
        (TradeCategory.TISCHLER, TISCHLER_KEYWORDS),
        (TradeCategory.BAU, BAU_KEYWORDS),
    ]

    best_category = TradeCategory.ALLGEMEIN
    best_count = 0

    for category, keywords in category_keywords:
        count = sum(1 for keyword in keywords if keyword in text_lower)
        if count > best_count:
            best_count = count
            best_category = category

    return best_category


def perform_triage(text: str) -> TriageResult:
    """
    Perform basic triage on job request text.

    Args:
        text: Job request description in German

    Returns:
        TriageResult with urgency level and category
    """
    text_lower = text.lower()
    matched_keywords: list[str] = []

    # Check urgency levels in order of priority
    # 1. Safety-critical (highest priority)
    for keyword in SICHERHEIT_KEYWORDS:
        if keyword in text_lower:
            matched_keywords.append(keyword)

    if matched_keywords:
        return TriageResult(
            level=UrgencyLevel.SICHERHEIT,
            category=detect_trade_category(text),
            confidence=0.95,
            matched_keywords=matched_keywords,
            recommended_action=URGENCY_ACTIONS[UrgencyLevel.SICHERHEIT],
        )

    # 2. Urgent
    for keyword in DRINGEND_KEYWORDS:
        if keyword in text_lower:
            matched_keywords.append(keyword)

    if matched_keywords:
        return TriageResult(
            level=UrgencyLevel.DRINGEND,
            category=detect_trade_category(text),
            confidence=0.85,
            matched_keywords=matched_keywords,
            recommended_action=URGENCY_ACTIONS[UrgencyLevel.DRINGEND],
        )

    # 3. Normal
    for keyword in NORMAL_KEYWORDS:
        if keyword in text_lower:
            matched_keywords.append(keyword)

    if matched_keywords:
        return TriageResult(
            level=UrgencyLevel.NORMAL,
            category=detect_trade_category(text),
            confidence=0.80,
            matched_keywords=matched_keywords,
            recommended_action=URGENCY_ACTIONS[UrgencyLevel.NORMAL],
        )

    # 4. Routine
    for keyword in ROUTINE_KEYWORDS:
        if keyword in text_lower:
            matched_keywords.append(keyword)

    if matched_keywords:
        return TriageResult(
            level=UrgencyLevel.ROUTINE,
            category=detect_trade_category(text),
            confidence=0.75,
            matched_keywords=matched_keywords,
            recommended_action=URGENCY_ACTIONS[UrgencyLevel.ROUTINE],
        )

    # Default: Normal with low confidence
    return TriageResult(
        level=UrgencyLevel.NORMAL,
        category=detect_trade_category(text),
        confidence=0.50,
        matched_keywords=[],
        recommended_action=URGENCY_ACTIONS[UrgencyLevel.NORMAL],
    )


def is_emergency(text: str) -> bool:
    """
    Quick check if text indicates an emergency.

    Args:
        text: Input text in German

    Returns:
        True if emergency keywords detected
    """
    text_lower = text.lower()
    return any(keyword in text_lower for keyword in SICHERHEIT_KEYWORDS)
