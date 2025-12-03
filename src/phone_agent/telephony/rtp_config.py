"""RTP (Real-time Transport Protocol) packet handling.

Implements RTP packet parsing, creation, and jitter buffering for
real-time audio streaming in telephony applications.

RTP Header Structure (RFC 3550):
    0                   1                   2                   3
    0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1
   +-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
   |V=2|P|X|  CC   |M|     PT      |       sequence number         |
   +-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
   |                           timestamp                           |
   +-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
   |           synchronization source (SSRC) identifier            |
   +=+=+=+=+=+=+=+=+=+=+=+=+=+=+=+=+=+=+=+=+=+=+=+=+=+=+=+=+=+=+=+=+
"""

from __future__ import annotations

import asyncio
import struct
import time
from collections import deque
from dataclasses import dataclass, field
from enum import IntEnum
from typing import TYPE_CHECKING, Callable

import numpy as np
from itf_shared import get_logger

if TYPE_CHECKING:
    from numpy.typing import NDArray

log = get_logger(__name__)


class RTPPayloadType(IntEnum):
    """Standard RTP payload types for audio."""

    PCMU = 0  # G.711 μ-law
    PCMA = 8  # G.711 A-law
    G722 = 9  # G.722
    L16_STEREO = 10  # Linear 16-bit stereo
    L16_MONO = 11  # Linear 16-bit mono
    DYNAMIC_START = 96  # Dynamic payload types start here


@dataclass
class RTPHeader:
    """Parsed RTP header."""

    version: int  # Protocol version (should be 2)
    padding: bool  # Padding flag
    extension: bool  # Extension flag
    csrc_count: int  # CSRC count
    marker: bool  # Marker bit
    payload_type: int  # Payload type
    sequence: int  # Sequence number (16-bit, wraps around)
    timestamp: int  # Timestamp (32-bit)
    ssrc: int  # Synchronization source identifier


@dataclass
class RTPPacket:
    """Complete RTP packet with header and payload."""

    header: RTPHeader
    payload: bytes
    received_time: float = field(default_factory=time.time)

    @classmethod
    def parse(cls, data: bytes) -> "RTPPacket":
        """Parse RTP packet from bytes.

        Args:
            data: Raw packet bytes

        Returns:
            Parsed RTP packet

        Raises:
            ValueError: If packet is malformed
        """
        if len(data) < 12:
            raise ValueError("RTP packet too short (min 12 bytes)")

        # Parse fixed header
        first_byte = data[0]
        second_byte = data[1]

        version = (first_byte >> 6) & 0x03
        if version != 2:
            raise ValueError(f"Unsupported RTP version: {version}")

        padding = bool((first_byte >> 5) & 0x01)
        extension = bool((first_byte >> 4) & 0x01)
        csrc_count = first_byte & 0x0F

        marker = bool((second_byte >> 7) & 0x01)
        payload_type = second_byte & 0x7F

        sequence, timestamp, ssrc = struct.unpack(">HII", data[2:12])

        # Calculate header length
        header_len = 12 + (csrc_count * 4)

        # Handle extension header
        if extension and len(data) >= header_len + 4:
            ext_header = struct.unpack(">HH", data[header_len : header_len + 4])
            ext_length = ext_header[1] * 4
            header_len += 4 + ext_length

        # Extract payload
        payload = data[header_len:]

        # Handle padding
        if padding and payload:
            padding_length = payload[-1]
            payload = payload[:-padding_length]

        header = RTPHeader(
            version=version,
            padding=padding,
            extension=extension,
            csrc_count=csrc_count,
            marker=marker,
            payload_type=payload_type,
            sequence=sequence,
            timestamp=timestamp,
            ssrc=ssrc,
        )

        return cls(header=header, payload=payload)

    def to_bytes(self) -> bytes:
        """Serialize RTP packet to bytes.

        Returns:
            Packet bytes
        """
        # Build first byte
        first_byte = (self.header.version << 6) | (self.header.csrc_count & 0x0F)
        if self.header.padding:
            first_byte |= 0x20
        if self.header.extension:
            first_byte |= 0x10

        # Build second byte
        second_byte = self.header.payload_type & 0x7F
        if self.header.marker:
            second_byte |= 0x80

        # Pack header
        header_bytes = struct.pack(
            ">BBHII",
            first_byte,
            second_byte,
            self.header.sequence,
            self.header.timestamp,
            self.header.ssrc,
        )

        return header_bytes + self.payload


