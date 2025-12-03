"""Follow-up campaign system for Handwerk (Trades).

Proactive outreach for:
- Maintenance reminders (Wartungserinnerung)
- Quote follow-ups (Angebotsnachfass)
- Seasonal campaigns (Saisonale Kampagnen)
- Annual inspections (Jahresprüfungen)
- Customer satisfaction follow-up
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, date, timedelta
from enum import Enum
from typing import Any
from uuid import UUID, uuid4


class FollowUpType(str, Enum):
    """Types of follow-up campaigns for trades."""

    MAINTENANCE = "maintenance"          # Wartung (Heizung, Klimaanlage)
    QUOTE_FOLLOWUP = "quote_followup"    # Angebotsnachfass
    SEASONAL = "seasonal"                # Saisonale Kampagne
    INSPECTION = "inspection"            # Jahresprüfung (TÜV, Sicherheit)
    WARRANTY = "warranty"                # Garantieablauf
    SATISFACTION = "satisfaction"        # Kundenzufriedenheit
    REFERRAL = "referral"                # Empfehlungsanfrage
    NO_SHOW = "no_show"                  # Verpasste Termine
    CUSTOM = "custom"                    # Individuelle Kampagne


class FollowUpStatus(str, Enum):
    """Status of follow-up attempts."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    CONTACTED = "contacted"
    APPOINTMENT_MADE = "appointment_made"
    QUOTE_ACCEPTED = "quote_accepted"
    DECLINED = "declined"
    UNREACHABLE = "unreachable"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class ContactMethod(str, Enum):
    """Methods for contacting customers."""

    PHONE = "phone"
    SMS = "sms"
    EMAIL = "email"
    WHATSAPP = "whatsapp"


class TradeCategory(str, Enum):
    """Trade categories for campaign targeting."""

    SHK = "shk"              # Sanitär, Heizung, Klima
    ELEKTRO = "elektro"      # Electrical
    SCHLOSSER = "schlosser"  # Locksmith
    DACHDECKER = "dachdecker"  # Roofing
    MALER = "maler"          # Painting
    TISCHLER = "tischler"    # Carpentry
    BAU = "bau"              # Construction
    ALLGEMEIN = "allgemein"  # General


@dataclass
class FollowUpCampaign:
    """Follow-up campaign configuration."""

    id: UUID
    name: str
    followup_type: FollowUpType
    description: str

    # Target criteria
    target_trade_category: TradeCategory | None = None
    target_service_type: str | None = None
    target_last_service_before: date | None = None
    target_last_service_after: date | None = None
    target_quote_age_days: int | None = None

    # Campaign settings
    start_date: date = field(default_factory=date.today)
    end_date: date | None = None
    contact_methods: list[ContactMethod] = field(default_factory=lambda: [ContactMethod.PHONE])
    max_attempts: int = 3
    days_between_attempts: int = 3

    # Message templates (German)
    phone_script: str = ""
    sms_template: str = ""
    email_template: str = ""

    # Status
    active: bool = True
    created_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": str(self.id),
            "name": self.name,
            "followup_type": self.followup_type.value,
            "description": self.description,
            "target_trade_category": self.target_trade_category.value if self.target_trade_category else None,
            "target_service_type": self.target_service_type,
            "target_last_service_before": self.target_last_service_before.isoformat() if self.target_last_service_before else None,
            "target_last_service_after": self.target_last_service_after.isoformat() if self.target_last_service_after else None,
            "target_quote_age_days": self.target_quote_age_days,
            "start_date": self.start_date.isoformat(),
            "end_date": self.end_date.isoformat() if self.end_date else None,
            "contact_methods": [m.value for m in self.contact_methods],
            "max_attempts": self.max_attempts,
            "days_between_attempts": self.days_between_attempts,
            "active": self.active,
            "created_at": self.created_at.isoformat(),
        }


