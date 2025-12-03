"""Audio bridge for streaming telephony audio to AI pipeline.

Provides bidirectional audio streaming between:
- SIP/FreeSWITCH telephony
- AI processing (STT → LLM → TTS)

Supports multiple protocols:
- TCP socket (FreeSWITCH mod_socket)
- WebSocket
- RTP direct

Integrates with:
- codecs.py: G.711/G.722 encoding/decoding
- rtp_config.py: RTP packet handling and jitter buffering
"""

from __future__ import annotations

import asyncio
import struct
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable
from uuid import UUID

import numpy as np
from itf_shared import get_logger

from .codecs import CodecType, CodecPipeline, get_codec

log = get_logger(__name__)


class AudioProtocol(str, Enum):
    """Supported audio protocols."""

    TCP_SOCKET = "tcp_socket"  # FreeSWITCH mod_socket
    WEBSOCKET = "websocket"  # WebSocket streaming
    RTP = "rtp"  # Direct RTP


@dataclass
class AudioBridgeConfig:
    """Audio bridge configuration."""

    # Server
    host: str = "0.0.0.0"
    port: int = 9090
    protocol: AudioProtocol = AudioProtocol.TCP_SOCKET

    # Audio format (internal/AI processing)
    sample_rate: int = 16000  # AI models expect 16kHz
    channels: int = 1
    sample_width: int = 2  # 16-bit

    # Telephony codec (incoming/outgoing audio)
    telephony_codec: CodecType = CodecType.PCMA  # G.711 A-law (Europe)
    telephony_sample_rate: int = 8000  # Standard telephony rate

    # Buffer settings
    chunk_size: int = 320  # 20ms at 16kHz
    buffer_chunks: int = 5  # 100ms buffer

    # Jitter buffer
    jitter_buffer_enabled: bool = True
    jitter_buffer_min_ms: int = 40
    jitter_buffer_max_ms: int = 200
    jitter_buffer_target_ms: int = 100


