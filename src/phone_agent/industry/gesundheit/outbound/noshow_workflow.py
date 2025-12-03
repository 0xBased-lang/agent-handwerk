"""No-Show Follow-up Workflow for Healthcare.

Automated outbound calling to follow up with patients who missed appointments:
- Empathetic, non-judgmental conversation tone
- Offer to reschedule
- Understand patient barriers
- Flag for manual follow-up if needed
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
    OutboundCallType,
    OutboundOutcome,
)
from phone_agent.industry.gesundheit.scheduling import (
    SchedulingService,
    Appointment,
    AppointmentType,
    SchedulingPreferences,
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


class NoShowReason(str, Enum):
    """Reasons for missing an appointment."""

    FORGOT = "forgot"                  # Vergessen
    SICK = "sick"                      # Krank
    EMERGENCY = "emergency"            # Notfall
    TRANSPORTATION = "transportation"  # Transportprobleme
    WORK = "work"                      # Arbeit
    CHILDCARE = "childcare"            # Kinderbetreuung
    FEELING_BETTER = "feeling_better"  # Besserung
    WRONG_TIME = "wrong_time"          # Falscher Zeitpunkt
    OTHER = "other"                    # Sonstiges
    NOT_DISCLOSED = "not_disclosed"    # Nicht angegeben


class NoShowOutcome(str, Enum):
    """Outcomes of no-show follow-up calls."""

    RESCHEDULED = "rescheduled"              # Neu terminiert
    DECLINED_CARE = "declined_care"          # Behandlung abgelehnt
    BARRIER_IDENTIFIED = "barrier_identified" # Hindernis erkannt
    UNREACHABLE = "unreachable"              # Nicht erreichbar
    NEEDS_FOLLOWUP = "needs_followup"        # Manuelle Nachverfolgung
    RESOLVED = "resolved"                    # Erledigt (z.B. anderswo behandelt)


@dataclass
class NoShowFollowupTask:
    """Task for following up on a missed appointment."""

    id: UUID
    missed_appointment_id: UUID
    patient_id: UUID
    patient_name: str
    patient_phone: str

    # Missed appointment details
    missed_time: datetime
    provider_name: str
    appointment_reason: str
    appointment_type: AppointmentType

    # Follow-up state
    status: str = "pending"  # pending, calling, completed, failed
    attempts: int = 0
    last_attempt: datetime | None = None

    # Outcome
    outcome: NoShowOutcome | None = None
    reason: NoShowReason | None = None
    new_appointment_id: UUID | None = None
    notes: str | None = None
    needs_manual_followup: bool = False

    # Timestamps
    created_at: datetime = field(default_factory=datetime.now)
    completed_at: datetime | None = None

    @property
    def hours_since_missed(self) -> float:
        """Hours since the missed appointment."""
        delta = datetime.now() - self.missed_time
        return delta.total_seconds() / 3600

    @property
    def priority(self) -> CallPriority:
        """Calculate priority based on appointment type and time since missed."""
        # Urgent appointments get higher priority
        if self.appointment_type in [AppointmentType.ACUTE, AppointmentType.SPECIALIST]:
            return CallPriority.HIGH

        # Recent no-shows get higher priority
        if self.hours_since_missed < 4:
            return CallPriority.HIGH
        elif self.hours_since_missed < 24:
            return CallPriority.NORMAL
        else:
            return CallPriority.LOW

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": str(self.id),
            "missed_appointment_id": str(self.missed_appointment_id),
            "patient_id": str(self.patient_id),
            "patient_name": self.patient_name,
            "missed_time": self.missed_time.isoformat(),
            "provider_name": self.provider_name,
            "appointment_type": self.appointment_type.value,
            "status": self.status,
            "attempts": self.attempts,
            "outcome": self.outcome.value if self.outcome else None,
            "reason": self.reason.value if self.reason else None,
            "needs_manual_followup": self.needs_manual_followup,
            "hours_since_missed": round(self.hours_since_missed, 1),
        }


@dataclass
class NoShowConfig:
    """Configuration for no-show follow-up."""

    # Timing
    min_hours_after_missed: float = 0.5  # Wait 30 min after missed time
    max_hours_after_missed: float = 72   # Don't call after 72 hours

    # Call settings
    max_attempts: int = 2
    retry_delay_hours: int = 4

    # Practice info
    practice_name: str = "Ihre Arztpraxis"
    practice_phone: str = ""


@dataclass
class NoShowStats:
    """Statistics for no-show follow-up."""

    total_missed: int = 0
    calls_attempted: int = 0
    rescheduled: int = 0
    declined: int = 0
    unreachable: int = 0
    barriers_identified: int = 0
    needs_followup: int = 0

    started_at: datetime = field(default_factory=datetime.now)
    completed_at: datetime | None = None

    @property
    def reschedule_rate(self) -> float:
        """Rate of successfully rescheduled appointments."""
        if self.calls_attempted == 0:
            return 0.0
        return (self.rescheduled / self.calls_attempted) * 100

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "total_missed": self.total_missed,
            "calls_attempted": self.calls_attempted,
            "rescheduled": self.rescheduled,
            "declined": self.declined,
            "unreachable": self.unreachable,
            "barriers_identified": self.barriers_identified,
            "needs_followup": self.needs_followup,
            "reschedule_rate": round(self.reschedule_rate, 1),
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }


class NoShowFollowupWorkflow:
    """Workflow for following up on missed appointments."""

    def __init__(
        self,
        dialer: OutboundDialer,
        scheduling: SchedulingService | None = None,
        consent_manager: ConsentManager | None = None,
        audit_logger: AuditLogger | None = None,
        config: NoShowConfig | None = None,
    ):
        """Initialize no-show follow-up workflow.

        Args:
            dialer: Outbound dialer service
            scheduling: Scheduling service
            consent_manager: Consent manager for DSGVO
            audit_logger: Audit logger
            config: Workflow configuration
        """
        self._dialer = dialer
        self._scheduling = scheduling or get_scheduling_service()
        self._consent = consent_manager or get_consent_manager()
        self._audit = audit_logger or get_audit_logger()
        self._config = config or NoShowConfig()

        # Task tracking
        self._tasks: dict[UUID, NoShowFollowupTask] = {}
        self._stats = NoShowStats()

        # Callbacks
        self._on_followup_complete: Callable[[NoShowFollowupTask], Any] | None = None

    async def process_no_show(
        self,
        appointment: Appointment,
        patient_phone: str,
    ) -> NoShowFollowupTask | None:
        """Process a no-show event and create follow-up task.

        Call this when an appointment window passes without the patient arriving.

        Args:
            appointment: The missed appointment
            patient_phone: Patient's phone number

        Returns:
            NoShowFollowupTask or None if follow-up not appropriate
        """
        # Check timing constraints
        hours_since = (datetime.now() - appointment.slot.start).total_seconds() / 3600

        if hours_since < self._config.min_hours_after_missed:
            log.info(
                "Too soon for no-show follow-up",
                appointment_id=str(appointment.id),
                hours_since=round(hours_since, 1),
            )
            return None

        if hours_since > self._config.max_hours_after_missed:
            log.info(
                "Too late for no-show follow-up",
                appointment_id=str(appointment.id),
                hours_since=round(hours_since, 1),
            )
            return None

        # Check consent
        has_consent = await self._consent.check_consent(
            patient_id=appointment.patient_id,
            consent_type=ConsentType.PHONE_CONTACT,
        )

        if not has_consent:
            log.info(
                "Skipping no-show follow-up - no consent",
                appointment_id=str(appointment.id),
            )
            return None

        # Create follow-up task
        task = NoShowFollowupTask(
            id=uuid4(),
            missed_appointment_id=appointment.id,
            patient_id=appointment.patient_id,
            patient_name=appointment.patient_name,
            patient_phone=patient_phone,
            missed_time=appointment.slot.start,
            provider_name=appointment.slot.provider_name,
            appointment_reason=appointment.reason,
            appointment_type=appointment.appointment_type,
        )

        self._tasks[task.id] = task
        self._stats.total_missed += 1

        # Queue the call
        await self._queue_followup_call(task)

        log.info(
            "No-show follow-up created",
            task_id=str(task.id),
            appointment_id=str(appointment.id),
            patient_name=appointment.patient_name,
        )

        return task

    async def process_daily_no_shows(
        self,
        target_date: date | None = None,
    ) -> NoShowStats:
        """Process all no-shows from a specific day.

        Run this at end of day or next morning.

        Args:
            target_date: Date to check (default: yesterday)

        Returns:
            Statistics for the batch
        """
        target = target_date or (date.today() - timedelta(days=1))

        log.info("Processing daily no-shows", target_date=target.isoformat())

        self._stats = NoShowStats()

        # Get no-shows from scheduling service
        no_shows = await self._get_no_shows_for_date(target)
        self._stats.total_missed = len(no_shows)

        for appointment, patient_phone in no_shows:
            task = await self.process_no_show(appointment, patient_phone)
            if task:
                # Task is automatically queued in process_no_show
                pass

        log.info(
            "Daily no-shows queued",
            target_date=target.isoformat(),
            total_missed=self._stats.total_missed,
        )

        return self._stats

    async def _get_no_shows_for_date(
        self,
        target_date: date,
    ) -> list[tuple[Appointment, str]]:
        """Get appointments that were no-shows on a specific date.

        In production, this would query the PVS for unchecked appointments.
        """
        # This is a simplified implementation
        # In production, query PVS for appointments where patient didn't arrive
        no_shows = []

        calendar = self._scheduling._calendar

        if hasattr(calendar, '_appointments'):
            for appt in calendar._appointments.values():
                appt_date = appt.slot.start.date()
                if appt_date == target_date:
                    # Check if appointment was confirmed but patient didn't show
                    if not appt.confirmed:
                        # In production, would get phone from patient record
                        patient_phone = "+49170000000"  # Placeholder
                        no_shows.append((appt, patient_phone))

        return no_shows

    async def _queue_followup_call(self, task: NoShowFollowupTask) -> None:
        """Queue a follow-up call for a no-show."""
        # Format missed appointment for script
        weekdays = ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"]
        day_name = weekdays[task.missed_time.weekday()]
        date_str = task.missed_time.strftime("%d.%m.")
        time_str = task.missed_time.strftime("%H:%M")

        metadata = {
            "workflow": "no_show_followup",
            "task_id": str(task.id),
            "missed_appointment_id": str(task.missed_appointment_id),
            "patient_id": str(task.patient_id),
            "missed_time": task.missed_time.isoformat(),
            "missed_date_formatted": f"{day_name}, {date_str} um {time_str} Uhr",
            "provider_name": task.provider_name,
            "appointment_reason": task.appointment_reason,
            "call_type": OutboundCallType.NO_SHOW_FOLLOWUP.value,
        }

        await self._dialer.queue_call(
            patient_id=task.patient_id,
            phone_number=task.patient_phone,
            call_type=OutboundCallType.NO_SHOW_FOLLOWUP,
            priority=task.priority,
            metadata=metadata,
            callback=lambda result: self._handle_call_result(task.id, result),
        )

        task.status = "calling"
        self._stats.calls_attempted += 1

        log.info(
            "Queued no-show follow-up call",
            task_id=str(task.id),
            hours_since_missed=round(task.hours_since_missed, 1),
            priority=task.priority.name,
        )

    async def _handle_call_result(
        self,
        task_id: UUID,
        result: dict[str, Any],
    ) -> None:
        """Handle the result of a follow-up call."""
        task = self._tasks.get(task_id)
        if not task:
            log.warning("Task not found for call result", task_id=str(task_id))
            return

        task.attempts += 1
        task.last_attempt = datetime.now()

        outcome = result.get("outcome")
        reason = result.get("reason")

        # Map to NoShowOutcome
        if outcome == OutboundOutcome.APPOINTMENT_RESCHEDULED:
            task.outcome = NoShowOutcome.RESCHEDULED
            task.new_appointment_id = result.get("new_appointment_id")
            task.status = "completed"
            self._stats.rescheduled += 1

        elif outcome == OutboundOutcome.DECLINED:
            task.outcome = NoShowOutcome.DECLINED_CARE
            task.status = "completed"
            self._stats.declined += 1

        elif outcome == OutboundOutcome.NO_ANSWER:
            if task.attempts >= self._config.max_attempts:
                task.outcome = NoShowOutcome.UNREACHABLE
                task.status = "completed"
                task.needs_manual_followup = True
                self._stats.unreachable += 1
                self._stats.needs_followup += 1
            else:
                task.status = "pending"
                # Schedule retry
                await self._schedule_retry(task)

        else:
            task.outcome = NoShowOutcome.RESOLVED
            task.status = "completed"

        # Capture reason if provided
        if reason:
            task.reason = NoShowReason(reason) if reason in [r.value for r in NoShowReason] else NoShowReason.OTHER

            # Identify barriers that need attention
            barrier_reasons = [
                NoShowReason.TRANSPORTATION,
                NoShowReason.CHILDCARE,
                NoShowReason.WORK,
            ]
            if task.reason in barrier_reasons:
                task.outcome = NoShowOutcome.BARRIER_IDENTIFIED
                task.needs_manual_followup = True
                self._stats.barriers_identified += 1
                self._stats.needs_followup += 1

        task.notes = result.get("notes")

        if task.status == "completed":
            task.completed_at = datetime.now()

        # Audit log
        await self._audit.log_event(
            event_type="no_show_followup_completed",
            patient_id=task.patient_id,
            details={
                "task_id": str(task.id),
                "outcome": task.outcome.value if task.outcome else None,
                "reason": task.reason.value if task.reason else None,
                "needs_manual_followup": task.needs_manual_followup,
                "attempts": task.attempts,
            },
        )

        # Notify callback
        if self._on_followup_complete:
            self._on_followup_complete(task)

        log.info(
            "No-show follow-up completed",
            task_id=str(task.id),
            outcome=task.outcome.value if task.outcome else None,
            reason=task.reason.value if task.reason else None,
            needs_manual_followup=task.needs_manual_followup,
        )

    async def _schedule_retry(self, task: NoShowFollowupTask) -> None:
        """Schedule a retry call for a follow-up task."""
        retry_time = datetime.now() + timedelta(hours=self._config.retry_delay_hours)

        # Don't retry if too late
        if (retry_time - task.missed_time).total_seconds() / 3600 > self._config.max_hours_after_missed:
            task.outcome = NoShowOutcome.UNREACHABLE
            task.status = "completed"
            task.needs_manual_followup = True
            self._stats.unreachable += 1
            self._stats.needs_followup += 1
            return

        log.info(
            "Scheduling retry for no-show follow-up",
            task_id=str(task.id),
            retry_time=retry_time.isoformat(),
        )

        # Wait and retry
        await asyncio.sleep(self._config.retry_delay_hours * 3600)
        await self._queue_followup_call(task)

    async def offer_reschedule(
        self,
        task_id: UUID,
        preferences: dict[str, Any],
    ) -> dict[str, Any]:
        """Offer rescheduling options during a follow-up call.

        Args:
            task_id: ID of the follow-up task
            preferences: Patient preferences from conversation

        Returns:
            Available slots or booking confirmation
        """
        task = self._tasks.get(task_id)
        if not task:
            return {"success": False, "error": "Task not found"}

        prefs = SchedulingPreferences(
            appointment_type=task.appointment_type,
            preferred_time=preferences.get("time_preference"),
            preferred_provider=task.provider_name if preferences.get("same_provider") else None,
            flexible_date=True,
            flexible_provider=not preferences.get("same_provider", False),
        )

        slots = await self._scheduling.find_slots(prefs, limit=3)

        if not slots:
            return {
                "success": False,
                "error": "no_slots",
                "message": "Leider sind aktuell keine Termine verfügbar. Wir rufen Sie zurück.",
            }

        selected_slot_id = preferences.get("selected_slot_id")
        if selected_slot_id:
            # Book the slot
            mock_patient = Patient(
                id=task.patient_id,
                first_name=task.patient_name.split()[0] if task.patient_name else "",
                last_name=task.patient_name.split()[-1] if task.patient_name else "",
                date_of_birth=date(1980, 1, 1),  # Placeholder
                phone=task.patient_phone,
            )

            try:
                appointment = await self._scheduling.book_appointment(
                    slot_id=selected_slot_id,
                    patient=mock_patient,
                    reason=task.appointment_reason,
                    appointment_type=task.appointment_type,
                )

                return {
                    "success": True,
                    "appointment_id": str(appointment.id),
                    "message": f"Ihr neuer Termin: {self._scheduling.format_slot_for_speech(appointment.slot)}",
                }

            except ValueError as e:
                return {"success": False, "error": str(e)}

        # Return slot options
        return {
            "success": True,
            "action": "offer_slots",
            "slots": [
                {
                    "id": str(slot.id),
                    "description": self._scheduling.format_slot_for_speech(slot),
                }
                for slot in slots
            ],
        }

    def on_followup_complete(self, callback: Callable[[NoShowFollowupTask], Any]) -> None:
        """Set callback for follow-up completion."""
        self._on_followup_complete = callback

    def get_task(self, task_id: UUID) -> NoShowFollowupTask | None:
        """Get a follow-up task by ID."""
        return self._tasks.get(task_id)

    def get_tasks_needing_manual_followup(self) -> list[NoShowFollowupTask]:
        """Get tasks that need manual staff follow-up."""
        return [t for t in self._tasks.values() if t.needs_manual_followup]

    def get_stats(self) -> NoShowStats:
        """Get current statistics."""
        return self._stats


# Factory function
def create_noshow_workflow(
    dialer: OutboundDialer,
    config: NoShowConfig | None = None,
) -> NoShowFollowupWorkflow:
    """Create a no-show follow-up workflow instance.

    Args:
        dialer: Outbound dialer service
        config: Optional workflow configuration

    Returns:
        Configured no-show workflow
    """
    return NoShowFollowupWorkflow(dialer=dialer, config=config)
