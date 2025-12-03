"""Freie Berufe scheduling service.

Manages appointments for professional services: lawyers, tax consultants, etc.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, time as dt_time
from enum import Enum
from typing import Any
import uuid


class AppointmentType(str, Enum):
    """Types of appointments."""

    INITIAL_CONSULTATION = "initial_consultation"  # Erstberatung
    FOLLOW_UP = "follow_up"  # Folgebesprechung
    PHONE_CALL = "phone_call"  # Telefontermin
    VIDEO_CALL = "video_call"  # Videoberatung
    DOCUMENT_REVIEW = "document_review"  # Unterlagenprüfung
    COURT_PREP = "court_prep"  # Gerichtsvorbereitung


class AppointmentStatus(str, Enum):
    """Status of an appointment."""

    SCHEDULED = "scheduled"
    CONFIRMED = "confirmed"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    NO_SHOW = "no_show"
    RESCHEDULED = "rescheduled"


class AdvisorRole(str, Enum):
    """Advisor roles/specializations."""

    LAWYER = "lawyer"
    TAX_CONSULTANT = "tax_consultant"
    AUDITOR = "auditor"
    CONSULTANT = "consultant"
    ARCHITECT = "architect"
    NOTARY = "notary"
    PARALEGAL = "paralegal"


@dataclass
class Advisor:
    """A professional advisor."""

    id: str
    name: str
    role: AdvisorRole
    specializations: list[str] = field(default_factory=list)
    email: str | None = None
    available_hours: dict[int, list[tuple[dt_time, dt_time]]] = field(default_factory=dict)
    max_daily_appointments: int = 8
    notes: str | None = None


@dataclass
class Appointment:
    """A client appointment."""

    id: str
    client_name: str
    client_phone: str
    client_email: str | None
    company: str | None

    appointment_type: AppointmentType
    advisor_id: str | None
    date: str  # YYYY-MM-DD
    time: str  # HH:MM
    duration_minutes: int = 60

    status: AppointmentStatus = AppointmentStatus.SCHEDULED
    service_area: str | None = None
    topic: str | None = None
    notes: str | None = None
    documents_required: list[str] = field(default_factory=list)

    # Follow-up
    requires_follow_up: bool = False
    follow_up_date: str | None = None

    # Meta
    created_at: datetime = field(default_factory=datetime.now)
    confirmed_at: datetime | None = None
    reminder_sent: bool = False
    lead_source: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "client_name": self.client_name,
            "client_phone": self.client_phone,
            "client_email": self.client_email,
            "company": self.company,
            "appointment_type": self.appointment_type.value,
            "advisor_id": self.advisor_id,
            "date": self.date,
            "time": self.time,
            "duration_minutes": self.duration_minutes,
            "status": self.status.value,
            "service_area": self.service_area,
            "topic": self.topic,
            "notes": self.notes,
            "documents_required": self.documents_required,
            "requires_follow_up": self.requires_follow_up,
            "follow_up_date": self.follow_up_date,
            "created_at": self.created_at.isoformat(),
            "confirmed_at": self.confirmed_at.isoformat() if self.confirmed_at else None,
            "reminder_sent": self.reminder_sent,
            "lead_source": self.lead_source,
        }


@dataclass
class AvailableSlot:
    """An available appointment slot."""

    date: str
    time: str
    duration_minutes: int
    advisor_id: str | None
    advisor_name: str | None
    appointment_type: AppointmentType
    is_priority: bool = False


class SchedulingService:
    """Service for managing professional service appointments."""

    def __init__(self):
        """Initialize scheduling service."""
        self._advisors: dict[str, Advisor] = {}
        self._appointments: dict[str, Appointment] = {}
        self._buffer_minutes = 15  # Between appointments

        # Default office hours
        self._default_hours = {
            0: [(dt_time(9, 0), dt_time(18, 0))],  # Monday
            1: [(dt_time(9, 0), dt_time(18, 0))],  # Tuesday
            2: [(dt_time(9, 0), dt_time(18, 0))],  # Wednesday
            3: [(dt_time(9, 0), dt_time(18, 0))],  # Thursday
            4: [(dt_time(9, 0), dt_time(16, 0))],  # Friday
            5: [],  # Saturday - closed
            6: [],  # Sunday - closed
        }

        # Duration by appointment type
        self._durations = {
            AppointmentType.INITIAL_CONSULTATION: 60,
            AppointmentType.FOLLOW_UP: 45,
            AppointmentType.PHONE_CALL: 30,
            AppointmentType.VIDEO_CALL: 45,
            AppointmentType.DOCUMENT_REVIEW: 30,
            AppointmentType.COURT_PREP: 90,
        }

        self._init_default_advisors()

    def _init_default_advisors(self) -> None:
        """Initialize default advisors."""
        default_advisors = [
            Advisor(
                id="adv1",
                name="Dr. Schmidt",
                role=AdvisorRole.LAWYER,
                specializations=["Arbeitsrecht", "Vertragsrecht"],
            ),
            Advisor(
                id="adv2",
                name="Frau Müller",
                role=AdvisorRole.TAX_CONSULTANT,
                specializations=["Einkommensteuer", "Gewerbesteuer"],
            ),
            Advisor(
                id="adv3",
                name="Herr Weber",
                role=AdvisorRole.CONSULTANT,
                specializations=["Unternehmensberatung", "Strategie"],
            ),
        ]

        for advisor in default_advisors:
            advisor.available_hours = self._default_hours.copy()
            self._advisors[advisor.id] = advisor

    def find_available_slots(
        self,
        date: str,
        appointment_type: AppointmentType = AppointmentType.INITIAL_CONSULTATION,
        service_area: str | None = None,
        preferred_advisor: str | None = None,
    ) -> list[AvailableSlot]:
        """
        Find available appointment slots.

        Args:
            date: Date to check (YYYY-MM-DD)
            appointment_type: Type of appointment
            service_area: Service area for advisor matching
            preferred_advisor: Preferred advisor ID

        Returns:
            List of available slots
        """
        try:
            check_date = datetime.strptime(date, "%Y-%m-%d")
        except ValueError:
            return []

        weekday = check_date.weekday()
        duration = self._durations.get(appointment_type, 60)
        available: list[AvailableSlot] = []

        # Get relevant advisors
        advisors = self._get_advisors_for_service(service_area)
        if preferred_advisor and preferred_advisor in self._advisors:
            advisors = [self._advisors[preferred_advisor]]

        for advisor in advisors:
            hours = advisor.available_hours.get(weekday, self._default_hours.get(weekday, []))

            for start_time, end_time in hours:
                current = datetime.combine(check_date.date(), start_time)
                end = datetime.combine(check_date.date(), end_time)

                while current + timedelta(minutes=duration) <= end:
                    time_str = current.strftime("%H:%M")

                    # Check if slot is free
                    if self._is_slot_available(advisor.id, date, time_str, duration):
                        available.append(AvailableSlot(
                            date=date,
                            time=time_str,
                            duration_minutes=duration,
                            advisor_id=advisor.id,
                            advisor_name=advisor.name,
                            appointment_type=appointment_type,
                        ))

                    current += timedelta(minutes=30)  # 30-minute intervals

        return available

    def _get_advisors_for_service(self, service_area: str | None) -> list[Advisor]:
        """Get advisors matching a service area."""
        if not service_area:
            return list(self._advisors.values())

        matching = []
        service_lower = service_area.lower()

        role_mapping = {
            "legal": AdvisorRole.LAWYER,
            "tax": AdvisorRole.TAX_CONSULTANT,
            "audit": AdvisorRole.AUDITOR,
            "consulting": AdvisorRole.CONSULTANT,
            "architecture": AdvisorRole.ARCHITECT,
        }

        target_role = role_mapping.get(service_lower)
        if target_role:
            for advisor in self._advisors.values():
                if advisor.role == target_role:
                    matching.append(advisor)

        return matching or list(self._advisors.values())

    def _is_slot_available(
        self,
        advisor_id: str,
        date: str,
        time: str,
        duration: int,
    ) -> bool:
        """Check if a slot is available."""
        # Check existing appointments
        for appt in self._appointments.values():
            if appt.advisor_id != advisor_id:
                continue
            if appt.date != date:
                continue
            if appt.status in [AppointmentStatus.CANCELLED, AppointmentStatus.RESCHEDULED]:
                continue

            # Check time overlap
            appt_start = datetime.strptime(f"{appt.date} {appt.time}", "%Y-%m-%d %H:%M")
            appt_end = appt_start + timedelta(minutes=appt.duration_minutes + self._buffer_minutes)

            check_start = datetime.strptime(f"{date} {time}", "%Y-%m-%d %H:%M")
            check_end = check_start + timedelta(minutes=duration)

            if appt_start < check_end and check_start < appt_end:
                return False

        return True

    def create_appointment(
        self,
        client_name: str,
        client_phone: str,
        date: str,
        time: str,
        appointment_type: AppointmentType = AppointmentType.INITIAL_CONSULTATION,
        client_email: str | None = None,
        company: str | None = None,
        advisor_id: str | None = None,
        service_area: str | None = None,
        topic: str | None = None,
        notes: str | None = None,
        lead_source: str | None = None,
    ) -> Appointment | None:
        """
        Create a new appointment.

        Returns:
            Created Appointment or None if no availability
        """
        duration = self._durations.get(appointment_type, 60)

        # Find advisor if not specified
        if not advisor_id:
            slots = self.find_available_slots(date, appointment_type, service_area)
            matching = [s for s in slots if s.time == time]
            if matching:
                advisor_id = matching[0].advisor_id
            elif slots:
                advisor_id = slots[0].advisor_id

        # Check availability
        if advisor_id and not self._is_slot_available(advisor_id, date, time, duration):
            return None

        # Create appointment
        appointment = Appointment(
            id=str(uuid.uuid4())[:8],
            client_name=client_name,
            client_phone=client_phone,
            client_email=client_email,
            company=company,
            appointment_type=appointment_type,
            advisor_id=advisor_id,
            date=date,
            time=time,
            duration_minutes=duration,
            status=AppointmentStatus.CONFIRMED,
            service_area=service_area,
            topic=topic,
            notes=notes,
            lead_source=lead_source,
            confirmed_at=datetime.now(),
        )

        # Set default documents required
        appointment.documents_required = self._get_required_documents(
            appointment_type, service_area
        )

        self._appointments[appointment.id] = appointment
        return appointment

    def _get_required_documents(
        self,
        appointment_type: AppointmentType,
        service_area: str | None,
    ) -> list[str]:
        """Get list of required documents for appointment type."""
        docs = ["Personalausweis/Reisepass"]

        if service_area == "legal":
            docs.extend([
                "Relevante Verträge und Korrespondenz",
                "Bisherige Schriftwechsel",
            ])
        elif service_area == "tax":
            docs.extend([
                "Letzte Steuerbescheide",
                "Einkommensnachweise",
                "Belege und Rechnungen",
            ])
        elif service_area == "consulting":
            docs.extend([
                "Geschäftszahlen/Jahresabschlüsse",
                "Organisationsübersicht",
            ])

        if appointment_type == AppointmentType.INITIAL_CONSULTATION:
            docs.append("Kurze schriftliche Zusammenfassung des Anliegens")

        return docs

    def cancel_appointment(self, appointment_id: str) -> bool:
        """Cancel an appointment by ID."""
        if appointment_id not in self._appointments:
            return False

        self._appointments[appointment_id].status = AppointmentStatus.CANCELLED
        return True

    def reschedule_appointment(
        self,
        appointment_id: str,
        new_date: str,
        new_time: str,
    ) -> Appointment | None:
        """Reschedule an existing appointment."""
        if appointment_id not in self._appointments:
            return None

        old_appt = self._appointments[appointment_id]

        # Check availability for new slot
        if old_appt.advisor_id:
            if not self._is_slot_available(
                old_appt.advisor_id,
                new_date,
                new_time,
                old_appt.duration_minutes,
            ):
                return None

        # Mark old as rescheduled
        old_appt.status = AppointmentStatus.RESCHEDULED

        # Create new appointment
        new_appt = Appointment(
            id=str(uuid.uuid4())[:8],
            client_name=old_appt.client_name,
            client_phone=old_appt.client_phone,
            client_email=old_appt.client_email,
            company=old_appt.company,
            appointment_type=old_appt.appointment_type,
            advisor_id=old_appt.advisor_id,
            date=new_date,
            time=new_time,
            duration_minutes=old_appt.duration_minutes,
            status=AppointmentStatus.CONFIRMED,
            service_area=old_appt.service_area,
            topic=old_appt.topic,
            notes=f"Umgebucht von {old_appt.date} {old_appt.time}. {old_appt.notes or ''}",
            documents_required=old_appt.documents_required,
            lead_source=old_appt.lead_source,
            confirmed_at=datetime.now(),
        )

        self._appointments[new_appt.id] = new_appt
        return new_appt

    def find_appointment(
        self,
        client_name: str | None = None,
        client_phone: str | None = None,
        date: str | None = None,
    ) -> Appointment | None:
        """Find an appointment by client details."""
        for appt in self._appointments.values():
            if appt.status in [AppointmentStatus.CANCELLED, AppointmentStatus.RESCHEDULED]:
                continue

            name_match = not client_name or client_name.lower() in appt.client_name.lower()
            phone_match = not client_phone or client_phone in appt.client_phone
            date_match = not date or appt.date == date

            if name_match and phone_match and date_match:
                return appt

        return None

    def get_appointments_for_date(self, date: str) -> list[Appointment]:
        """Get all appointments for a specific date."""
        return [
            appt for appt in self._appointments.values()
            if appt.date == date and appt.status not in [
                AppointmentStatus.CANCELLED,
                AppointmentStatus.RESCHEDULED,
            ]
        ]

    def get_advisor(self, advisor_id: str) -> Advisor | None:
        """Get advisor by ID."""
        return self._advisors.get(advisor_id)


# Singleton instance
_scheduling_service: SchedulingService | None = None


def get_scheduling_service() -> SchedulingService:
    """Get or create scheduling service singleton."""
    global _scheduling_service
    if _scheduling_service is None:
        _scheduling_service = SchedulingService()
    return _scheduling_service
