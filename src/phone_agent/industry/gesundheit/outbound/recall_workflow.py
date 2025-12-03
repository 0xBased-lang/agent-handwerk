"""Recall Campaign Workflow for Healthcare.

Integration with RecallService for proactive patient outreach:
- Preventive care reminders (Vorsorge)
- Vaccination campaigns (Impfkampagnen)
- Chronic disease management (DMP)
- Lab results follow-up
- Custom campaigns

Uses existing RecallService templates and phone scripts.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Callable
from uuid import UUID, uuid4
import asyncio

import structlog

from phone_agent.industry.gesundheit.outbound.dialer import (
    OutboundDialer,
    CallPriority,
)
from phone_agent.industry.gesundheit.outbound.conversation_outbound import (
    OutboundConversationManager,
    OutboundCallType,
    OutboundOutcome,
)
from phone_agent.industry.gesundheit.recall import (
    RecallService,
    RecallCampaign,
    RecallPatient,
    RecallAttempt,
    RecallType,
    RecallStatus,
    ContactMethod,
    CAMPAIGN_TEMPLATES,
    get_recall_service,
)
from phone_agent.industry.gesundheit.scheduling import (
    SchedulingService,
    SchedulingPreferences,
    AppointmentType,
    Patient,
    get_scheduling_service,
)
from phone_agent.industry.gesundheit.compliance import (
    ConsentManager,
    ConsentType,
    AuditLogger,
    get_consent_manager,
    get_audit_logger,
)


log = structlog.get_logger(__name__)


# Map recall types to outbound call types
RECALL_TYPE_TO_CALL_TYPE: dict[RecallType, OutboundCallType] = {
    RecallType.PREVENTIVE: OutboundCallType.RECALL_CAMPAIGN,
    RecallType.VACCINATION: OutboundCallType.RECALL_CAMPAIGN,
    RecallType.FOLLOWUP: OutboundCallType.RECALL_CAMPAIGN,
    RecallType.CHRONIC: OutboundCallType.RECALL_CAMPAIGN,
    RecallType.NO_SHOW: OutboundCallType.NO_SHOW_FOLLOWUP,
    RecallType.LAB_RESULTS: OutboundCallType.RECALL_CAMPAIGN,
    RecallType.PRESCRIPTION: OutboundCallType.RECALL_CAMPAIGN,
    RecallType.CUSTOM: OutboundCallType.RECALL_CAMPAIGN,
}

# Map recall types to appointment types
RECALL_TYPE_TO_APPOINTMENT_TYPE: dict[RecallType, AppointmentType] = {
    RecallType.PREVENTIVE: AppointmentType.PREVENTIVE,
    RecallType.VACCINATION: AppointmentType.VACCINATION,
    RecallType.FOLLOWUP: AppointmentType.FOLLOWUP,
    RecallType.CHRONIC: AppointmentType.REGULAR,
    RecallType.NO_SHOW: AppointmentType.REGULAR,
    RecallType.LAB_RESULTS: AppointmentType.LAB,
    RecallType.PRESCRIPTION: AppointmentType.REGULAR,
    RecallType.CUSTOM: AppointmentType.REGULAR,
}


class RecallCallStatus(str, Enum):
    """Status of a recall call within the workflow."""

    QUEUED = "queued"
    CALLING = "calling"
    APPOINTMENT_MADE = "appointment_made"
    DECLINED = "declined"
    UNREACHABLE = "unreachable"
    RETRY_SCHEDULED = "retry_scheduled"
    SMS_FALLBACK = "sms_fallback"
    COMPLETED = "completed"


@dataclass
class RecallCallTask:
    """Task for calling a single patient in a recall campaign."""

    id: UUID
    recall_patient: RecallPatient
    campaign: RecallCampaign

    # Call state
    status: RecallCallStatus = RecallCallStatus.QUEUED
    current_attempt_id: UUID | None = None

    # Outcome
    outcome: OutboundOutcome | None = None
    appointment_id: UUID | None = None
    call_duration_seconds: int | None = None

    # Timestamps
    queued_at: datetime = field(default_factory=datetime.now)
    completed_at: datetime | None = None

    @property
    def priority(self) -> CallPriority:
        """Calculate call priority from patient priority."""
        patient_priority = self.recall_patient.priority
        if patient_priority >= 8:
            return CallPriority.URGENT
        elif patient_priority >= 6:
            return CallPriority.HIGH
        elif patient_priority >= 4:
            return CallPriority.NORMAL
        else:
            return CallPriority.LOW


@dataclass
class RecallCampaignStats:
    """Statistics for a recall campaign execution."""

    campaign_id: UUID
    campaign_name: str
    recall_type: RecallType

    # Counts
    total_patients: int = 0
    calls_attempted: int = 0
    appointments_made: int = 0
    declined: int = 0
    unreachable: int = 0
    pending: int = 0

    # Timing
    started_at: datetime = field(default_factory=datetime.now)
    completed_at: datetime | None = None

    @property
    def success_rate(self) -> float:
        """Appointment success rate."""
        if self.calls_attempted == 0:
            return 0.0
        return (self.appointments_made / self.calls_attempted) * 100

    @property
    def contact_rate(self) -> float:
        """Rate of patients successfully contacted."""
        if self.calls_attempted == 0:
            return 0.0
        contacted = self.appointments_made + self.declined
        return (contacted / self.calls_attempted) * 100

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "campaign_id": str(self.campaign_id),
            "campaign_name": self.campaign_name,
            "recall_type": self.recall_type.value,
            "total_patients": self.total_patients,
            "calls_attempted": self.calls_attempted,
            "appointments_made": self.appointments_made,
            "declined": self.declined,
            "unreachable": self.unreachable,
            "pending": self.pending,
            "success_rate": round(self.success_rate, 1),
            "contact_rate": round(self.contact_rate, 1),
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }


class RecallCampaignWorkflow:
    """Workflow for executing recall campaigns via outbound calls."""

    def __init__(
        self,
        dialer: OutboundDialer,
        recall_service: RecallService | None = None,
        scheduling: SchedulingService | None = None,
        consent_manager: ConsentManager | None = None,
        audit_logger: AuditLogger | None = None,
        practice_name: str = "Ihre Arztpraxis",
    ):
        """Initialize recall campaign workflow.

        Args:
            dialer: Outbound dialer service
            recall_service: Recall service (uses singleton if not provided)
            scheduling: Scheduling service for booking appointments
            consent_manager: Consent manager for DSGVO compliance
            audit_logger: Audit logger for compliance tracking
            practice_name: Name of the practice for scripts
        """
        self._dialer = dialer
        self._recall = recall_service or get_recall_service()
        self._scheduling = scheduling or get_scheduling_service()
        self._consent = consent_manager or get_consent_manager()
        self._audit = audit_logger or get_audit_logger()
        self._practice_name = practice_name

        # Active campaigns
        self._active_campaigns: dict[UUID, RecallCampaignStats] = {}
        self._tasks: dict[UUID, RecallCallTask] = {}

        # Callbacks
        self._on_call_complete: Callable[[RecallCallTask], Any] | None = None

    async def start_campaign(
        self,
        campaign_id: UUID,
        max_calls: int | None = None,
    ) -> RecallCampaignStats:
        """Start calling patients in a recall campaign.

        Args:
            campaign_id: ID of the campaign to execute
            max_calls: Maximum number of calls to queue (for batching)

        Returns:
            Campaign statistics
        """
        # Get campaign from recall service
        campaign = self._recall._campaigns.get(campaign_id)
        if not campaign:
            raise ValueError(f"Campaign {campaign_id} not found")

        if not campaign.active:
            raise ValueError(f"Campaign {campaign_id} is not active")

        log.info(
            "Starting recall campaign",
            campaign_id=str(campaign_id),
            campaign_name=campaign.name,
            recall_type=campaign.recall_type.value,
        )

        # Initialize stats
        stats = RecallCampaignStats(
            campaign_id=campaign_id,
            campaign_name=campaign.name,
            recall_type=campaign.recall_type,
        )
        self._active_campaigns[campaign_id] = stats

        # Get patients to call
        patients = self._get_campaign_patients(campaign_id)
        stats.total_patients = len(patients)

        if max_calls:
            patients = patients[:max_calls]

        # Queue calls for each patient
        for patient in patients:
            task = await self._create_call_task(campaign, patient)
            if task:
                self._tasks[task.id] = task
                await self._queue_recall_call(task)
                stats.pending += 1

        log.info(
            "Recall campaign queued",
            campaign_id=str(campaign_id),
            total_patients=stats.total_patients,
            calls_queued=stats.pending,
        )

        return stats

    def _get_campaign_patients(self, campaign_id: UUID) -> list[RecallPatient]:
        """Get patients ready to be called in a campaign.

        Returns patients sorted by priority.
        """
        patients = []

        for patient in self._recall._patients.values():
            if patient.campaign_id != campaign_id:
                continue

            # Only include callable statuses
            if patient.status not in [RecallStatus.PENDING, RecallStatus.IN_PROGRESS]:
                continue

            # Check if ready for next attempt
            if patient.next_attempt and patient.next_attempt > datetime.now():
                continue

            patients.append(patient)

        # Sort by priority (highest first)
        patients.sort(key=lambda p: -p.priority)

        return patients

    async def _create_call_task(
        self,
        campaign: RecallCampaign,
        patient: RecallPatient,
    ) -> RecallCallTask | None:
        """Create a call task for a patient.

        Returns:
            RecallCallTask or None if patient shouldn't be called
        """
        # Check consent for phone contact
        has_consent = await self._consent.check_consent(
            patient_id=patient.patient_id,
            consent_type=ConsentType.PHONE_CONTACT,
        )

        if not has_consent:
            log.info(
                "Skipping recall - no phone consent",
                patient_id=str(patient.patient_id),
                campaign_id=str(campaign.id),
            )
            return None

        # Check max attempts
        if patient.attempts >= campaign.max_attempts:
            patient.status = RecallStatus.UNREACHABLE
            log.info(
                "Skipping recall - max attempts reached",
                patient_id=str(patient.patient_id),
                attempts=patient.attempts,
            )
            return None

        task = RecallCallTask(
            id=uuid4(),
            recall_patient=patient,
            campaign=campaign,
        )

        return task

    async def _queue_recall_call(self, task: RecallCallTask) -> None:
        """Queue a recall call for a patient."""
        campaign = task.campaign
        patient = task.recall_patient

        # Get personalized phone script
        phone_script = self._recall.get_phone_script(
            campaign_id=campaign.id,
            patient=patient,
            practice_name=self._practice_name,
        )

        # Start attempt in recall service
        attempt = self._recall.start_attempt(
            recall_patient_id=patient.id,
            method=ContactMethod.PHONE,
        )
        task.current_attempt_id = attempt.id

        # Build call metadata
        call_type = RECALL_TYPE_TO_CALL_TYPE.get(
            campaign.recall_type, OutboundCallType.RECALL_CAMPAIGN
        )

        metadata = {
            "workflow": "recall_campaign",
            "task_id": str(task.id),
            "campaign_id": str(campaign.id),
            "campaign_name": campaign.name,
            "recall_type": campaign.recall_type.value,
            "patient_id": str(patient.patient_id),
            "recall_patient_id": str(patient.id),
            "attempt_id": str(attempt.id),
            "attempt_number": patient.attempts,
            "phone_script": phone_script,
            "call_type": call_type.value,
            "appointment_type": RECALL_TYPE_TO_APPOINTMENT_TYPE.get(
                campaign.recall_type, AppointmentType.REGULAR
            ).value,
        }

        # Queue the call
        await self._dialer.queue_call(
            patient_id=patient.patient_id,
            phone_number=patient.phone,
            call_type=call_type,
            priority=task.priority,
            metadata=metadata,
            callback=lambda result: self._handle_call_result(task.id, result),
        )

        task.status = RecallCallStatus.CALLING

        log.info(
            "Queued recall call",
            task_id=str(task.id),
            patient_name=f"{patient.first_name} {patient.last_name}",
            campaign_name=campaign.name,
            attempt_number=patient.attempts,
            priority=task.priority.name,
        )

    async def _handle_call_result(
        self,
        task_id: UUID,
        result: dict[str, Any],
    ) -> None:
        """Handle the result of a recall call.

        Args:
            task_id: ID of the call task
            result: Call result from dialer
        """
        task = self._tasks.get(task_id)
        if not task:
            log.warning("Task not found for call result", task_id=str(task_id))
            return

        patient = task.recall_patient
        campaign = task.campaign
        stats = self._active_campaigns.get(campaign.id)

        outcome = result.get("outcome")
        task.outcome = outcome
        task.call_duration_seconds = result.get("duration_seconds")

        # Map outcome to recall status
        recall_outcome = self._map_outcome_to_recall_status(outcome)

        # Complete attempt in recall service
        if task.current_attempt_id:
            self._recall.complete_attempt(
                attempt_id=task.current_attempt_id,
                outcome=recall_outcome,
                transcript=result.get("transcript"),
                notes=result.get("notes"),
                appointment_id=result.get("appointment_id"),
            )

        # Update stats
        if stats:
            stats.calls_attempted += 1
            stats.pending = max(0, stats.pending - 1)

        if outcome == OutboundOutcome.APPOINTMENT_CONFIRMED:
            task.status = RecallCallStatus.APPOINTMENT_MADE
            task.appointment_id = result.get("appointment_id")
            if stats:
                stats.appointments_made += 1

            log.info(
                "Recall call success - appointment made",
                task_id=str(task.id),
                patient_name=f"{patient.first_name} {patient.last_name}",
            )

        elif outcome == OutboundOutcome.DECLINED:
            task.status = RecallCallStatus.DECLINED
            if stats:
                stats.declined += 1

            log.info(
                "Recall call - patient declined",
                task_id=str(task.id),
                patient_name=f"{patient.first_name} {patient.last_name}",
            )

        elif outcome == OutboundOutcome.NO_ANSWER:
            # Check if we should retry or mark unreachable
            if patient.attempts >= campaign.max_attempts:
                task.status = RecallCallStatus.UNREACHABLE
                if stats:
                    stats.unreachable += 1

                # Send SMS fallback if configured
                if ContactMethod.SMS in campaign.contact_methods:
                    await self._send_sms_fallback(task)
            else:
                task.status = RecallCallStatus.RETRY_SCHEDULED

                log.info(
                    "Recall call - no answer, will retry",
                    task_id=str(task.id),
                    attempts=patient.attempts,
                    max_attempts=campaign.max_attempts,
                )

        else:
            task.status = RecallCallStatus.COMPLETED
            if stats:
                stats.unreachable += 1

        task.completed_at = datetime.now()

        # Log audit event
        await self._audit.log_event(
            event_type="recall_call_completed",
            patient_id=patient.patient_id,
            details={
                "task_id": str(task.id),
                "campaign_id": str(campaign.id),
                "recall_type": campaign.recall_type.value,
                "outcome": outcome.value if outcome else None,
                "attempts": patient.attempts,
                "appointment_id": str(task.appointment_id) if task.appointment_id else None,
            },
        )

        # Notify callback
        if self._on_call_complete:
            self._on_call_complete(task)

        log.info(
            "Recall call completed",
            task_id=str(task.id),
            status=task.status.value,
            outcome=outcome.value if outcome else None,
        )

    def _map_outcome_to_recall_status(self, outcome: OutboundOutcome | None) -> RecallStatus:
        """Map outbound outcome to recall status."""
        if outcome == OutboundOutcome.APPOINTMENT_CONFIRMED:
            return RecallStatus.APPOINTMENT_MADE
        elif outcome == OutboundOutcome.DECLINED:
            return RecallStatus.DECLINED
        elif outcome == OutboundOutcome.NO_ANSWER:
            return RecallStatus.UNREACHABLE
        elif outcome == OutboundOutcome.VOICEMAIL_LEFT:
            return RecallStatus.CONTACTED
        else:
            return RecallStatus.UNREACHABLE

    async def _send_sms_fallback(self, task: RecallCallTask) -> None:
        """Send SMS fallback after failed call attempts."""
        campaign = task.campaign
        patient = task.recall_patient

        if not campaign.sms_template:
            return

        # Personalize SMS
        sms_text = campaign.sms_template.replace("{practice_name}", self._practice_name)
        sms_text = sms_text.replace("{first_name}", patient.first_name)
        sms_text = sms_text.replace("{last_name}", patient.last_name)

        log.info(
            "Sending SMS fallback",
            task_id=str(task.id),
            patient_phone=patient.phone[:8] + "...",
        )

        # In production: Send via SMS gateway
        # await sms_gateway.send(patient.phone, sms_text)

        task.status = RecallCallStatus.SMS_FALLBACK

    async def book_appointment_during_call(
        self,
        task_id: UUID,
        patient_preferences: dict[str, Any],
    ) -> dict[str, Any]:
        """Book an appointment during a recall call.

        Called by the conversation manager when patient agrees to an appointment.

        Args:
            task_id: ID of the call task
            patient_preferences: Preferences from the conversation

        Returns:
            Booking result with appointment details
        """
        task = self._tasks.get(task_id)
        if not task:
            return {"success": False, "error": "Task not found"}

        patient = task.recall_patient
        campaign = task.campaign

        # Determine appointment type
        appointment_type = RECALL_TYPE_TO_APPOINTMENT_TYPE.get(
            campaign.recall_type, AppointmentType.REGULAR
        )

        # Build scheduling preferences
        prefs = SchedulingPreferences(
            appointment_type=appointment_type,
            preferred_time=patient_preferences.get("time_preference"),
            flexible_date=patient_preferences.get("flexible", True),
            flexible_provider=patient_preferences.get("flexible_provider", True),
        )

        # Find available slots
        slots = await self._scheduling.find_slots(prefs, limit=3)

        if not slots:
            return {
                "success": False,
                "error": "no_slots_available",
                "message": "Leider sind aktuell keine Termine verfügbar.",
            }

        # If patient selected a slot
        selected_slot_id = patient_preferences.get("selected_slot_id")
        if selected_slot_id:
            # Book the selected slot
            # In production, would get full patient object from PVS
            mock_patient = Patient(
                id=patient.patient_id,
                first_name=patient.first_name,
                last_name=patient.last_name,
                date_of_birth=None,  # Would come from PVS
                phone=patient.phone,
                email=patient.email,
            )

            try:
                appointment = await self._scheduling.book_appointment(
                    slot_id=selected_slot_id,
                    patient=mock_patient,
                    reason=f"Recall: {campaign.name}",
                    appointment_type=appointment_type,
                )

                # Update recall patient
                patient.appointment_id = appointment.id
                patient.status = RecallStatus.APPOINTMENT_MADE

                return {
                    "success": True,
                    "appointment_id": str(appointment.id),
                    "appointment_time": appointment.slot.start.isoformat(),
                    "provider_name": appointment.slot.provider_name,
                    "message": self._scheduling.format_slot_for_speech(appointment.slot),
                }

            except ValueError as e:
                return {
                    "success": False,
                    "error": "booking_failed",
                    "message": str(e),
                }

        # Return available slots for patient to choose
        return {
            "success": True,
            "action": "offer_slots",
            "slots": [
                {
                    "id": str(slot.id),
                    "description": self._scheduling.format_slot_for_speech(slot),
                    "start": slot.start.isoformat(),
                    "provider_name": slot.provider_name,
                }
                for slot in slots
            ],
        }

    def on_call_complete(self, callback: Callable[[RecallCallTask], Any]) -> None:
        """Set callback for call completion."""
        self._on_call_complete = callback

    def get_campaign_stats(self, campaign_id: UUID) -> RecallCampaignStats | None:
        """Get statistics for an active campaign."""
        return self._active_campaigns.get(campaign_id)

    def get_all_campaign_stats(self) -> list[RecallCampaignStats]:
        """Get statistics for all active campaigns."""
        return list(self._active_campaigns.values())

    def get_task(self, task_id: UUID) -> RecallCallTask | None:
        """Get a call task by ID."""
        return self._tasks.get(task_id)

    async def pause_campaign(self, campaign_id: UUID) -> bool:
        """Pause a recall campaign."""
        campaign = self._recall._campaigns.get(campaign_id)
        if campaign:
            campaign.active = False
            log.info("Recall campaign paused", campaign_id=str(campaign_id))
            return True
        return False

    async def resume_campaign(self, campaign_id: UUID) -> bool:
        """Resume a paused recall campaign."""
        campaign = self._recall._campaigns.get(campaign_id)
        if campaign:
            campaign.active = True
            log.info("Recall campaign resumed", campaign_id=str(campaign_id))
            return True
        return False


# Factory function
def create_recall_workflow(
    dialer: OutboundDialer,
    practice_name: str = "Ihre Arztpraxis",
) -> RecallCampaignWorkflow:
    """Create a recall campaign workflow instance.

    Args:
        dialer: Outbound dialer service
        practice_name: Name of the practice for phone scripts

    Returns:
        Configured recall workflow
    """
    return RecallCampaignWorkflow(dialer=dialer, practice_name=practice_name)
