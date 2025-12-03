"""WebSocket audio streaming for browser-based testing.

Enables real-time audio communication between browser clients and the
phone-agent AI pipeline without requiring actual phone hardware.

Protocol:
- Client sends: PCM audio frames (16-bit, 16kHz, mono)
- Server sends: PCM audio frames (16-bit, 16kHz, mono)
- Control messages: JSON objects for start/stop/status

Use Cases:
- Development testing without phone infrastructure
- Demo/showcase of AI capabilities
- Integration testing of AI pipeline
"""

from __future__ import annotations

import asyncio
import base64
import json
import struct
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any, Callable
from uuid import UUID, uuid4

import numpy as np
from itf_shared import get_logger

if TYPE_CHECKING:
    from fastapi import WebSocket
    from numpy.typing import NDArray

log = get_logger(__name__)


class WebSocketMessageType(str, Enum):
    """Message types for WebSocket protocol."""

    # Control messages
    START = "start"  # Start audio session
    STOP = "stop"  # Stop audio session
    STATUS = "status"  # Get session status

    # Audio messages
    AUDIO = "audio"  # Audio data frame
    AUDIO_START = "audio_start"  # Begin audio stream
    AUDIO_END = "audio_end"  # End audio stream

    # Events
    CONNECTED = "connected"  # Session established
    DISCONNECTED = "disconnected"  # Session ended
    ERROR = "error"  # Error occurred
    TRANSCRIPT = "transcript"  # Transcription result
    RESPONSE = "response"  # AI response text


