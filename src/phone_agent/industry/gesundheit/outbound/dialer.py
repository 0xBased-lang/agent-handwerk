"""Outbound Dialer Service for Healthcare.

Manages outbound call queue with:
- Priority-based ordering
- Business hours enforcement
- Rate limiting for Raspberry Pi
- Consent verification
- Retry logic with SMS fallback
"""
from __future__ import annotations

import asyncio
import heapq
from dataclasses import dataclass, field
from datetime import datetime, time, date
from enum import Enum
from typing import Any, Callable, Awaitable, TYPE_CHECKING
from uuid import UUID, uuid4

from itf_shared import get_logger

if TYPE_CHECKING:
    from phone_agent.integrations.sms.base import SMSGateway

log = get_logger(__name__)


class DialerStatus(str, Enum):
    """Dialer service status."""

    STOPPED = "stopped"
    RUNNING = "running"
    PAUSED = "paused"


class CallPriority(int, Enum):
    """Call priority levels (lower = higher priority)."""

    URGENT = 1      # Emergency follow-ups
    HIGH = 3        # Same-day appointments
    NORMAL = 5      # Standard reminders
    LOW = 7         # Routine campaigns


class CallOutcome(str, Enum):
    """Outcome of an outbound call attempt."""

    ANSWERED = "answered"           # Call was answered
    NO_ANSWER = "no_answer"         # No answer (retry)
    BUSY = "busy"                   # Line busy (retry)
    FAILED = "failed"               # Technical failure (retry)
    VOICEMAIL = "voicemail"         # Went to voicemail
    DECLINED = "declined"           # Patient declined
    WRONG_NUMBER = "wrong_number"   # Wrong number
    NO_CONSENT = "no_consent"       # Patient hasn't consented


@dataclass(order=True)
class QueuedCall:
    """Call queued for outbound dialing."""

    # For priority queue ordering
    priority: int = field(compare=True)
    scheduled_at: datetime = field(compare=True)

    # Call details (not used for ordering)
    call_id: UUID = field(default_factory=uuid4, compare=False)
    patient_id: str = field(default="", compare=False)
    phone_number: str = field(default="", compare=False)
    patient_name: str = field(default="", compare=False)
    campaign_id: UUID | None = field(default=None, compare=False)
    campaign_type: str = field(default="reminder", compare=False)
    attempt_number: int = field(default=1, compare=False)
    max_attempts: int = field(default=3, compare=False)
    metadata: dict[str, Any] = field(default_factory=dict, compare=False)
    created_at: datetime = field(default_factory=datetime.now, compare=False)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "call_id": str(self.call_id),
            "patient_id": self.patient_id,
            "phone_number": self.phone_number,
            "patient_name": self.patient_name,
            "campaign_id": str(self.campaign_id) if self.campaign_id else None,
            "campaign_type": self.campaign_type,
            "priority": self.priority,
            "attempt_number": self.attempt_number,
            "max_attempts": self.max_attempts,
            "scheduled_at": self.scheduled_at.isoformat(),
            "created_at": self.created_at.isoformat(),
        }


@dataclass
class DialerConfig:
    """Outbound dialer configuration."""

    # Business hours (German time)
    business_hours_start: time = field(default_factory=lambda: time(9, 0))
    business_hours_end: time = field(default_factory=lambda: time(18, 0))
    weekdays_only: bool = True

    # Rate limiting (optimized for Raspberry Pi)
    max_concurrent_calls: int = 1
    calls_per_minute: int = 4
    min_call_interval_seconds: float = 15.0

    # Retry settings
    max_attempts: int = 3
    retry_delay_minutes: int = 60
    sms_after_failed_attempts: int = 2

    # Timeouts
    ring_timeout_seconds: int = 25
    call_max_duration_seconds: int = 300

    # Caller ID
    caller_id: str = ""