@dataclass
class FollowUpCustomer:
    """Customer in a follow-up campaign."""

    id: UUID
    customer_id: UUID
    campaign_id: UUID
    first_name: str
    last_name: str
    company_name: str | None
    phone: str
    email: str | None = None
    address: str | None = None

    # Service history
    last_service_date: date | None = None
    last_service_type: str | None = None
    equipment_info: str | None = None  # e.g., "Viessmann Vitodens 200-W"

    # Follow-up status
    status: FollowUpStatus = FollowUpStatus.PENDING
    attempts: int = 0
    last_attempt: datetime | None = None
    next_attempt: datetime | None = None

    # Outcome
    appointment_id: UUID | None = None
    quote_id: UUID | None = None
    notes: str | None = None

    # Priority (0-10, higher = more urgent)
    priority: int = 5

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": str(self.id),
            "customer_id": str(self.customer_id),
            "campaign_id": str(self.campaign_id),
            "first_name": self.first_name,
            "last_name": self.last_name,
            "company_name": self.company_name,
            "phone": self.phone,
            "email": self.email,
            "address": self.address,
            "last_service_date": self.last_service_date.isoformat() if self.last_service_date else None,
            "last_service_type": self.last_service_type,
            "equipment_info": self.equipment_info,
            "status": self.status.value,
            "attempts": self.attempts,
            "last_attempt": self.last_attempt.isoformat() if self.last_attempt else None,
            "next_attempt": self.next_attempt.isoformat() if self.next_attempt else None,
            "appointment_id": str(self.appointment_id) if self.appointment_id else None,
            "quote_id": str(self.quote_id) if self.quote_id else None,
            "notes": self.notes,
            "priority": self.priority,
        }


@dataclass
class FollowUpAttempt:
    """Record of a follow-up attempt."""

    id: UUID
    followup_customer_id: UUID
    campaign_id: UUID
    attempt_number: int
    method: ContactMethod
    started_at: datetime
    ended_at: datetime | None = None
    outcome: FollowUpStatus | None = None
    duration_seconds: int | None = None
    transcript: str | None = None
    notes: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": str(self.id),
            "followup_customer_id": str(self.followup_customer_id),
            "campaign_id": str(self.campaign_id),
            "attempt_number": self.attempt_number,
            "method": self.method.value,
            "started_at": self.started_at.isoformat(),
            "ended_at": self.ended_at.isoformat() if self.ended_at else None,
            "outcome": self.outcome.value if self.outcome else None,
            "duration_seconds": self.duration_seconds,
            "transcript": self.transcript,
            "notes": self.notes,
        }