@dataclass
class JitterBufferConfig:
    """Jitter buffer configuration."""

    min_delay_ms: int = 40  # Minimum buffer delay
    max_delay_ms: int = 200  # Maximum buffer delay
    target_delay_ms: int = 100  # Target delay
    adaptive: bool = True  # Adaptive jitter compensation
    packet_time_ms: int = 20  # Expected packet interval


class JitterBuffer:
    """Adaptive jitter buffer for RTP packet reordering and timing.

    Handles:
    - Packet reordering (out-of-order delivery)
    - Variable network delay (jitter)
    - Packet loss detection
    - Playout timing

    The buffer collects incoming packets and releases them at regular
    intervals, smoothing out network jitter.
    """

    def __init__(self, config: JitterBufferConfig | None = None) -> None:
        """Initialize jitter buffer.

        Args:
            config: Buffer configuration
        """
        self.config = config or JitterBufferConfig()

        # Packet storage (sorted by sequence number)
        self._packets: deque[RTPPacket] = deque(maxlen=100)

        # Sequence tracking
        self._last_seq: int | None = None
        self._expected_seq: int | None = None

        # Timing
        self._playout_time: float | None = None
        self._buffer_delay_ms = self.config.target_delay_ms

        # Statistics
        self._packets_received = 0
        self._packets_dropped = 0
        self._packets_late = 0
        self._packets_lost = 0
        self._max_jitter_ms = 0.0

    def put(self, packet: RTPPacket) -> None:
        """Add packet to buffer.

        Args:
            packet: RTP packet to buffer
        """
        self._packets_received += 1

        # Initialize on first packet
        if self._expected_seq is None:
            self._expected_seq = packet.header.sequence
            self._playout_time = packet.received_time + (self.config.target_delay_ms / 1000)

        # Check for duplicates
        for existing in self._packets:
            if existing.header.sequence == packet.header.sequence:
                return  # Duplicate packet

        # Calculate jitter
        if self._last_seq is not None:
            expected_time = self._playout_time
            actual_delay = (packet.received_time - expected_time) * 1000 if expected_time else 0
            self._max_jitter_ms = max(self._max_jitter_ms, abs(actual_delay))

        self._last_seq = packet.header.sequence

        # Insert in sequence order
        inserted = False
        for i, existing in enumerate(self._packets):
            if self._sequence_less_than(packet.header.sequence, existing.header.sequence):
                self._packets.insert(i, packet)
                inserted = True
                break

        if not inserted:
            self._packets.append(packet)

        # Adaptive delay adjustment
        if self.config.adaptive:
            self._adjust_delay()

    def get(self) -> RTPPacket | None:
        """Get next packet for playout.

        Returns:
            Next packet or None if buffer is empty/not ready
        """
        if not self._packets:
            return None

        current_time = time.time()

        # Check if we have enough buffer
        if self._playout_time and current_time < self._playout_time:
            return None

        # Get next packet in sequence
        packet = self._packets.popleft()

        # Check for gaps (lost packets)
        if self._expected_seq is not None:
            gap = self._sequence_diff(packet.header.sequence, self._expected_seq)
            if gap > 0:
                self._packets_lost += gap

        # Update expected sequence
        self._expected_seq = (packet.header.sequence + 1) & 0xFFFF

        # Update playout time
        if self._playout_time:
            self._playout_time += self.config.packet_time_ms / 1000

        return packet

    def get_audio(
        self,
        sample_rate: int = 8000,
        samples_per_packet: int = 160,
    ) -> NDArray[np.int16] | None:
        """Get audio samples for playout.

        Handles packet loss concealment by returning silence for missing packets.

        Args:
            sample_rate: Audio sample rate
            samples_per_packet: Samples per RTP packet

        Returns:
            Audio samples or None if not ready
        """
        packet = self.get()
        if packet is None:
            return None

        # Check for lost packets and generate silence
        if self._packets_lost > 0:
            # Concealment: return silence for lost packets
            lost = min(self._packets_lost, 5)  # Max 5 packets concealment
            self._packets_lost -= lost
            silence = np.zeros(samples_per_packet * lost, dtype=np.int16)
            log.debug(f"Concealing {lost} lost packets with silence")
            return silence

        # Return payload as audio samples
        return np.frombuffer(packet.payload, dtype=np.int16)

    def _sequence_less_than(self, a: int, b: int) -> bool:
        """Compare sequence numbers with wrap-around handling.

        Args:
            a: First sequence number
            b: Second sequence number

        Returns:
            True if a < b (accounting for wrap-around)
        """
        diff = (b - a) & 0xFFFF
        return 0 < diff < 0x8000

    def _sequence_diff(self, a: int, b: int) -> int:
        """Calculate sequence number difference.

        Args:
            a: First sequence number
            b: Second sequence number

        Returns:
            Difference (a - b) with wrap-around
        """
        diff = (a - b) & 0xFFFF
        if diff > 0x8000:
            diff -= 0x10000
        return diff

    def _adjust_delay(self) -> None:
        """Adjust buffer delay based on jitter measurements."""
        # Increase delay if jitter is high
        if self._max_jitter_ms > self._buffer_delay_ms * 0.8:
            self._buffer_delay_ms = min(
                self.config.max_delay_ms,
                self._buffer_delay_ms + 10,
            )

        # Decrease delay if jitter is low
        elif self._max_jitter_ms < self._buffer_delay_ms * 0.3:
            self._buffer_delay_ms = max(
                self.config.min_delay_ms,
                self._buffer_delay_ms - 5,
            )

    @property
    def stats(self) -> dict:
        """Get buffer statistics.

        Returns:
            Statistics dictionary
        """
        return {
            "packets_received": self._packets_received,
            "packets_dropped": self._packets_dropped,
            "packets_late": self._packets_late,
            "packets_lost": self._packets_lost,
            "buffer_size": len(self._packets),
            "buffer_delay_ms": self._buffer_delay_ms,
            "max_jitter_ms": self._max_jitter_ms,
        }

    def clear(self) -> None:
        """Clear the buffer."""
        self._packets.clear()
        self._last_seq = None
        self._expected_seq = None
        self._playout_time = None