class AudioBridge:
    """Bidirectional audio bridge for telephony integration.

    Accepts connections from FreeSWITCH (via mod_socket) and
    bridges audio to/from the AI pipeline.

    The bridge:
    1. Receives audio from telephony (caller's voice)
    2. Buffers and forwards to AI pipeline (STT)
    3. Receives synthesized audio from AI pipeline (TTS)
    4. Streams back to telephony (caller hears response)

    Usage:
        bridge = AudioBridge()

        @bridge.on_audio_received
        async def handle_audio(call_id, audio):
            # Process with STT
            text = await stt.transcribe(audio)
            response = await llm.generate(text)
            audio_response = await tts.synthesize(response)
            await bridge.send_audio(call_id, audio_response)

        await bridge.start()
    """

    def __init__(self, config: AudioBridgeConfig | None = None) -> None:
        """Initialize audio bridge.

        Args:
            config: Bridge configuration
        """
        self.config = config or AudioBridgeConfig()
        self._server: asyncio.Server | None = None
        self._connections: dict[UUID, AudioConnection] = {}

        # Codec pipeline for telephony <-> AI conversion
        self._codec_pipeline = CodecPipeline(
            telephony_codec=self.config.telephony_codec,
            ai_sample_rate=self.config.sample_rate,
        )

        # Callbacks
        self._on_audio_received: Callable[[UUID, np.ndarray], Any] | None = None
        self._on_connection: Callable[[UUID], Any] | None = None
        self._on_disconnection: Callable[[UUID], Any] | None = None

        # Statistics
        self._stats = BridgeStatistics()

    async def start(self) -> None:
        """Start the audio bridge server."""
        self._server = await asyncio.start_server(
            self._handle_connection,
            self.config.host,
            self.config.port,
        )

        log.info(
            "Audio bridge started",
            host=self.config.host,
            port=self.config.port,
        )

        async with self._server:
            await self._server.serve_forever()

    async def stop(self) -> None:
        """Stop the audio bridge server."""
        if self._server:
            self._server.close()
            await self._server.wait_closed()

        # Close all connections
        for conn in list(self._connections.values()):
            await conn.close()

        log.info("Audio bridge stopped")

    async def _handle_connection(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        """Handle new socket connection."""
        from uuid import uuid4

        call_id = uuid4()
        conn = AudioConnection(
            call_id=call_id,
            reader=reader,
            writer=writer,
            config=self.config,
        )
        self._connections[call_id] = conn

        peer = writer.get_extra_info("peername")
        log.info("New audio connection", call_id=str(call_id), peer=peer)

        if self._on_connection:
            result = self._on_connection(call_id)
            if asyncio.iscoroutine(result):
                await result

        try:
            await self._process_connection(conn)
        except Exception as e:
            log.error("Connection error", call_id=str(call_id), error=str(e))
        finally:
            await conn.close()
            del self._connections[call_id]

            if self._on_disconnection:
                result = self._on_disconnection(call_id)
                if asyncio.iscoroutine(result):
                    await result

            log.info("Audio connection closed", call_id=str(call_id))

    async def _process_connection(self, conn: "AudioConnection") -> None:
        """Process audio from connection."""
        audio_buffer: list[bytes] = []
        bytes_per_chunk = self.config.chunk_size * self.config.sample_width

        while not conn.closed:
            try:
                # Read audio data
                data = await asyncio.wait_for(
                    conn.reader.read(bytes_per_chunk),
                    timeout=5.0,
                )

                if not data:
                    break

                audio_buffer.append(data)

                # Process when we have enough data
                if len(audio_buffer) >= self.config.buffer_chunks:
                    # Combine chunks
                    combined = b"".join(audio_buffer)
                    audio_buffer = []

                    # Convert to numpy array
                    audio = np.frombuffer(combined, dtype=np.int16)
                    audio = audio.astype(np.float32) / 32768.0

                    # Notify callback
                    if self._on_audio_received:
                        result = self._on_audio_received(conn.call_id, audio)
                        if asyncio.iscoroutine(result):
                            await result

            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break

    async def send_audio(self, call_id: UUID, audio: np.ndarray | bytes) -> bool:
        """Send audio to a connection.

        Args:
            call_id: Target connection
            audio: Audio data (numpy float32 or bytes)

        Returns:
            True if sent successfully
        """
        conn = self._connections.get(call_id)
        if not conn or conn.closed:
            return False

        try:
            if isinstance(audio, np.ndarray):
                # Convert float32 to int16 bytes
                audio_int16 = (audio * 32767).astype(np.int16)
                audio_bytes = audio_int16.tobytes()
            else:
                audio_bytes = audio

            conn.writer.write(audio_bytes)
            await conn.writer.drain()
            return True

        except Exception as e:
            log.error("Send audio failed", call_id=str(call_id), error=str(e))
            return False

    def on_audio_received(
        self,
        callback: Callable[[UUID, np.ndarray], Any],
    ) -> None:
        """Set callback for received audio."""
        self._on_audio_received = callback

    def on_connection(self, callback: Callable[[UUID], Any]) -> None:
        """Set callback for new connections."""
        self._on_connection = callback

    def on_disconnection(self, callback: Callable[[UUID], Any]) -> None:
        """Set callback for disconnections."""
        self._on_disconnection = callback

    def get_connection(self, call_id: UUID) -> "AudioConnection | None":
        """Get connection by call ID."""
        return self._connections.get(call_id)

    @property
    def active_connections(self) -> int:
        """Get number of active connections."""
        return len(self._connections)


@dataclass
class AudioConnection:
    """Represents an audio connection."""

    call_id: UUID
    reader: asyncio.StreamReader
    writer: asyncio.StreamWriter
    config: AudioBridgeConfig
    closed: bool = False

    async def close(self) -> None:
        """Close the connection."""
        if not self.closed:
            self.closed = True
            self.writer.close()
            try:
                await self.writer.wait_closed()
            except Exception:
                pass


class FreeSwitchAudioProtocol:
    """Protocol handler for FreeSWITCH audio socket.

    FreeSWITCH sends audio with a simple header:
    - 4 bytes: sequence number (uint32)
    - N bytes: audio data (linear PCM)

    This class handles the protocol parsing.
    """

    @staticmethod
    def parse_packet(data: bytes) -> tuple[int, bytes]:
        """Parse FreeSWITCH audio packet.

        Args:
            data: Raw packet data

        Returns:
            Tuple of (sequence_number, audio_data)
        """
        if len(data) < 4:
            return 0, b""

        seq = struct.unpack(">I", data[:4])[0]
        audio = data[4:]
        return seq, audio

    @staticmethod
    def create_packet(seq: int, audio: bytes) -> bytes:
        """Create FreeSWITCH audio packet.

        Args:
            seq: Sequence number
            audio: Audio data

        Returns:
            Packet bytes
        """
        header = struct.pack(">I", seq)
        return header + audio


async def run_audio_bridge_server(
    config: AudioBridgeConfig | None = None,
    on_audio: Callable[[UUID, np.ndarray], Any] | None = None,
) -> None:
    """Run standalone audio bridge server.

    Convenience function for testing and standalone operation.

    Args:
        config: Bridge configuration
        on_audio: Audio callback
    """
    bridge = AudioBridge(config)

    if on_audio:
        bridge.on_audio_received(on_audio)

    await bridge.start()


@dataclass
class BridgeStatistics:
    """Statistics for audio bridge operations."""

    connections_total: int = 0
    connections_active: int = 0
    bytes_received: int = 0
    bytes_sent: int = 0
    frames_received: int = 0
    frames_sent: int = 0
    codec_decode_errors: int = 0
    codec_encode_errors: int = 0
    jitter_buffer_underruns: int = 0
    jitter_buffer_overruns: int = 0

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "connections_total": self.connections_total,
            "connections_active": self.connections_active,
            "bytes_received": self.bytes_received,
            "bytes_sent": self.bytes_sent,
            "frames_received": self.frames_received,
            "frames_sent": self.frames_sent,
            "codec_decode_errors": self.codec_decode_errors,
            "codec_encode_errors": self.codec_encode_errors,
            "jitter_buffer_underruns": self.jitter_buffer_underruns,
            "jitter_buffer_overruns": self.jitter_buffer_overruns,
        }