# Pre-built campaign templates for trades
CAMPAIGN_TEMPLATES: dict[FollowUpType, dict[str, Any]] = {
    FollowUpType.MAINTENANCE: {
        "name": "Heizungswartung",
        "description": "Jährliche Heizungswartung - Einladung zur Wartung",
        "target_trade_category": TradeCategory.SHK,
        "phone_script": """Guten Tag, hier spricht der Telefonassistent von {company_name}.
Wir melden uns, weil die jährliche Wartung Ihrer Heizungsanlage ansteht.
Regelmäßige Wartung sichert den effizienten Betrieb und beugt Störungen vor.
{equipment_info}
Darf ich Ihnen einen Termin für die Wartung vorschlagen?""",
        "sms_template": """{company_name}: Ihre jährliche Heizungswartung steht an!
Vereinbaren Sie jetzt einen Termin: {phone}""",
    },
    FollowUpType.QUOTE_FOLLOWUP: {
        "name": "Angebotsnachfass",
        "description": "Nachfassen bei offenen Angeboten",
        "phone_script": """Guten Tag, hier spricht der Telefonassistent von {company_name}.
Wir haben Ihnen vor {days_since_quote} Tagen ein Angebot für {service_description} zugeschickt.
Ich wollte nachfragen, ob Sie noch Fragen zum Angebot haben oder ob ich Ihnen weiterhelfen kann.
Haben Sie sich schon entschieden?""",
        "sms_template": """{company_name}: Ihr Angebot wartet auf Sie!
Haben Sie Fragen? Rufen Sie an: {phone}""",
    },
    FollowUpType.SEASONAL: {
        "name": "Herbst-Check Heizung",
        "description": "Saisonale Kampagne vor der Heizperiode",
        "target_trade_category": TradeCategory.SHK,
        "phone_script": """Guten Tag, hier spricht der Telefonassistent von {company_name}.
Der Herbst steht vor der Tür und damit auch die Heizperiode.
Wir bieten Ihnen einen Heizungs-Check an, damit Sie gut durch den Winter kommen.
Sollen wir einen Termin vereinbaren?""",
        "sms_template": """{company_name}: Heizungs-Check vor dem Winter!
Termin vereinbaren: {phone}""",
    },
    FollowUpType.INSPECTION: {
        "name": "Jahresprüfung Elektro",
        "description": "Pflichtprüfung elektrischer Anlagen",
        "target_trade_category": TradeCategory.ELEKTRO,
        "phone_script": """Guten Tag, hier spricht der Telefonassistent von {company_name}.
Die regelmäßige Prüfung Ihrer elektrischen Anlagen ist wichtig für die Sicherheit.
Nach unseren Unterlagen steht bei Ihnen eine Prüfung an.
Wann passt es Ihnen für einen Prüftermin?""",
        "sms_template": """{company_name}: E-Check fällig!
Sicherheit geht vor - Termin unter {phone}""",
    },
    FollowUpType.WARRANTY: {
        "name": "Garantieablauf",
        "description": "Erinnerung vor Garantieende",
        "phone_script": """Guten Tag, hier spricht der Telefonassistent von {company_name}.
Wir möchten Sie darauf hinweisen, dass die Garantie für {equipment_info} bald abläuft.
Möchten Sie vorher noch eine Inspektion durchführen lassen oder einen Wartungsvertrag abschließen?""",
        "sms_template": """{company_name}: Garantie läuft bald ab!
Jetzt handeln: {phone}""",
    },
    FollowUpType.SATISFACTION: {
        "name": "Kundenzufriedenheit",
        "description": "Nachfrage nach Kundenzufriedenheit",
        "phone_script": """Guten Tag, hier spricht der Telefonassistent von {company_name}.
Unser Techniker war kürzlich bei Ihnen für {last_service_type}.
Wir möchten nachfragen, ob alles zu Ihrer Zufriedenheit erledigt wurde.
Gibt es noch etwas, womit wir Ihnen helfen können?""",
        "sms_template": """{company_name}: War alles in Ordnung?
Wir freuen uns über Ihr Feedback: {phone}""",
    },
    FollowUpType.REFERRAL: {
        "name": "Empfehlungsanfrage",
        "description": "Bitte um Weiterempfehlung",
        "phone_script": """Guten Tag, hier spricht der Telefonassistent von {company_name}.
Wir freuen uns, dass Sie mit unserer Arbeit zufrieden sind.
Kennen Sie jemanden, der auch unsere Dienste benötigen könnte?
Für jede erfolgreiche Empfehlung erhalten Sie {referral_bonus}.""",
        "sms_template": """{company_name}: Empfehlen Sie uns weiter und erhalten Sie {referral_bonus}!
Mehr Infos: {phone}""",
    },
    FollowUpType.NO_SHOW: {
        "name": "Verpasster Termin",
        "description": "Nachfassen bei nicht erschienenen Kunden",
        "phone_script": """Guten Tag, hier spricht der Telefonassistent von {company_name}.
Leider konnten wir Sie zu Ihrem Termin am {missed_date} nicht antreffen.
Wir hoffen, es ist alles in Ordnung. Möchten Sie einen neuen Termin vereinbaren?""",
        "sms_template": """{company_name}: Schade, dass wir Sie nicht angetroffen haben.
Neuer Termin? {phone}""",
    },
}