@dataclass
class DialerStats:
    """Dialer statistics."""

    calls_queued: int = 0
    calls_completed: int = 0
    calls_answered: int = 0
    calls_no_answer: int = 0
    calls_failed: int = 0
    sms_sent: int = 0
    started_at: datetime | None = None
    last_call_at: datetime | None = None


# Global singleton
_outbound_dialer: OutboundDialer | None = None


class OutboundDialer:
    """Outbound calling service with priority queue.

    Features:
    - Priority queue with heap-based ordering
    - Business hours enforcement
    - Rate limiting for Raspberry Pi resources
    - DSGVO consent verification before each call
    - Retry logic with SMS fallback

    Usage:
        dialer = OutboundDialer(config, sip_client, consent_manager)
        await dialer.start()

        # Queue a call
        call = dialer.queue_call(
            patient_id="123",
            phone_number="+4930123456",
            patient_name="Max Mustermann",
            priority=CallPriority.NORMAL,
            campaign_type="reminder",
        )

        # Wait for completion
        await asyncio.sleep(60)

        # Stop dialer
        await dialer.stop()
    """

    def __init__(
        self,
        config: DialerConfig | None = None,
        sip_client: Any | None = None,
        consent_manager: Any | None = None,
        audit_logger: Any | None = None,
        sms_gateway: "SMSGateway | None" = None,
        practice_name: str = "Praxis",
    ) -> None:
        """Initialize outbound dialer.

        Args:
            config: Dialer configuration
            sip_client: SIP client for making calls
            consent_manager: Consent manager for DSGVO verification
            audit_logger: Audit logger for compliance
            sms_gateway: SMS gateway for fallback messages
            practice_name: Practice name for SMS messages
        """
        self.config = config or DialerConfig()
        self._sip_client = sip_client
        self._consent_manager = consent_manager
        self._audit_logger = audit_logger
        self._sms_gateway = sms_gateway
        self._practice_name = practice_name
        self._conversation_manager: Any | None = None
        self._audio_processor: Any | None = None  # For speech-to-text/text-to-speech

        self._status = DialerStatus.STOPPED
        self._queue: list[QueuedCall] = []  # heapq
        self._active_calls: dict[UUID, QueuedCall] = {}
        self._stats = DialerStats()

        # Main loop task
        self._loop_task: asyncio.Task | None = None
        self._last_call_time: datetime | None = None

        # Callbacks
        self._on_call_start: Callable[[QueuedCall], Awaitable[None]] | None = None
        self._on_call_complete: Callable[[QueuedCall, CallOutcome], Awaitable[None]] | None = None
        self._on_sms_fallback: Callable[[QueuedCall], Awaitable[None]] | None = None

    # ========== Lifecycle ==========

    async def start(self) -> None:
        """Start the dialer service."""
        if self._status == DialerStatus.RUNNING:
            return

        self._status = DialerStatus.RUNNING
        self._stats.started_at = datetime.now()
        self._loop_task = asyncio.create_task(self._run_loop())

        log.info("Outbound dialer started")

    async def stop(self) -> None:
        """Stop the dialer service."""
        if self._status == DialerStatus.STOPPED:
            return

        self._status = DialerStatus.STOPPED

        if self._loop_task:
            self._loop_task.cancel()
            try:
                await self._loop_task
            except asyncio.CancelledError:
                pass
            self._loop_task = None

        log.info(
            "Outbound dialer stopped",
            calls_completed=self._stats.calls_completed,
            calls_answered=self._stats.calls_answered,
        )

    def pause(self) -> None:
        """Pause the dialer (queue continues to accept calls)."""
        if self._status == DialerStatus.RUNNING:
            self._status = DialerStatus.PAUSED
            log.info("Outbound dialer paused")

    def resume(self) -> None:
        """Resume the paused dialer."""
        if self._status == DialerStatus.PAUSED:
            self._status = DialerStatus.RUNNING
            log.info("Outbound dialer resumed")

    # ========== Queue Management ==========

    def queue_call(
        self,
        patient_id: str,
        phone_number: str,
        patient_name: str = "",
        priority: CallPriority = CallPriority.NORMAL,
        campaign_id: UUID | None = None,
        campaign_type: str = "reminder",
        scheduled_at: datetime | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> QueuedCall:
        """Add a call to the queue.

        Args:
            patient_id: Patient identifier
            phone_number: Phone number to dial
            patient_name: Patient name for greeting
            priority: Call priority
            campaign_id: Associated campaign ID
            campaign_type: Type of campaign (reminder, recall, noshow)
            scheduled_at: When to make the call (defaults to now)
            metadata: Additional call metadata

        Returns:
            QueuedCall object
        """
        call = QueuedCall(
            priority=priority.value,
            scheduled_at=scheduled_at or datetime.now(),
            patient_id=patient_id,
            phone_number=phone_number,
            patient_name=patient_name,
            campaign_id=campaign_id,
            campaign_type=campaign_type,
            max_attempts=self.config.max_attempts,
            metadata=metadata or {},
        )

        heapq.heappush(self._queue, call)
        self._stats.calls_queued += 1

        log.info(
            "Call queued",
            call_id=str(call.call_id),
            patient_id=patient_id,
            priority=priority.name,
            queue_size=len(self._queue),
        )

        return call

    def cancel_call(self, call_id: UUID) -> bool:
        """Cancel a queued call.

        Args:
            call_id: Call ID to cancel

        Returns:
            True if found and cancelled
        """
        for i, call in enumerate(self._queue):
            if call.call_id == call_id:
                self._queue.pop(i)
                heapq.heapify(self._queue)
                log.info("Call cancelled", call_id=str(call_id))
                return True
        return False

    def get_queue(self) -> list[QueuedCall]:
        """Get current queue (sorted by priority)."""
        return sorted(self._queue)

    def get_queue_snapshot(self) -> list[QueuedCall]:
        """Get snapshot of current queue (alias for get_queue)."""
        return self.get_queue()

    def clear_queue(self) -> int:
        """Clear all calls from the queue.

        Returns:
            Number of calls cleared
        """
        count = len(self._queue)
        self._queue.clear()
        log.info("Queue cleared", cleared_count=count)
        return count

    @property
    def queue_size(self) -> int:
        """Get current queue size."""
        return len(self._queue)

    @property
    def stats(self) -> DialerStats:
        """Get dialer statistics."""
        return self._stats

    @property
    def status(self) -> DialerStatus:
        """Get dialer status."""
        return self._status

    # ========== Main Loop ==========

    async def _run_loop(self) -> None:
        """Main dialer loop."""
        log.info("Dialer loop started")

        while self._status != DialerStatus.STOPPED:
            try:
                # Check if paused
                if self._status == DialerStatus.PAUSED:
                    await asyncio.sleep(1.0)
                    continue

                # Check if within business hours
                if not self._is_within_business_hours():
                    await asyncio.sleep(60.0)  # Check every minute
                    continue

                # Check rate limiting
                if not self._can_make_call():
                    await asyncio.sleep(1.0)
                    continue

                # Check concurrent calls
                if len(self._active_calls) >= self.config.max_concurrent_calls:
                    await asyncio.sleep(1.0)
                    continue

                # Get next call from queue
                if not self._queue:
                    await asyncio.sleep(1.0)
                    continue

                # Peek at next call
                next_call = self._queue[0]

                # Check if scheduled time has arrived
                if next_call.scheduled_at > datetime.now():
                    await asyncio.sleep(1.0)
                    continue

                # Pop and execute
                call = heapq.heappop(self._queue)
                await self._execute_call(call)

            except asyncio.CancelledError:
                break
            except Exception as e:
                log.error("Dialer loop error", error=str(e))
                await asyncio.sleep(5.0)

        log.info("Dialer loop ended")

    def _is_within_business_hours(self) -> bool:
        """Check if current time is within business hours."""
        now = datetime.now()

        # Check weekday
        if self.config.weekdays_only and now.weekday() >= 5:
            return False

        # Check time
        current_time = now.time()
        return (
            self.config.business_hours_start
            <= current_time
            <= self.config.business_hours_end
        )

    def _can_make_call(self) -> bool:
        """Check if rate limit allows making a call."""
        if self._last_call_time is None:
            return True

        elapsed = (datetime.now() - self._last_call_time).total_seconds()
        return elapsed >= self.config.min_call_interval_seconds

    # ========== Call Execution ==========

    async def _execute_call(self, call: QueuedCall) -> None:
        """Execute a single outbound call.

        Args:
            call: Call to execute
        """
        log.info(
            "Executing call",
            call_id=str(call.call_id),
            patient_id=call.patient_id,
            attempt=call.attempt_number,
        )

        # Track active call
        self._active_calls[call.call_id] = call
        self._last_call_time = datetime.now()

        try:
            # Step 1: Check consent
            if not await self._check_consent(call):
                await self._handle_outcome(call, CallOutcome.NO_CONSENT)
                return

            # Step 2: Log audit entry
            await self._log_call_attempt(call)

            # Step 3: Notify callback
            if self._on_call_start:
                await self._on_call_start(call)

            # Step 4: Make the call
            outcome = await self._make_call(call)

            # Step 5: Handle outcome
            await self._handle_outcome(call, outcome)

        except Exception as e:
            log.error(
                "Call execution error",
                call_id=str(call.call_id),
                error=str(e),
            )
            await self._handle_outcome(call, CallOutcome.FAILED)

        finally:
            # Remove from active calls
            self._active_calls.pop(call.call_id, None)

    async def _check_consent(self, call: QueuedCall) -> bool:
        """Check if patient has consented to phone contact.

        Args:
            call: Call to check

        Returns:
            True if consent is granted
        """
        if self._consent_manager is None:
            # No consent manager configured, assume consent
            log.warning(
                "No consent manager configured",
                call_id=str(call.call_id),
            )
            return True

        try:
            # Import here to avoid circular dependency
            from phone_agent.industry.gesundheit.compliance import ConsentType

            has_consent = self._consent_manager.check_consent(
                call.patient_id,
                ConsentType.PHONE_CONTACT,
            )

            if not has_consent:
                log.warning(
                    "Patient has not consented to phone contact",
                    call_id=str(call.call_id),
                    patient_id=call.patient_id,
                )

            return has_consent

        except Exception as e:
            log.error("Consent check failed", error=str(e))
            return False

    async def _log_call_attempt(self, call: QueuedCall) -> None:
        """Log call attempt for DSGVO compliance."""
        if self._audit_logger is None:
            return

        try:
            from phone_agent.industry.gesundheit.compliance import AuditAction

            self._audit_logger.log_action(
                actor="phone-agent-dialer",
                action=AuditAction.CALL,
                resource_type="patient",
                resource_id=call.patient_id,
                details={
                    "call_id": str(call.call_id),
                    "campaign_type": call.campaign_type,
                    "attempt_number": call.attempt_number,
                    "phone_number_masked": call.phone_number[-4:],
                },
            )
        except Exception as e:
            log.error("Audit log failed", error=str(e))

    async def _make_call(self, call: QueuedCall) -> CallOutcome:
        """Make the actual outbound call.

        Args:
            call: Call to make

        Returns:
            Call outcome
        """
        if self._sip_client is None:
            log.warning("No SIP client configured, simulating call")
            # Simulate for testing
            await asyncio.sleep(2.0)
            return CallOutcome.ANSWERED

        try:
            # Originate call
            sip_call = await self._sip_client.originate_call(
                destination=call.phone_number,
                caller_id=self.config.caller_id or None,
                timeout=self.config.ring_timeout_seconds,
                metadata={
                    "call_id": str(call.call_id),
                    "patient_id": call.patient_id,
                    "campaign_type": call.campaign_type,
                },
            )

            # Wait for answer
            answered = await self._sip_client.wait_for_answer(
                sip_call.call_id,
                timeout=self.config.ring_timeout_seconds,
            )

            if not answered:
                # Hangup and return no answer
                await self._sip_client.hangup(sip_call.call_id)
                return CallOutcome.NO_ANSWER

            # Call was answered - run the conversation
            outcome = await self._run_outbound_conversation(call, sip_call.call_id)

            # Hangup after conversation ends
            await self._sip_client.hangup(sip_call.call_id)

            return outcome

        except Exception as e:
            log.error("SIP call failed", error=str(e))
            return CallOutcome.FAILED

    async def _run_outbound_conversation(
        self,
        call: QueuedCall,
        sip_call_id: str,
    ) -> CallOutcome:
        """Run the outbound conversation flow.

        Args:
            call: Queued call with patient info
            sip_call_id: Active SIP call ID

        Returns:
            Call outcome based on conversation result
        """
        from phone_agent.industry.gesundheit.outbound.conversation_outbound import (
            CampaignType,
            OutboundContext,
            OutboundOutcome,
            get_outbound_conversation_manager,
        )
        from datetime import date, time as dt_time

        log.info(
            "Starting outbound conversation",
            call_id=str(call.call_id),
            sip_call_id=sip_call_id,
        )

        # Get or create conversation manager
        if self._conversation_manager is None:
            self._conversation_manager = get_outbound_conversation_manager()

        # Map campaign type
        try:
            campaign = CampaignType(call.campaign_type)
        except ValueError:
            campaign = CampaignType.REMINDER

        # Build conversation context from call metadata
        context = OutboundContext(
            call_id=call.call_id,
            campaign_type=campaign,
            patient_id=call.patient_id,
            patient_name=call.patient_name,
            patient_first_name=call.patient_name.split()[0] if call.patient_name else "",
            patient_phone=call.phone_number,
            campaign_id=call.campaign_id,
        )

        # Add appointment info from metadata if available
        if "appointment_date" in call.metadata:
            try:
                # Try to parse date string (e.g., "15.01.2025" or ISO format)
                date_str = call.metadata["appointment_date"]
                if "." in date_str:
                    parts = date_str.split(".")
                    context.appointment_date = date(
                        int(parts[2]), int(parts[1]), int(parts[0])
                    )
                else:
                    context.appointment_date = date.fromisoformat(date_str)
            except (ValueError, IndexError, KeyError):
                pass

        if "appointment_time" in call.metadata:
            try:
                time_str = call.metadata["appointment_time"]
                if ":" in time_str:
                    parts = time_str.split(":")
                    context.appointment_time = dt_time(int(parts[0]), int(parts[1]))
            except (ValueError, IndexError, KeyError):
                pass

        if "provider_name" in call.metadata:
            context.provider_name = call.metadata["provider_name"]

        try:
            # Start conversation - get initial greeting
            response = await self._conversation_manager.start_conversation(context)

            # Speak the greeting
            await self._speak_and_listen(sip_call_id, response.message)

            # Conversation loop
            max_turns = 20  # Safety limit
            turn_count = 0

            while not response.should_end_call and turn_count < max_turns:
                turn_count += 1

                # Listen for patient response
                patient_input = await self._listen_to_patient(sip_call_id)

                if not patient_input:
                    # Silence or failed transcription
                    patient_input = ""

                # Process through conversation manager
                response = await self._conversation_manager.process_input(
                    context, patient_input
                )

                # Handle transfer request
                if response.should_transfer:
                    log.info(
                        "Transfer requested",
                        call_id=str(call.call_id),
                        target=response.transfer_target,
                    )
                    # In production: initiate transfer via SIP
                    # await self._sip_client.transfer(sip_call_id, response.transfer_target)
                    return CallOutcome.ANSWERED

                # Speak the response
                if response.message:
                    await self._speak_and_listen(sip_call_id, response.message)

            # Map outcome to CallOutcome
            return self._map_conversation_outcome(context.outcome)

        except Exception as e:
            log.error(
                "Outbound conversation error",
                call_id=str(call.call_id),
                error=str(e),
            )
            return CallOutcome.FAILED

    async def _speak_and_listen(self, sip_call_id: str, message: str) -> None:
        """Speak message through TTS and prepare for listening.

        Args:
            sip_call_id: Active SIP call ID
            message: Text to speak
        """
        if self._sip_client is None:
            log.debug("No SIP client, simulating speech: %s", message[:50])
            await asyncio.sleep(len(message) * 0.05)  # Simulate speaking time
            return

        try:
            # In production: stream TTS audio to call
            # await self._sip_client.play_audio(sip_call_id, tts_audio)
            log.debug("Speaking: %s", message[:50])
            await asyncio.sleep(0.5)  # Placeholder
        except Exception as e:
            log.warning("TTS error", error=str(e))

    async def _listen_to_patient(self, sip_call_id: str) -> str:
        """Listen to patient and transcribe speech.

        Args:
            sip_call_id: Active SIP call ID

        Returns:
            Transcribed patient speech
        """
        if self._sip_client is None:
            log.debug("No SIP client, simulating listen")
            await asyncio.sleep(1.0)
            return "ja"  # Simulate positive response

        try:
            # In production: capture audio and transcribe via STT
            # audio = await self._sip_client.record(sip_call_id, duration=10)
            # transcription = await stt.transcribe(audio)
            log.debug("Listening for patient response")
            await asyncio.sleep(2.0)  # Placeholder
            return ""  # Would be actual transcription
        except Exception as e:
            log.warning("STT error", error=str(e))
            return ""

    def _map_conversation_outcome(self, outcome: Any) -> CallOutcome:
        """Map OutboundOutcome to CallOutcome.

        Args:
            outcome: Conversation outcome

        Returns:
            Corresponding call outcome
        """
        from phone_agent.industry.gesundheit.outbound.conversation_outbound import (
            OutboundOutcome,
        )

        if outcome is None:
            return CallOutcome.ANSWERED

        # Map outcomes
        outcome_map = {
            OutboundOutcome.APPOINTMENT_CONFIRMED: CallOutcome.ANSWERED,
            OutboundOutcome.APPOINTMENT_RESCHEDULED: CallOutcome.ANSWERED,
            OutboundOutcome.INFORMATION_DELIVERED: CallOutcome.ANSWERED,
            OutboundOutcome.CALLBACK_SCHEDULED: CallOutcome.ANSWERED,
            OutboundOutcome.PATIENT_DECLINED: CallOutcome.DECLINED,
            OutboundOutcome.PATIENT_UNAVAILABLE: CallOutcome.NO_ANSWER,
            OutboundOutcome.CALLBACK_REQUESTED: CallOutcome.ANSWERED,
            OutboundOutcome.VOICEMAIL_LEFT: CallOutcome.VOICEMAIL,
            OutboundOutcome.WRONG_PERSON: CallOutcome.WRONG_NUMBER,
            OutboundOutcome.WRONG_NUMBER: CallOutcome.WRONG_NUMBER,
            OutboundOutcome.IDENTITY_NOT_VERIFIED: CallOutcome.FAILED,
            OutboundOutcome.CONVERSATION_FAILED: CallOutcome.FAILED,
            OutboundOutcome.PATIENT_HUNG_UP: CallOutcome.ANSWERED,  # Still answered initially
        }

        return outcome_map.get(outcome, CallOutcome.ANSWERED)

    async def _handle_outcome(self, call: QueuedCall, outcome: CallOutcome) -> None:
        """Handle call outcome (retry, SMS fallback, etc).

        Args:
            call: Call that completed
            outcome: Outcome of the call
        """
        self._stats.calls_completed += 1
        self._stats.last_call_at = datetime.now()

        # Update stats
        if outcome == CallOutcome.ANSWERED:
            self._stats.calls_answered += 1
        elif outcome == CallOutcome.NO_ANSWER:
            self._stats.calls_no_answer += 1
        elif outcome in (CallOutcome.FAILED, CallOutcome.NO_CONSENT):
            self._stats.calls_failed += 1

        log.info(
            "Call completed",
            call_id=str(call.call_id),
            outcome=outcome.value,
            attempt=call.attempt_number,
        )

        # Notify callback
        if self._on_call_complete:
            await self._on_call_complete(call, outcome)

        # Handle retry logic
        if outcome in (CallOutcome.NO_ANSWER, CallOutcome.BUSY, CallOutcome.FAILED):
            if call.attempt_number < call.max_attempts:
                # Schedule retry
                await self._schedule_retry(call)
            elif call.attempt_number >= self.config.sms_after_failed_attempts:
                # SMS fallback
                await self._send_sms_fallback(call)

    async def _schedule_retry(self, call: QueuedCall) -> None:
        """Schedule a retry for failed call.

        Args:
            call: Call to retry
        """
        from datetime import timedelta

        retry_time = datetime.now() + timedelta(
            minutes=self.config.retry_delay_minutes
        )

        retry_call = QueuedCall(
            priority=call.priority,
            scheduled_at=retry_time,
            patient_id=call.patient_id,
            phone_number=call.phone_number,
            patient_name=call.patient_name,
            campaign_id=call.campaign_id,
            campaign_type=call.campaign_type,
            attempt_number=call.attempt_number + 1,
            max_attempts=call.max_attempts,
            metadata=call.metadata,
        )

        heapq.heappush(self._queue, retry_call)

        log.info(
            "Call retry scheduled",
            call_id=str(retry_call.call_id),
            attempt=retry_call.attempt_number,
            scheduled_at=retry_time.isoformat(),
        )

    async def _send_sms_fallback(self, call: QueuedCall) -> None:
        """Send SMS fallback after failed call attempts.

        Args:
            call: Call that failed
        """
        log.info(
            "Sending SMS fallback",
            call_id=str(call.call_id),
            patient_id=call.patient_id,
        )

        # Notify callback first (for any custom handling)
        if self._on_sms_fallback:
            await self._on_sms_fallback(call)

        # Send actual SMS via gateway
        if self._sms_gateway is None:
            log.warning(
                "SMS gateway not configured, cannot send fallback SMS",
                call_id=str(call.call_id),
            )
            return

        try:
            from phone_agent.integrations.sms.base import SMSMessage

            # Generate message based on campaign type
            sms_body = self._generate_fallback_sms(call)

            message = SMSMessage(
                to=call.phone_number,
                body=sms_body,
                reference=f"fallback_{call.call_id}",
            )

            result = await self._sms_gateway.send(message)

            if result.success:
                self._stats.sms_sent += 1
                log.info(
                    "SMS fallback sent successfully",
                    call_id=str(call.call_id),
                    message_id=result.message_id,
                )
            else:
                log.error(
                    "SMS fallback failed",
                    call_id=str(call.call_id),
                    error=result.error_message,
                )

        except Exception as e:
            log.error(
                "SMS fallback error",
                call_id=str(call.call_id),
                error=str(e),
            )

    def _generate_fallback_sms(self, call: QueuedCall) -> str:
        """Generate SMS content based on campaign type.

        Args:
            call: Call that failed

        Returns:
            SMS message body
        """
        first_name = call.patient_name.split()[0] if call.patient_name else "Patient"
        practice = self._practice_name

        if call.campaign_type == "reminder":
            # Appointment reminder
            appointment_info = call.metadata.get("appointment_date", "")
            appointment_time = call.metadata.get("appointment_time", "")
            if appointment_info and appointment_time:
                return (
                    f"Terminerinnerung {practice}\n\n"
                    f"Guten Tag {first_name},\n"
                    f"wir erinnern Sie an Ihren Termin am {appointment_info} "
                    f"um {appointment_time} Uhr.\n\n"
                    f"Bei Verhinderung rufen Sie uns bitte an.\n"
                    f"Ihre {practice}"
                )
            return (
                f"Terminerinnerung {practice}\n\n"
                f"Guten Tag {first_name},\n"
                f"wir wollten Sie an Ihren bevorstehenden Termin erinnern. "
                f"Bitte kontaktieren Sie uns bei Fragen.\n\n"
                f"Ihre {practice}"
            )

        elif call.campaign_type == "recall":
            # Recall/checkup reminder
            return (
                f"Gesundheitsvorsorge {practice}\n\n"
                f"Guten Tag {first_name},\n"
                f"es ist Zeit für Ihren nächsten Vorsorgetermin. "
                f"Bitte rufen Sie uns an zur Terminvereinbarung.\n\n"
                f"Ihre {practice}"
            )

        elif call.campaign_type == "noshow":
            # No-show follow-up
            return (
                f"Terminabsage {practice}\n\n"
                f"Guten Tag {first_name},\n"
                f"wir haben Sie leider bei Ihrem Termin verpasst. "
                f"Bitte kontaktieren Sie uns zur Neuterminierung.\n\n"
                f"Ihre {practice}"
            )

        elif call.campaign_type == "followup":
            # Post-treatment follow-up
            return (
                f"Nachsorge {practice}\n\n"
                f"Guten Tag {first_name},\n"
                f"wir möchten uns nach Ihrer Behandlung erkundigen. "
                f"Bitte rufen Sie uns bei Fragen an.\n\n"
                f"Ihre {practice}"
            )

        else:
            # Generic fallback
            return (
                f"{practice}\n\n"
                f"Guten Tag {first_name},\n"
                f"wir haben versucht, Sie telefonisch zu erreichen. "
                f"Bitte rufen Sie uns zurück.\n\n"
                f"Ihre {practice}"
            )

    # ========== Callbacks ==========

    def on_call_start(
        self,
        callback: Callable[[QueuedCall], Awaitable[None]],
    ) -> None:
        """Set callback for when a call starts."""
        self._on_call_start = callback

    def on_call_complete(
        self,
        callback: Callable[[QueuedCall, CallOutcome], Awaitable[None]],
    ) -> None:
        """Set callback for when a call completes."""
        self._on_call_complete = callback

    def on_sms_fallback(
        self,
        callback: Callable[[QueuedCall], Awaitable[None]],
    ) -> None:
        """Set callback for SMS fallback."""
        self._on_sms_fallback = callback


def get_outbound_dialer(
    config: DialerConfig | None = None,
    sip_client: Any | None = None,
    consent_manager: Any | None = None,
    audit_logger: Any | None = None,
    sms_gateway: "SMSGateway | None" = None,
    practice_name: str = "Praxis",
) -> OutboundDialer:
    """Get or create the global OutboundDialer singleton.

    Args:
        config: Dialer configuration (only used on first call)
        sip_client: SIP client (only used on first call)
        consent_manager: Consent manager (only used on first call)
        audit_logger: Audit logger (only used on first call)
        sms_gateway: SMS gateway for fallback (only used on first call)
        practice_name: Practice name for SMS (only used on first call)

    Returns:
        OutboundDialer instance
    """
    global _outbound_dialer

    if _outbound_dialer is None:
        _outbound_dialer = OutboundDialer(
            config=config,
            sip_client=sip_client,
            consent_manager=consent_manager,
            audit_logger=audit_logger,
            sms_gateway=sms_gateway,
            practice_name=practice_name,
        )

    return _outbound_dialer
