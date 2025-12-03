"""Telephony service integrating all components.

Main service that orchestrates:
- SIP/FreeSWITCH connectivity
- Audio bridge
- AI conversation pipeline
- Call state management
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any
from uuid import UUID

import numpy as np
from itf_shared import get_logger

from phone_agent.config import get_settings
from phone_agent.core import ConversationEngine, CallHandler, CallState
from phone_agent.telephony.sip_client import SIPClient, SIPConfig, SIPCall
from phone_agent.telephony.freeswitch import FreeSwitchClient, FreeSwitchConfig, FreeSwitchEvent
from phone_agent.telephony.audio_bridge import AudioBridge, AudioBridgeConfig

log = get_logger(__name__)


@dataclass
class TelephonyServiceConfig:
    """Telephony service configuration."""

    # Backend selection
    backend: str = "webhook"  # webhook, freeswitch, sip

    # FreeSWITCH (if using)
    freeswitch_host: str = "127.0.0.1"
    freeswitch_port: int = 8021
    freeswitch_password: str = "ClueCon"

    # SIP (if using)
    sip_server: str = ""
    sip_username: str = ""
    sip_password: str = ""

    # Audio bridge
    audio_bridge_host: str = "0.0.0.0"
    audio_bridge_port: int = 9090

    # AI
    preload_models: bool = True


class TelephonyService:
    """Main telephony service.

    Coordinates all telephony components:
    - Call handling (SIP or FreeSWITCH)
    - Audio streaming
    - AI conversation

    Usage:
        service = TelephonyService()
        await service.start()

        # Service runs until stopped
        await service.wait_until_stopped()
    """

    def __init__(self, config: TelephonyServiceConfig | None = None) -> None:
        """Initialize telephony service.

        Args:
            config: Service configuration
        """
        self.config = config or TelephonyServiceConfig()

        # Components
        self.conversation_engine = ConversationEngine()
        self.call_handler = CallHandler(conversation_engine=self.conversation_engine)
        self.audio_bridge = AudioBridge(
            AudioBridgeConfig(
                host=self.config.audio_bridge_host,
                port=self.config.audio_bridge_port,
            )
        )

        # Backend-specific clients
        self.freeswitch_client: FreeSwitchClient | None = None
        self.sip_client: SIPClient | None = None

        # State
        self._running = False
        self._tasks: list[asyncio.Task[Any]] = []
        self._stop_event = asyncio.Event()

        # Call mapping: external_id -> internal_call_id
        self._call_map: dict[str, UUID] = {}

    async def start(self) -> None:
        """Start the telephony service."""
        if self._running:
            return

        self._running = True
        self._stop_event.clear()

        log.info("Starting telephony service", backend=self.config.backend)

        # Preload AI models
        if self.config.preload_models:
            log.info("Preloading AI models...")
            self.conversation_engine.preload_models()

        # Setup audio bridge callbacks
        self.audio_bridge.on_audio_received(self._on_audio_received)
        self.audio_bridge.on_connection(self._on_audio_connection)
        self.audio_bridge.on_disconnection(self._on_audio_disconnection)

        # Start backend
        if self.config.backend == "freeswitch":
            await self._start_freeswitch()
        elif self.config.backend == "sip":
            await self._start_sip()
        else:
            log.info("Using webhook backend (no active connection)")

        # Start audio bridge in background
        bridge_task = asyncio.create_task(self.audio_bridge.start())
        self._tasks.append(bridge_task)

        log.info("Telephony service started")

    async def stop(self) -> None:
        """Stop the telephony service."""
        if not self._running:
            return

        log.info("Stopping telephony service...")
        self._running = False
        self._stop_event.set()

        # Stop backends
        if self.freeswitch_client:
            await self.freeswitch_client.disconnect()
        if self.sip_client:
            await self.sip_client.stop()

        # Stop audio bridge
        await self.audio_bridge.stop()

        # Cancel tasks
        for task in self._tasks:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        # Unload models
        self.conversation_engine.unload_models()

        log.info("Telephony service stopped")

    async def wait_until_stopped(self) -> None:
        """Wait until service is stopped."""
        await self._stop_event.wait()

    async def _start_freeswitch(self) -> None:
        """Start FreeSWITCH backend."""
        self.freeswitch_client = FreeSwitchClient(
            FreeSwitchConfig(
                host=self.config.freeswitch_host,
                port=self.config.freeswitch_port,
                password=self.config.freeswitch_password,
            )
        )

        # Register event handlers
        @self.freeswitch_client.on_event("CHANNEL_CREATE")
        async def on_channel_create(event: FreeSwitchEvent):
            await self._handle_freeswitch_incoming(event)

        @self.freeswitch_client.on_event("CHANNEL_HANGUP")
        async def on_channel_hangup(event: FreeSwitchEvent):
            await self._handle_freeswitch_hangup(event)

        await self.freeswitch_client.connect()

    async def _start_sip(self) -> None:
        """Start SIP backend."""
        self.sip_client = SIPClient(
            SIPConfig(
                server=self.config.sip_server,
                username=self.config.sip_username,
                password=self.config.sip_password,
            )
        )

        self.sip_client.on_incoming_call(self._handle_sip_incoming)
        await self.sip_client.start()

    # FreeSWITCH Handlers

    async def _handle_freeswitch_incoming(self, event: FreeSwitchEvent) -> None:
        """Handle incoming call from FreeSWITCH."""
        channel_uuid = event.channel_uuid
        caller_id = event.caller_id_number

        log.info(
            "FreeSWITCH incoming call",
            channel=channel_uuid,
            caller=caller_id,
        )

        # Create internal call
        call_context = await self.call_handler.handle_incoming_call(
            caller_id=caller_id,
            callee_id=event.destination_number,
            metadata={"channel_uuid": channel_uuid},
        )

        self._call_map[channel_uuid] = call_context.call_id

        # Answer and connect to audio bridge
        if self.freeswitch_client:
            await self.freeswitch_client.answer(channel_uuid)
            await self.freeswitch_client.stream_to_socket(
                channel_uuid,
                self.config.audio_bridge_host,
                self.config.audio_bridge_port,
            )

        # Answer in call handler
        await self.call_handler.answer_call()

    async def _handle_freeswitch_hangup(self, event: FreeSwitchEvent) -> None:
        """Handle hangup from FreeSWITCH."""
        channel_uuid = event.channel_uuid
        call_id = self._call_map.pop(channel_uuid, None)

        if call_id:
            log.info("FreeSWITCH hangup", channel=channel_uuid)
            await self.call_handler.hangup()

    # SIP Handlers

    async def _handle_sip_incoming(self, sip_call: SIPCall) -> None:
        """Handle incoming SIP call."""
        log.info(
            "SIP incoming call",
            sip_call_id=sip_call.sip_call_id,
            caller=sip_call.caller_id,
        )

        # Create internal call
        call_context = await self.call_handler.handle_incoming_call(
            caller_id=sip_call.caller_id,
            callee_id=sip_call.callee_id,
            metadata={"sip_call_id": sip_call.sip_call_id},
        )

        self._call_map[sip_call.sip_call_id] = call_context.call_id

        # Answer
        if self.sip_client:
            await self.sip_client.answer(sip_call.call_id)

        await self.call_handler.answer_call()

    # Audio Bridge Handlers

    async def _on_audio_received(self, call_id: UUID, audio: np.ndarray) -> None:
        """Handle audio received from telephony."""
        if not self.call_handler.is_in_call:
            return

        # Validate call state before accessing conversation
        current_call = self.call_handler.current_call
        if current_call is None or current_call.conversation is None:
            log.warning("Audio received but no active conversation", call_id=str(call_id))
            return

        try:
            # Process through AI pipeline
            response_text, response_audio = await self.conversation_engine.process_audio(
                audio,
                current_call.conversation.id,
            )

            log.info("AI response", text=response_text[:50])

            # Send response audio back
            await self.audio_bridge.send_audio(call_id, response_audio)

        except Exception:
            log.exception("Audio processing error", call_id=str(call_id))

    async def _on_audio_connection(self, call_id: UUID) -> None:
        """Handle new audio connection."""
        log.info("Audio connection established", call_id=str(call_id))

    async def _on_audio_disconnection(self, call_id: UUID) -> None:
        """Handle audio disconnection."""
        log.info("Audio connection closed", call_id=str(call_id))

        # Hangup if still in call
        if self.call_handler.is_in_call:
            await self.call_handler.hangup()

    # Webhook Support (for external SIP systems)

    async def handle_webhook_incoming(
        self,
        call_id: str,
        caller_id: str,
        callee_id: str,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Handle incoming call webhook.

        Called by external SIP system via REST API.

        Args:
            call_id: External call ID
            caller_id: Caller number
            callee_id: Called number
            metadata: Additional data

        Returns:
            Response dict with instructions
        """
        log.info(
            "Webhook incoming call",
            external_call_id=call_id,
            caller=caller_id,
        )

        # Create internal call
        call_context = await self.call_handler.handle_incoming_call(
            caller_id=caller_id,
            callee_id=callee_id,
            metadata={"external_call_id": call_id, **(metadata or {})},
        )

        self._call_map[call_id] = call_context.call_id

        # Answer
        await self.call_handler.answer_call()

        # Return audio bridge connection info
        return {
            "action": "answer",
            "internal_call_id": str(call_context.call_id),
            "audio_bridge": {
                "host": self.config.audio_bridge_host,
                "port": self.config.audio_bridge_port,
            },
        }

    async def handle_webhook_hangup(self, call_id: str) -> dict[str, Any]:
        """Handle hangup webhook.

        Args:
            call_id: External call ID

        Returns:
            Response dict
        """
        internal_id = self._call_map.pop(call_id, None)

        if internal_id:
            await self.call_handler.hangup()

        return {"action": "hangup", "success": internal_id is not None}

    @property
    def is_running(self) -> bool:
        """Check if service is running."""
        return self._running


async def run_telephony_service(config: TelephonyServiceConfig | None = None) -> None:
    """Run telephony service standalone.

    Args:
        config: Service configuration
    """
    service = TelephonyService(config)

    try:
        await service.start()
        await service.wait_until_stopped()
    except KeyboardInterrupt:
        pass
    finally:
        await service.stop()
