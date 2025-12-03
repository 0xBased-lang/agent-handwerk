"""Audio codec implementations for telephony integration.

Provides encoding/decoding for standard telephony codecs:
- G.711 μ-law (PCMU) - Common in North America
- G.711 A-law (PCMA) - Common in Europe (Germany)
- G.722 - Wideband audio (16kHz)

All codecs convert to/from 16-bit linear PCM for AI processing.
"""

from __future__ import annotations

import struct
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING

import numpy as np
from itf_shared import get_logger

if TYPE_CHECKING:
    from numpy.typing import NDArray

log = get_logger(__name__)


class CodecType(str, Enum):
    """Supported audio codecs."""

    PCMU = "PCMU"  # G.711 μ-law
    PCMA = "PCMA"  # G.711 A-law
    G722 = "G722"  # G.722 wideband
    L16 = "L16"  # Linear 16-bit PCM (no encoding)


@dataclass
class CodecInfo:
    """Codec information and capabilities."""

    codec_type: CodecType
    sample_rate: int  # Native sample rate
    bits_per_sample: int  # Encoded bits per sample
    frame_size_ms: int  # Frame duration in ms
    bitrate_kbps: int  # Encoded bitrate


# Codec specifications
CODEC_INFO: dict[CodecType, CodecInfo] = {
    CodecType.PCMU: CodecInfo(
        codec_type=CodecType.PCMU,
        sample_rate=8000,
        bits_per_sample=8,
        frame_size_ms=20,
        bitrate_kbps=64,
    ),
    CodecType.PCMA: CodecInfo(
        codec_type=CodecType.PCMA,
        sample_rate=8000,
        bits_per_sample=8,
        frame_size_ms=20,
        bitrate_kbps=64,
    ),
    CodecType.G722: CodecInfo(
        codec_type=CodecType.G722,
        sample_rate=16000,
        bits_per_sample=8,
        frame_size_ms=20,
        bitrate_kbps=64,
    ),
    CodecType.L16: CodecInfo(
        codec_type=CodecType.L16,
        sample_rate=16000,
        bits_per_sample=16,
        frame_size_ms=20,
        bitrate_kbps=256,
    ),
}


class AudioCodec(ABC):
    """Base class for audio codecs."""

    def __init__(self, codec_type: CodecType) -> None:
        """Initialize codec.

        Args:
            codec_type: Type of codec
        """
        self.codec_type = codec_type
        self.info = CODEC_INFO[codec_type]

    @abstractmethod
    def encode(self, pcm: NDArray[np.int16]) -> bytes:
        """Encode linear PCM to codec format.

        Args:
            pcm: 16-bit linear PCM samples

        Returns:
            Encoded audio bytes
        """
        ...

    @abstractmethod
    def decode(self, data: bytes) -> NDArray[np.int16]:
        """Decode codec format to linear PCM.

        Args:
            data: Encoded audio bytes

        Returns:
            16-bit linear PCM samples
        """
        ...