class RTPSession:
    """RTP session for bidirectional audio streaming.

    Manages RTP packet sending and receiving for a single call.
    """

    def __init__(
        self,
        ssrc: int | None = None,
        payload_type: int = RTPPayloadType.PCMA,
        sample_rate: int = 8000,
    ) -> None:
        """Initialize RTP session.

        Args:
            ssrc: Synchronization source ID (random if None)
            payload_type: RTP payload type
            sample_rate: Audio sample rate
        """
        import random

        self.ssrc = ssrc or random.randint(0, 0xFFFFFFFF)
        self.payload_type = payload_type
        self.sample_rate = sample_rate

        # Sequence and timestamp
        self._sequence = random.randint(0, 0xFFFF)
        self._timestamp = random.randint(0, 0xFFFFFFFF)
        self._samples_per_packet = (sample_rate * 20) // 1000  # 20ms packets

        # Receive buffer
        self.jitter_buffer = JitterBuffer()

        # Callbacks
        self._on_audio: Callable[[NDArray[np.int16]], None] | None = None

    def create_packet(self, audio: bytes, marker: bool = False) -> RTPPacket:
        """Create RTP packet for audio data.

        Args:
            audio: Audio payload bytes
            marker: Marker bit (e.g., start of talk spurt)

        Returns:
            RTP packet
        """
        header = RTPHeader(
            version=2,
            padding=False,
            extension=False,
            csrc_count=0,
            marker=marker,
            payload_type=self.payload_type,
            sequence=self._sequence,
            timestamp=self._timestamp,
            ssrc=self.ssrc,
        )

        packet = RTPPacket(header=header, payload=audio)

        # Update sequence and timestamp
        self._sequence = (self._sequence + 1) & 0xFFFF
        self._timestamp = (self._timestamp + self._samples_per_packet) & 0xFFFFFFFF

        return packet

    def receive_packet(self, data: bytes) -> None:
        """Process received RTP packet.

        Args:
            data: Raw packet bytes
        """
        try:
            packet = RTPPacket.parse(data)
            self.jitter_buffer.put(packet)
        except ValueError as e:
            log.warning(f"Invalid RTP packet: {e}")

    def on_audio(self, callback: Callable[[NDArray[np.int16]], None]) -> None:
        """Set audio callback.

        Args:
            callback: Function called with audio samples
        """
        self._on_audio = callback