# Seasonal campaign calendar (month -> list of campaigns)
SEASONAL_CALENDAR: dict[int, list[dict[str, Any]]] = {
    # Spring
    3: [
        {"type": FollowUpType.SEASONAL, "trade": TradeCategory.SHK, "name": "Klimaanlagen-Check vor dem Sommer"},
        {"type": FollowUpType.SEASONAL, "trade": TradeCategory.DACHDECKER, "name": "Frühjahrs-Dachinspektion"},
    ],
    4: [
        {"type": FollowUpType.SEASONAL, "trade": TradeCategory.MALER, "name": "Fassadenanstrich-Saison"},
        {"type": FollowUpType.SEASONAL, "trade": TradeCategory.TISCHLER, "name": "Fenster- und Türen-Check"},
    ],
    # Fall
    9: [
        {"type": FollowUpType.SEASONAL, "trade": TradeCategory.SHK, "name": "Herbst-Check Heizung"},
        {"type": FollowUpType.SEASONAL, "trade": TradeCategory.DACHDECKER, "name": "Herbst-Dachinspektion"},
    ],
    10: [
        {"type": FollowUpType.MAINTENANCE, "trade": TradeCategory.SHK, "name": "Heizungswartung vor dem Winter"},
        {"type": FollowUpType.SEASONAL, "trade": TradeCategory.SCHLOSSER, "name": "Türen winterfest machen"},
    ],
    # Winter preparation
    11: [
        {"type": FollowUpType.INSPECTION, "trade": TradeCategory.ELEKTRO, "name": "Weihnachtsbeleuchtung Check"},
    ],
}


