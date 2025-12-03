"""Freie Berufe-specific workflows and classification logic.

Implements lead intake handling for German professional services.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from itf_shared import get_logger

log = get_logger(__name__)


class InquiryType(str, Enum):
    """Types of client inquiries."""

    CONSULTATION = "consultation"  # Initial consultation request
    EXISTING_CLIENT = "existing_client"  # Existing client follow-up
    INFORMATION = "information"  # General information request
    CALLBACK = "callback"  # Callback request
    COMPLAINT = "complaint"  # Service complaint
    REFERRAL = "referral"  # Referred by another client


class ServiceArea(str, Enum):
    """Professional service areas."""

    LEGAL = "legal"  # Rechtsanwalt
    TAX = "tax"  # Steuerberater
    AUDIT = "audit"  # Wirtschaftsprüfer
    CONSULTING = "consulting"  # Unternehmensberater
    ARCHITECTURE = "architecture"  # Architekt
    NOTARY = "notary"  # Notar
    GENERAL = "general"  # Allgemein


class UrgencyLevel(str, Enum):
    """Urgency levels for inquiries."""

    CRITICAL = "critical"  # Court deadline, tax filing due
    URGENT = "urgent"  # Within 1 week
    STANDARD = "standard"  # Within 2-4 weeks
    LOW = "low"  # No specific timeline


@dataclass
class InquiryResult:
    """Result of inquiry classification."""

    inquiry_type: InquiryType
    service_area: ServiceArea
    urgency: UrgencyLevel
    reason: str
    action: str
    keywords_matched: list[str]
    confidence: float
    requires_callback: bool = False
    priority_score: int = 50  # 0-100


# Keywords for service area detection
LEGAL_KEYWORDS = [
    # General legal
    "anwalt", "rechtsanwalt", "rechtlich", "juristisch",
    "klage", "gericht", "prozess", "urteil",
    # Specific areas
    "arbeitsrecht", "kündigung", "abfindung",
    "mietrecht", "mieter", "vermieter",
    "familienrecht", "scheidung", "unterhalt", "sorgerecht",
    "erbrecht", "testament", "erbe", "nachlass",
    "verkehrsrecht", "unfall", "bußgeld",
    "strafrecht", "anzeige", "vorladung",
    "vertragsrecht", "vertrag", "agb",
    "gesellschaftsrecht", "gmbh", "gründung",
]

TAX_KEYWORDS = [
    # General tax
    "steuer", "steuererklärung", "finanzamt",
    "steuerberater", "buchhaltung", "bilanz",
    # Specific areas
    "einkommensteuer", "umsatzsteuer", "gewerbesteuer",
    "lohnsteuer", "erbschaftsteuer", "schenkungssteuer",
    "betriebsprüfung", "steuerbescheid", "einspruch",
    "jahresabschluss", "gewinn", "verlust",
]

CONSULTING_KEYWORDS = [
    # General consulting
    "beratung", "berater", "consulting",
    "strategie", "optimierung", "digitalisierung",
    # Specific areas
    "unternehmensberatung", "prozessoptimierung",
    "organisationsberatung", "change management",
    "it-beratung", "projektmanagement",
]

ARCHITECTURE_KEYWORDS = [
    # Architecture
    "architekt", "architektur", "planung",
    "bauantrag", "baugenehmigung", "umbau",
    "neubau", "sanierung", "renovierung",
    "bauplan", "grundriss", "entwurf",
]

# Keywords for urgency detection
URGENT_KEYWORDS = [
    # Legal urgency
    "frist", "termin", "morgen", "diese woche",
    "eilig", "dringend", "sofort", "schnell",
    # Legal deadlines
    "ladung", "zustellung", "einspruchsfrist",
    "klagefrist", "widerspruchsfrist",
    # Tax deadlines
    "abgabefrist", "mahnbescheid", "zwangsgeld",
]

CRITICAL_KEYWORDS = [
    # Legal
    "heute", "gerichtstermin morgen", "verhaftung",
    "einstweilige verfügung", "pfändung",
    # Tax
    "vollstreckung", "kontosperre", "haftbefehl",
]

# Keywords for existing client detection
EXISTING_CLIENT_KEYWORDS = [
    "mandant", "bestehender kunde", "aktenzeichen",
    "bei ihnen", "schon mandant", "laufendes mandat",
    "mein berater", "mein anwalt", "mein steuerberater",
    "nochmal sprechen", "war schon", "kennen mich",
]

CALLBACK_KEYWORDS = [
    "rückruf", "zurückrufen", "ruf zurück",
    "nicht erreicht", "verpasst", "mailbox",
]


def classify_inquiry(message: str) -> InquiryResult:
    """Classify client inquiry based on message content.

    Args:
        message: Client's message/request

    Returns:
        InquiryResult with type, service area, and urgency
    """
    message_lower = message.lower()
    matched_keywords: list[str] = []
    priority_score = 50

    # Check for existing client (high priority routing)
    for keyword in EXISTING_CLIENT_KEYWORDS:
        if keyword in message_lower:
            matched_keywords.append(keyword)

    if matched_keywords:
        return InquiryResult(
            inquiry_type=InquiryType.EXISTING_CLIENT,
            service_area=ServiceArea.GENERAL,
            urgency=UrgencyLevel.STANDARD,
            reason=f"Bestandsmandant erkannt: {', '.join(matched_keywords)}",
            action="Ich verbinde Sie gerne mit Ihrem zuständigen Berater.",
            keywords_matched=matched_keywords,
            confidence=0.85,
            requires_callback=True,
            priority_score=80,
        )

    # Check for callback request
    matched_keywords = []
    for keyword in CALLBACK_KEYWORDS:
        if keyword in message_lower:
            matched_keywords.append(keyword)

    if matched_keywords:
        return InquiryResult(
            inquiry_type=InquiryType.CALLBACK,
            service_area=ServiceArea.GENERAL,
            urgency=UrgencyLevel.STANDARD,
            reason=f"Rückrufwunsch erkannt: {', '.join(matched_keywords)}",
            action="Ich organisiere gerne einen Rückruf. Wann sind Sie erreichbar?",
            keywords_matched=matched_keywords,
            confidence=0.80,
            requires_callback=True,
            priority_score=60,
        )

    # Detect service area
    service_area = ServiceArea.GENERAL
    matched_keywords = []

    for keyword in LEGAL_KEYWORDS:
        if keyword in message_lower:
            matched_keywords.append(keyword)
    if matched_keywords:
        service_area = ServiceArea.LEGAL
        priority_score += 10

    if not matched_keywords:
        for keyword in TAX_KEYWORDS:
            if keyword in message_lower:
                matched_keywords.append(keyword)
        if matched_keywords:
            service_area = ServiceArea.TAX
            priority_score += 10

    if not matched_keywords:
        for keyword in CONSULTING_KEYWORDS:
            if keyword in message_lower:
                matched_keywords.append(keyword)
        if matched_keywords:
            service_area = ServiceArea.CONSULTING

    if not matched_keywords:
        for keyword in ARCHITECTURE_KEYWORDS:
            if keyword in message_lower:
                matched_keywords.append(keyword)
        if matched_keywords:
            service_area = ServiceArea.ARCHITECTURE

    # Detect urgency
    urgency = UrgencyLevel.STANDARD

    for keyword in CRITICAL_KEYWORDS:
        if keyword in message_lower:
            urgency = UrgencyLevel.CRITICAL
            priority_score = min(priority_score + 30, 100)
            matched_keywords.append(keyword)
            break

    if urgency != UrgencyLevel.CRITICAL:
        for keyword in URGENT_KEYWORDS:
            if keyword in message_lower:
                urgency = UrgencyLevel.URGENT
                priority_score = min(priority_score + 15, 100)
                matched_keywords.append(keyword)
                break

    # Determine inquiry type and action
    if matched_keywords:
        return InquiryResult(
            inquiry_type=InquiryType.CONSULTATION,
            service_area=service_area,
            urgency=urgency,
            reason=f"Beratungsanfrage erkannt: {', '.join(matched_keywords[:3])}",
            action=_get_action_for_urgency(urgency),
            keywords_matched=matched_keywords,
            confidence=0.75,
            requires_callback=urgency in [UrgencyLevel.CRITICAL, UrgencyLevel.URGENT],
            priority_score=priority_score,
        )

    # Default to general inquiry
    return InquiryResult(
        inquiry_type=InquiryType.INFORMATION,
        service_area=ServiceArea.GENERAL,
        urgency=UrgencyLevel.LOW,
        reason="Allgemeine Anfrage",
        action="Wie kann ich Ihnen weiterhelfen? Geht es um eine rechtliche oder steuerliche Frage?",
        keywords_matched=[],
        confidence=0.50,
        priority_score=40,
    )


def _get_action_for_urgency(urgency: UrgencyLevel) -> str:
    """Get appropriate action based on urgency."""
    actions = {
        UrgencyLevel.CRITICAL: (
            "Das klingt sehr dringend. Ich versuche sofort, "
            "einen unserer Berater für Sie zu erreichen."
        ),
        UrgencyLevel.URGENT: (
            "Ich verstehe, dass die Zeit drängt. "
            "Lassen Sie mich schauen, wann wir Sie schnellstmöglich beraten können."
        ),
        UrgencyLevel.STANDARD: (
            "Gerne nehme ich Ihre Anfrage auf. "
            "Darf ich Ihnen ein paar Fragen stellen?"
        ),
        UrgencyLevel.LOW: (
            "Vielen Dank für Ihre Anfrage. "
            "Worum geht es bei Ihrem Anliegen?"
        ),
    }
    return actions.get(urgency, actions[UrgencyLevel.STANDARD])


async def get_time_of_day() -> str:
    """Get German greeting based on time of day."""
    from datetime import datetime

    hour = datetime.now().hour

    if hour < 11:
        return "Morgen"
    elif hour < 14:
        return "Tag"
    elif hour < 18:
        return "Nachmittag"
    else:
        return "Abend"


def extract_contact_info(message: str) -> dict[str, Any]:
    """Extract contact information from message.

    Args:
        message: Client message to parse

    Returns:
        Dict with contact fields
    """
    import re

    result: dict[str, Any] = {}
    message_lower = message.lower()

    # Extract phone number
    phone_match = re.search(r'(\+?\d[\d\s/-]{8,}\d)', message)
    if phone_match:
        result["phone"] = phone_match.group(1).replace(" ", "").replace("-", "")

    # Extract email
    email_match = re.search(r'[\w.+-]+@[\w-]+\.[\w.-]+', message)
    if email_match:
        result["email"] = email_match.group(0)

    # Extract name patterns
    name_patterns = [
        r'(?:name ist|heiße|ich bin|spreche mit)\s+([A-ZÄÖÜ][a-zäöüß]+(?:\s+[A-ZÄÖÜ][a-zäöüß]+)?)',
        r'(?:herr|frau)\s+([A-ZÄÖÜ][a-zäöüß]+)',
    ]
    for pattern in name_patterns:
        match = re.search(pattern, message, re.IGNORECASE)
        if match:
            result["name"] = match.group(1).strip()
            break

    # Extract company
    company_patterns = [
        r'(?:firma|unternehmen|gesellschaft|gmbh|ag|kg|ohg)\s+([A-ZÄÖÜ][^\.,!?]+)',
        r'([A-ZÄÖÜ][a-zäöüß]+\s+(?:GmbH|AG|KG|OHG|UG|e\.V\.))',
    ]
    for pattern in company_patterns:
        match = re.search(pattern, message, re.IGNORECASE)
        if match:
            result["company"] = match.group(1).strip()
            break

    return result


def detect_deadline(message: str) -> dict[str, Any]:
    """Detect deadline or time pressure from message.

    Args:
        message: Client message to parse

    Returns:
        Dict with deadline info
    """
    import re
    from datetime import datetime, timedelta

    result: dict[str, Any] = {"has_deadline": False}
    message_lower = message.lower()

    # Check for deadline keywords
    if any(kw in message_lower for kw in ["frist", "termin", "bis zum", "spätestens"]):
        result["has_deadline"] = True

    # Extract specific dates
    date_patterns = [
        r'(\d{1,2})\.(\d{1,2})\.(\d{2,4})',  # DD.MM.YYYY
        r'(\d{1,2})\.\s*(januar|februar|märz|april|mai|juni|juli|august|september|oktober|november|dezember)',
    ]

    for pattern in date_patterns:
        match = re.search(pattern, message_lower)
        if match:
            result["has_deadline"] = True
            result["deadline_text"] = match.group(0)
            break

    # Check for relative time
    today = datetime.now()
    if "heute" in message_lower:
        result["has_deadline"] = True
        result["urgency"] = "today"
        result["deadline_date"] = today.strftime("%Y-%m-%d")
    elif "morgen" in message_lower:
        result["has_deadline"] = True
        result["urgency"] = "tomorrow"
        result["deadline_date"] = (today + timedelta(days=1)).strftime("%Y-%m-%d")
    elif "diese woche" in message_lower:
        result["has_deadline"] = True
        result["urgency"] = "this_week"
    elif "nächste woche" in message_lower:
        result["has_deadline"] = True
        result["urgency"] = "next_week"

    return result


def format_available_slots(slots: list[dict[str, Any]]) -> str:
    """Format available appointment slots for LLM prompt.

    Args:
        slots: List of slot dictionaries with date, time, advisor

    Returns:
        Formatted string for prompt injection
    """
    if not slots:
        return "Leider sind aktuell keine freien Termine verfügbar."

    lines = []
    for slot in slots[:5]:  # Limit to 5 options
        date_str = slot.get("date", "")
        time_str = slot.get("time", "")
        advisor = slot.get("advisor", "")
        slot_type = slot.get("type", "Persönlich")

        if advisor:
            lines.append(f"- {date_str} um {time_str} Uhr bei {advisor} ({slot_type})")
        else:
            lines.append(f"- {date_str} um {time_str} Uhr ({slot_type})")

    return "\n".join(lines)


def calculate_lead_score(
    service_area: ServiceArea,
    urgency: UrgencyLevel,
    has_company: bool,
    is_decision_maker: bool,
    referral_source: str | None = None,
) -> int:
    """Calculate lead quality score.

    Args:
        service_area: Detected service area
        urgency: Urgency level
        has_company: Whether company is provided
        is_decision_maker: Whether caller is decision maker
        referral_source: How they found us

    Returns:
        Score from 0-100
    """
    score = 30  # Base score

    # Service area bonus
    if service_area in [ServiceArea.LEGAL, ServiceArea.TAX]:
        score += 15
    elif service_area == ServiceArea.CONSULTING:
        score += 10

    # Urgency bonus
    urgency_bonus = {
        UrgencyLevel.CRITICAL: 20,
        UrgencyLevel.URGENT: 15,
        UrgencyLevel.STANDARD: 5,
        UrgencyLevel.LOW: 0,
    }
    score += urgency_bonus.get(urgency, 0)

    # Company bonus
    if has_company:
        score += 15

    # Decision maker bonus
    if is_decision_maker:
        score += 10

    # Referral bonus
    if referral_source:
        if referral_source.lower() in ["empfehlung", "referral", "mandant"]:
            score += 15
        else:
            score += 5

    return min(score, 100)
