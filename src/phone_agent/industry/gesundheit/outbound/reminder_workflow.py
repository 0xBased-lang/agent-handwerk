"""Appointment Reminder Workflow for Healthcare.

Automated outbound calling to remind patients of upcoming appointments:
- 24-48 hour advance reminders
- Confirm, reschedule, or cancel options
- SMS confirmation after successful calls
- Integration with SchedulingService
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, date, timedelta
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
from phone_agent.industry.gesundheit.scheduling import (
    SchedulingService,
    Appointment,
    AppointmentType,
    TimeSlot,
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


class ReminderStatus(str, Enum):
    """Status of reminder attempts."""

    PENDING = "pending"
    CALLING = "calling"
    CONFIRMED = "confirmed"
    RESCHEDULED = "rescheduled"
    CANCELLED = "cancelled"
    NO_ANSWER = "no_answer"
    DECLINED = "declined"
    FAILED = "failed"


@dataclass
class ReminderTask:
    """A reminder task for a single appointment."""

    id: UUID
    appointment_id: UUID
    patient_id: UUID
    patient_name: str
    patient_phone: str

    # Appointment details
    appointment_time: datetime
    provider_name: str
    appointment_type: AppointmentType

    # Reminder state
    status: ReminderStatus = ReminderStatus.PENDING
    attempts: int = 0
    last_attempt: datetime | None = None
    call_duration_seconds: int | None = None

    # Outcome
    outcome: OutboundOutcome | None = None
    new_appointment_id: UUID | None = None
    notes: str | None = None

    # Timestamps
    created_at: datetime = field(default_factory=datetime.now)
    completed_at: datetime | None = None

    @property
    def hours_until_appointment(self) -> float:
        """Hours until the appointment."""
        delta = self.appointment_time - datetime.now()
        return delta.total_seconds() / 3600

    @property
    def priority(self) -> CallPriority:
        """Calculate call priority based on time until appointment."""
        hours = self.hours_until_appointment
        if hours < 4:
            return CallPriority.URGENT
        elif hours < 12:
            return CallPriority.HIGH
        elif hours < 24:
            return CallPriority.NORMAL
        else:
            return CallPriority.LOW

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": str(self.id),
            "appointment_id": str(self.appointment_id),
            "patient_id": str(self.patient_id),
            "patient_name": self.patient_name,
            "appointment_time": self.appointment_time.isoformat(),
            "provider_name": self.provider_name,
            "appointment_type": self.appointment_type.value,
            "status": self.status.value,
            "attempts": self.attempts,
            "outcome": self.outcome.value if self.outcome else None,
            "hours_until_appointment": round(self.hours_until_appointment, 1),
        }


@dataclass
class ReminderCampaignConfig:
    """Configuration for reminder campaign."""

    # Time windows
    reminder_hours_before: int = 24  # Start reminders 24h before
    min_hours_before: int = 2  # Stop reminding if <2h before

    # Call settings
    max_attempts: int = 2
    retry_delay_minutes: int = 60

    # SMS fallback
    sms_after_failed_attempts: int = 2
    sms_enabled: bool = True

    # Practice info
    practice_name: str = "Ihre Arztpraxis"
    practice_phone: str = ""


@dataclass
class ReminderCampaignStats:
    """Statistics for a reminder campaign run."""

    total_appointments: int = 0
    reminders_sent: int = 0
    confirmed: int = 0
    rescheduled: int = 0
    cancelled: int = 0
    no_answer: int = 0
    declined: int = 0

    started_at: datetime = field(default_factory=datetime.now)
    completed_at: datetime | None = None

    @property
    def confirmation_rate(self) -> float:
        """Percentage of confirmed appointments."""
        if self.reminders_sent == 0:
            return 0.0
        return (self.confirmed / self.reminders_sent) * 100

    @property
    def no_show_prevention_rate(self) -> float:
        """Rate of appointments where patient responded (prevented blind no-show)."""
        if self.reminders_sent == 0:
            return 0.0
        responded = self.confirmed + self.rescheduled + self.cancelled + self.declined
        return (responded / self.reminders_sent) * 100

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "total_appointments": self.total_appointments,
            "reminders_sent": self.reminders_sent,
            "confirmed": self.confirmed,
            "rescheduled": self.rescheduled,
            "cancelled": self.cancelled,
            "no_answer": self.no_answer,
            "declined": self.declined,
            "confirmation_rate": round(self.confirmation_rate, 1),
            "no_show_prevention_rate": round(self.no_show_prevention_rate, 1),
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }


class AppointmentReminderWorkflow:
    """Workflow for sending appointment reminders via outbound calls."""

    def __init__(
        self,
        dialer: OutboundDialer,
        scheduling: SchedulingService | None = None,
        consent_manager: ConsentManager | None = None,
        audit_logger: AuditLogger | None = None,
        config: ReminderCampaignConfig | None = None,
    ):
        """Initialize reminder workflow.

        Args:
            dialer: Outbound dialer service
            scheduling: Scheduling service (uses singleton if not provided)
            consent_manager: Consent manager for DSGVO compliance
            audit_logger: Audit logger for compliance tracking
            config: Campaign configuration
        """
        self._dialer = dialer
        self._scheduling = scheduling or get_scheduling_service()
        self._consent = consent_manager or get_consent_manager()
        self._audit = audit_logger or get_audit_logger()
        self._config = config or ReminderCampaignConfig()

        # Task tracking
        self._tasks: dict[UUID, ReminderTask] = {}
        self._stats = ReminderCampaignStats()

        # Callbacks
        self._on_reminder_complete: Callable[[ReminderTask], Any] | None = None

    async def start_campaign(
        self,
        target_date: date | None = None,
        appointment_types: list[AppointmentType] | None = None,
    ) -> ReminderCampaignStats:
        """Start a reminder campaign for appointments.

        Args:
            target_date: Date to check for appointments (default: tomorrow)
            appointment_types: Filter by appointment types (default: all)

        Returns:
            Campaign statistics
        """
        target = target_date or (date.today() + timedelta(days=1))

        log.info(
            "Starting reminder campaign",
            target_date=target.isoformat(),
            appointment_types=[t.value for t in appointment_types] if appointment_types else "all",
        )

        self._stats = ReminderCampaignStats()

        # Query appointments for target date
        appointments = await self._get_appointments_for_date(target, appointment_types)
        self._stats.total_appointments = len(appointments)

        if not appointments:
            log.info("No appointments found for reminder campaign", target_date=target.isoformat())
            self._stats.completed_at = datetime.now()
            return self._stats

        # Create reminder tasks
        for appointment in appointments:
            task = await self._create_reminder_task(appointment)
            if task:
                self._tasks[task.id] = task

                # Queue call with priority based on appointment time
                await self._queue_reminder_call(task)

        log.info(
            "Reminder campaign queued",
            total_appointments=self._stats.total_appointments,
            tasks_queued=len(self._tasks),
        )

        return self._stats

    async def _get_appointments_for_date(
        self,
        target_date: date,
        appointment_types: list[AppointmentType] | None = None,
    ) -> list[Appointment]:
        """Get appointments for a specific date.

        In production, this would query the PVS/calendar system.
        For now, we use mock data from the scheduling service.
        """
        # This is a simplified implementation
        # In production, query the calendar integration
        calendar = self._scheduling._calendar

        appointments = []

        # Access mock appointments (in production, use proper API)
        if hasattr(calendar, '_appointments'):
            for appt in calendar._appointments.values():
                appt_date = appt.slot.start.date()
                if appt_date == target_date:
                    if appointment_types is None or appt.appointment_type in appointment_types:
                        appointments.append(appt)

        return appointments

    async def _create_reminder_task(self, appointment: Appointment) -> ReminderTask | None:
        """Create a reminder task for an appointment.

        Returns:
            ReminderTask or None if patient shouldn't be contacted
        """
        # Check consent for phone contact
        has_consent = await self._consent.check_consent(
            patient_id=appointment.patient_id,
            consent_type=ConsentType.PHONE_CONTACT,
        )

        if not has_consent:
            log.info(
                "Skipping reminder - no phone consent",
                appointment_id=str(appointment.id),
                patient_id=str(appointment.patient_id),
            )
            return None

        # Check time constraints
        hours_until = (appointment.slot.start - datetime.now()).total_seconds() / 3600

        if hours_until < self._config.min_hours_before:
            log.info(
                "Skipping reminder - too close to appointment",
                appointment_id=str(appointment.id),
                hours_until=round(hours_until, 1),
            )
            return None

        if hours_until > self._config.reminder_hours_before:
            log.info(
                "Skipping reminder - too far from appointment",
                appointment_id=str(appointment.id),
                hours_until=round(hours_until, 1),
            )
            return None

        # Get patient phone (in production, from PVS)
        # For now, use a placeholder - would come from patient record
        patient_phone = "+49170000000"  # Placeholder

        task = ReminderTask(
            id=uuid4(),
            appointment_id=appointment.id,
            patient_id=appointment.patient_id,
            patient_name=appointment.patient_name,
            patient_phone=patient_phone,
            appointment_time=appointment.slot.start,
            provider_name=appointment.slot.provider_name,
            appointment_type=appointment.appointment_type,
        )

        return task

    async def _queue_reminder_call(self, task: ReminderTask) -> None:
        """Queue a reminder call for a task."""
        # Build call metadata
        metadata = {
            "workflow": "appointment_reminder",
            "task_id": str(task.id),
            "appointment_id": str(task.appointment_id),
            "patient_id": str(task.patient_id),
            "appointment_time": task.appointment_time.isoformat(),
            "provider_name": task.provider_name,
            "call_type": OutboundCallType.APPOINTMENT_REMINDER.value,
        }

        # Queue the call
        await self._dialer.queue_call(
            patient_id=task.patient_id,
            phone_number=task.patient_phone,
            call_type=OutboundCallType.APPOINTMENT_REMINDER,
            priority=task.priority,
            metadata=metadata,
            callback=lambda result: self._handle_call_result(task.id, result),
        )

        self._stats.reminders_sent += 1
        task.status = ReminderStatus.CALLING

        log.info(
            "Queued reminder call",
            task_id=str(task.id),
            appointment_time=task.appointment_time.isoformat(),
            priority=task.priority.name,
        )

    async def _handle_call_result(
        self,
        task_id: UUID,
        result: dict[str, Any],
    ) -> None:
        """Handle the result of a reminder call.

        Args:
            task_id: ID of the reminder task
            result: Call result from dialer
        """
        task = self._tasks.get(task_id)
        if not task:
            log.warning("Task not found for call result", task_id=str(task_id))
            return

        task.attempts += 1
        task.last_attempt = datetime.now()

        outcome = result.get("outcome")

        if outcome == OutboundOutcome.APPOINTMENT_CONFIRMED:
            task.status = ReminderStatus.CONFIRMED
            task.outcome = OutboundOutcome.APPOINTMENT_CONFIRMED
            self._stats.confirmed += 1

            # Send SMS confirmation
            if self._config.sms_enabled:
                await self._send_confirmation_sms(task)

        elif outcome == OutboundOutcome.APPOINTMENT_RESCHEDULED:
            task.status = ReminderStatus.RESCHEDULED
            task.outcome = OutboundOutcome.APPOINTMENT_RESCHEDULED
            task.new_appointment_id = result.get("new_appointment_id")
            self._stats.rescheduled += 1

        elif outcome == OutboundOutcome.APPOINTMENT_CANCELLED:
            task.status = ReminderStatus.CANCELLED
            task.outcome = OutboundOutcome.APPOINTMENT_CANCELLED
            self._stats.cancelled += 1

        elif outcome == OutboundOutcome.NO_ANSWER:
            if task.attempts >= self._config.max_attempts:
                task.status = ReminderStatus.NO_ANSWER
                task.outcome = OutboundOutcome.NO_ANSWER
                self._stats.no_answer += 1

                # Send SMS fallback
                if self._config.sms_enabled and task.attempts >= self._config.sms_after_failed_attempts:
                    await self._send_fallback_sms(task)
            else:
                # Retry later
                await self._schedule_retry(task)

        elif outcome == OutboundOutcome.DECLINED:
            task.status = ReminderStatus.DECLINED
            task.outcome = OutboundOutcome.DECLINED
            self._stats.declined += 1

        else:
            task.status = ReminderStatus.FAILED
            task.outcome = outcome

        task.call_duration_seconds = result.get("duration_seconds")
        task.notes = result.get("notes")

        if task.status != ReminderStatus.CALLING:
            task.completed_at = datetime.now()

        # Log audit event
        await self._audit.log_event(
            event_type="reminder_call_completed",
            patient_id=task.patient_id,
            details={
                "task_id": str(task.id),
                "appointment_id": str(task.appointment_id),
                "outcome": task.outcome.value if task.outcome else None,
                "attempts": task.attempts,
            },
        )

        # Notify callback
        if self._on_reminder_complete:
            self._on_reminder_complete(task)

        log.info(
            "Reminder call completed",
            task_id=str(task.id),
            status=task.status.value,
            outcome=task.outcome.value if task.outcome else None,
            attempts=task.attempts,
        )

    async def _schedule_retry(self, task: ReminderTask) -> None:
        """Schedule a retry call for a task."""
        retry_time = datetime.now() + timedelta(minutes=self._config.retry_delay_minutes)

        # Only retry if there's still time before the appointment
        if task.hours_until_appointment < self._config.min_hours_before + 1:
            task.status = ReminderStatus.NO_ANSWER
            task.outcome = OutboundOutcome.NO_ANSWER
            self._stats.no_answer += 1

            if self._config.sms_enabled:
                await self._send_fallback_sms(task)
            return

        log.info(
            "Scheduling retry call",
            task_id=str(task.id),
            retry_time=retry_time.isoformat(),
            attempt_number=task.attempts + 1,
        )

        # Re-queue with delay
        await asyncio.sleep(self._config.retry_delay_minutes * 60)
        await self._queue_reminder_call(task)

    async def _send_confirmation_sms(self, task: ReminderTask) -> None:
        """Send SMS confirmation after successful reminder call."""
        # Format appointment time for German audience
        weekdays = ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"]
        day_name = weekdays[task.appointment_time.weekday()]
        date_str = task.appointment_time.strftime("%d.%m.%Y")
        time_str = task.appointment_time.strftime("%H:%M")

        message = (
            f"{self._config.practice_name}: Ihr Termin am {day_name}, {date_str} "
            f"um {time_str} Uhr bei {task.provider_name} ist bestätigt. "
            f"Bitte kommen Sie 10 Min. vorher."
        )

        log.info(
            "Sending confirmation SMS",
            task_id=str(task.id),
            phone=task.patient_phone[:8] + "...",
        )

        # In production: Send via SMS gateway
        # await sms_gateway.send(task.patient_phone, message)

    async def _send_fallback_sms(self, task: ReminderTask) -> None:
        """Send SMS fallback after failed call attempts."""
        weekdays = ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"]
        day_name = weekdays[task.appointment_time.weekday()]
        date_str = task.appointment_time.strftime("%d.%m.%Y")
        time_str = task.appointment_time.strftime("%H:%M")

        message = (
            f"{self._config.practice_name}: Terminerinnerung - {day_name}, {date_str} "
            f"um {time_str} Uhr bei {task.provider_name}. "
            f"Absagen/Umbuchung: {self._config.practice_phone}"
        )

        log.info(
            "Sending fallback SMS",
            task_id=str(task.id),
            phone=task.patient_phone[:8] + "...",
        )

        # In production: Send via SMS gateway
        # await sms_gateway.send(task.patient_phone, message)

    def on_reminder_complete(self, callback: Callable[[ReminderTask], Any]) -> None:
        """Set callback for reminder completion."""
        self._on_reminder_complete = callback

    def get_task(self, task_id: UUID) -> ReminderTask | None:
        """Get a reminder task by ID."""
        return self._tasks.get(task_id)

    def get_all_tasks(self) -> list[ReminderTask]:
        """Get all reminder tasks."""
        return list(self._tasks.values())

    def get_stats(self) -> ReminderCampaignStats:
        """Get current campaign statistics."""
        return self._stats

    async def cancel_campaign(self) -> None:
        """Cancel the running reminder campaign."""
        for task in self._tasks.values():
            if task.status == ReminderStatus.CALLING:
                task.status = ReminderStatus.FAILED
                task.notes = "Campaign cancelled"

        self._stats.completed_at = datetime.now()

        log.info("Reminder campaign cancelled", stats=self._stats.to_dict())


# Factory function
def create_reminder_workflow(
    dialer: OutboundDialer,
    config: ReminderCampaignConfig | None = None,
) -> AppointmentReminderWorkflow:
    """Create a reminder workflow instance.

    Args:
        dialer: Outbound dialer service
        config: Optional campaign configuration

    Returns:
        Configured reminder workflow
    """
    return AppointmentReminderWorkflow(dialer=dialer, config=config)
