"""Campaign Scheduler Service.

Background job scheduler for processing recall campaign calls.
Runs as an asyncio task and continuously processes due contacts.

Features:
- Configurable polling interval
- Concurrent call limit
- Graceful shutdown
- Error recovery
- Metrics collection
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, time
from enum import Enum
from typing import Any, Callable
from uuid import UUID

from itf_shared import get_logger

log = get_logger(__name__)


class SchedulerState(str, Enum):
    """Scheduler states."""

    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    PAUSED = "paused"
    STOPPING = "stopping"


@dataclass
class SchedulerConfig:
    """Campaign scheduler configuration."""

    # Polling
    poll_interval_seconds: int = 10  # How often to check for due contacts
    batch_size: int = 5  # Contacts to process per batch

    # Concurrency
    max_concurrent_calls: int = 3  # Maximum simultaneous calls

    # Timing
    start_hour: int = 8  # Don't call before (local time)
    end_hour: int = 20  # Don't call after (local time)
    respect_quiet_hours: bool = True

    # Error handling
    max_retries_on_error: int = 3
    retry_delay_seconds: int = 60

    # Metrics
    collect_metrics: bool = True
    metrics_interval_seconds: int = 60


@dataclass
class SchedulerMetrics:
    """Scheduler performance metrics."""

    started_at: datetime | None = None
    contacts_processed: int = 0
    calls_initiated: int = 0
    calls_completed: int = 0
    calls_failed: int = 0
    errors: int = 0
    last_poll_at: datetime | None = None
    last_error: str | None = None
    average_call_duration: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "contacts_processed": self.contacts_processed,
            "calls_initiated": self.calls_initiated,
            "calls_completed": self.calls_completed,
            "calls_failed": self.calls_failed,
            "errors": self.errors,
            "last_poll_at": self.last_poll_at.isoformat() if self.last_poll_at else None,
            "last_error": self.last_error,
            "average_call_duration": round(self.average_call_duration, 2),
        }


class CampaignScheduler:
    """Background scheduler for processing recall campaign calls.

    Runs as an asyncio background task, continuously polling for
    contacts that are due for calling and initiating calls.

    Usage:
        scheduler = CampaignScheduler(
            config=SchedulerConfig(poll_interval_seconds=10),
            call_handler=my_call_handler,
        )

        # In application lifespan
        await scheduler.start()

        # When shutting down
        await scheduler.stop()
    """

    def __init__(
        self,
        config: SchedulerConfig | None = None,
        call_handler: Callable[[UUID, dict[str, Any]], Any] | None = None,
    ) -> None:
        """Initialize scheduler.

        Args:
            config: Scheduler configuration
            call_handler: Async function to initiate calls
        """
        self.config = config or SchedulerConfig()
        self._call_handler = call_handler

        self._state = SchedulerState.STOPPED
        self._task: asyncio.Task | None = None
        self._active_calls: set[UUID] = set()
        self._metrics = SchedulerMetrics()

        # Semaphore for concurrent call limiting
        self._call_semaphore = asyncio.Semaphore(self.config.max_concurrent_calls)

        # Stop event
        self._stop_event = asyncio.Event()

    @property
    def state(self) -> SchedulerState:
        """Get current scheduler state."""
        return self._state

    @property
    def metrics(self) -> SchedulerMetrics:
        """Get scheduler metrics."""
        return self._metrics

    @property
    def is_running(self) -> bool:
        """Check if scheduler is running."""
        return self._state == SchedulerState.RUNNING

    @property
    def active_call_count(self) -> int:
        """Get number of active calls."""
        return len(self._active_calls)

    def set_call_handler(
        self,
        handler: Callable[[UUID, dict[str, Any]], Any],
    ) -> None:
        """Set the call handler function.

        Args:
            handler: Async function called to initiate calls
                     Receives (contact_id, contact_data) and should
                     return call result dict
        """
        self._call_handler = handler

    async def start(self) -> None:
        """Start the scheduler background task."""
        if self._state != SchedulerState.STOPPED:
            log.warning(f"Scheduler already in state: {self._state}")
            return

        self._state = SchedulerState.STARTING
        self._stop_event.clear()
        self._metrics = SchedulerMetrics(started_at=datetime.now())

        log.info("Starting campaign scheduler")

        # Start background task
        self._task = asyncio.create_task(self._run_loop())
        self._state = SchedulerState.RUNNING

        log.info("Campaign scheduler started")

    async def stop(self, timeout: float = 30.0) -> None:
        """Stop the scheduler gracefully.

        Args:
            timeout: Maximum time to wait for active calls to complete
        """
        if self._state == SchedulerState.STOPPED:
            return

        log.info("Stopping campaign scheduler")
        self._state = SchedulerState.STOPPING
        self._stop_event.set()

        # Wait for background task
        if self._task:
            try:
                await asyncio.wait_for(self._task, timeout=timeout)
            except asyncio.TimeoutError:
                log.warning("Scheduler stop timed out, cancelling task")
                self._task.cancel()
                try:
                    await self._task
                except asyncio.CancelledError:
                    pass

        self._state = SchedulerState.STOPPED
        log.info("Campaign scheduler stopped")

    async def pause(self) -> None:
        """Pause the scheduler (stop processing new calls)."""
        if self._state == SchedulerState.RUNNING:
            self._state = SchedulerState.PAUSED
            log.info("Campaign scheduler paused")

    async def resume(self) -> None:
        """Resume a paused scheduler."""
        if self._state == SchedulerState.PAUSED:
            self._state = SchedulerState.RUNNING
            log.info("Campaign scheduler resumed")

    async def _run_loop(self) -> None:
        """Main scheduler loop."""
        while not self._stop_event.is_set():
            try:
                # Only process if running (not paused)
                if self._state == SchedulerState.RUNNING:
                    await self._process_batch()

                self._metrics.last_poll_at = datetime.now()

                # Wait for next poll or stop
                try:
                    await asyncio.wait_for(
                        self._stop_event.wait(),
                        timeout=self.config.poll_interval_seconds,
                    )
                except asyncio.TimeoutError:
                    pass  # Normal timeout, continue loop

            except Exception as e:
                self._metrics.errors += 1
                self._metrics.last_error = str(e)
                log.error(f"Scheduler loop error: {e}")

                # Wait before retrying
                await asyncio.sleep(self.config.retry_delay_seconds)

        # Wait for active calls to complete
        if self._active_calls:
            log.info(f"Waiting for {len(self._active_calls)} active calls to complete")
            # Give calls time to finish
            await asyncio.sleep(5)

    async def _process_batch(self) -> None:
        """Process a batch of due contacts."""
        # Check quiet hours
        if self.config.respect_quiet_hours and not self._is_calling_allowed():
            log.debug("Outside calling hours, skipping batch")
            return

        # Check if we have capacity
        if self.active_call_count >= self.config.max_concurrent_calls:
            log.debug("At max concurrent calls, skipping batch")
            return

        # Get due contacts
        contacts = await self._get_due_contacts()
        if not contacts:
            return

        log.debug(f"Processing {len(contacts)} contacts")

        # Process each contact
        for contact in contacts:
            if self._stop_event.is_set():
                break

            # Check capacity again
            if self.active_call_count >= self.config.max_concurrent_calls:
                break

            # Start call in background
            asyncio.create_task(self._process_contact(contact))

    async def _process_contact(self, contact: dict[str, Any]) -> None:
        """Process a single contact (initiate call).

        Args:
            contact: Contact data dict
        """
        contact_id = contact.get("id")
        if not contact_id:
            return

        contact_uuid = UUID(contact_id) if isinstance(contact_id, str) else contact_id

        async with self._call_semaphore:
            self._active_calls.add(contact_uuid)
            self._metrics.contacts_processed += 1

            try:
                log.info(f"Initiating call for contact: {contact_id}")

                if self._call_handler:
                    self._metrics.calls_initiated += 1
                    result = await self._call_handler(contact_uuid, contact)

                    if result and result.get("success"):
                        self._metrics.calls_completed += 1
                        duration = result.get("duration", 0)
                        self._update_average_duration(duration)
                    else:
                        self._metrics.calls_failed += 1
                else:
                    log.warning("No call handler configured")

            except Exception as e:
                self._metrics.calls_failed += 1
                self._metrics.errors += 1
                self._metrics.last_error = str(e)
                log.error(f"Error processing contact {contact_id}: {e}")

            finally:
                self._active_calls.discard(contact_uuid)

    async def _get_due_contacts(self) -> list[dict[str, Any]]:
        """Get contacts that are due for calling.

        Returns:
            List of contact data dicts
        """
        from phone_agent.db import get_session
        from phone_agent.services.recall_service import RecallService

        try:
            async with get_session() as session:
                service = RecallService(session)
                contacts = await service.get_contacts_to_call(
                    limit=self.config.batch_size
                )
                return [c.to_dict() for c in contacts]

        except Exception as e:
            log.error(f"Error getting due contacts: {e}")
            return []

    def _is_calling_allowed(self) -> bool:
        """Check if current time is within calling hours.

        Returns:
            True if calling is allowed
        """
        now = datetime.now()
        current_hour = now.hour

        return self.config.start_hour <= current_hour < self.config.end_hour

    def _update_average_duration(self, duration: int) -> None:
        """Update rolling average call duration.

        Args:
            duration: Call duration in seconds
        """
        completed = self._metrics.calls_completed
        if completed > 0:
            # Exponential moving average
            alpha = 0.2
            self._metrics.average_call_duration = (
                alpha * duration
                + (1 - alpha) * self._metrics.average_call_duration
            )

    def get_status(self) -> dict[str, Any]:
        """Get scheduler status.

        Returns:
            Status dictionary
        """
        return {
            "state": self._state.value,
            "is_running": self.is_running,
            "active_calls": self.active_call_count,
            "max_concurrent_calls": self.config.max_concurrent_calls,
            "poll_interval_seconds": self.config.poll_interval_seconds,
            "calling_hours": {
                "start": self.config.start_hour,
                "end": self.config.end_hour,
                "currently_allowed": self._is_calling_allowed(),
            },
            "metrics": self._metrics.to_dict(),
        }


class OutboundCallHandler:
    """Default call handler for outbound campaign calls.

    Integrates with the telephony service to make actual calls.
    """

    def __init__(self) -> None:
        """Initialize call handler."""
        self._telephony_service = None

    async def __call__(
        self,
        contact_id: UUID,
        contact_data: dict[str, Any],
    ) -> dict[str, Any]:
        """Handle outbound call for a contact.

        Args:
            contact_id: Campaign contact UUID
            contact_data: Contact data dict

        Returns:
            Call result dict
        """
        from phone_agent.db import get_session
        from phone_agent.services.recall_service import RecallService
        from phone_agent.telephony.service import TelephonyService

        phone_number = contact_data.get("phone_number")
        if not phone_number:
            return {"success": False, "error": "No phone number"}

        try:
            # Get telephony service
            if not self._telephony_service:
                self._telephony_service = TelephonyService()

            # Initiate call
            call_result = await self._telephony_service.originate_call(
                destination=phone_number,
                caller_id_name=contact_data.get("campaign_name", "Phone Agent"),
                metadata={
                    "campaign_contact_id": str(contact_id),
                    "campaign_id": contact_data.get("campaign_id"),
                    "contact_name": contact_data.get("contact_name"),
                },
            )

            # Record result
            async with get_session() as session:
                service = RecallService(session)
                await service.record_call_attempt(
                    contact_id=contact_id,
                    result=call_result.get("result", "unknown"),
                    duration=call_result.get("duration"),
                    call_id=call_result.get("call_id"),
                )

            return {
                "success": call_result.get("success", False),
                "call_id": call_result.get("call_id"),
                "duration": call_result.get("duration"),
                "result": call_result.get("result"),
            }

        except Exception as e:
            log.error(f"Call handler error: {e}")
            return {"success": False, "error": str(e)}
