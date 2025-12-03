"""Patient recall campaign system.

Proactive outreach for:
- Preventive care reminders (Vorsorge)
- Vaccination campaigns (Impfkampagnen)
- Follow-up appointments (Wiedervorstellung)
- Chronic disease management
- No-show follow-up
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, date, timedelta
from enum import Enum
from typing import Any, AsyncIterator, Callable
from uuid import UUID, uuid4
import asyncio


class RecallType(str, Enum):
    """Types of recall campaigns."""

    PREVENTIVE = "preventive"           # Vorsorge (Check-up, Krebsvorsorge)
    VACCINATION = "vaccination"         # Impfungen (Grippe, COVID, Tetanus)
    FOLLOWUP = "followup"               # Wiedervorstellung
    CHRONIC = "chronic"                 # Chroniker-Betreuung (DMP)
    NO_SHOW = "no_show"                 # Verpasste Termine
    LAB_RESULTS = "lab_results"         # Laborbefunde besprechen
    PRESCRIPTION = "prescription"       # Rezeptabholung
    CUSTOM = "custom"                   # Individuelle Kampagne


class RecallStatus(str, Enum):
    """Status of recall attempts."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    CONTACTED = "contacted"
    APPOINTMENT_MADE = "appointment_made"
    DECLINED = "declined"
    UNREACHABLE = "unreachable"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class ContactMethod(str, Enum):
    """Methods for contacting patients."""

    PHONE = "phone"
    SMS = "sms"
    EMAIL = "email"
    LETTER = "letter"


@dataclass
class RecallCampaign:
    """Recall campaign configuration."""

    id: UUID
    name: str
    recall_type: RecallType
    description: str

    # Target criteria
    target_age_min: int | None = None
    target_age_max: int | None = None
    target_gender: str | None = None  # "M", "F", None for all
    target_conditions: list[str] = field(default_factory=list)
    target_last_visit_before: date | None = None

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
            "recall_type": self.recall_type.value,
            "description": self.description,
            "target_age_min": self.target_age_min,
            "target_age_max": self.target_age_max,
            "target_gender": self.target_gender,
            "target_conditions": self.target_conditions,
            "target_last_visit_before": self.target_last_visit_before.isoformat() if self.target_last_visit_before else None,
            "start_date": self.start_date.isoformat(),
            "end_date": self.end_date.isoformat() if self.end_date else None,
            "contact_methods": [m.value for m in self.contact_methods],
            "max_attempts": self.max_attempts,
            "days_between_attempts": self.days_between_attempts,
            "active": self.active,
            "created_at": self.created_at.isoformat(),
        }


@dataclass
class RecallPatient:
    """Patient in a recall campaign."""

    id: UUID
    patient_id: UUID
    campaign_id: UUID
    first_name: str
    last_name: str
    phone: str
    email: str | None = None

    # Recall status
    status: RecallStatus = RecallStatus.PENDING
    attempts: int = 0
    last_attempt: datetime | None = None
    next_attempt: datetime | None = None

    # Outcome
    appointment_id: UUID | None = None
    notes: str | None = None

    # Priority (0-10, higher = more urgent)
    priority: int = 5

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": str(self.id),
            "patient_id": str(self.patient_id),
            "campaign_id": str(self.campaign_id),
            "first_name": self.first_name,
            "last_name": self.last_name,
            "phone": self.phone,
            "email": self.email,
            "status": self.status.value,
            "attempts": self.attempts,
            "last_attempt": self.last_attempt.isoformat() if self.last_attempt else None,
            "next_attempt": self.next_attempt.isoformat() if self.next_attempt else None,
            "appointment_id": str(self.appointment_id) if self.appointment_id else None,
            "notes": self.notes,
            "priority": self.priority,
        }


