"""Advanced triage system for professional services.

Implements intelligent lead qualification and routing for:
- Lawyers, tax consultants, auditors
- Consultants, architects
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class LeadPriority(str, Enum):
    """Lead priority levels."""

    HOT = "hot"  # Immediate action, high value
    WARM = "warm"  # Good potential, follow up soon
    COOL = "cool"  # General inquiry, standard follow-up
    COLD = "cold"  # Low priority, may not fit


class QualificationStatus(str, Enum):
    """Lead qualification status."""

    QUALIFIED = "qualified"  # Fits our services, ready for advisor
    PARTIALLY_QUALIFIED = "partially_qualified"  # Needs more info
    NOT_QUALIFIED = "not_qualified"  # Doesn't fit our services
    NEEDS_REVIEW = "needs_review"  # Complex, needs human review


class ClientType(str, Enum):
    """Type of client/prospect."""

    INDIVIDUAL = "individual"  # Private person
    SMALL_BUSINESS = "small_business"  # <10 employees
    MEDIUM_BUSINESS = "medium_business"  # 10-250 employees
    LARGE_BUSINESS = "large_business"  # >250 employees
    STARTUP = "startup"
    NONPROFIT = "nonprofit"


@dataclass
class ContactContext:
    """Contact information for lead qualification."""

    name: str | None = None
    phone: str | None = None
    email: str | None = None
    company: str | None = None
    position: str | None = None
    client_type: ClientType = ClientType.INDIVIDUAL

    # Lead source
    referral_source: str | None = None  # How they found us
    referred_by: str | None = None  # Specific referrer

    # Engagement
    is_decision_maker: bool = False
    previous_contact: bool = False
    existing_client: bool = False

    def calculate_contact_score(self) -> int:
        """Calculate contact quality score."""
        score = 0

        # Contact completeness
        if self.name:
            score += 10
        if self.phone:
            score += 10
        if self.email:
            score += 10
        if self.company:
            score += 15

        # Client type value
        type_scores = {
            ClientType.LARGE_BUSINESS: 25,
            ClientType.MEDIUM_BUSINESS: 20,
            ClientType.SMALL_BUSINESS: 15,
            ClientType.STARTUP: 12,
            ClientType.NONPROFIT: 10,
            ClientType.INDIVIDUAL: 5,
        }
        score += type_scores.get(self.client_type, 5)

        # Decision maker bonus
        if self.is_decision_maker:
            score += 15

        # Referral bonus
        if self.referred_by:
            score += 20
        elif self.referral_source:
            score += 10

        return min(score, 100)


@dataclass
class InquiryContext:
    """Context about the client's inquiry."""

    service_area: str | None = None
    specific_topic: str | None = None
    description: str | None = None

    # Urgency factors
    has_deadline: bool = False
    deadline_date: str | None = None
    court_date: bool = False
    tax_deadline: bool = False

    # Complexity indicators
    estimated_complexity: str = "standard"  # simple, standard, complex
    estimated_value: str = "standard"  # low, standard, high

    # History
    previous_attempts: int = 0  # Times they've contacted us
    competitor_contact: bool = False  # Have they talked to competitors?

    def calculate_urgency_score(self) -> int:
        """Calculate urgency score."""
        score = 20  # Base score

        if self.court_date:
            score += 40
        if self.tax_deadline:
            score += 35
        if self.has_deadline:
            score += 25

        # Deadline proximity
        if self.deadline_date:
            try:
                deadline = datetime.strptime(self.deadline_date, "%Y-%m-%d")
                days_until = (deadline - datetime.now()).days
                if days_until <= 1:
                    score += 30
                elif days_until <= 7:
                    score += 20
                elif days_until <= 14:
                    score += 10
            except ValueError:
                pass

        return min(score, 100)


@dataclass
class TriageResult:
    """Result of lead triage assessment."""

    priority: LeadPriority
    qualification: QualificationStatus
    lead_score: int  # 0-100
    urgency_score: int  # 0-100
    contact_score: int  # 0-100

    recommended_action: str
    recommended_advisor: str | None = None
    callback_priority: bool = False
    time_to_respond: str = "24h"  # Target response time

    qualification_notes: list[str] = field(default_factory=list)
    missing_info: list[str] = field(default_factory=list)
    red_flags: list[str] = field(default_factory=list)

    timestamp: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "priority": self.priority.value,
            "qualification": self.qualification.value,
            "lead_score": self.lead_score,
            "urgency_score": self.urgency_score,
            "contact_score": self.contact_score,
            "recommended_action": self.recommended_action,
            "recommended_advisor": self.recommended_advisor,
            "callback_priority": self.callback_priority,
            "time_to_respond": self.time_to_respond,
            "qualification_notes": self.qualification_notes,
            "missing_info": self.missing_info,
            "red_flags": self.red_flags,
            "timestamp": self.timestamp.isoformat(),
        }


