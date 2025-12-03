"""FreeSWITCH integration via Event Socket Library (ESL).

Provides integration with FreeSWITCH PBX for:
- Call control (answer, hangup, transfer, bridge)
- Outbound call origination (for recall campaigns)
- Audio streaming (via mod_shout or WebSocket)
- DTMF detection and generation
- Event handling (CHANNEL_ANSWER, DTMF, CHANNEL_BRIDGE, etc.)
- Dialplan execution

Requires FreeSWITCH to be installed and configured with:
- mod_event_socket enabled
- mod_shout for audio streaming (optional)

See configs/freeswitch/ for configuration files.
"""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable
from uuid import UUID, uuid4

from itf_shared import get_logger

log = get_logger(__name__)


class ChannelState(str, Enum):
    """FreeSWITCH channel states."""

    NEW = "CS_NEW"
    INIT = "CS_INIT"
    ROUTING = "CS_ROUTING"
    SOFT_EXECUTE = "CS_SOFT_EXECUTE"
    EXECUTE = "CS_EXECUTE"
    EXCHANGE_MEDIA = "CS_EXCHANGE_MEDIA"
    PARK = "CS_PARK"
    CONSUME_MEDIA = "CS_CONSUME_MEDIA"
    HIBERNATE = "CS_HIBERNATE"
    RESET = "CS_RESET"
    HANGUP = "CS_HANGUP"
    REPORTING = "CS_REPORTING"
    DESTROY = "CS_DESTROY"


class HangupCause(str, Enum):
    """FreeSWITCH hangup cause codes."""

    NORMAL_CLEARING = "NORMAL_CLEARING"
    USER_BUSY = "USER_BUSY"
    NO_ANSWER = "NO_ANSWER"
    CALL_REJECTED = "CALL_REJECTED"
    DESTINATION_OUT_OF_ORDER = "DESTINATION_OUT_OF_ORDER"
    INVALID_NUMBER_FORMAT = "INVALID_NUMBER_FORMAT"
    NORMAL_TEMPORARY_FAILURE = "NORMAL_TEMPORARY_FAILURE"
    RECOVERY_ON_TIMER_EXPIRE = "RECOVERY_ON_TIMER_EXPIRE"
    ORIGINATOR_CANCEL = "ORIGINATOR_CANCEL"
    LOSE_RACE = "LOSE_RACE"
    USER_NOT_REGISTERED = "USER_NOT_REGISTERED"


class TransferType(str, Enum):
    """Transfer types."""

    BLIND = "blind"  # Immediate transfer
    ATTENDED = "attended"  # Announce before transfer


@dataclass
class FreeSwitchConfig:
    """FreeSWITCH ESL configuration."""

    # Connection
    host: str = "127.0.0.1"
    port: int = 8021
    password: str = ""  # Required - must be provided from config/environment

    # Audio streaming
    audio_ws_port: int = 8080  # WebSocket for audio
    audio_sample_rate: int = 16000
    audio_channels: int = 1

    # Reconnection
    reconnect: bool = True
    reconnect_delay: float = 5.0
    max_reconnect_attempts: int = 10


@dataclass
class FreeSwitchEvent:
    """FreeSWITCH event data."""

    event_name: str
    event_uuid: str = ""
    channel_uuid: str = ""
    caller_id_number: str = ""
    caller_id_name: str = ""
    destination_number: str = ""
    channel_state: str = ""
    headers: dict[str, str] = field(default_factory=dict)
    body: str = ""