@dataclass
class RecallAttempt:
    """Record of a recall attempt."""

    id: UUID
    recall_patient_id: UUID
    campaign_id: UUID
    attempt_number: int
    method: ContactMethod
    started_at: datetime
    ended_at: datetime | None = None
    outcome: RecallStatus | None = None
    duration_seconds: int | None = None
    transcript: str | None = None
    notes: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": str(self.id),
            "recall_patient_id": str(self.recall_patient_id),
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


# Pre-built campaign templates
CAMPAIGN_TEMPLATES: dict[RecallType, dict[str, Any]] = {
    RecallType.PREVENTIVE: {
        "name": "Gesundheits-Check-up",
        "description": "Einladung zur Vorsorgeuntersuchung (Check-up 35+)",
        "target_age_min": 35,
        "phone_script": """Guten Tag, hier spricht der Telefonassistent der Praxis {practice_name}.
Ich rufe an, weil für Sie eine Vorsorgeuntersuchung ansteht.
Der Check-up ist eine wichtige Untersuchung zur Früherkennung von Krankheiten.
Darf ich Ihnen einen Termin vorschlagen?""",
        "sms_template": """Praxis {practice_name}: Ihre Vorsorgeuntersuchung steht an!
Vereinbaren Sie einen Termin unter {phone} oder antworten Sie auf diese SMS.""",
    },
    RecallType.VACCINATION: {
        "name": "Grippeimpfung",
        "description": "Einladung zur saisonalen Grippeimpfung",
        "phone_script": """Guten Tag, hier spricht der Telefonassistent der Praxis {practice_name}.
Die Grippesaison steht bevor und wir möchten Sie zur Grippeimpfung einladen.
Die Impfung wird von den Krankenkassen übernommen.
Möchten Sie einen Termin vereinbaren?""",
        "sms_template": """Praxis {practice_name}: Grippeimpfung jetzt verfügbar!
Termin unter {phone}.""",
    },
    RecallType.CHRONIC: {
        "name": "DMP-Kontrolle",
        "description": "Quartalsweise Kontrolle für chronisch Kranke (DMP)",
        "phone_script": """Guten Tag, hier spricht der Telefonassistent der Praxis {practice_name}.
Ihre regelmäßige Kontrolluntersuchung im Rahmen des Disease-Management-Programms steht an.
Diese Untersuchung ist wichtig für Ihre Gesundheit und wird von der Krankenkasse erwartet.
Wann passt es Ihnen am besten?""",
        "sms_template": """Praxis {practice_name}: Ihre DMP-Kontrolle ist fällig.
Bitte vereinbaren Sie einen Termin: {phone}""",
    },
    RecallType.NO_SHOW: {
        "name": "Verpasster Termin",
        "description": "Nachfassen bei nicht erschienenen Patienten",
        "phone_script": """Guten Tag, hier spricht der Telefonassistent der Praxis {practice_name}.
Wir haben bemerkt, dass Sie Ihren Termin am {missed_date} leider nicht wahrnehmen konnten.
Wir hoffen, es geht Ihnen gut. Möchten Sie einen neuen Termin vereinbaren?""",
        "sms_template": """Praxis {practice_name}: Schade, dass Sie nicht kommen konnten.
Neuer Termin? {phone}""",
    },
    RecallType.LAB_RESULTS: {
        "name": "Laborbefund",
        "description": "Besprechung von Laborergebnissen",
        "phone_script": """Guten Tag, hier spricht der Telefonassistent der Praxis {practice_name}.
Ihre Laborergebnisse liegen vor und der Arzt möchte diese gerne mit Ihnen besprechen.
Haben Sie Zeit für einen kurzen Termin?""",
        "sms_template": """Praxis {practice_name}: Ihre Laborergebnisse sind da.
Bitte vereinbaren Sie einen Besprechungstermin: {phone}""",
    },
}