class FollowUpService:
    """Service for managing follow-up campaigns."""

    def __init__(self):
        """Initialize follow-up service."""
        self._campaigns: dict[UUID, FollowUpCampaign] = {}
        self._customers: dict[UUID, FollowUpCustomer] = {}
        self._attempts: dict[UUID, FollowUpAttempt] = {}

    def create_campaign(
        self,
        followup_type: FollowUpType,
        name: str | None = None,
        **kwargs,
    ) -> FollowUpCampaign:
        """
        Create a new follow-up campaign.

        Args:
            followup_type: Type of follow-up campaign
            name: Optional custom name (uses template name if not provided)
            **kwargs: Additional campaign parameters

        Returns:
            Created campaign
        """
        # Start with template if available
        template = CAMPAIGN_TEMPLATES.get(followup_type, {}).copy()

        # Build base params from template
        base_params = {
            "id": uuid4(),
            "name": name or template.get("name", f"{followup_type.value} Campaign"),
            "followup_type": followup_type,
            "description": template.get("description", ""),
            "phone_script": template.get("phone_script", ""),
            "sms_template": template.get("sms_template", ""),
        }

        # Add target_trade_category from template only if not in kwargs
        if "target_trade_category" not in kwargs and template.get("target_trade_category"):
            base_params["target_trade_category"] = template["target_trade_category"]

        # Merge kwargs (kwargs override base_params)
        campaign = FollowUpCampaign(
            **base_params,
            **kwargs,
        )

        self._campaigns[campaign.id] = campaign
        return campaign

    def create_maintenance_campaign(
        self,
        trade_category: TradeCategory,
        equipment_type: str | None = None,
        months_since_last_service: int = 12,
    ) -> FollowUpCampaign:
        """
        Create a maintenance reminder campaign.

        Args:
            trade_category: Trade category (SHK, ELEKTRO, etc.)
            equipment_type: Specific equipment type to target
            months_since_last_service: Months since last service

        Returns:
            Created campaign
        """
        cutoff_date = date.today() - timedelta(days=months_since_last_service * 30)

        name_map = {
            TradeCategory.SHK: "Heizungswartung",
            TradeCategory.ELEKTRO: "E-Check",
            TradeCategory.DACHDECKER: "Dachinspektion",
            TradeCategory.MALER: "Fassadeninspektion",
            TradeCategory.TISCHLER: "Fenster-/Türenwartung",
            TradeCategory.SCHLOSSER: "Schloss-/Türwartung",
            TradeCategory.BAU: "Bauwerksinspektion",
            TradeCategory.ALLGEMEIN: "Wartungserinnerung",
        }

        return self.create_campaign(
            followup_type=FollowUpType.MAINTENANCE,
            name=name_map.get(trade_category, "Wartungserinnerung"),
            target_trade_category=trade_category,
            target_service_type=equipment_type,
            target_last_service_before=cutoff_date,
        )

    def create_quote_followup_campaign(
        self,
        days_since_quote: int = 7,
    ) -> FollowUpCampaign:
        """
        Create a quote follow-up campaign.

        Args:
            days_since_quote: Days since quote was sent

        Returns:
            Created campaign
        """
        return self.create_campaign(
            followup_type=FollowUpType.QUOTE_FOLLOWUP,
            name="Angebotsnachfass",
            target_quote_age_days=days_since_quote,
        )

    def get_seasonal_campaigns_for_month(
        self,
        month: int | None = None,
    ) -> list[dict[str, Any]]:
        """
        Get recommended seasonal campaigns for a month.

        Args:
            month: Month number (1-12), defaults to current month

        Returns:
            List of recommended campaign configurations
        """
        if month is None:
            month = date.today().month

        return SEASONAL_CALENDAR.get(month, [])

    def add_customer_to_campaign(
        self,
        campaign_id: UUID,
        customer_id: UUID,
        first_name: str,
        last_name: str,
        phone: str,
        company_name: str | None = None,
        email: str | None = None,
        address: str | None = None,
        last_service_date: date | None = None,
        last_service_type: str | None = None,
        equipment_info: str | None = None,
        priority: int = 5,
    ) -> FollowUpCustomer:
        """
        Add a customer to a follow-up campaign.

        Args:
            campaign_id: ID of the campaign
            customer_id: ID of the customer
            first_name: Customer's first name
            last_name: Customer's last name
            phone: Customer's phone number
            company_name: Company name (optional)
            email: Customer's email (optional)
            address: Service address (optional)
            last_service_date: Date of last service
            last_service_type: Type of last service
            equipment_info: Equipment details
            priority: Priority level (0-10)

        Returns:
            Created follow-up customer record
        """
        if campaign_id not in self._campaigns:
            raise ValueError(f"Campaign {campaign_id} not found")

        followup_customer = FollowUpCustomer(
            id=uuid4(),
            customer_id=customer_id,
            campaign_id=campaign_id,
            first_name=first_name,
            last_name=last_name,
            company_name=company_name,
            phone=phone,
            email=email,
            address=address,
            last_service_date=last_service_date,
            last_service_type=last_service_type,
            equipment_info=equipment_info,
            priority=priority,
            next_attempt=datetime.now(),
        )

        self._customers[followup_customer.id] = followup_customer
        return followup_customer

    def get_next_customer(
        self,
        campaign_id: UUID | None = None,
    ) -> FollowUpCustomer | None:
        """
        Get next customer to contact.

        Args:
            campaign_id: Optional campaign filter

        Returns:
            Next customer to call or None
        """
        now = datetime.now()
        candidates = []

        for customer in self._customers.values():
            # Skip inactive statuses
            if customer.status not in [FollowUpStatus.PENDING, FollowUpStatus.IN_PROGRESS]:
                continue

            # Filter by campaign if specified
            if campaign_id and customer.campaign_id != campaign_id:
                continue

            # Check if campaign is active
            campaign = self._campaigns.get(customer.campaign_id)
            if not campaign or not campaign.active:
                continue

            # Check max attempts
            if customer.attempts >= campaign.max_attempts:
                customer.status = FollowUpStatus.UNREACHABLE
                continue

            # Check if ready for next attempt
            if customer.next_attempt and customer.next_attempt > now:
                continue

            candidates.append(customer)

        if not candidates:
            return None

        # Sort by priority (highest first) and next_attempt (earliest first)
        candidates.sort(key=lambda c: (-c.priority, c.next_attempt or now))

        return candidates[0]

    def start_attempt(
        self,
        followup_customer_id: UUID,
        method: ContactMethod = ContactMethod.PHONE,
    ) -> FollowUpAttempt:
        """
        Start a follow-up attempt.

        Args:
            followup_customer_id: ID of the follow-up customer
            method: Contact method

        Returns:
            Created attempt record
        """
        customer = self._customers.get(followup_customer_id)
        if not customer:
            raise ValueError(f"Follow-up customer {followup_customer_id} not found")

        customer.status = FollowUpStatus.IN_PROGRESS
        customer.attempts += 1
        customer.last_attempt = datetime.now()

        attempt = FollowUpAttempt(
            id=uuid4(),
            followup_customer_id=followup_customer_id,
            campaign_id=customer.campaign_id,
            attempt_number=customer.attempts,
            method=method,
            started_at=datetime.now(),
        )

        self._attempts[attempt.id] = attempt
        return attempt

    def complete_attempt(
        self,
        attempt_id: UUID,
        outcome: FollowUpStatus,
        transcript: str | None = None,
        notes: str | None = None,
        appointment_id: UUID | None = None,
        quote_id: UUID | None = None,
    ) -> FollowUpAttempt:
        """
        Complete a follow-up attempt.

        Args:
            attempt_id: ID of the attempt
            outcome: Outcome status
            transcript: Call transcript (optional)
            notes: Additional notes
            appointment_id: ID of scheduled appointment (if any)
            quote_id: ID of accepted quote (if any)

        Returns:
            Updated attempt record
        """
        attempt = self._attempts.get(attempt_id)
        if not attempt:
            raise ValueError(f"Attempt {attempt_id} not found")

        customer = self._customers.get(attempt.followup_customer_id)
        if not customer:
            raise ValueError(f"Customer not found for attempt {attempt_id}")

        campaign = self._campaigns.get(customer.campaign_id)

        # Update attempt
        attempt.ended_at = datetime.now()
        attempt.outcome = outcome
        attempt.transcript = transcript
        attempt.notes = notes
        attempt.duration_seconds = int(
            (attempt.ended_at - attempt.started_at).total_seconds()
        )

        # Update customer status based on outcome
        if outcome == FollowUpStatus.APPOINTMENT_MADE:
            customer.status = FollowUpStatus.APPOINTMENT_MADE
            customer.appointment_id = appointment_id
        elif outcome == FollowUpStatus.QUOTE_ACCEPTED:
            customer.status = FollowUpStatus.QUOTE_ACCEPTED
            customer.quote_id = quote_id
        elif outcome == FollowUpStatus.DECLINED:
            customer.status = FollowUpStatus.DECLINED
        elif outcome == FollowUpStatus.UNREACHABLE:
            # Schedule next attempt if within limits
            if campaign and customer.attempts < campaign.max_attempts:
                customer.status = FollowUpStatus.PENDING
                customer.next_attempt = datetime.now() + timedelta(
                    days=campaign.days_between_attempts
                )
            else:
                customer.status = FollowUpStatus.UNREACHABLE
        elif outcome == FollowUpStatus.CONTACTED:
            customer.status = FollowUpStatus.CONTACTED

        customer.notes = notes

        return attempt

    def get_campaign_stats(self, campaign_id: UUID) -> dict[str, Any]:
        """
        Get statistics for a campaign.

        Args:
            campaign_id: ID of the campaign

        Returns:
            Campaign statistics
        """
        campaign = self._campaigns.get(campaign_id)
        if not campaign:
            raise ValueError(f"Campaign {campaign_id} not found")

        customers = [
            c for c in self._customers.values()
            if c.campaign_id == campaign_id
        ]

        stats = {
            "campaign_id": str(campaign_id),
            "campaign_name": campaign.name,
            "followup_type": campaign.followup_type.value,
            "total_customers": len(customers),
            "status_breakdown": {},
            "total_attempts": 0,
            "appointments_made": 0,
            "quotes_accepted": 0,
            "success_rate": 0.0,
            "conversion_rate": 0.0,
        }

        for status in FollowUpStatus:
            count = sum(1 for c in customers if c.status == status)
            stats["status_breakdown"][status.value] = count

        stats["appointments_made"] = stats["status_breakdown"].get(
            FollowUpStatus.APPOINTMENT_MADE.value, 0
        )
        stats["quotes_accepted"] = stats["status_breakdown"].get(
            FollowUpStatus.QUOTE_ACCEPTED.value, 0
        )

        if customers:
            successful = stats["appointments_made"] + stats["quotes_accepted"]
            stats["success_rate"] = successful / len(customers) * 100

            # Conversion rate for quote follow-ups
            if campaign.followup_type == FollowUpType.QUOTE_FOLLOWUP:
                stats["conversion_rate"] = stats["quotes_accepted"] / len(customers) * 100

        # Count total attempts
        stats["total_attempts"] = sum(
            1 for a in self._attempts.values()
            if a.campaign_id == campaign_id
        )

        return stats

    def get_phone_script(
        self,
        campaign_id: UUID,
        customer: FollowUpCustomer,
        company_name: str = "Mustermann GmbH",
        **kwargs,
    ) -> str:
        """
        Get personalized phone script for a customer.

        Args:
            campaign_id: ID of the campaign
            customer: Follow-up customer
            company_name: Name of the company
            **kwargs: Additional template variables

        Returns:
            Personalized phone script
        """
        campaign = self._campaigns.get(campaign_id)
        if not campaign:
            return ""

        script = campaign.phone_script

        # Build equipment info string
        equipment_str = ""
        if customer.equipment_info:
            equipment_str = f"Laut unseren Unterlagen handelt es sich um eine {customer.equipment_info}."

        # Calculate days since quote if applicable
        days_since_quote = ""
        if customer.last_service_date:
            days = (date.today() - customer.last_service_date).days
            days_since_quote = str(days)

        # Replace placeholders
        replacements = {
            "{company_name}": company_name,
            "{first_name}": customer.first_name,
            "{last_name}": customer.last_name,
            "{full_name}": f"{customer.first_name} {customer.last_name}",
            "{customer_company}": customer.company_name or "",
            "{address}": customer.address or "",
            "{equipment_info}": equipment_str,
            "{last_service_type}": customer.last_service_type or "eine Dienstleistung",
            "{last_service_date}": customer.last_service_date.strftime("%d.%m.%Y") if customer.last_service_date else "",
            "{days_since_quote}": days_since_quote,
            "{phone}": customer.phone,
            **{f"{{{k}}}": str(v) for k, v in kwargs.items()},
        }

        for placeholder, value in replacements.items():
            script = script.replace(placeholder, value)

        return script

    def get_campaigns(
        self,
        active_only: bool = True,
        followup_type: FollowUpType | None = None,
    ) -> list[FollowUpCampaign]:
        """
        Get list of campaigns.

        Args:
            active_only: Only return active campaigns
            followup_type: Filter by follow-up type

        Returns:
            List of campaigns
        """
        campaigns = list(self._campaigns.values())

        if active_only:
            campaigns = [c for c in campaigns if c.active]

        if followup_type:
            campaigns = [c for c in campaigns if c.followup_type == followup_type]

        return campaigns

    def deactivate_campaign(self, campaign_id: UUID) -> bool:
        """
        Deactivate a campaign.

        Args:
            campaign_id: ID of the campaign

        Returns:
            True if deactivated, False if not found
        """
        campaign = self._campaigns.get(campaign_id)
        if not campaign:
            return False

        campaign.active = False
        return True


# Singleton instance
_followup_service: FollowUpService | None = None


def get_followup_service() -> FollowUpService:
    """Get or create follow-up service singleton."""
    global _followup_service
    if _followup_service is None:
        _followup_service = FollowUpService()
    return _followup_service