@dataclass
class AudioFrame:
    """Audio frame for WebSocket transport."""

    data: bytes  # PCM audio data
    sample_rate: int = 16000
    channels: int = 1
    bits_per_sample: int = 16
    timestamp_ms: int = 0  # Timestamp in milliseconds

    def to_dict(self) -> dict:
        """Serialize to dictionary for JSON transport.

        Returns:
            Dict with base64-encoded audio
        """
        return {
            "type": WebSocketMessageType.AUDIO.value,
            "data": base64.b64encode(self.data).decode("utf-8"),
            "sample_rate": self.sample_rate,
            "channels": self.channels,
            "bits_per_sample": self.bits_per_sample,
            "timestamp_ms": self.timestamp_ms,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "AudioFrame":
        """Deserialize from dictionary.

        Args:
            data: Dict with base64-encoded audio

        Returns:
            AudioFrame instance
        """
        return cls(
            data=base64.b64decode(data["data"]),
            sample_rate=data.get("sample_rate", 16000),
            channels=data.get("channels", 1),
            bits_per_sample=data.get("bits_per_sample", 16),
            timestamp_ms=data.get("timestamp_ms", 0),
        )

    def to_numpy(self) -> NDArray[np.float32]:
        """Convert to numpy float32 array.

        Returns:
            Normalized float32 audio array
        """
        audio = np.frombuffer(self.data, dtype=np.int16)
        return audio.astype(np.float32) / 32768.0

    @classmethod
    def from_numpy(
        cls,
        audio: NDArray[np.float32],
        sample_rate: int = 16000,
        timestamp_ms: int = 0,
    ) -> "AudioFrame":
        """Create from numpy array.

        Args:
            audio: Float32 audio array
            sample_rate: Sample rate
            timestamp_ms: Timestamp

        Returns:
            AudioFrame instance
        """
        audio_int16 = (audio * 32767).astype(np.int16)
        return cls(
            data=audio_int16.tobytes(),
            sample_rate=sample_rate,
            timestamp_ms=timestamp_ms,
        )


@dataclass
class WebSocketSession:
    """Active WebSocket audio session."""

    session_id: UUID
    websocket: Any  # WebSocket connection
    created_at: float = field(default_factory=lambda: __import__("time").time())
    audio_started: bool = False
    bytes_received: int = 0
    bytes_sent: int = 0
    frames_received: int = 0
    frames_sent: int = 0
    last_activity: float = field(default_factory=lambda: __import__("time").time())

    # Callbacks
    on_audio: Callable[[UUID, NDArray[np.float32]], Any] | None = None
    on_disconnect: Callable[[UUID], Any] | None = None


class WebSocketAudioHandler:
    """Handler for WebSocket audio connections.

    Manages multiple concurrent WebSocket sessions for audio streaming.
    Integrates with the AI pipeline for real-time speech processing.

    Usage:
        handler = WebSocketAudioHandler()

        @app.websocket("/api/v1/audio/ws")
        async def audio_websocket(websocket: WebSocket):
            await handler.handle_connection(websocket)
    """

    def __init__(
        self,
        sample_rate: int = 16000,
        frame_duration_ms: int = 20,
        max_connections: int = 10,
    ) -> None:
        """Initialize handler.

        Args:
            sample_rate: Audio sample rate
            frame_duration_ms: Frame duration in milliseconds
            max_connections: Maximum concurrent connections
        """
        self.sample_rate = sample_rate
        self.frame_duration_ms = frame_duration_ms
        self.max_connections = max_connections

        self._sessions: dict[UUID, WebSocketSession] = {}
        self._audio_callback: Callable[[UUID, NDArray[np.float32]], Any] | None = None
        self._connection_callback: Callable[[UUID], Any] | None = None
        self._disconnection_callback: Callable[[UUID], Any] | None = None

    async def handle_connection(self, websocket: "WebSocket") -> None:
        """Handle new WebSocket connection.

        This is the main entry point for WebSocket connections.

        Args:
            websocket: FastAPI WebSocket connection
        """
        # Check connection limit
        if len(self._sessions) >= self.max_connections:
            await websocket.close(code=1013, reason="Max connections reached")
            return

        # Accept connection
        await websocket.accept()

        # Create session
        session_id = uuid4()
        session = WebSocketSession(
            session_id=session_id,
            websocket=websocket,
        )
        self._sessions[session_id] = session

        log.info(f"WebSocket connected: {session_id}")

        # Send connected message
        await self._send_message(
            websocket,
            {
                "type": WebSocketMessageType.CONNECTED.value,
                "session_id": str(session_id),
                "sample_rate": self.sample_rate,
                "frame_duration_ms": self.frame_duration_ms,
            },
        )

        # Notify connection callback
        if self._connection_callback:
            result = self._connection_callback(session_id)
            if asyncio.iscoroutine(result):
                await result

        try:
            await self._handle_session(session)
        except Exception as e:
            log.error(f"WebSocket error: {e}", session_id=str(session_id))
            await self._send_error(websocket, str(e))
        finally:
            await self._close_session(session)

    async def _handle_session(self, session: WebSocketSession) -> None:
        """Handle session messages.

        Args:
            session: Active session
        """
        websocket = session.websocket

        while True:
            try:
                # Receive message (text or binary)
                message = await websocket.receive()

                if message.get("type") == "websocket.disconnect":
                    break

                session.last_activity = __import__("time").time()

                # Handle text message (JSON control)
                if "text" in message:
                    await self._handle_text_message(session, message["text"])

                # Handle binary message (audio data)
                elif "bytes" in message:
                    await self._handle_binary_message(session, message["bytes"])

            except Exception as e:
                log.error(f"Message handling error: {e}")
                break

    async def _handle_text_message(self, session: WebSocketSession, text: str) -> None:
        """Handle text (JSON) message.

        Args:
            session: Active session
            text: JSON message text
        """
        try:
            data = json.loads(text)
            msg_type = data.get("type")

            if msg_type == WebSocketMessageType.START.value:
                session.audio_started = True
                await self._send_message(
                    session.websocket,
                    {"type": WebSocketMessageType.AUDIO_START.value},
                )

            elif msg_type == WebSocketMessageType.STOP.value:
                session.audio_started = False
                await self._send_message(
                    session.websocket,
                    {"type": WebSocketMessageType.AUDIO_END.value},
                )

            elif msg_type == WebSocketMessageType.STATUS.value:
                await self._send_message(
                    session.websocket,
                    {
                        "type": WebSocketMessageType.STATUS.value,
                        "session_id": str(session.session_id),
                        "audio_started": session.audio_started,
                        "bytes_received": session.bytes_received,
                        "bytes_sent": session.bytes_sent,
                        "frames_received": session.frames_received,
                        "frames_sent": session.frames_sent,
                    },
                )

            elif msg_type == WebSocketMessageType.AUDIO.value:
                # JSON-wrapped audio (base64 encoded)
                frame = AudioFrame.from_dict(data)
                await self._process_audio(session, frame)

        except json.JSONDecodeError:
            await self._send_error(session.websocket, "Invalid JSON")

    async def _handle_binary_message(
        self,
        session: WebSocketSession,
        data: bytes,
    ) -> None:
        """Handle binary (audio) message.

        Args:
            session: Active session
            data: Binary audio data
        """
        if not session.audio_started:
            # Auto-start on first audio
            session.audio_started = True

        frame = AudioFrame(data=data, sample_rate=self.sample_rate)
        await self._process_audio(session, frame)

    async def _process_audio(
        self,
        session: WebSocketSession,
        frame: AudioFrame,
    ) -> None:
        """Process received audio frame.

        Args:
            session: Active session
            frame: Audio frame
        """
        session.bytes_received += len(frame.data)
        session.frames_received += 1

        # Convert to numpy
        audio = frame.to_numpy()

        # Notify callback
        if self._audio_callback:
            result = self._audio_callback(session.session_id, audio)
            if asyncio.iscoroutine(result):
                await result

    async def send_audio(
        self,
        session_id: UUID,
        audio: NDArray[np.float32],
        as_binary: bool = True,
    ) -> bool:
        """Send audio to client.

        Args:
            session_id: Target session
            audio: Float32 audio data
            as_binary: Send as binary (True) or base64 JSON (False)

        Returns:
            True if sent successfully
        """
        session = self._sessions.get(session_id)
        if not session:
            return False

        try:
            # Convert to PCM bytes
            audio_int16 = (audio * 32767).astype(np.int16)
            data = audio_int16.tobytes()

            if as_binary:
                await session.websocket.send_bytes(data)
            else:
                frame = AudioFrame(data=data, sample_rate=self.sample_rate)
                await self._send_message(session.websocket, frame.to_dict())

            session.bytes_sent += len(data)
            session.frames_sent += 1
            return True

        except Exception as e:
            log.error(f"Send audio failed: {e}")
            return False

    async def send_transcript(self, session_id: UUID, text: str, is_final: bool = False) -> bool:
        """Send transcription result to client.

        Args:
            session_id: Target session
            text: Transcribed text
            is_final: Whether this is final transcription

        Returns:
            True if sent successfully
        """
        session = self._sessions.get(session_id)
        if not session:
            return False

        try:
            await self._send_message(
                session.websocket,
                {
                    "type": WebSocketMessageType.TRANSCRIPT.value,
                    "text": text,
                    "is_final": is_final,
                },
            )
            return True
        except Exception as e:
            log.error(f"Send transcript failed: {e}")
            return False

    async def send_response(self, session_id: UUID, text: str) -> bool:
        """Send AI response text to client.

        Args:
            session_id: Target session
            text: Response text

        Returns:
            True if sent successfully
        """
        session = self._sessions.get(session_id)
        if not session:
            return False

        try:
            await self._send_message(
                session.websocket,
                {
                    "type": WebSocketMessageType.RESPONSE.value,
                    "text": text,
                },
            )
            return True
        except Exception as e:
            log.error(f"Send response failed: {e}")
            return False

    async def _send_message(self, websocket: "WebSocket", data: dict) -> None:
        """Send JSON message.

        Args:
            websocket: WebSocket connection
            data: Message data
        """
        await websocket.send_json(data)

    async def _send_error(self, websocket: "WebSocket", error: str) -> None:
        """Send error message.

        Args:
            websocket: WebSocket connection
            error: Error message
        """
        await self._send_message(
            websocket,
            {
                "type": WebSocketMessageType.ERROR.value,
                "error": error,
            },
        )

    async def _close_session(self, session: WebSocketSession) -> None:
        """Close and cleanup session.

        Args:
            session: Session to close
        """
        session_id = session.session_id

        # Remove from active sessions
        self._sessions.pop(session_id, None)

        # Notify callback
        if self._disconnection_callback:
            result = self._disconnection_callback(session_id)
            if asyncio.iscoroutine(result):
                await result

        log.info(f"WebSocket disconnected: {session_id}")

    def on_audio_received(
        self,
        callback: Callable[[UUID, NDArray[np.float32]], Any],
    ) -> None:
        """Set audio received callback.

        Args:
            callback: Function called with (session_id, audio_data)
        """
        self._audio_callback = callback

    def on_connection(self, callback: Callable[[UUID], Any]) -> None:
        """Set connection callback.

        Args:
            callback: Function called with session_id
        """
        self._connection_callback = callback

    def on_disconnection(self, callback: Callable[[UUID], Any]) -> None:
        """Set disconnection callback.

        Args:
            callback: Function called with session_id
        """
        self._disconnection_callback = callback

    def get_session(self, session_id: UUID) -> WebSocketSession | None:
        """Get session by ID.

        Args:
            session_id: Session ID

        Returns:
            Session or None
        """
        return self._sessions.get(session_id)

    @property
    def active_sessions(self) -> int:
        """Get number of active sessions."""
        return len(self._sessions)

    @property
    def session_ids(self) -> list[UUID]:
        """Get all active session IDs."""
        return list(self._sessions.keys())


class TwilioMediaStreamHandler:
    """Handler for Twilio Media Streams WebSocket.

    Twilio Media Streams sends audio via WebSocket with a specific
    protocol for real-time audio streaming.

    Protocol:
    - Connected: Receive 'connected' event
    - Start: Receive 'start' event with stream info
    - Media: Receive 'media' events with audio chunks
    - Stop: Receive 'stop' event when stream ends

    Audio format:
    - μ-law encoded (PCMU)
    - 8kHz sample rate
    - Base64 encoded in JSON
    """

    def __init__(self) -> None:
        """Initialize Twilio handler."""
        from .codecs import MuLawCodec, AudioResampler

        self._codec = MuLawCodec()
        self._resampler = AudioResampler(8000, 16000)

        self._sessions: dict[str, dict] = {}
        self._audio_callback: Callable[[str, NDArray[np.float32]], Any] | None = None

    async def handle_connection(self, websocket: "WebSocket") -> None:
        """Handle Twilio WebSocket connection.

        Args:
            websocket: FastAPI WebSocket
        """
        await websocket.accept()
        stream_sid: str | None = None

        try:
            while True:
                message = await websocket.receive_json()
                event = message.get("event")

                if event == "connected":
                    log.info("Twilio stream connected")

                elif event == "start":
                    stream_sid = message.get("streamSid")
                    self._sessions[stream_sid] = {
                        "call_sid": message.get("start", {}).get("callSid"),
                        "account_sid": message.get("start", {}).get("accountSid"),
                    }
                    log.info(f"Twilio stream started: {stream_sid}")

                elif event == "media":
                    if stream_sid:
                        await self._handle_media(stream_sid, message)

                elif event == "stop":
                    log.info(f"Twilio stream stopped: {stream_sid}")
                    break

        except Exception as e:
            log.error(f"Twilio WebSocket error: {e}")
        finally:
            if stream_sid:
                self._sessions.pop(stream_sid, None)
            await websocket.close()

    async def _handle_media(self, stream_sid: str, message: dict) -> None:
        """Handle Twilio media event.

        Args:
            stream_sid: Stream identifier
            message: Media message
        """
        media = message.get("media", {})
        payload = media.get("payload", "")

        # Decode base64 μ-law audio
        mulaw_data = base64.b64decode(payload)

        # Decode to PCM
        pcm = self._codec.decode(mulaw_data)

        # Resample to 16kHz
        pcm_16k = self._resampler.resample(pcm)

        # Convert to float32
        audio = pcm_16k.astype(np.float32) / 32768.0

        # Notify callback
        if self._audio_callback:
            result = self._audio_callback(stream_sid, audio)
            if asyncio.iscoroutine(result):
                await result

    async def send_audio(
        self,
        websocket: "WebSocket",
        stream_sid: str,
        audio: NDArray[np.float32],
    ) -> None:
        """Send audio back to Twilio.

        Args:
            websocket: WebSocket connection
            stream_sid: Stream identifier
            audio: Audio data (16kHz float32)
        """
        from .codecs import AudioResampler

        # Resample to 8kHz
        resampler = AudioResampler(16000, 8000)
        audio_8k = resampler.resample((audio * 32767).astype(np.int16))

        # Encode to μ-law
        mulaw = self._codec.encode(audio_8k)

        # Base64 encode
        payload = base64.b64encode(mulaw).decode("utf-8")

        # Send media message
        await websocket.send_json(
            {
                "event": "media",
                "streamSid": stream_sid,
                "media": {"payload": payload},
            }
        )

    def on_audio(self, callback: Callable[[str, NDArray[np.float32]], Any]) -> None:
        """Set audio callback.

        Args:
            callback: Called with (stream_sid, audio_data)
        """
        self._audio_callback = callback