class RecallService:
    """Service for managing recall campaigns."""

    def __init__(self):
        """Initialize recall service."""
        self._campaigns: dict[UUID, RecallCampaign] = {}
        self._patients: dict[UUID, RecallPatient] = {}
        self._attempts: dict[UUID, RecallAttempt] = {}

    def create_campaign(
        self,
        recall_type: RecallType,
        name: str | None = None,
        **kwargs,
    ) -> RecallCampaign:
        """
        Create a new recall campaign.

        Args:
            recall_type: Type of recall campaign
            name: Optional custom name (uses template name if not provided)
            **kwargs: Additional campaign parameters

        Returns:
            Created campaign
        """
        # Start with template if available
        template = CAMPAIGN_TEMPLATES.get(recall_type, {})

        campaign = RecallCampaign(
            id=uuid4(),
            name=name or template.get("name", f"{recall_type.value} Campaign"),
            recall_type=recall_type,
            description=template.get("description", ""),
            phone_script=template.get("phone_script", ""),
            sms_template=template.get("sms_template", ""),
            **kwargs,
        )

        self._campaigns[campaign.id] = campaign
        return campaign

    def add_patient_to_campaign(
        self,
        campaign_id: UUID,
        patient_id: UUID,
        first_name: str,
        last_name: str,
        phone: str,
        email: str | None = None,
        priority: int = 5,
    ) -> RecallPatient:
        """
        Add a patient to a recall campaign.

        Args:
            campaign_id: ID of the campaign
            patient_id: ID of the patient
            first_name: Patient's first name
            last_name: Patient's last name
            phone: Patient's phone number
            email: Patient's email (optional)
            priority: Priority level (0-10)

        Returns:
            Created recall patient record
        """
        if campaign_id not in self._campaigns:
            raise ValueError(f"Campaign {campaign_id} not found")

        recall_patient = RecallPatient(
            id=uuid4(),
            patient_id=patient_id,
            campaign_id=campaign_id,
            first_name=first_name,
            last_name=last_name,
            phone=phone,
            email=email,
            priority=priority,
            next_attempt=datetime.now(),
        )

        self._patients[recall_patient.id] = recall_patient
        return recall_patient

    def get_next_patient(
        self,
        campaign_id: UUID | None = None,
    ) -> RecallPatient | None:
        """
        Get next patient to contact.

        Args:
            campaign_id: Optional campaign filter

        Returns:
            Next patient to call or None
        """
        now = datetime.now()
        candidates = []

        for patient in self._patients.values():
            # Skip inactive statuses
            if patient.status not in [RecallStatus.PENDING, RecallStatus.IN_PROGRESS]:
                continue

            # Filter by campaign if specified
            if campaign_id and patient.campaign_id != campaign_id:
                continue

            # Check if campaign is active
            campaign = self._campaigns.get(patient.campaign_id)
            if not campaign or not campaign.active:
                continue

            # Check max attempts
            if patient.attempts >= campaign.max_attempts:
                patient.status = RecallStatus.UNREACHABLE
                continue

            # Check if ready for next attempt
            if patient.next_attempt and patient.next_attempt > now:
                continue

            candidates.append(patient)

        if not candidates:
            return None

        # Sort by priority (highest first) and next_attempt (earliest first)
        candidates.sort(key=lambda p: (-p.priority, p.next_attempt or now))

        return candidates[0]

    def start_attempt(
        self,
        recall_patient_id: UUID,
        method: ContactMethod = ContactMethod.PHONE,
    ) -> RecallAttempt:
        """
        Start a recall attempt.

        Args:
            recall_patient_id: ID of the recall patient
            method: Contact method

        Returns:
            Created attempt record
        """
        patient = self._patients.get(recall_patient_id)
        if not patient:
            raise ValueError(f"Recall patient {recall_patient_id} not found")

        patient.status = RecallStatus.IN_PROGRESS
        patient.attempts += 1
        patient.last_attempt = datetime.now()

        attempt = RecallAttempt(
            id=uuid4(),
            recall_patient_id=recall_patient_id,
            campaign_id=patient.campaign_id,
            attempt_number=patient.attempts,
            method=method,
            started_at=datetime.now(),
        )

        self._attempts[attempt.id] = attempt
        return attempt

    def complete_attempt(
        self,
        attempt_id: UUID,
        outcome: RecallStatus,
        transcript: str | None = None,
        notes: str | None = None,
        appointment_id: UUID | None = None,
    ) -> RecallAttempt:
        """
        Complete a recall attempt.

        Args:
            attempt_id: ID of the attempt
            outcome: Outcome status
            transcript: Call transcript (optional)
            notes: Additional notes
            appointment_id: ID of scheduled appointment (if any)

        Returns:
            Updated attempt record
        """
        attempt = self._attempts.get(attempt_id)
        if not attempt:
            raise ValueError(f"Attempt {attempt_id} not found")

        patient = self._patients.get(attempt.recall_patient_id)
        if not patient:
            raise ValueError(f"Patient not found for attempt {attempt_id}")

        campaign = self._campaigns.get(patient.campaign_id)

        # Update attempt
        attempt.ended_at = datetime.now()
        attempt.outcome = outcome
        attempt.transcript = transcript
        attempt.notes = notes
        attempt.duration_seconds = int(
            (attempt.ended_at - attempt.started_at).total_seconds()
        )

        # Update patient status
        if outcome == RecallStatus.APPOINTMENT_MADE:
            patient.status = RecallStatus.APPOINTMENT_MADE
            patient.appointment_id = appointment_id
        elif outcome == RecallStatus.DECLINED:
            patient.status = RecallStatus.DECLINED
        elif outcome == RecallStatus.UNREACHABLE:
            # Schedule next attempt if within limits
            if campaign and patient.attempts < campaign.max_attempts:
                patient.status = RecallStatus.PENDING
                patient.next_attempt = datetime.now() + timedelta(
                    days=campaign.days_between_attempts
                )
            else:
                patient.status = RecallStatus.UNREACHABLE
        elif outcome == RecallStatus.CONTACTED:
            patient.status = RecallStatus.CONTACTED

        patient.notes = notes

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

        patients = [
            p for p in self._patients.values()
            if p.campaign_id == campaign_id
        ]

        stats = {
            "campaign_id": str(campaign_id),
            "campaign_name": campaign.name,
            "total_patients": len(patients),
            "status_breakdown": {},
            "total_attempts": 0,
            "appointments_made": 0,
            "success_rate": 0.0,
        }

        for status in RecallStatus:
            count = sum(1 for p in patients if p.status == status)
            stats["status_breakdown"][status.value] = count

        stats["appointments_made"] = stats["status_breakdown"].get(
            RecallStatus.APPOINTMENT_MADE.value, 0
        )

        if patients:
            stats["success_rate"] = stats["appointments_made"] / len(patients) * 100

        # Count total attempts
        stats["total_attempts"] = sum(
            1 for a in self._attempts.values()
            if a.campaign_id == campaign_id
        )

        return stats

    def get_phone_script(
        self,
        campaign_id: UUID,
        patient: RecallPatient,
        practice_name: str = "Dr. Mustermann",
        **kwargs,
    ) -> str:
        """
        Get personalized phone script for a patient.

        Args:
            campaign_id: ID of the campaign
            patient: Recall patient
            practice_name: Name of the practice
            **kwargs: Additional template variables

        Returns:
            Personalized phone script
        """
        campaign = self._campaigns.get(campaign_id)
        if not campaign:
            return ""

        script = campaign.phone_script

        # Replace placeholders
        replacements = {
            "{practice_name}": practice_name,
            "{first_name}": patient.first_name,
            "{last_name}": patient.last_name,
            "{full_name}": f"{patient.first_name} {patient.last_name}",
            **{f"{{{k}}}": str(v) for k, v in kwargs.items()},
        }

        for placeholder, value in replacements.items():
            script = script.replace(placeholder, value)

        return script


# Singleton instance
_recall_service: RecallService | None = None


def get_recall_service() -> RecallService:
    """Get or create recall service singleton."""
    global _recall_service
    if _recall_service is None:
        _recall_service = RecallService()
    return _recall_service