@dataclass
class RTCPReport:
    """RTCP Sender/Receiver Report for quality monitoring.

    Used to track call quality metrics.
    """

    ssrc: int  # Source being reported on
    fraction_lost: int  # Fraction lost since last report (0-255)
    cumulative_lost: int  # Total packets lost
    highest_seq: int  # Highest sequence number received
    jitter: int  # Interarrival jitter (timestamp units)
    last_sr_timestamp: int  # Middle 32 bits of NTP timestamp from last SR
    delay_since_sr: int  # Delay since last SR (1/65536 seconds)

    @classmethod
    def parse(cls, data: bytes) -> "RTCPReport":
        """Parse RTCP report block.

        Args:
            data: Report block bytes (24 bytes)

        Returns:
            Parsed report
        """
        if len(data) < 24:
            raise ValueError("RTCP report too short")

        ssrc, fraction_cumulative, highest_seq, jitter, lsr, dlsr = struct.unpack(
            ">IIIIII", data[:24]
        )

        fraction_lost = (fraction_cumulative >> 24) & 0xFF
        cumulative_lost = fraction_cumulative & 0x00FFFFFF

        return cls(
            ssrc=ssrc,
            fraction_lost=fraction_lost,
            cumulative_lost=cumulative_lost,
            highest_seq=highest_seq,
            jitter=jitter,
            last_sr_timestamp=lsr,
            delay_since_sr=dlsr,
        )


class RTPReceiver:
    """Async RTP packet receiver.

    Listens for UDP packets on a specified port and processes them.
    """

    def __init__(
        self,
        host: str = "0.0.0.0",
        port: int = 10000,
        session: RTPSession | None = None,
    ) -> None:
        """Initialize receiver.

        Args:
            host: Bind address
            port: UDP port
            session: RTP session (creates new if None)
        """
        self.host = host
        self.port = port
        self.session = session or RTPSession()
        self._transport: asyncio.DatagramTransport | None = None
        self._protocol: _RTPProtocol | None = None

    async def start(self) -> None:
        """Start receiving RTP packets."""
        loop = asyncio.get_event_loop()
        self._transport, self._protocol = await loop.create_datagram_endpoint(
            lambda: _RTPProtocol(self.session),
            local_addr=(self.host, self.port),
        )
        log.info(f"RTP receiver started on {self.host}:{self.port}")

    async def stop(self) -> None:
        """Stop receiver."""
        if self._transport:
            self._transport.close()
            log.info("RTP receiver stopped")


class _RTPProtocol(asyncio.DatagramProtocol):
    """Internal UDP protocol handler for RTP."""

    def __init__(self, session: RTPSession) -> None:
        self.session = session

    def datagram_received(self, data: bytes, addr: tuple[str, int]) -> None:
        """Handle received datagram."""
        self.session.receive_packet(data)

    def error_received(self, exc: Exception) -> None:
        """Handle error."""
        log.error(f"RTP receive error: {exc}")


class RTPSender:
    """Async RTP packet sender.

    Sends RTP packets to a remote endpoint.
    """

    def __init__(
        self,
        remote_host: str,
        remote_port: int,
        session: RTPSession | None = None,
    ) -> None:
        """Initialize sender.

        Args:
            remote_host: Destination address
            remote_port: Destination port
            session: RTP session (creates new if None)
        """
        self.remote_host = remote_host
        self.remote_port = remote_port
        self.session = session or RTPSession()
        self._transport: asyncio.DatagramTransport | None = None

    async def start(self) -> None:
        """Start sender."""
        loop = asyncio.get_event_loop()
        self._transport, _ = await loop.create_datagram_endpoint(
            asyncio.DatagramProtocol,
            remote_addr=(self.remote_host, self.remote_port),
        )
        log.info(f"RTP sender started to {self.remote_host}:{self.remote_port}")

    async def send(self, audio: bytes, marker: bool = False) -> None:
        """Send audio as RTP packet.

        Args:
            audio: Audio payload
            marker: Marker bit
        """
        if not self._transport:
            raise RuntimeError("Sender not started")

        packet = self.session.create_packet(audio, marker)
        self._transport.sendto(packet.to_bytes())

    async def stop(self) -> None:
        """Stop sender."""
        if self._transport:
            self._transport.close()
            log.info("RTP sender stopped")