class MuLawCodec(AudioCodec):
    """G.711 μ-law (PCMU) codec.

    Used primarily in North America and Japan.
    Compands 16-bit linear PCM to 8-bit μ-law.

    μ-law formula: F(x) = sgn(x) * ln(1 + μ|x|) / ln(1 + μ)
    where μ = 255 (standard value)
    """

    # μ-law encoding table (from ITU-T G.711)
    _MULAW_ENCODE_TABLE: bytes | None = None
    _MULAW_DECODE_TABLE: NDArray[np.int16] | None = None

    def __init__(self) -> None:
        """Initialize μ-law codec."""
        super().__init__(CodecType.PCMU)
        self._ensure_tables()

    @classmethod
    def _ensure_tables(cls) -> None:
        """Initialize lookup tables for fast encoding/decoding."""
        if cls._MULAW_ENCODE_TABLE is not None:
            return

        # Build decode table (8-bit μ-law to 16-bit linear)
        decode_table = np.zeros(256, dtype=np.int16)
        for i in range(256):
            # Invert the input
            inv = ~i
            # Extract sign, exponent, and mantissa
            sign = inv & 0x80
            exponent = (inv >> 4) & 0x07
            mantissa = inv & 0x0F
            # Calculate linear value
            value = ((mantissa << 3) + 0x84) << exponent
            value -= 0x84
            if sign:
                value = -value
            decode_table[i] = value

        cls._MULAW_DECODE_TABLE = decode_table

        # Build encode table (16-bit linear to 8-bit μ-law)
        # We use a direct calculation instead of full table for memory efficiency
        cls._MULAW_ENCODE_TABLE = b""  # Placeholder - encoding uses formula

    def encode(self, pcm: NDArray[np.int16]) -> bytes:
        """Encode 16-bit PCM to μ-law.

        Args:
            pcm: 16-bit linear PCM samples

        Returns:
            μ-law encoded bytes
        """
        # Bias constant for μ-law
        BIAS = 0x84
        CLIP = 32635

        # Vectorized encoding
        sign = (pcm >> 8) & 0x80
        pcm_abs = np.abs(pcm.astype(np.int32))
        pcm_abs = np.clip(pcm_abs, 0, CLIP)
        pcm_abs = pcm_abs + BIAS

        # Find segment
        exponent = np.zeros(len(pcm), dtype=np.uint8)
        for i in range(7, 0, -1):
            mask = pcm_abs >= (1 << (i + 7))
            exponent[mask] = np.maximum(exponent[mask], i)

        # Calculate mantissa
        mantissa = (pcm_abs >> (exponent + 3)) & 0x0F

        # Combine and invert
        result = ~(sign | (exponent << 4) | mantissa) & 0xFF

        return result.astype(np.uint8).tobytes()

    def decode(self, data: bytes) -> NDArray[np.int16]:
        """Decode μ-law to 16-bit PCM.

        Args:
            data: μ-law encoded bytes

        Returns:
            16-bit linear PCM samples
        """
        if self._MULAW_DECODE_TABLE is None:
            self._ensure_tables()

        indices = np.frombuffer(data, dtype=np.uint8)
        return self._MULAW_DECODE_TABLE[indices]  # type: ignore[index]


class ALawCodec(AudioCodec):
    """G.711 A-law (PCMA) codec.

    Used primarily in Europe (including Germany) and rest of world.
    Compands 16-bit linear PCM to 8-bit A-law.

    A-law formula:
    F(x) = sgn(x) * { A|x|/(1+ln(A))     if |x| < 1/A
                    { (1+ln(A|x|))/(1+ln(A)) if 1/A ≤ |x| ≤ 1
    where A = 87.6
    """

    _ALAW_DECODE_TABLE: NDArray[np.int16] | None = None

    def __init__(self) -> None:
        """Initialize A-law codec."""
        super().__init__(CodecType.PCMA)
        self._ensure_tables()

    @classmethod
    def _ensure_tables(cls) -> None:
        """Initialize lookup tables for fast encoding/decoding."""
        if cls._ALAW_DECODE_TABLE is not None:
            return

        # Build decode table (8-bit A-law to 16-bit linear)
        decode_table = np.zeros(256, dtype=np.int16)
        for i in range(256):
            # Toggle even bits
            value = i ^ 0x55
            # Extract sign and magnitude
            sign = value & 0x80
            segment = (value >> 4) & 0x07
            mantissa = value & 0x0F

            if segment == 0:
                linear = (mantissa << 4) + 8
            else:
                linear = ((mantissa << 4) + 0x108) << (segment - 1)

            if sign:
                linear = -linear

            decode_table[i] = linear

        cls._ALAW_DECODE_TABLE = decode_table

    def encode(self, pcm: NDArray[np.int16]) -> bytes:
        """Encode 16-bit PCM to A-law.

        Args:
            pcm: 16-bit linear PCM samples

        Returns:
            A-law encoded bytes
        """
        # Segment encoding table
        SEG_END = [0x1F, 0x3F, 0x7F, 0xFF, 0x1FF, 0x3FF, 0x7FF, 0xFFF]

        # Get sign
        sign = np.zeros(len(pcm), dtype=np.uint8)
        pcm_work = pcm.astype(np.int32)
        mask = pcm_work >= 0
        sign[mask] = 0xD5
        sign[~mask] = 0x55
        pcm_work = np.abs(pcm_work)

        # Compress and find segment
        result = np.zeros(len(pcm), dtype=np.uint8)

        for seg, end_val in enumerate(SEG_END):
            if seg == len(SEG_END) - 1:
                # Last segment - all remaining values
                mask = pcm_work > SEG_END[seg - 1] if seg > 0 else np.ones(len(pcm), dtype=bool)
            else:
                lower = SEG_END[seg - 1] if seg > 0 else 0
                mask = (pcm_work > lower) & (pcm_work <= end_val)

            if seg < 2:
                result[mask] = (pcm_work[mask] >> 4) & 0x0F
            else:
                result[mask] = (pcm_work[mask] >> (seg + 3)) & 0x0F

            result[mask] |= seg << 4

        result ^= sign

        return result.tobytes()

    def decode(self, data: bytes) -> NDArray[np.int16]:
        """Decode A-law to 16-bit PCM.

        Args:
            data: A-law encoded bytes

        Returns:
            16-bit linear PCM samples
        """
        if self._ALAW_DECODE_TABLE is None:
            self._ensure_tables()

        indices = np.frombuffer(data, dtype=np.uint8)
        return self._ALAW_DECODE_TABLE[indices]  # type: ignore[index]


