"""Elektro-Betrieb Service Layer.

Orchestrates job creation, calendar integration, and conversation transcript
storage for the electrician company dashboard.
"""
from __future__ import annotations

from datetime import datetime, date, timedelta
from typing import Any
from uuid import UUID

from itf_shared import get_logger

from phone_agent.db.models.crm import ContactModel
from phone_agent.db.models.handwerk import JobModel, JobStatus, JobUrgency
from phone_agent.db.models.elektro import ConversationTranscriptModel
from phone_agent.db.repositories import ContactRepository, JobRepository, TranscriptRepository
from phone_agent.integrations.calendar.local import LocalCalendarIntegration
from phone_agent.integrations.calendar.base import TimeSlot
from phone_agent.services.handwerk_service import HandwerkService

log = get_logger(__name__)


class ElektroService:
    """Service for Elektro-Betrieb operations.

    Provides:
    - Job creation with conversation transcript storage
    - Calendar slot management for AI-offered appointments
    - Dashboard statistics and job listings
    """

    def __init__(
        self,
        contact_repo: ContactRepository,
        job_repo: JobRepository,
        transcript_repo: TranscriptRepository,
        calendar: LocalCalendarIntegration | None = None,
    ):
        """Initialize the service.

        Args:
            contact_repo: Contact repository
            job_repo: Job repository
            transcript_repo: Transcript repository
            calendar: Optional calendar integration
        """
        self.contact_repo = contact_repo
        self.job_repo = job_repo
        self.transcript_repo = transcript_repo
        self.calendar = calendar or LocalCalendarIntegration()

        # Initialize HandwerkService for job creation
        self._handwerk_service = HandwerkService(
            contact_repo=contact_repo,
            job_repo=job_repo,
        )

    async def create_job_with_transcript(
        self,
        customer_name: str,
        description: str,
        urgency: str,
        customer_phone: str | None = None,
        address: dict[str, Any] | None = None,
        session_id: str | None = None,
        conversation_turns: list[dict[str, Any]] | None = None,
        detected_language: str = "de",
        preferred_slot_id: str | None = None,
    ) -> dict[str, Any]:
        """Create a job with conversation transcript.

        Args:
            customer_name: Customer name
            description: Problem description
            urgency: Urgency level (notfall, dringend, normal, routine)
            customer_phone: Customer phone number
            address: Customer address dict
            session_id: Voice session ID
            conversation_turns: List of conversation turns
            detected_language: Primary language of conversation
            preferred_slot_id: Selected time slot ID

        Returns:
            Dict with job details and transcript ID
        """
        log.info(
            "Creating elektro job with transcript",
            customer=customer_name,
            urgency=urgency,
            session_id=session_id,
        )

        # 1. Create job via HandwerkService
        job_result = await self._handwerk_service.create_job_from_intake(
            customer_name=customer_name,
            description=description,
            trade_category="elektro",
            urgency=urgency,
            customer_phone=customer_phone,
            address=address,
            session_id=session_id,
            source_language=detected_language,
        )

        job_id = UUID(job_result["job_id"])
        transcript_id = None

        # 2. Store conversation transcript if provided
        if session_id and conversation_turns:
            try:
                transcript = await self.transcript_repo.create_from_session(
                    session_id=session_id,
                    turns=conversation_turns,
                    language=detected_language,
                    urgency=urgency,
                    trade="elektro",
                    problem_description=description,
                    job_id=job_id,
                )
                transcript_id = str(transcript.id)
                log.info(
                    "Transcript stored",
                    transcript_id=transcript_id,
                    turns=len(conversation_turns),
                )
            except Exception as e:
                log.warning(
                    "Failed to store transcript",
                    error=str(e),
                    session_id=session_id,
                )

        # 3. Book slot if selected
        if preferred_slot_id:
            try:
                await self._book_slot(job_id, preferred_slot_id)
                log.info(
                    "Slot booked",
                    job_id=str(job_id),
                    slot_id=preferred_slot_id,
                )
            except Exception as e:
                log.warning(
                    "Failed to book slot",
                    error=str(e),
                    slot_id=preferred_slot_id,
                )

        return {
            **job_result,
            "transcript_id": transcript_id,
            "slot_booked": preferred_slot_id is not None,
        }

    async def get_available_slots(
        self,
        urgency: str = "normal",
        days_ahead: int = 7,
        duration_minutes: int = 60,
    ) -> list[dict[str, Any]]:
        """Get available time slots for scheduling.

        Adjusts slot search based on urgency:
        - notfall: Today only, next 3 available
        - dringend: Today + tomorrow, next 5 available
        - normal: Next 7 days, next 10 available

        Args:
            urgency: Urgency level
            days_ahead: Default days to look ahead
            duration_minutes: Required slot duration

        Returns:
            List of available slots as dicts
        """
        today = date.today()

        if urgency == "notfall":
            # Emergency: today only
            end_date = today
            limit = 3
        elif urgency == "dringend":
            # Urgent: today + tomorrow
            end_date = today + timedelta(days=1)
            limit = 5
        else:
            # Normal: next week
            end_date = today + timedelta(days=days_ahead)
            limit = 10

        try:
            slots = await self.calendar.get_available_slots(
                start_date=today,
                end_date=end_date,
                duration_minutes=duration_minutes,
            )

            return [slot.to_dict() for slot in slots[:limit]]
        except Exception as e:
            log.warning("Failed to get calendar slots", error=str(e))
            return []

    async def format_slots_for_ai(
        self,
        urgency: str = "normal",
        language: str = "de",
    ) -> str:
        """Format available slots for AI to speak to customer.

        Args:
            urgency: Urgency level
            language: Response language

        Returns:
            Human-readable slot options
        """
        slots = await self.get_available_slots(urgency=urgency)

        if not slots:
            messages = {
                "de": "Leider haben wir momentan keine freien Termine. Wir rufen Sie zurück.",
                "en": "Unfortunately, we have no available slots right now. We will call you back.",
                "ru": "К сожалению, у нас сейчас нет свободных мест. Мы перезвоним вам.",
                "tr": "Maalesef şu anda müsait randevumuz yok. Sizi arayacağız.",
            }
            return messages.get(language, messages["de"])

        # Format slots
        def format_slot(slot: dict) -> str:
            dt = datetime.fromisoformat(slot["start"])
            weekdays_de = ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"]
            weekday = weekdays_de[dt.weekday()]
            return f"{weekday} um {dt.strftime('%H:%M')} Uhr"

        slot_texts = [format_slot(s) for s in slots[:3]]

        templates = {
            "de": f"Wir haben folgende Termine frei: {', oder '.join(slot_texts)}. Welcher passt Ihnen?",
            "en": f"We have these slots available: {', or '.join(slot_texts)}. Which works for you?",
            "ru": f"У нас есть свободные места: {', или '.join(slot_texts)}. Какой вам подходит?",
            "tr": f"Şu randevularımız müsait: {', veya '.join(slot_texts)}. Hangisi size uygun?",
        }

        return templates.get(language, templates["de"])

    async def get_jobs_list(
        self,
        status: str | None = None,
        urgency: str | None = None,
        limit: int = 50,
        offset: int = 0,
        days_back: int | None = 30,
    ) -> list[dict[str, Any]]:
        """Get list of elektro jobs for dashboard.

        Args:
            status: Filter by status
            urgency: Filter by urgency
            limit: Maximum number to return
            offset: Pagination offset
            days_back: Only return jobs from last N days

        Returns:
            List of job dicts with contact and transcript info
        """
        jobs = await self.job_repo.list_by_trade(
            trade_category="elektro",
            status=status,
            urgency=urgency,
            limit=limit,
            offset=offset,
            days_back=days_back,
        )

        result = []
        for job in jobs:
            job_dict = job.to_dict() if hasattr(job, 'to_dict') else {
                "id": str(job.id),
                "job_number": job.job_number,
                "title": job.title,
                "description": job.description,
                "status": job.status,
                "urgency": job.urgency,
                "trade_category": job.trade_category,
                "created_at": job.created_at.isoformat() if job.created_at else None,
            }

            # Add contact info if available
            if job.contact:
                job_dict["customer"] = {
                    "name": f"{job.contact.first_name} {job.contact.last_name}".strip(),
                    "phone": job.contact.phone_primary,
                    "email": job.contact.email,
                }

            # Add transcript summary if available
            if job.transcript:
                job_dict["transcript"] = {
                    "id": str(job.transcript.id),
                    "turn_count": job.transcript.turn_count,
                    "language": job.transcript.language,
                }

            result.append(job_dict)

        return result

    async def get_job_detail(self, job_id: UUID) -> dict[str, Any] | None:
        """Get detailed job information including transcript.

        Args:
            job_id: Job UUID

        Returns:
            Job dict with full transcript or None
        """
        # Use get_with_relations to eager-load contact and transcript
        job = await self.job_repo.get_with_relations(job_id)
        if not job:
            return None

        result = job.to_dict() if hasattr(job, 'to_dict') else {
            "id": str(job.id),
            "job_number": job.job_number,
            "title": job.title,
            "description": job.description,
            "status": job.status,
            "urgency": job.urgency,
        }

        # Add full contact
        if job.contact:
            result["customer"] = {
                "id": str(job.contact.id),
                "name": f"{job.contact.first_name} {job.contact.last_name}".strip(),
                "phone": job.contact.phone_primary,
                "email": job.contact.email,
                "street": job.contact.street,
                "zip": job.contact.zip_code,
                "city": job.contact.city,
            }

        # Add full transcript
        if job.transcript:
            result["transcript"] = job.transcript.to_dict()

        return result

    async def get_dashboard_stats(self, days_back: int = 7) -> dict[str, Any]:
        """Get dashboard statistics.

        Args:
            days_back: Calculate stats for last N days

        Returns:
            Dict with KPI stats
        """
        cutoff = datetime.now() - timedelta(days=days_back)

        # Count by status
        total = await self.job_repo.count_by_trade("elektro", days_back=days_back)
        today_count = await self.job_repo.count_by_trade("elektro", days_back=1)

        # Count by urgency
        urgency_counts = await self.transcript_repo.count_by_urgency(
            days_back=days_back,
            trade="elektro",
        )

        # Count pending/open jobs
        open_statuses = [JobStatus.REQUESTED, JobStatus.QUOTED, JobStatus.ACCEPTED, JobStatus.SCHEDULED]
        open_count = 0
        for status in open_statuses:
            open_count += await self.job_repo.count_by_status_and_trade(status, "elektro")

        return {
            "total_jobs": total,
            "today_jobs": today_count,
            "open_jobs": open_count,
            "emergencies": urgency_counts.get("notfall", 0),
            "urgent": urgency_counts.get("dringend", 0),
            "normal": urgency_counts.get("normal", 0),
            "period_days": days_back,
        }

    async def _book_slot(self, job_id: UUID, slot_id: str) -> None:
        """Book a calendar slot for a job.

        Args:
            job_id: Job UUID
            slot_id: Slot UUID
        """
        # Get job to update scheduled date/time
        job = await self.job_repo.get(job_id)
        if not job:
            return

        # Book the slot
        try:
            slot = await self.calendar.book_slot(
                slot_id=UUID(slot_id),
                customer_name=f"Job {job.job_number}",
                job_id=str(job_id),
            )

            # Update job with scheduled time
            if slot:
                job.scheduled_date = slot.start.date()
                job.scheduled_time = slot.start.time()
                job.status = JobStatus.SCHEDULED
                await self.job_repo.update(job)

        except Exception as e:
            log.error("Failed to book slot", error=str(e), slot_id=slot_id)
            raise