class TelephonyAudioBridge(AudioBridge):
    """Enhanced audio bridge with full codec and jitter buffer support.

    Extends AudioBridge with:
    - Automatic codec transcoding (G.711 <-> PCM)
    - Jitter buffer for network variations
    - RTP packet handling
    - Quality metrics

    Usage:
        bridge = TelephonyAudioBridge(
            config=AudioBridgeConfig(
                telephony_codec=CodecType.PCMA,  # G.711 A-law
            )
        )

        @bridge.on_audio_received
        async def handle_audio(call_id, audio):
            # audio is already decoded and resampled to 16kHz float32
            text = await stt.transcribe(audio)
            response_audio = await tts.synthesize(response)
            # send_audio will encode to G.711 automatically
            await bridge.send_audio(call_id, response_audio)
    """

    def __init__(self, config: AudioBridgeConfig | None = None) -> None:
        """Initialize telephony audio bridge.

        Args:
            config: Bridge configuration
        """
        super().__init__(config)

        # Optional jitter buffer (imported when needed)
        self._jitter_buffers: dict[UUID, Any] = {}

    async def _process_connection(self, conn: "AudioConnection") -> None:
        """Process audio from connection with codec transcoding.

        Overrides parent to add codec decoding and jitter buffering.
        """
        from .rtp_config import JitterBuffer, JitterBufferConfig

        # Create jitter buffer for this connection if enabled
        jitter_buffer = None
        if self.config.jitter_buffer_enabled:
            jitter_buffer = JitterBuffer(
                JitterBufferConfig(
                    min_delay_ms=self.config.jitter_buffer_min_ms,
                    max_delay_ms=self.config.jitter_buffer_max_ms,
                    target_delay_ms=self.config.jitter_buffer_target_ms,
                )
            )
            self._jitter_buffers[conn.call_id] = jitter_buffer

        audio_buffer: list[bytes] = []
        # Telephony frames are smaller (160 samples at 8kHz = 20ms)
        bytes_per_chunk = 160 * self.config.sample_width

        while not conn.closed:
            try:
                # Read audio data
                data = await asyncio.wait_for(
                    conn.reader.read(bytes_per_chunk),
                    timeout=5.0,
                )

                if not data:
                    break

                self._stats.bytes_received += len(data)
                audio_buffer.append(data)

                # Process when we have enough data
                if len(audio_buffer) >= self.config.buffer_chunks:
                    # Combine chunks
                    combined = b"".join(audio_buffer)
                    audio_buffer = []

                    try:
                        # Decode from telephony codec to float32 at 16kHz
                        audio = self._codec_pipeline.decode_for_ai(combined)
                        self._stats.frames_received += 1

                        # Notify callback
                        if self._on_audio_received:
                            result = self._on_audio_received(conn.call_id, audio)
                            if asyncio.iscoroutine(result):
                                await result

                    except Exception as e:
                        self._stats.codec_decode_errors += 1
                        log.warning(f"Codec decode error: {e}")

            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break

        # Cleanup jitter buffer
        self._jitter_buffers.pop(conn.call_id, None)

    async def send_audio(self, call_id: UUID, audio: np.ndarray | bytes) -> bool:
        """Send audio to a connection with codec encoding.

        Args:
            call_id: Target connection
            audio: Audio data (numpy float32 at 16kHz or raw bytes)

        Returns:
            True if sent successfully
        """
        conn = self._connections.get(call_id)
        if not conn or conn.closed:
            return False

        try:
            if isinstance(audio, np.ndarray):
                # Encode from float32 16kHz to telephony codec
                audio_bytes = self._codec_pipeline.encode_for_telephony(audio)
            else:
                audio_bytes = audio

            conn.writer.write(audio_bytes)
            await conn.writer.drain()

            self._stats.bytes_sent += len(audio_bytes)
            self._stats.frames_sent += 1
            return True

        except Exception as e:
            self._stats.codec_encode_errors += 1
            log.error("Send audio failed", call_id=str(call_id), error=str(e))
            return False

    @property
    def statistics(self) -> BridgeStatistics:
        """Get bridge statistics."""
        self._stats.connections_active = len(self._connections)
        return self._stats