class G722Codec(AudioCodec):
    """G.722 wideband codec.

    Provides 7kHz bandwidth audio at 64kbps (vs 3.4kHz for G.711).
    Uses Sub-Band Adaptive Differential PCM (SB-ADPCM).

    Native sample rate: 16kHz
    """

    def __init__(self) -> None:
        """Initialize G.722 codec."""
        super().__init__(CodecType.G722)
        # G.722 state variables for encoder/decoder
        self._encoder_state: dict = {}
        self._decoder_state: dict = {}

    def encode(self, pcm: NDArray[np.int16]) -> bytes:
        """Encode 16-bit PCM to G.722.

        This is a simplified implementation. For production, consider
        using a dedicated G.722 library.

        Args:
            pcm: 16-bit linear PCM samples at 16kHz

        Returns:
            G.722 encoded bytes
        """
        # G.722 encodes 2 samples into 1 byte
        # Split into lower and upper subbands using QMF filterbank

        try:
            # Try to use av (PyAV) for proper G.722 encoding
            import av

            # Create a memory buffer
            output = []

            # Create encoder
            codec = av.Codec("g722", "w")
            encoder = codec.create()
            encoder.sample_rate = 16000
            encoder.channels = 1
            encoder.format = av.AudioFormat("s16")

            # Encode frame
            frame = av.AudioFrame.from_ndarray(
                pcm.reshape(1, -1),
                format="s16",
                layout="mono",
            )
            frame.sample_rate = 16000

            for packet in encoder.encode(frame):
                output.append(bytes(packet))

            return b"".join(output)

        except ImportError:
            # Fallback: Return raw PCM (lossy, but functional)
            log.warning("G.722 encoding requires PyAV, falling back to PCM")
            return pcm.tobytes()

    def decode(self, data: bytes) -> NDArray[np.int16]:
        """Decode G.722 to 16-bit PCM.

        Args:
            data: G.722 encoded bytes

        Returns:
            16-bit linear PCM samples at 16kHz
        """
        try:
            import av
            import io

            # Create decoder
            container = av.open(io.BytesIO(data), format="g722", mode="r")

            output = []
            for frame in container.decode(audio=0):
                arr = frame.to_ndarray()
                if arr.ndim > 1:
                    arr = arr[0]
                output.append(arr)

            container.close()
            return np.concatenate(output).astype(np.int16)

        except ImportError:
            # Fallback: Assume raw PCM
            log.warning("G.722 decoding requires PyAV, falling back to PCM")
            return np.frombuffer(data, dtype=np.int16)


class LinearPCMCodec(AudioCodec):
    """Linear 16-bit PCM (no encoding).

    Passthrough codec for uncompressed audio.
    """

    def __init__(self) -> None:
        """Initialize linear PCM codec."""
        super().__init__(CodecType.L16)

    def encode(self, pcm: NDArray[np.int16]) -> bytes:
        """Return raw PCM bytes.

        Args:
            pcm: 16-bit linear PCM samples

        Returns:
            Raw PCM bytes
        """
        return pcm.tobytes()

    def decode(self, data: bytes) -> NDArray[np.int16]:
        """Parse raw PCM bytes.

        Args:
            data: Raw PCM bytes

        Returns:
            16-bit linear PCM samples
        """
        return np.frombuffer(data, dtype=np.int16)


