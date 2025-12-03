"""Advanced gastro triage system.

Implements intelligent reservation handling and guest request routing
for restaurant operations.

Features:
- Multi-factor request classification
- Party size validation
- Special request handling
- No-show risk assessment
- VIP guest recognition
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, time as dt_time
from enum import Enum
from typing import Any


class GuestPriority(str, Enum):
    """Guest priority levels."""

    VIP = "vip"  # Repeat customers, large spenders
    REGULAR = "regular"  # Returning guests
    NEW = "new"  # First-time guests
    GROUP = "group"  # Large party bookings


class RequestUrgency(str, Enum):
    """Urgency levels for requests."""

    IMMEDIATE = "immediate"  # Same-day reservation
    STANDARD = "standard"  # Normal advance booking
    FLEXIBLE = "flexible"  # Information queries


class SpecialRequestType(str, Enum):
    """Types of special requests."""

    ALLERGY = "allergy"
    DIETARY = "dietary"  # Vegetarian, vegan, etc.
    OCCASION = "occasion"  # Birthday, anniversary
    SEATING = "seating"  # Window, terrace, quiet area
    ACCESSIBILITY = "accessibility"  # Wheelchair, etc.
    CHILD = "child"  # High chair, kids menu
    PET = "pet"  # Dog allowed areas


@dataclass
class SpecialRequest:
    """A special request from a guest."""

    request_type: SpecialRequestType
    details: str
    is_critical: bool = False  # True for severe allergies
    can_accommodate: bool = True


@dataclass
class GuestContext:
    """Guest information for reservation context."""

    name: str | None = None
    phone: str | None = None
    email: str | None = None

    # Guest history
    visit_count: int = 0
    last_visit: datetime | None = None
    is_vip: bool = False
    preferred_table: str | None = None

    # Current request
    party_size: int = 2
    preferred_date: str | None = None
    preferred_time: str | None = None

    # Risk factors
    no_show_history: int = 0
    late_cancellation_count: int = 0

    # Special requests
    special_requests: list[SpecialRequest] = field(default_factory=list)
    occasion: str | None = None

    def calculate_priority(self) -> GuestPriority:
        """Calculate guest priority based on history."""
        if self.is_vip or self.visit_count >= 10:
            return GuestPriority.VIP
        elif self.visit_count >= 3:
            return GuestPriority.REGULAR
        elif self.party_size >= 8:
            return GuestPriority.GROUP
        return GuestPriority.NEW

    def calculate_no_show_risk(self) -> float:
        """Calculate risk of no-show (0-1)."""
        risk = 0.1  # Base risk 10%

        # Increase risk based on history
        if self.no_show_history > 0:
            risk += 0.2 * self.no_show_history

        if self.late_cancellation_count > 0:
            risk += 0.1 * self.late_cancellation_count

        # Decrease risk for loyal customers
        if self.visit_count >= 5:
            risk *= 0.5
        elif self.visit_count >= 2:
            risk *= 0.7

        # New customers have slightly higher risk
        if self.visit_count == 0:
            risk += 0.05

        return min(risk, 0.9)  # Cap at 90%


@dataclass
class ReservationSlot:
    """A reservation time slot."""

    date: str
    time: str
    capacity: int
    table_ids: list[str]
    is_peak: bool = False
    notes: str | None = None


@dataclass
class TriageResult:
    """Result of reservation triage assessment."""

    can_accommodate: bool
    guest_priority: GuestPriority
    request_urgency: RequestUrgency
    recommended_slots: list[ReservationSlot]
    special_handling: list[str]
    no_show_risk: float
    requires_deposit: bool
    requires_callback: bool
    response_message: str
    notes: list[str] = field(default_factory=list)
    timestamp: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "can_accommodate": self.can_accommodate,
            "guest_priority": self.guest_priority.value,
            "request_urgency": self.request_urgency.value,
            "recommended_slots": [
                {"date": s.date, "time": s.time, "capacity": s.capacity}
                for s in self.recommended_slots
            ],
            "special_handling": self.special_handling,
            "no_show_risk": self.no_show_risk,
            "requires_deposit": self.requires_deposit,
            "requires_callback": self.requires_callback,
            "response_message": self.response_message,
            "notes": self.notes,
            "timestamp": self.timestamp.isoformat(),
        }


# Restaurant configuration
RESTAURANT_CONFIG = {
    "max_party_size": 12,
    "deposit_threshold_party": 8,  # Require deposit for 8+ guests
    "deposit_threshold_risk": 0.5,  # Require deposit if no-show risk > 50%
    "peak_times": {
        "friday_dinner": (dt_time(19, 0), dt_time(21, 0)),
        "saturday_dinner": (dt_time(18, 30), dt_time(21, 30)),
        "sunday_lunch": (dt_time(12, 0), dt_time(14, 0)),
    },
    "service_hours": {
        "lunch": (dt_time(11, 30), dt_time(14, 30)),
        "dinner": (dt_time(17, 30), dt_time(22, 0)),
        "sunday": (dt_time(11, 30), dt_time(21, 0)),
    },
    "closed_days": [0],  # Monday
}


# Allergy keywords for detection
ALLERGY_KEYWORDS = {
    "glutenfrei": SpecialRequestType.ALLERGY,
    "gluten": SpecialRequestType.ALLERGY,
    "zöliakie": SpecialRequestType.ALLERGY,
    "laktosefrei": SpecialRequestType.ALLERGY,
    "laktose": SpecialRequestType.ALLERGY,
    "milchfrei": SpecialRequestType.ALLERGY,
    "nussallergie": SpecialRequestType.ALLERGY,
    "nussfrei": SpecialRequestType.ALLERGY,
    "erdnuss": SpecialRequestType.ALLERGY,
    "meeresfrüchte": SpecialRequestType.ALLERGY,
    "fisch": SpecialRequestType.ALLERGY,
    "vegetarisch": SpecialRequestType.DIETARY,
    "vegan": SpecialRequestType.DIETARY,
    "halal": SpecialRequestType.DIETARY,
    "koscher": SpecialRequestType.DIETARY,
}

OCCASION_KEYWORDS = {
    "geburtstag": "Geburtstag",
    "jubiläum": "Jubiläum",
    "hochzeitstag": "Hochzeitstag",
    "jahrestag": "Jahrestag",
    "verlobung": "Verlobung",
    "firmenevent": "Firmenevent",
    "geschäftsessen": "Geschäftsessen",
    "abschied": "Abschiedsfeier",
    "willkommen": "Willkommensfeier",
}

SEATING_KEYWORDS = {
    "terrasse": "Terrasse",
    "draußen": "Außenbereich",
    "fenster": "Fensterplatz",
    "ruhig": "Ruhiger Bereich",
    "privat": "Separater Bereich",
    "bar": "Barplatz",
}


class TriageEngine:
    """Intelligent triage engine for restaurant reservations."""

    def __init__(self):
        """Initialize triage engine."""
        self._config = RESTAURANT_CONFIG

    def assess(
        self,
        guest: GuestContext,
        free_text: str | None = None,
        available_slots: list[ReservationSlot] | None = None,
    ) -> TriageResult:
        """
        Perform triage assessment for reservation request.

        Args:
            guest: Guest context with request details
            free_text: Free-text message for special request extraction
            available_slots: List of available slots to consider

        Returns:
            TriageResult with recommendations
        """
        available_slots = available_slots or []
        special_handling: list[str] = []
        notes: list[str] = []

        # Calculate guest priority
        priority = guest.calculate_priority()

        # Determine urgency
        urgency = self._determine_urgency(guest)

        # Extract special requests from free text
        if free_text:
            self._extract_special_requests(free_text, guest)

        # Process special requests
        for req in guest.special_requests:
            if req.is_critical:
                special_handling.append(f"KRITISCH: {req.details}")
            else:
                notes.append(f"Wunsch: {req.details}")

        # Check party size
        can_accommodate = True
        if guest.party_size > self._config["max_party_size"]:
            can_accommodate = False
            notes.append(f"Gruppengröße ({guest.party_size}) übersteigt Maximum ({self._config['max_party_size']})")
            special_handling.append("Restaurantleiter kontaktieren für große Gruppen")

        # Filter slots by capacity
        suitable_slots = [
            s for s in available_slots
            if s.capacity >= guest.party_size
        ]

        # Calculate no-show risk
        no_show_risk = guest.calculate_no_show_risk()

        # Determine if deposit required
        requires_deposit = (
            guest.party_size >= self._config["deposit_threshold_party"]
            or no_show_risk >= self._config["deposit_threshold_risk"]
        )

        if requires_deposit:
            notes.append("Anzahlung empfohlen")

        # Determine if callback needed
        requires_callback = (
            priority == GuestPriority.VIP
            or guest.party_size >= 8
            or any(r.is_critical for r in guest.special_requests)
        )

        # Generate response message
        response_message = self._generate_response(
            can_accommodate=can_accommodate,
            priority=priority,
            suitable_slots=suitable_slots[:3],
            guest=guest,
        )

        return TriageResult(
            can_accommodate=can_accommodate and len(suitable_slots) > 0,
            guest_priority=priority,
            request_urgency=urgency,
            recommended_slots=suitable_slots[:5],
            special_handling=special_handling,
            no_show_risk=round(no_show_risk, 2),
            requires_deposit=requires_deposit,
            requires_callback=requires_callback,
            response_message=response_message,
            notes=notes,
        )

    def _determine_urgency(self, guest: GuestContext) -> RequestUrgency:
        """Determine request urgency based on timing."""
        from datetime import datetime

        if not guest.preferred_date:
            return RequestUrgency.FLEXIBLE

        try:
            req_date = datetime.strptime(guest.preferred_date, "%Y-%m-%d").date()
            today = datetime.now().date()
            days_ahead = (req_date - today).days

            if days_ahead <= 0:
                return RequestUrgency.IMMEDIATE
            elif days_ahead <= 2:
                return RequestUrgency.IMMEDIATE
            else:
                return RequestUrgency.STANDARD
        except ValueError:
            return RequestUrgency.FLEXIBLE

    def _extract_special_requests(self, text: str, guest: GuestContext) -> None:
        """Extract special requests from free text."""
        text_lower = text.lower()

        # Check allergies and dietary
        for keyword, req_type in ALLERGY_KEYWORDS.items():
            if keyword in text_lower:
                is_critical = req_type == SpecialRequestType.ALLERGY
                guest.special_requests.append(SpecialRequest(
                    request_type=req_type,
                    details=keyword.capitalize(),
                    is_critical=is_critical,
                ))

        # Check occasions
        for keyword, occasion in OCCASION_KEYWORDS.items():
            if keyword in text_lower:
                guest.occasion = occasion
                guest.special_requests.append(SpecialRequest(
                    request_type=SpecialRequestType.OCCASION,
                    details=occasion,
                ))
                break

        # Check seating preferences
        for keyword, pref in SEATING_KEYWORDS.items():
            if keyword in text_lower:
                guest.special_requests.append(SpecialRequest(
                    request_type=SpecialRequestType.SEATING,
                    details=pref,
                ))

        # Check accessibility
        if any(w in text_lower for w in ["rollstuhl", "barrierefrei", "gehbehindert"]):
            guest.special_requests.append(SpecialRequest(
                request_type=SpecialRequestType.ACCESSIBILITY,
                details="Barrierefreier Zugang",
                is_critical=True,
            ))

        # Check child-related
        if any(w in text_lower for w in ["kinderstuhl", "hochstuhl", "kinder", "baby"]):
            guest.special_requests.append(SpecialRequest(
                request_type=SpecialRequestType.CHILD,
                details="Kinderstuhl/Kinderkarte",
            ))

        # Check pets
        if any(w in text_lower for w in ["hund", "tier"]):
            guest.special_requests.append(SpecialRequest(
                request_type=SpecialRequestType.PET,
                details="Hund/Haustier",
            ))

    def _generate_response(
        self,
        can_accommodate: bool,
        priority: GuestPriority,
        suitable_slots: list[ReservationSlot],
        guest: GuestContext,
    ) -> str:
        """Generate appropriate response message."""
        if not can_accommodate:
            if guest.party_size > self._config["max_party_size"]:
                return (
                    f"Für {guest.party_size} Personen empfehle ich ein Gespräch mit unserem "
                    "Restaurantleiter, der Ihnen gerne individuelle Möglichkeiten aufzeigt."
                )
            return "Leider haben wir zu diesem Zeitpunkt keine Verfügbarkeit."

        if not suitable_slots:
            return (
                "Zum gewünschten Zeitpunkt ist leider alles reserviert. "
                "Darf ich Ihnen einen anderen Termin vorschlagen?"
            )

        # VIP greeting
        if priority == GuestPriority.VIP:
            prefix = "Es freut uns sehr, Sie wieder bei uns begrüßen zu dürfen! "
        elif priority == GuestPriority.REGULAR:
            prefix = "Willkommen zurück! "
        else:
            prefix = "Vielen Dank für Ihre Anfrage! "

        # Format slots
        slot = suitable_slots[0]
        slot_info = f"am {slot.date} um {slot.time} Uhr"

        return f"{prefix}Für {guest.party_size} Personen {slot_info} ist noch ein schöner Tisch frei."


# Singleton instance
_triage_engine: TriageEngine | None = None


def get_triage_engine() -> TriageEngine:
    """Get or create triage engine singleton."""
    global _triage_engine
    if _triage_engine is None:
        _triage_engine = TriageEngine()
    return _triage_engine
