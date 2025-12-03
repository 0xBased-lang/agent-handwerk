"""SIP Client for VoIP integration.

Provides a high-level interface for SIP operations:
- Register with SIP server
- Answer incoming calls
- Make outgoing calls
- Handle call audio
- Transfer calls

Works with SIP gateways like Grandstream HT801 or software PBX.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable
from uuid import UUID, uuid4

from itf_shared import get_logger

log = get_logger(__name__)


class SIPCallState(str, Enum):
    """SIP call states."""

    IDLE = "idle"
    TRYING = "trying"
    RINGING = "ringing"
    EARLY_MEDIA = "early_media"
    CONFIRMED = "confirmed"
    ON_HOLD = "on_hold"
    DISCONNECTED = "disconnected"


@dataclass
class SIPConfig:
    """SIP client configuration."""

    # SIP Server
    server: str = ""
    port: int = 5060
    transport: str = "udp"  # udp, tcp, tls

    # Authentication
    username: str = ""
    password: str = ""
    realm: str = ""
    display_name: str = "Phone Agent"

    # Registration
    register: bool = True
    register_expires: int = 300  # seconds

    # Audio
    rtp_port_start: int = 10000
    rtp_port_end: int = 10100
    codecs: list[str] = field(default_factory=lambda: ["PCMU", "PCMA", "G722"])

    # Timeouts
    call_timeout: int = 60  # seconds
    ring_timeout: int = 30  # seconds


@dataclass
class SIPCall:
    """Represents an active SIP call."""

    call_id: UUID = field(default_factory=uuid4)
    sip_call_id: str = ""
    direction: str = "inbound"  # inbound, outbound
    state: SIPCallState = SIPCallState.IDLE
    caller_id: str = ""
    callee_id: str = ""
    started_at: datetime | None = None
    answered_at: datetime | None = None
    ended_at: datetime | None = None
    rtp_local_port: int = 0
    rtp_remote_host: str = ""
    rtp_remote_port: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def duration_seconds(self) -> float | None:
        """Get call duration in seconds."""
        if self.answered_at is None:
            return None
        end = self.ended_at or datetime.now()
        return (end - self.answered_at).total_seconds()


class SIPClient:
    """SIP client for VoIP integration.

    This is a simplified SIP client that works via webhooks and
    external media handling. For full SIP stack, use FreeSwitchClient.

    Usage:
        client = SIPClient(SIPConfig(server="sip.example.com"))
        await client.start()

        @client.on_incoming_call
        async def handle_call(call: SIPCall):
            await client.answer(call.call_id)
            # Handle audio...
            await client.hangup(call.call_id)
    """

    def __init__(self, config: SIPConfig) -> None:
        """Initialize SIP client.

        Args:
            config: SIP configuration
        """
        self.config = config
        self._running = False
        self._calls: dict[UUID, SIPCall] = {}
        self._registered = False

        # Callbacks
        self._on_incoming_call: Callable[[SIPCall], Any] | None = None
        self._on_call_state_change: Callable[[SIPCall, SIPCallState], Any] | None = None
        self._on_audio_frame: Callable[[UUID, bytes], Any] | None = None

    async def start(self) -> None:
        """Start the SIP client."""
        if self._running:
            return

        self._running = True

        if self.config.register and self.config.server:
            await self._register()

        log.info(
            "SIP client started",
            server=self.config.server,
            username=self.config.username,
        )

    async def stop(self) -> None:
        """Stop the SIP client."""
        if not self._running:
            return

        # Hangup all calls
        for call_id in list(self._calls.keys()):
            await self.hangup(call_id)

        # Unregister
        if self._registered:
            await self._unregister()

        self._running = False
        log.info("SIP client stopped")

    async def _register(self) -> None:
        """Register with SIP server."""
        log.info("Registering with SIP server", server=self.config.server)
        # In a real implementation, this would send SIP REGISTER
        # For now, we assume registration is handled externally (e.g., by gateway)
        self._registered = True

    async def _unregister(self) -> None:
        """Unregister from SIP server."""
        log.info("Unregistering from SIP server")
        self._registered = False

    async def handle_incoming_call(
        self,
        sip_call_id: str,
        caller_id: str,
        callee_id: str,
        metadata: dict[str, Any] | None = None,
    ) -> SIPCall:
        """Handle an incoming SIP call (called by webhook).

        Args:
            sip_call_id: SIP Call-ID header
            caller_id: Caller's number/URI
            callee_id: Called number/URI
            metadata: Additional SIP headers/data

        Returns:
            SIPCall object
        """
        call = SIPCall(
            sip_call_id=sip_call_id,
            direction="inbound",
            state=SIPCallState.RINGING,
            caller_id=caller_id,
            callee_id=callee_id,
            started_at=datetime.now(),
            metadata=metadata or {},
        )
        self._calls[call.call_id] = call

        log.info(
            "Incoming call",
            call_id=str(call.call_id),
            sip_call_id=sip_call_id,
            caller=caller_id,
        )

        if self._on_incoming_call:
            await self._on_incoming_call(call)

        return call

    async def answer(self, call_id: UUID) -> bool:
        """Answer an incoming call.

        Args:
            call_id: Call to answer

        Returns:
            True if successful
        """
        call = self._calls.get(call_id)
        if not call:
            log.warning("Cannot answer: call not found", call_id=str(call_id))
            return False

        if call.state != SIPCallState.RINGING:
            log.warning("Cannot answer: call not ringing", state=call.state.value)
            return False

        # In real implementation: send SIP 200 OK
        call.state = SIPCallState.CONFIRMED
        call.answered_at = datetime.now()

        log.info("Call answered", call_id=str(call_id))

        if self._on_call_state_change:
            await self._on_call_state_change(call, SIPCallState.CONFIRMED)

        return True

    async def hangup(self, call_id: UUID) -> bool:
        """Hangup a call.

        Args:
            call_id: Call to hangup

        Returns:
            True if successful
        """
        call = self._calls.get(call_id)
        if not call:
            return False

        # In real implementation: send SIP BYE
        call.state = SIPCallState.DISCONNECTED
        call.ended_at = datetime.now()

        log.info(
            "Call ended",
            call_id=str(call_id),
            duration=call.duration_seconds,
        )

        if self._on_call_state_change:
            await self._on_call_state_change(call, SIPCallState.DISCONNECTED)

        # Remove from active calls
        del self._calls[call_id]

        return True

    async def transfer(self, call_id: UUID, target: str) -> bool:
        """Transfer a call to another number.

        Args:
            call_id: Call to transfer
            target: Target number/URI

        Returns:
            True if successful
        """
        call = self._calls.get(call_id)
        if not call or call.state != SIPCallState.CONFIRMED:
            return False

        # In real implementation: send SIP REFER
        log.info(
            "Transferring call",
            call_id=str(call_id),
            target=target,
        )

        # For now, just hangup (transfer would be handled by PBX)
        return await self.hangup(call_id)

    async def hold(self, call_id: UUID) -> bool:
        """Put a call on hold.

        Args:
            call_id: Call to hold

        Returns:
            True if successful
        """
        call = self._calls.get(call_id)
        if not call or call.state != SIPCallState.CONFIRMED:
            return False

        call.state = SIPCallState.ON_HOLD
        log.info("Call on hold", call_id=str(call_id))

        if self._on_call_state_change:
            await self._on_call_state_change(call, SIPCallState.ON_HOLD)

        return True

    async def unhold(self, call_id: UUID) -> bool:
        """Resume a held call.

        Args:
            call_id: Call to resume

        Returns:
            True if successful
        """
        call = self._calls.get(call_id)
        if not call or call.state != SIPCallState.ON_HOLD:
            return False

        call.state = SIPCallState.CONFIRMED
        log.info("Call resumed", call_id=str(call_id))

        if self._on_call_state_change:
            await self._on_call_state_change(call, SIPCallState.CONFIRMED)

        return True

    async def send_dtmf(self, call_id: UUID, digits: str) -> bool:
        """Send DTMF tones.

        Args:
            call_id: Call to send DTMF on
            digits: DTMF digits (0-9, *, #)

        Returns:
            True if successful
        """
        call = self._calls.get(call_id)
        if not call or call.state != SIPCallState.CONFIRMED:
            return False

        log.info("Sending DTMF", call_id=str(call_id), digits=digits)
        return True

    # ========== OUTBOUND CALLING ==========

    async def originate_call(
        self,
        destination: str,
        caller_id: str | None = None,
        timeout: int | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> SIPCall:
        """Initiate an outbound call.

        Args:
            destination: Phone number to dial (E.164 format preferred)
            caller_id: Caller ID to display (defaults to config display_name)
            timeout: Ring timeout in seconds (defaults to config ring_timeout)
            metadata: Additional call metadata (campaign_id, patient_id, etc.)

        Returns:
            SIPCall object in TRYING state
        """
        if not self._running:
            raise RuntimeError("SIP client not running")

        ring_timeout = timeout or self.config.ring_timeout

        call = SIPCall(
            sip_call_id=f"out-{uuid4().hex[:12]}",
            direction="outbound",
            state=SIPCallState.TRYING,
            caller_id=caller_id or self.config.display_name,
            callee_id=destination,
            started_at=datetime.now(),
            metadata=metadata or {},
        )
        self._calls[call.call_id] = call

        log.info(
            "Originating outbound call",
            call_id=str(call.call_id),
            destination=destination,
            timeout=ring_timeout,
        )

        # In production: Send SIP INVITE via FreeSWITCH ESL or webhook
        # For now, simulate state transitions for testing
        # The actual INVITE would be handled by the PBX/gateway

        return call

    async def wait_for_answer(
        self,
        call_id: UUID,
        timeout: int | None = None,
    ) -> bool:
        """Wait for an outbound call to be answered.

        Args:
            call_id: Call ID to wait for
            timeout: Timeout in seconds (defaults to config ring_timeout)

        Returns:
            True if call was answered, False if timeout or not found
        """
        call = self._calls.get(call_id)
        if not call:
            log.warning("Cannot wait: call not found", call_id=str(call_id))
            return False

        if call.direction != "outbound":
            log.warning("Cannot wait: not an outbound call", call_id=str(call_id))
            return False

        wait_timeout = timeout or self.config.ring_timeout
        poll_interval = 0.5  # 500ms

        elapsed = 0.0
        while elapsed < wait_timeout:
            call = self._calls.get(call_id)
            if not call:
                log.warning("Call disappeared while waiting", call_id=str(call_id))
                return False

            if call.state == SIPCallState.CONFIRMED:
                log.info(
                    "Outbound call answered",
                    call_id=str(call_id),
                    wait_time=elapsed,
                )
                return True

            if call.state == SIPCallState.DISCONNECTED:
                log.info(
                    "Outbound call not answered",
                    call_id=str(call_id),
                    wait_time=elapsed,
                )
                return False

            await asyncio.sleep(poll_interval)
            elapsed += poll_interval

        log.info(
            "Outbound call timeout",
            call_id=str(call_id),
            timeout=wait_timeout,
        )
        return False

    async def handle_outbound_progress(
        self,
        call_id: UUID,
        new_state: SIPCallState,
    ) -> bool:
        """Handle outbound call progress (called by webhook/ESL).

        Args:
            call_id: Call ID
            new_state: New state (RINGING, EARLY_MEDIA, CONFIRMED, DISCONNECTED)

        Returns:
            True if state was updated
        """
        call = self._calls.get(call_id)
        if not call:
            return False

        old_state = call.state
        call.state = new_state

        if new_state == SIPCallState.CONFIRMED and call.answered_at is None:
            call.answered_at = datetime.now()

        log.info(
            "Outbound call progress",
            call_id=str(call_id),
            old_state=old_state.value,
            new_state=new_state.value,
        )

        if self._on_call_state_change:
            await self._on_call_state_change(call, new_state)

        return True

    def on_incoming_call(self, callback: Callable[[SIPCall], Any]) -> None:
        """Set callback for incoming calls."""
        self._on_incoming_call = callback

    def on_call_state_change(
        self,
        callback: Callable[[SIPCall, SIPCallState], Any],
    ) -> None:
        """Set callback for call state changes."""
        self._on_call_state_change = callback

    def on_audio_frame(self, callback: Callable[[UUID, bytes], Any]) -> None:
        """Set callback for audio frames."""
        self._on_audio_frame = callback

    def get_call(self, call_id: UUID) -> SIPCall | None:
        """Get call by ID."""
        return self._calls.get(call_id)

    def get_call_by_sip_id(self, sip_call_id: str) -> SIPCall | None:
        """Get call by SIP Call-ID."""
        for call in self._calls.values():
            if call.sip_call_id == sip_call_id:
                return call
        return None

    @property
    def active_calls(self) -> list[SIPCall]:
        """Get list of active calls."""
        return [
            c for c in self._calls.values()
            if c.state not in (SIPCallState.IDLE, SIPCallState.DISCONNECTED)
        ]

    @property
    def is_registered(self) -> bool:
        """Check if registered with SIP server."""
        return self._registered

    @property
    def is_running(self) -> bool:
        """Check if client is running."""
        return self._running