class FreeSwitchClient:
    """FreeSWITCH ESL client for PBX integration.

    Connects to FreeSWITCH via Event Socket and provides:
    - Event subscription and handling
    - Call control commands
    - Audio streaming coordination

    Usage:
        client = FreeSwitchClient(FreeSwitchConfig(host="localhost"))
        await client.connect()

        @client.on_event("CHANNEL_CREATE")
        async def on_new_channel(event: FreeSwitchEvent):
            print(f"New call from {event.caller_id_number}")

        # Answer and bridge to AI
        await client.answer(channel_uuid)
        await client.execute_app(channel_uuid, "socket", "127.0.0.1:9090 async")
    """

    def __init__(self, config: FreeSwitchConfig) -> None:
        """Initialize FreeSWITCH client.

        Args:
            config: FreeSWITCH configuration
        """
        self.config = config
        self._connected = False
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._reconnect_task: asyncio.Task[None] | None = None

        # Event handlers
        self._event_handlers: dict[str, list[Callable[[FreeSwitchEvent], Any]]] = {}
        self._global_handlers: list[Callable[[FreeSwitchEvent], Any]] = []

        # Call tracking
        self._calls: dict[str, UUID] = {}  # channel_uuid -> our call_id

    async def connect(self) -> bool:
        """Connect to FreeSWITCH ESL.

        Returns:
            True if connected successfully
        """
        try:
            log.info(
                "Connecting to FreeSWITCH",
                host=self.config.host,
                port=self.config.port,
            )

            self._reader, self._writer = await asyncio.open_connection(
                self.config.host,
                self.config.port,
            )

            # Read welcome message
            welcome = await self._read_response()
            if "Content-Type: auth/request" not in welcome:
                raise ConnectionError("Unexpected welcome message")

            # Authenticate
            await self._send_command(f"auth {self.config.password}")
            auth_response = await self._read_response()

            if "Reply-Text: +OK" not in auth_response:
                raise ConnectionError("Authentication failed")

            # Subscribe to events
            await self._send_command("event plain all")
            await self._read_response()

            self._connected = True
            log.info("Connected to FreeSWITCH")

            # Start event loop
            asyncio.create_task(self._event_loop())

            return True

        except Exception as e:
            log.error("Failed to connect to FreeSWITCH", error=str(e))
            if self.config.reconnect:
                self._schedule_reconnect()
            return False

    async def disconnect(self) -> None:
        """Disconnect from FreeSWITCH."""
        self._connected = False

        if self._reconnect_task:
            self._reconnect_task.cancel()

        if self._writer:
            self._writer.close()
            await self._writer.wait_closed()

        log.info("Disconnected from FreeSWITCH")

    async def _send_command(self, command: str) -> None:
        """Send command to FreeSWITCH."""
        if not self._writer:
            raise ConnectionError("Not connected")

        self._writer.write(f"{command}\n\n".encode())
        await self._writer.drain()

    async def _read_response(self) -> str:
        """Read response from FreeSWITCH."""
        if not self._reader:
            raise ConnectionError("Not connected")

        response_lines = []
        content_length = 0

        # Read headers
        while True:
            line = await self._reader.readline()
            line_str = line.decode().strip()

            if not line_str:
                break

            response_lines.append(line_str)

            if line_str.startswith("Content-Length:"):
                content_length = int(line_str.split(":")[1].strip())

        # Read body if present
        if content_length > 0:
            body = await self._reader.read(content_length)
            response_lines.append(body.decode())

        return "\n".join(response_lines)

    async def _event_loop(self) -> None:
        """Main event processing loop."""
        while self._connected and self._reader:
            try:
                response = await self._read_response()
                if response:
                    event = self._parse_event(response)
                    if event:
                        await self._dispatch_event(event)
            except asyncio.CancelledError:
                break
            except Exception as e:
                log.error("Event loop error", error=str(e))
                if self.config.reconnect:
                    self._schedule_reconnect()
                break

    def _parse_event(self, data: str) -> FreeSwitchEvent | None:
        """Parse FreeSWITCH event data.

        FreeSWITCH event format:
        Content-Type: text/event-plain

        Event-Name: CHANNEL_CREATE
        Event-UUID: abc-123
        ... other headers ...

        optional body
        """
        if "Content-Type: text/event-plain" not in data:
            return None

        headers: dict[str, str] = {}
        body = ""

        lines = data.split("\n")
        empty_line_count = 0
        in_body = False

        for line in lines:
            # Skip the Content-Type line
            if line.startswith("Content-Type:"):
                continue

            # Count empty lines - body starts after second empty line
            if not line.strip():
                empty_line_count += 1
                if empty_line_count >= 2:
                    in_body = True
                continue

            if in_body:
                body += line + "\n"
            elif ":" in line:
                key, value = line.split(":", 1)
                headers[key.strip()] = value.strip()

        event_name = headers.get("Event-Name", "")
        if not event_name:
            return None

        return FreeSwitchEvent(
            event_name=event_name,
            event_uuid=headers.get("Event-UUID", ""),
            channel_uuid=headers.get("Unique-ID", ""),
            caller_id_number=headers.get("Caller-Caller-ID-Number", ""),
            caller_id_name=headers.get("Caller-Caller-ID-Name", ""),
            destination_number=headers.get("Caller-Destination-Number", ""),
            channel_state=headers.get("Channel-State", ""),
            headers=headers,
            body=body.strip(),
        )

    async def _dispatch_event(self, event: FreeSwitchEvent) -> None:
        """Dispatch event to handlers."""
        # Call specific handlers
        handlers = self._event_handlers.get(event.event_name, [])
        for handler in handlers:
            try:
                result = handler(event)
                if asyncio.iscoroutine(result):
                    await result
            except Exception as e:
                log.error(
                    "Event handler error",
                    event=event.event_name,
                    error=str(e),
                )

        # Call global handlers
        for handler in self._global_handlers:
            try:
                result = handler(event)
                if asyncio.iscoroutine(result):
                    await result
            except Exception as e:
                log.error("Global handler error", error=str(e))

    def _schedule_reconnect(self) -> None:
        """Schedule reconnection attempt."""

        async def reconnect():
            await asyncio.sleep(self.config.reconnect_delay)
            await self.connect()

        self._reconnect_task = asyncio.create_task(reconnect())

    # Call Control Methods

    async def answer(self, channel_uuid: str) -> bool:
        """Answer a ringing channel.

        Args:
            channel_uuid: Channel to answer

        Returns:
            True if successful
        """
        try:
            await self._send_command(f"api uuid_answer {channel_uuid}")
            response = await self._read_response()
            success = "+OK" in response
            log.info("Answer channel", uuid=channel_uuid, success=success)
            return success
        except Exception as e:
            log.error("Answer failed", error=str(e))
            return False

    async def hangup(self, channel_uuid: str, cause: str = "NORMAL_CLEARING") -> bool:
        """Hangup a channel.

        Args:
            channel_uuid: Channel to hangup
            cause: Hangup cause code

        Returns:
            True if successful
        """
        try:
            await self._send_command(f"api uuid_kill {channel_uuid} {cause}")
            response = await self._read_response()
            success = "+OK" in response
            log.info("Hangup channel", uuid=channel_uuid, success=success)
            return success
        except Exception as e:
            log.error("Hangup failed", error=str(e))
            return False

    async def transfer(
        self,
        channel_uuid: str,
        destination: str,
        dialplan: str = "XML",
        context: str = "default",
    ) -> bool:
        """Transfer a channel to another destination.

        Args:
            channel_uuid: Channel to transfer
            destination: Destination extension/number
            dialplan: Dialplan type
            context: Dialplan context

        Returns:
            True if successful
        """
        try:
            await self._send_command(
                f"api uuid_transfer {channel_uuid} {destination} {dialplan} {context}"
            )
            response = await self._read_response()
            success = "+OK" in response
            log.info(
                "Transfer channel",
                uuid=channel_uuid,
                destination=destination,
                success=success,
            )
            return success
        except Exception as e:
            log.error("Transfer failed", error=str(e))
            return False

    async def bridge(
        self,
        channel_uuid: str,
        destination: str,
    ) -> bool:
        """Bridge a channel to another endpoint.

        Args:
            channel_uuid: Channel to bridge
            destination: Destination dial string

        Returns:
            True if successful
        """
        try:
            await self._send_command(
                f"api uuid_bridge {channel_uuid} {destination}"
            )
            response = await self._read_response()
            success = "+OK" in response
            log.info("Bridge channel", uuid=channel_uuid, success=success)
            return success
        except Exception as e:
            log.error("Bridge failed", error=str(e))
            return False

    async def execute_app(
        self,
        channel_uuid: str,
        app: str,
        args: str = "",
    ) -> bool:
        """Execute a dialplan application on a channel.

        Args:
            channel_uuid: Target channel
            app: Application name (e.g., "playback", "socket")
            args: Application arguments

        Returns:
            True if successful
        """
        try:
            cmd = f"api uuid_broadcast {channel_uuid} {app}::{args}"
            await self._send_command(cmd)
            response = await self._read_response()
            success = "+OK" in response
            log.info(
                "Execute app",
                uuid=channel_uuid,
                app=app,
                success=success,
            )
            return success
        except Exception as e:
            log.error("Execute app failed", error=str(e))
            return False

    async def playback(
        self,
        channel_uuid: str,
        file_path: str,
    ) -> bool:
        """Play audio file to channel.

        Args:
            channel_uuid: Target channel
            file_path: Path to audio file

        Returns:
            True if successful
        """
        return await self.execute_app(channel_uuid, "playback", file_path)

    async def record(
        self,
        channel_uuid: str,
        file_path: str,
        max_seconds: int = 60,
    ) -> bool:
        """Record audio from channel.

        Args:
            channel_uuid: Target channel
            file_path: Path to save recording
            max_seconds: Maximum recording duration

        Returns:
            True if successful
        """
        return await self.execute_app(
            channel_uuid,
            "record",
            f"{file_path} {max_seconds}",
        )

    async def stream_to_socket(
        self,
        channel_uuid: str,
        host: str,
        port: int,
    ) -> bool:
        """Stream audio to external socket (for AI processing).

        Args:
            channel_uuid: Target channel
            host: Socket server host
            port: Socket server port

        Returns:
            True if successful
        """
        return await self.execute_app(
            channel_uuid,
            "socket",
            f"{host}:{port} async full",
        )

    # Event Handler Registration

    def on_event(self, event_name: str) -> Callable:
        """Decorator to register event handler.

        Usage:
            @client.on_event("CHANNEL_CREATE")
            async def on_new_channel(event):
                print(event.caller_id_number)
        """

        def decorator(func: Callable[[FreeSwitchEvent], Any]) -> Callable:
            if event_name not in self._event_handlers:
                self._event_handlers[event_name] = []
            self._event_handlers[event_name].append(func)
            return func

        return decorator

    def on_all_events(self, func: Callable[[FreeSwitchEvent], Any]) -> Callable:
        """Register handler for all events."""
        self._global_handlers.append(func)
        return func

    @property
    def is_connected(self) -> bool:
        """Check if connected to FreeSWITCH."""
        return self._connected

    # Enhanced Call Control

    async def originate(
        self,
        destination: str,
        caller_id_number: str | None = None,
        caller_id_name: str | None = None,
        timeout: int = 30,
        context: str = "outbound",
        gateway: str = "sipgate",
        variables: dict[str, str] | None = None,
    ) -> str | None:
        """Originate an outbound call.

        Used for recall campaigns and outbound calling.

        Args:
            destination: Destination phone number
            caller_id_number: Caller ID number to display
            caller_id_name: Caller ID name to display
            timeout: Ring timeout in seconds
            context: Dialplan context
            gateway: SIP gateway to use
            variables: Additional channel variables

        Returns:
            Channel UUID if successful, None otherwise
        """
        try:
            # Build dial string
            vars_str = ""
            if variables:
                var_parts = [f"{k}={v}" for k, v in variables.items()]
                vars_str = "{" + ",".join(var_parts) + "}"

            # Set caller ID
            cid_parts = []
            if caller_id_name:
                cid_parts.append(f"origination_caller_id_name={caller_id_name}")
            if caller_id_number:
                cid_parts.append(f"origination_caller_id_number={caller_id_number}")
            cid_parts.append(f"originate_timeout={timeout}")

            if cid_parts:
                if vars_str:
                    vars_str = vars_str[:-1] + "," + ",".join(cid_parts) + "}"
                else:
                    vars_str = "{" + ",".join(cid_parts) + "}"

            # Build originate command
            dial_string = f"sofia/gateway/{gateway}/{destination}"
            cmd = f"api originate {vars_str}{dial_string} &park()"

            await self._send_command(cmd)
            response = await self._read_response()

            # Extract channel UUID from response
            if "+OK" in response:
                # Response format: "+OK <uuid>"
                match = re.search(r"\+OK\s+([a-f0-9-]+)", response)
                if match:
                    channel_uuid = match.group(1)
                    log.info(
                        "Originated call",
                        destination=destination,
                        uuid=channel_uuid,
                    )
                    return channel_uuid

            log.warning("Originate failed", response=response)
            return None

        except Exception as e:
            log.error("Originate failed", error=str(e))
            return None

    async def blind_transfer(
        self,
        channel_uuid: str,
        destination: str,
        is_emergency: bool = False,
    ) -> bool:
        """Perform blind transfer (immediate transfer without announcement).

        Args:
            channel_uuid: Channel to transfer
            destination: Destination number
            is_emergency: True if emergency number (112, 110)

        Returns:
            True if successful
        """
        if is_emergency:
            log.warning(
                "Emergency transfer",
                uuid=channel_uuid,
                destination=destination,
            )

        return await self.transfer(channel_uuid, destination)

    async def attended_transfer(
        self,
        channel_uuid: str,
        destination: str,
        announcement: str | None = None,
    ) -> bool:
        """Perform attended transfer with optional announcement.

        The AI plays an announcement before transferring the call.

        Args:
            channel_uuid: Channel to transfer
            destination: Destination number
            announcement: Path to announcement audio file

        Returns:
            True if successful
        """
        try:
            # Play announcement if provided
            if announcement:
                await self.playback(channel_uuid, announcement)

            # Transfer after announcement
            return await self.transfer(channel_uuid, destination)

        except Exception as e:
            log.error("Attended transfer failed", error=str(e))
            return False

    async def transfer_to_operator(
        self,
        channel_uuid: str,
        operator_number: str | None = None,
        fallback_voicemail: bool = True,
    ) -> bool:
        """Transfer call to human operator.

        Used when AI cannot handle the request.

        Args:
            channel_uuid: Channel to transfer
            operator_number: Operator phone number
            fallback_voicemail: If True, go to voicemail if no answer

        Returns:
            True if successful
        """
        destination = operator_number or "operator"

        try:
            # Set timeout and fallback
            if fallback_voicemail:
                await self._send_command(
                    f"api uuid_setvar {channel_uuid} continue_on_fail true"
                )
                await self._read_response()

            success = await self.transfer(channel_uuid, destination)

            log.info(
                "Transfer to operator",
                uuid=channel_uuid,
                destination=destination,
                success=success,
            )

            return success

        except Exception as e:
            log.error("Operator transfer failed", error=str(e))
            return False

    # DTMF Handling

    async def send_dtmf(
        self,
        channel_uuid: str,
        digits: str,
        duration_ms: int = 100,
    ) -> bool:
        """Send DTMF tones to channel.

        Args:
            channel_uuid: Target channel
            digits: DTMF digits (0-9, *, #, A-D)
            duration_ms: Tone duration in milliseconds

        Returns:
            True if successful
        """
        try:
            cmd = f"api uuid_send_dtmf {channel_uuid} {digits}@{duration_ms}"
            await self._send_command(cmd)
            response = await self._read_response()
            success = "+OK" in response
            log.debug("Send DTMF", uuid=channel_uuid, digits=digits, success=success)
            return success
        except Exception as e:
            log.error("Send DTMF failed", error=str(e))
            return False

    async def detect_dtmf(
        self,
        channel_uuid: str,
        callback: Callable[[str], Any],
    ) -> None:
        """Start DTMF detection on channel.

        Args:
            channel_uuid: Target channel
            callback: Function called with detected digits
        """
        # Register DTMF event handler for this channel

        @self.on_event("DTMF")
        async def dtmf_handler(event: FreeSwitchEvent):
            if event.channel_uuid == channel_uuid:
                digit = event.headers.get("DTMF-Digit", "")
                if digit:
                    result = callback(digit)
                    if asyncio.iscoroutine(result):
                        await result

    # Channel Variable Management

    async def set_variable(
        self,
        channel_uuid: str,
        name: str,
        value: str,
    ) -> bool:
        """Set channel variable.

        Args:
            channel_uuid: Target channel
            name: Variable name
            value: Variable value

        Returns:
            True if successful
        """
        try:
            cmd = f"api uuid_setvar {channel_uuid} {name} {value}"
            await self._send_command(cmd)
            response = await self._read_response()
            return "+OK" in response
        except Exception as e:
            log.error("Set variable failed", error=str(e))
            return False

    async def get_variable(
        self,
        channel_uuid: str,
        name: str,
    ) -> str | None:
        """Get channel variable.

        Args:
            channel_uuid: Target channel
            name: Variable name

        Returns:
            Variable value or None
        """
        try:
            cmd = f"api uuid_getvar {channel_uuid} {name}"
            await self._send_command(cmd)
            response = await self._read_response()
            if "+OK" not in response and "-ERR" not in response:
                return response.strip()
            return None
        except Exception as e:
            log.error("Get variable failed", error=str(e))
            return None

    # Audio Control

    async def hold(self, channel_uuid: str, music_path: str | None = None) -> bool:
        """Put channel on hold.

        Args:
            channel_uuid: Target channel
            music_path: Hold music file path

        Returns:
            True if successful
        """
        try:
            await self._send_command(f"api uuid_hold {channel_uuid}")
            response = await self._read_response()
            success = "+OK" in response

            if success and music_path:
                await self.execute_app(channel_uuid, "playback", music_path)

            log.info("Hold channel", uuid=channel_uuid, success=success)
            return success
        except Exception as e:
            log.error("Hold failed", error=str(e))
            return False

    async def unhold(self, channel_uuid: str) -> bool:
        """Take channel off hold.

        Args:
            channel_uuid: Target channel

        Returns:
            True if successful
        """
        try:
            await self._send_command(f"api uuid_hold off {channel_uuid}")
            response = await self._read_response()
            success = "+OK" in response
            log.info("Unhold channel", uuid=channel_uuid, success=success)
            return success
        except Exception as e:
            log.error("Unhold failed", error=str(e))
            return False

    async def mute(self, channel_uuid: str, direction: str = "read") -> bool:
        """Mute audio on channel.

        Args:
            channel_uuid: Target channel
            direction: "read" (mute inbound), "write" (mute outbound), "both"

        Returns:
            True if successful
        """
        try:
            await self._send_command(f"api uuid_audio {channel_uuid} start {direction} mute")
            response = await self._read_response()
            return "+OK" in response
        except Exception as e:
            log.error("Mute failed", error=str(e))
            return False

    async def unmute(self, channel_uuid: str, direction: str = "read") -> bool:
        """Unmute audio on channel.

        Args:
            channel_uuid: Target channel
            direction: "read", "write", "both"

        Returns:
            True if successful
        """
        try:
            await self._send_command(f"api uuid_audio {channel_uuid} stop {direction} mute")
            response = await self._read_response()
            return "+OK" in response
        except Exception as e:
            log.error("Unmute failed", error=str(e))
            return False

    # Channel Information

    async def get_channel_info(self, channel_uuid: str) -> dict | None:
        """Get detailed channel information.

        Args:
            channel_uuid: Target channel

        Returns:
            Channel info dict or None
        """
        try:
            await self._send_command(f"api uuid_dump {channel_uuid}")
            response = await self._read_response()

            if "-ERR" in response:
                return None

            # Parse response into dict
            info = {}
            for line in response.split("\n"):
                if ":" in line:
                    key, value = line.split(":", 1)
                    info[key.strip()] = value.strip()

            return info

        except Exception as e:
            log.error("Get channel info failed", error=str(e))
            return None

    async def get_active_calls(self) -> list[dict]:
        """Get list of all active calls.

        Returns:
            List of call info dicts
        """
        try:
            await self._send_command("api show calls")
            response = await self._read_response()

            calls = []
            lines = response.split("\n")

            # Skip header line
            for line in lines[1:]:
                if not line.strip() or line.startswith("-"):
                    continue

                parts = line.split(",")
                if len(parts) >= 6:
                    calls.append(
                        {
                            "uuid": parts[0],
                            "direction": parts[1],
                            "created": parts[2],
                            "name": parts[3],
                            "state": parts[4],
                            "cid_name": parts[5] if len(parts) > 5 else "",
                            "cid_number": parts[6] if len(parts) > 6 else "",
                        }
                    )

            return calls

        except Exception as e:
            log.error("Get active calls failed", error=str(e))
            return []

    # Utility Methods

    async def send_message(
        self,
        channel_uuid: str,
        message: str,
    ) -> bool:
        """Send message to channel (for SIP MESSAGE).

        Args:
            channel_uuid: Target channel
            message: Message content

        Returns:
            True if successful
        """
        try:
            cmd = f"api uuid_send_message {channel_uuid} {message}"
            await self._send_command(cmd)
            response = await self._read_response()
            return "+OK" in response
        except Exception as e:
            log.error("Send message failed", error=str(e))
            return False

    async def broadcast(
        self,
        channel_uuid: str,
        audio_path: str,
        leg: str = "aleg",
    ) -> bool:
        """Broadcast audio to channel without interrupting.

        Args:
            channel_uuid: Target channel
            audio_path: Path to audio file
            leg: "aleg", "bleg", or "both"

        Returns:
            True if successful
        """
        try:
            cmd = f"api uuid_broadcast {channel_uuid} {audio_path} {leg}"
            await self._send_command(cmd)
            response = await self._read_response()
            return "+OK" in response
        except Exception as e:
            log.error("Broadcast failed", error=str(e))
            return False

    async def break_audio(self, channel_uuid: str) -> bool:
        """Stop current playback on channel.

        Args:
            channel_uuid: Target channel

        Returns:
            True if successful
        """
        try:
            await self._send_command(f"api uuid_break {channel_uuid}")
            response = await self._read_response()
            return "+OK" in response
        except Exception as e:
            log.error("Break audio failed", error=str(e))
            return False


@dataclass
class FreeSwitchCallSession:
    """Track an active call session.

    Used to coordinate between FreeSWITCH events and phone-agent processing.
    """

    call_id: UUID
    channel_uuid: str
    direction: str  # "inbound" or "outbound"
    caller_id_number: str
    caller_id_name: str
    destination_number: str
    state: ChannelState = ChannelState.NEW
    started_at: float = field(default_factory=lambda: __import__("time").time())
    answered_at: float | None = None
    ended_at: float | None = None
    hangup_cause: str | None = None
    transferred: bool = False
    transfer_destination: str | None = None

    @property
    def duration(self) -> float:
        """Get call duration in seconds."""
        end = self.ended_at or __import__("time").time()
        start = self.answered_at or self.started_at
        return end - start

    @property
    def is_active(self) -> bool:
        """Check if call is still active."""
        return self.ended_at is None