# Service configuration
SERVICE_CONFIG = {
    "service_areas": ["legal", "tax", "consulting"],
    "response_times": {
        "hot": "2h",
        "warm": "8h",
        "cool": "24h",
        "cold": "48h",
    },
    "qualification_thresholds": {
        "qualified": 70,
        "partially_qualified": 40,
        "not_qualified": 0,
    },
}


class TriageEngine:
    """Intelligent triage engine for professional services leads."""

    def __init__(self):
        """Initialize triage engine."""
        self._config = SERVICE_CONFIG

    def assess(
        self,
        contact: ContactContext,
        inquiry: InquiryContext,
        free_text: str | None = None,
    ) -> TriageResult:
        """
        Perform lead triage assessment.

        Args:
            contact: Contact context with client info
            inquiry: Inquiry context with request details
            free_text: Free-text message for analysis

        Returns:
            TriageResult with qualification and recommendations
        """
        notes: list[str] = []
        missing: list[str] = []
        red_flags: list[str] = []

        # Calculate scores
        contact_score = contact.calculate_contact_score()
        urgency_score = inquiry.calculate_urgency_score()

        # Extract additional info from free text
        if free_text:
            self._extract_additional_info(free_text, contact, inquiry)

        # Check for missing critical info
        if not contact.name:
            missing.append("Name")
        if not contact.phone and not contact.email:
            missing.append("Kontaktdaten")
        if not inquiry.service_area:
            missing.append("Fachgebiet")

        # Check for red flags
        if inquiry.previous_attempts >= 3:
            red_flags.append("Mehrfache Kontaktversuche ohne Abschluss")
        if inquiry.competitor_contact:
            notes.append("Hat bereits mit Wettbewerber gesprochen")

        # Calculate overall lead score
        lead_score = self._calculate_lead_score(contact_score, urgency_score, inquiry)

        # Determine priority
        priority = self._determine_priority(lead_score, urgency_score, inquiry)

        # Determine qualification status
        qualification = self._determine_qualification(
            lead_score=lead_score,
            inquiry=inquiry,
            missing_info=missing,
        )

        # Determine recommended action
        action, time_to_respond = self._determine_action(
            priority=priority,
            qualification=qualification,
            contact=contact,
            inquiry=inquiry,
        )

        # Callback priority for urgent cases
        callback_priority = priority == LeadPriority.HOT or urgency_score >= 70

        return TriageResult(
            priority=priority,
            qualification=qualification,
            lead_score=lead_score,
            urgency_score=urgency_score,
            contact_score=contact_score,
            recommended_action=action,
            recommended_advisor=self._suggest_advisor(inquiry),
            callback_priority=callback_priority,
            time_to_respond=time_to_respond,
            qualification_notes=notes,
            missing_info=missing,
            red_flags=red_flags,
        )

    def _extract_additional_info(
        self,
        text: str,
        contact: ContactContext,
        inquiry: InquiryContext,
    ) -> None:
        """Extract additional information from free text."""
        text_lower = text.lower()

        # Detect decision maker
        if any(w in text_lower for w in ["geschäftsführer", "inhaber", "ceo", "vorstand"]):
            contact.is_decision_maker = True
            contact.position = "Geschäftsführung"
        elif any(w in text_lower for w in ["leiter", "abteilungsleiter", "manager"]):
            contact.is_decision_maker = True
            contact.position = "Führungskraft"

        # Detect company size
        if any(w in text_lower for w in ["großunternehmen", "konzern", "ag"]):
            contact.client_type = ClientType.LARGE_BUSINESS
        elif any(w in text_lower for w in ["mittelstand", "mittelständisch"]):
            contact.client_type = ClientType.MEDIUM_BUSINESS
        elif any(w in text_lower for w in ["startup", "gründung", "neugründung"]):
            contact.client_type = ClientType.STARTUP
        elif any(w in text_lower for w in ["gmbh", "firma", "unternehmen"]):
            contact.client_type = ClientType.SMALL_BUSINESS

        # Detect urgency keywords
        if any(w in text_lower for w in ["gerichtstermin", "ladung", "vorladung"]):
            inquiry.court_date = True
            inquiry.has_deadline = True
        if any(w in text_lower for w in ["steuererklärung", "abgabefrist", "finanzamt"]):
            inquiry.tax_deadline = True
            inquiry.has_deadline = True

        # Detect complexity
        if any(w in text_lower for w in ["komplex", "kompliziert", "schwierig", "umfangreich"]):
            inquiry.estimated_complexity = "complex"
        elif any(w in text_lower for w in ["einfach", "schnell", "kurz"]):
            inquiry.estimated_complexity = "simple"

        # Detect referral
        if any(w in text_lower for w in ["empfohlen", "empfehlung", "bekannter"]):
            contact.referral_source = "Empfehlung"

    def _calculate_lead_score(
        self,
        contact_score: int,
        urgency_score: int,
        inquiry: InquiryContext,
    ) -> int:
        """Calculate overall lead score."""
        # Weighted average
        score = (
            contact_score * 0.4 +
            urgency_score * 0.3 +
            self._value_score(inquiry) * 0.3
        )
        return int(min(score, 100))

    def _value_score(self, inquiry: InquiryContext) -> int:
        """Calculate potential value score."""
        base = 50

        # Complexity adds value
        if inquiry.estimated_complexity == "complex":
            base += 20
        elif inquiry.estimated_complexity == "simple":
            base -= 10

        # Estimated value
        if inquiry.estimated_value == "high":
            base += 25
        elif inquiry.estimated_value == "low":
            base -= 15

        return min(max(base, 0), 100)

    def _determine_priority(
        self, lead_score: int, urgency_score: int, inquiry: InquiryContext | None = None
    ) -> LeadPriority:
        """Determine lead priority from scores."""
        # Critical urgency factors always make it HOT
        if inquiry and (inquiry.court_date or inquiry.tax_deadline):
            return LeadPriority.HOT

        # Combined score with urgency weight
        combined = lead_score * 0.6 + urgency_score * 0.4

        if combined >= 70 or urgency_score >= 75:
            return LeadPriority.HOT
        elif combined >= 50:
            return LeadPriority.WARM
        elif combined >= 30:
            return LeadPriority.COOL
        return LeadPriority.COLD

    def _determine_qualification(
        self,
        lead_score: int,
        inquiry: InquiryContext,
        missing_info: list[str],
    ) -> QualificationStatus:
        """Determine qualification status."""
        thresholds = self._config["qualification_thresholds"]

        # Check if service area matches
        if inquiry.service_area and inquiry.service_area not in self._config["service_areas"]:
            return QualificationStatus.NOT_QUALIFIED

        # Missing critical info
        if len(missing_info) >= 2:
            return QualificationStatus.PARTIALLY_QUALIFIED

        # Score-based qualification
        if lead_score >= thresholds["qualified"]:
            return QualificationStatus.QUALIFIED
        elif lead_score >= thresholds["partially_qualified"]:
            return QualificationStatus.PARTIALLY_QUALIFIED

        return QualificationStatus.NEEDS_REVIEW

    def _determine_action(
        self,
        priority: LeadPriority,
        qualification: QualificationStatus,
        contact: ContactContext,
        inquiry: InquiryContext,
    ) -> tuple[str, str]:
        """Determine recommended action and response time."""
        response_time = self._config["response_times"][priority.value]

        if qualification == QualificationStatus.NOT_QUALIFIED:
            return (
                "Höflich ablehnen und Alternative empfehlen.",
                "24h",
            )

        if priority == LeadPriority.HOT:
            if inquiry.court_date or inquiry.tax_deadline:
                return (
                    "SOFORT: Dringenden Rückruf durch Senior-Berater organisieren.",
                    "2h",
                )
            return (
                "Priorität: Schnellstmöglich Erstberatungstermin anbieten.",
                response_time,
            )

        if priority == LeadPriority.WARM:
            if contact.referred_by:
                return (
                    "Empfehlung: Bevorzugt behandeln und zeitnah Termin anbieten.",
                    "8h",
                )
            return (
                "Standard: Erstberatungstermin innerhalb dieser Woche anbieten.",
                response_time,
            )

        if priority == LeadPriority.COOL:
            return (
                "Normal: In Rückrufliste aufnehmen, innerhalb 24h kontaktieren.",
                response_time,
            )

        return (
            "Niedrig: Bei Kapazität kontaktieren, sonst auf allgemeine Info verweisen.",
            response_time,
        )

    def _suggest_advisor(self, inquiry: InquiryContext) -> str | None:
        """Suggest appropriate advisor based on inquiry."""
        # This would integrate with actual staff database
        advisor_map = {
            "legal": "Rechtsabteilung",
            "tax": "Steuerberatung",
            "consulting": "Unternehmensberatung",
        }
        if inquiry.service_area:
            return advisor_map.get(inquiry.service_area, None)
        return None


# Singleton instance
_triage_engine: TriageEngine | None = None


def get_triage_engine() -> TriageEngine:
    """Get or create triage engine singleton."""
    global _triage_engine
    if _triage_engine is None:
        _triage_engine = TriageEngine()
    return _triage_engine