def get_codec(codec_type: CodecType | str) -> AudioCodec:
    """Get codec instance by type.

    Args:
        codec_type: Codec type (enum or string)

    Returns:
        Codec instance

    Raises:
        ValueError: If codec type is unknown
    """
    if isinstance(codec_type, str):
        codec_type = CodecType(codec_type.upper())

    codecs: dict[CodecType, type[AudioCodec]] = {
        CodecType.PCMU: MuLawCodec,
        CodecType.PCMA: ALawCodec,
        CodecType.G722: G722Codec,
        CodecType.L16: LinearPCMCodec,
    }

    if codec_type not in codecs:
        raise ValueError(f"Unknown codec type: {codec_type}")

    return codecs[codec_type]()


class AudioResampler:
    """Resample audio between sample rates.

    Handles conversion between telephony rates (8kHz) and
    AI processing rate (16kHz).
    """

    def __init__(
        self,
        input_rate: int = 8000,
        output_rate: int = 16000,
        channels: int = 1,
    ) -> None:
        """Initialize resampler.

        Args:
            input_rate: Input sample rate
            output_rate: Output sample rate
            channels: Number of audio channels
        """
        self.input_rate = input_rate
        self.output_rate = output_rate
        self.channels = channels
        self._resampler = None

    def resample(self, audio: NDArray[np.int16]) -> NDArray[np.int16]:
        """Resample audio to target rate.

        Args:
            audio: Input audio samples

        Returns:
            Resampled audio samples
        """
        if self.input_rate == self.output_rate:
            return audio

        try:
            # Try using scipy for high-quality resampling
            from scipy import signal

            # Calculate target length
            target_length = int(len(audio) * self.output_rate / self.input_rate)

            # Resample
            resampled = signal.resample(audio.astype(np.float64), target_length)
            return np.clip(resampled, -32768, 32767).astype(np.int16)

        except ImportError:
            # Fallback to simple linear interpolation
            ratio = self.output_rate / self.input_rate
            target_length = int(len(audio) * ratio)
            indices = np.linspace(0, len(audio) - 1, target_length)
            resampled = np.interp(indices, np.arange(len(audio)), audio.astype(np.float64))
            return np.clip(resampled, -32768, 32767).astype(np.int16)


class CodecPipeline:
    """Audio codec pipeline for telephony-to-AI conversion.

    Handles the complete flow:
    1. Decode telephony codec (G.711/G.722)
    2. Resample to AI rate (16kHz)
    3. Convert to float32 for AI processing
    4. Convert back to int16
    5. Resample to telephony rate
    6. Encode to telephony codec
    """

    def __init__(
        self,
        telephony_codec: CodecType = CodecType.PCMA,
        ai_sample_rate: int = 16000,
    ) -> None:
        """Initialize codec pipeline.

        Args:
            telephony_codec: Codec used for telephony
            ai_sample_rate: Sample rate for AI processing
        """
        self.codec = get_codec(telephony_codec)
        self.ai_sample_rate = ai_sample_rate

        # Resamplers
        codec_rate = self.codec.info.sample_rate
        self._upsample = AudioResampler(codec_rate, ai_sample_rate)
        self._downsample = AudioResampler(ai_sample_rate, codec_rate)

    def decode_for_ai(self, data: bytes) -> NDArray[np.float32]:
        """Decode telephony audio for AI processing.

        Args:
            data: Encoded telephony audio

        Returns:
            Float32 audio at AI sample rate
        """
        # Decode to PCM
        pcm = self.codec.decode(data)

        # Resample to AI rate
        resampled = self._upsample.resample(pcm)

        # Convert to float32 normalized
        return resampled.astype(np.float32) / 32768.0

    def encode_for_telephony(self, audio: NDArray[np.float32]) -> bytes:
        """Encode AI audio for telephony.

        Args:
            audio: Float32 audio from AI (TTS)

        Returns:
            Encoded telephony audio
        """
        # Convert to int16
        pcm = (audio * 32767).astype(np.int16)

        # Resample to codec rate
        resampled = self._downsample.resample(pcm)

        # Encode
        return self.codec.encode(resampled)


# Convenience functions
def decode_pcmu(data: bytes) -> NDArray[np.int16]:
    """Decode μ-law to linear PCM."""
    return MuLawCodec().decode(data)


def encode_pcmu(pcm: NDArray[np.int16]) -> bytes:
    """Encode linear PCM to μ-law."""
    return MuLawCodec().encode(pcm)


def decode_pcma(data: bytes) -> NDArray[np.int16]:
    """Decode A-law to linear PCM."""
    return ALawCodec().decode(data)


def encode_pcma(pcm: NDArray[np.int16]) -> bytes:
    """Encode linear PCM to A-law."""
    return ALawCodec().encode(pcm)
