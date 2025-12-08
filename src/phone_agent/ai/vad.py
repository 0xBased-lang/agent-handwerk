"""Voice Activity Detection (VAD) module.

Provides multiple VAD backends:
- SileroVAD: Neural network-based VAD (recommended, more accurate)
- SimpleVAD: RMS energy-based VAD (fallback, faster but less accurate)

Silero VAD is a pre-trained model that provides accurate speech detection
even in noisy environments, with low latency suitable for real-time use.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Iterator

import numpy as np
from itf_shared import get_logger

log = get_logger(__name__)


@dataclass
class VADSegment:
    """A detected speech segment."""

    start_time: float  # Start time in seconds
    end_time: float  # End time in seconds
    confidence: float  # Detection confidence (0-1)

    @property
    def duration(self) -> float:
        """Duration of the segment in seconds."""
        return self.end_time - self.start_time


@dataclass
class VADFrame:
    """VAD result for a single audio frame."""

    is_speech: bool  # Whether speech is detected
    confidence: float  # Detection confidence (0-1)
    audio: np.ndarray  # The audio frame


class BaseVAD(ABC):
    """Abstract base class for VAD implementations."""

    @abstractmethod
    def is_speech(self, audio: np.ndarray, sample_rate: int = 16000) -> tuple[bool, float]:
        """Check if audio frame contains speech.

        Args:
            audio: Audio samples as float32 numpy array
            sample_rate: Sample rate of audio

        Returns:
            Tuple of (is_speech, confidence)
        """
        pass

    @abstractmethod
    def reset(self) -> None:
        """Reset VAD state for new utterance."""
        pass


class SimpleVAD(BaseVAD):
    """Simple RMS energy-based VAD.

    Fast but less accurate than neural VAD.
    Good for quiet environments with minimal background noise.
    """

    def __init__(
        self,
        threshold: float = 0.02,
        min_speech_duration: float = 0.1,
        min_silence_duration: float = 0.3,
    ):
        """Initialize simple VAD.

        Args:
            threshold: RMS energy threshold for speech detection
            min_speech_duration: Minimum duration to consider as speech
            min_silence_duration: Minimum silence to end speech
        """
        self.threshold = threshold
        self.min_speech_duration = min_speech_duration
        self.min_silence_duration = min_silence_duration
        self._speech_frames = 0
        self._silence_frames = 0

    def is_speech(self, audio: np.ndarray, sample_rate: int = 16000) -> tuple[bool, float]:
        """Check if audio contains speech using RMS energy."""
        rms = np.sqrt(np.mean(audio**2))
        is_speech = rms > self.threshold

        # Confidence is scaled RMS (capped at 1.0)
        confidence = min(rms / (self.threshold * 5), 1.0) if is_speech else 0.0

        return is_speech, confidence

    def reset(self) -> None:
        """Reset VAD state."""
        self._speech_frames = 0
        self._silence_frames = 0


class SileroVAD(BaseVAD):
    """Silero VAD - Neural network-based voice activity detection.

    Uses a pre-trained model from Silero that provides:
    - High accuracy even in noisy environments
    - Low latency (30ms frames)
    - Low CPU usage (runs on CPU efficiently)

    The model is loaded from torch hub on first use.
    """

    # Silero VAD expects 16kHz audio
    SAMPLE_RATE = 16000

    # Frame sizes supported by Silero VAD
    FRAME_SIZES = [512, 1024, 1536]  # 32ms, 64ms, 96ms at 16kHz

    def __init__(
        self,
        threshold: float = 0.5,
        min_speech_duration: float = 0.1,
        min_silence_duration: float = 0.3,
        frame_size: int = 512,
    ):
        """Initialize Silero VAD.

        Args:
            threshold: Speech probability threshold (0-1)
            min_speech_duration: Minimum speech duration in seconds
            min_silence_duration: Minimum silence to end speech in seconds
            frame_size: Audio frame size (512, 1024, or 1536 samples)
        """
        if frame_size not in self.FRAME_SIZES:
            raise ValueError(f"frame_size must be one of {self.FRAME_SIZES}")

        self.threshold = threshold
        self.min_speech_duration = min_speech_duration
        self.min_silence_duration = min_silence_duration
        self.frame_size = frame_size

        self._model = None
        self._loaded = False

        # State tracking
        self._speech_frames = 0
        self._silence_frames = 0
        self._is_speaking = False

    def load(self) -> None:
        """Load the Silero VAD model from torch hub."""
        if self._loaded:
            return

        try:
            import torch

            log.info("Loading Silero VAD model...")

            # Load model from torch hub
            model, utils = torch.hub.load(
                repo_or_dir="snakers4/silero-vad",
                model="silero_vad",
                force_reload=False,
                onnx=False,
                trust_repo=True,
            )

            self._model = model
            self._get_speech_timestamps = utils[0]
            self._loaded = True

            log.info("Silero VAD model loaded successfully")

        except Exception as e:
            log.error("Failed to load Silero VAD model", error=str(e))
            raise

    def is_speech(self, audio: np.ndarray, sample_rate: int = 16000) -> tuple[bool, float]:
        """Check if audio frame contains speech using neural network.

        Args:
            audio: Audio samples as float32 numpy array
            sample_rate: Sample rate (will resample to 16kHz if different)

        Returns:
            Tuple of (is_speech, confidence/probability)
        """
        if not self._loaded:
            self.load()

        import torch

        # Resample if needed
        if sample_rate != self.SAMPLE_RATE:
            from scipy import signal

            samples = int(len(audio) * self.SAMPLE_RATE / sample_rate)
            audio = signal.resample(audio, samples)

        # Ensure correct frame size (pad or truncate)
        if len(audio) < self.frame_size:
            audio = np.pad(audio, (0, self.frame_size - len(audio)))
        elif len(audio) > self.frame_size:
            audio = audio[: self.frame_size]

        # Convert to tensor
        audio_tensor = torch.from_numpy(audio).float()

        # Get speech probability
        with torch.no_grad():
            speech_prob = self._model(audio_tensor, self.SAMPLE_RATE).item()

        is_speech = speech_prob > self.threshold

        return is_speech, speech_prob

    def process_audio_stream(
        self,
        audio_chunks: Iterator[np.ndarray],
        sample_rate: int = 16000,
    ) -> Iterator[VADFrame]:
        """Process a stream of audio chunks.

        Args:
            audio_chunks: Iterator of audio chunks
            sample_rate: Sample rate of audio

        Yields:
            VADFrame for each processed chunk
        """
        for chunk in audio_chunks:
            is_speech, confidence = self.is_speech(chunk, sample_rate)

            yield VADFrame(
                is_speech=is_speech,
                confidence=confidence,
                audio=chunk,
            )

    def detect_speech_segments(
        self,
        audio: np.ndarray,
        sample_rate: int = 16000,
    ) -> list[VADSegment]:
        """Detect speech segments in audio.

        Uses Silero's built-in speech timestamp detection.

        Args:
            audio: Full audio as numpy array
            sample_rate: Sample rate

        Returns:
            List of detected speech segments
        """
        if not self._loaded:
            self.load()

        import torch

        # Resample if needed
        if sample_rate != self.SAMPLE_RATE:
            from scipy import signal

            samples = int(len(audio) * self.SAMPLE_RATE / sample_rate)
            audio = signal.resample(audio, samples)
            sample_rate = self.SAMPLE_RATE

        # Convert to tensor
        audio_tensor = torch.from_numpy(audio).float()

        # Get speech timestamps
        speech_timestamps = self._get_speech_timestamps(
            audio_tensor,
            self._model,
            sampling_rate=sample_rate,
            threshold=self.threshold,
            min_speech_duration_ms=int(self.min_speech_duration * 1000),
            min_silence_duration_ms=int(self.min_silence_duration * 1000),
        )

        # Convert to VADSegment objects
        segments = []
        for ts in speech_timestamps:
            segment = VADSegment(
                start_time=ts["start"] / sample_rate,
                end_time=ts["end"] / sample_rate,
                confidence=1.0,  # Silero doesn't provide per-segment confidence
            )
            segments.append(segment)

        return segments

    def reset(self) -> None:
        """Reset VAD state for new utterance."""
        if self._model is not None:
            self._model.reset_states()
        self._speech_frames = 0
        self._silence_frames = 0
        self._is_speaking = False

    @property
    def is_loaded(self) -> bool:
        """Check if model is loaded."""
        return self._loaded


class VADFactory:
    """Factory for creating VAD instances."""

    @staticmethod
    def create(
        backend: str = "silero",
        threshold: float = 0.5,
        **kwargs,
    ) -> BaseVAD:
        """Create a VAD instance.

        Args:
            backend: VAD backend ("silero" or "simple")
            threshold: Detection threshold
            **kwargs: Additional arguments for the backend

        Returns:
            VAD instance
        """
        if backend == "silero":
            return SileroVAD(threshold=threshold, **kwargs)
        elif backend == "simple":
            return SimpleVAD(threshold=threshold, **kwargs)
        else:
            raise ValueError(f"Unknown VAD backend: {backend}")


# Convenience function
def get_vad(backend: str = "silero", **kwargs) -> BaseVAD:
    """Get a VAD instance.

    Args:
        backend: VAD backend ("silero" or "simple")
        **kwargs: Arguments for the VAD

    Returns:
        VAD instance
    """
    return VADFactory.create(backend, **kwargs)
