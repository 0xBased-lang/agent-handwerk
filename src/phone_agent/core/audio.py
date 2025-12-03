"""Audio capture and playback pipeline.

Handles real-time audio I/O for the phone agent, including:
- Microphone capture
- Speaker playback
- Voice Activity Detection (VAD)
- Audio buffering and streaming
"""

from __future__ import annotations

import asyncio
import queue
import threading
from dataclasses import dataclass, field
from typing import Callable

import numpy as np
from itf_shared import get_logger

log = get_logger(__name__)


@dataclass
class AudioConfig:
    """Audio pipeline configuration."""

    sample_rate: int = 16000  # 16kHz for Whisper
    channels: int = 1  # Mono
    chunk_size: int = 1024  # Samples per chunk
    input_device: str | int | None = None  # None = default
    output_device: str | int | None = None
    vad_enabled: bool = True
    vad_threshold: float = 0.02  # RMS threshold for speech
    silence_duration: float = 1.0  # Seconds of silence to end utterance
    max_recording_duration: float = 30.0  # Max seconds per utterance


@dataclass
class AudioChunk:
    """A chunk of audio data with metadata."""

    data: np.ndarray
    sample_rate: int
    is_speech: bool = False
    rms: float = 0.0
    timestamp: float = 0.0


class AudioPipeline:
    """Real-time audio capture and playback pipeline.

    Provides:
    - Continuous audio capture with VAD
    - Utterance detection (speech start/end)
    - Audio playback queue
    - Thread-safe operation
    """

    def __init__(self, config: AudioConfig | None = None) -> None:
        """Initialize audio pipeline.

        Args:
            config: Audio configuration (uses defaults if None)
        """
        self.config = config or AudioConfig()
        self._running = False
        self._capture_thread: threading.Thread | None = None
        self._playback_thread: threading.Thread | None = None

        # Audio buffers
        self._capture_queue: queue.Queue[AudioChunk] = queue.Queue()
        self._playback_queue: queue.Queue[np.ndarray] = queue.Queue()
        self._utterance_buffer: list[np.ndarray] = []

        # State
        self._is_speaking = False
        self._silence_samples = 0
        self._recording_samples = 0

        # Callbacks
        self._on_utterance: Callable[[np.ndarray], None] | None = None
        self._on_speech_start: Callable[[], None] | None = None
        self._on_speech_end: Callable[[], None] | None = None

    def start(self) -> None:
        """Start audio capture and playback threads."""
        if self._running:
            return

        self._running = True

        # Start capture thread
        self._capture_thread = threading.Thread(
            target=self._capture_loop,
            daemon=True,
            name="audio-capture",
        )
        self._capture_thread.start()

        # Start playback thread
        self._playback_thread = threading.Thread(
            target=self._playback_loop,
            daemon=True,
            name="audio-playback",
        )
        self._playback_thread.start()

        log.info(
            "Audio pipeline started",
            sample_rate=self.config.sample_rate,
            chunk_size=self.config.chunk_size,
        )

    def stop(self) -> None:
        """Stop audio capture and playback threads."""
        self._running = False

        if self._capture_thread:
            self._capture_thread.join(timeout=2.0)
        if self._playback_thread:
            self._playback_thread.join(timeout=2.0)

        log.info("Audio pipeline stopped")

    def _capture_loop(self) -> None:
        """Continuous audio capture loop."""
        try:
            import sounddevice as sd

            def callback(indata: np.ndarray, frames: int, time_info: dict, status: int) -> None:
                if status:
                    log.warning("Audio capture status", status=status)

                # Convert to float32 mono
                audio = indata[:, 0] if indata.ndim > 1 else indata.flatten()
                audio = audio.astype(np.float32)

                # Calculate RMS
                rms = np.sqrt(np.mean(audio**2))

                # Simple VAD
                is_speech = rms > self.config.vad_threshold if self.config.vad_enabled else True

                chunk = AudioChunk(
                    data=audio.copy(),
                    sample_rate=self.config.sample_rate,
                    is_speech=is_speech,
                    rms=rms,
                )

                self._process_chunk(chunk)

            with sd.InputStream(
                device=self.config.input_device,
                samplerate=self.config.sample_rate,
                channels=self.config.channels,
                blocksize=self.config.chunk_size,
                dtype=np.float32,
                callback=callback,
            ):
                while self._running:
                    sd.sleep(100)

        except ImportError:
            log.error("sounddevice not installed - audio capture disabled")
        except Exception as e:
            log.error("Audio capture error", error=str(e))

    def _process_chunk(self, chunk: AudioChunk) -> None:
        """Process an audio chunk for VAD and utterance detection."""
        silence_threshold = int(
            self.config.silence_duration * self.config.sample_rate / self.config.chunk_size
        )
        max_chunks = int(
            self.config.max_recording_duration * self.config.sample_rate / self.config.chunk_size
        )

        if chunk.is_speech:
            if not self._is_speaking:
                # Speech started
                self._is_speaking = True
                self._utterance_buffer = []
                self._silence_samples = 0
                self._recording_samples = 0

                if self._on_speech_start:
                    self._on_speech_start()

                log.debug("Speech started", rms=chunk.rms)

            # Add to buffer
            self._utterance_buffer.append(chunk.data)
            self._silence_samples = 0
            self._recording_samples += 1

        elif self._is_speaking:
            # Silence during speech
            self._utterance_buffer.append(chunk.data)
            self._silence_samples += 1
            self._recording_samples += 1

            # Check for end of utterance
            if self._silence_samples >= silence_threshold or self._recording_samples >= max_chunks:
                self._end_utterance()

    def _end_utterance(self) -> None:
        """End current utterance and trigger callback."""
        if not self._utterance_buffer:
            return

        # Combine chunks
        utterance = np.concatenate(self._utterance_buffer)

        # Remove trailing silence
        trailing_silence = int(self._silence_samples * self.config.chunk_size)
        if trailing_silence > 0 and trailing_silence < len(utterance):
            utterance = utterance[:-trailing_silence]

        self._is_speaking = False
        self._utterance_buffer = []

        duration = len(utterance) / self.config.sample_rate
        log.debug("Utterance complete", duration=f"{duration:.2f}s", samples=len(utterance))

        if self._on_speech_end:
            self._on_speech_end()

        if self._on_utterance:
            self._on_utterance(utterance)

    def _playback_loop(self) -> None:
        """Audio playback loop."""
        try:
            import sounddevice as sd

            while self._running:
                try:
                    audio = self._playback_queue.get(timeout=0.5)
                    sd.play(audio, self.config.sample_rate, device=self.config.output_device)
                    sd.wait()
                except queue.Empty:
                    continue

        except ImportError:
            log.error("sounddevice not installed - audio playback disabled")
        except Exception as e:
            log.error("Audio playback error", error=str(e))

    def play(self, audio: np.ndarray | bytes, sample_rate: int | None = None) -> None:
        """Queue audio for playback.

        Args:
            audio: Audio data as numpy array or WAV bytes
            sample_rate: Sample rate (required if audio is raw samples)
        """
        if isinstance(audio, bytes):
            # Parse WAV
            import io
            import wave

            with io.BytesIO(audio) as f:
                with wave.open(f, "rb") as wav:
                    frames = wav.readframes(wav.getnframes())
                    audio_array = np.frombuffer(frames, dtype=np.int16)
                    audio_array = audio_array.astype(np.float32) / 32768.0
                    sample_rate = wav.getframerate()
        else:
            audio_array = audio
            sample_rate = sample_rate or self.config.sample_rate

        # Resample if needed
        if sample_rate != self.config.sample_rate:
            from scipy import signal

            samples = int(len(audio_array) * self.config.sample_rate / sample_rate)
            audio_array = signal.resample(audio_array, samples)

        self._playback_queue.put(audio_array)

    def on_utterance(self, callback: Callable[[np.ndarray], None]) -> None:
        """Set callback for when an utterance is detected.

        Args:
            callback: Function called with audio numpy array
        """
        self._on_utterance = callback

    def on_speech_start(self, callback: Callable[[], None]) -> None:
        """Set callback for when speech starts."""
        self._on_speech_start = callback

    def on_speech_end(self, callback: Callable[[], None]) -> None:
        """Set callback for when speech ends."""
        self._on_speech_end = callback

    async def capture_utterance(self, timeout: float = 30.0) -> np.ndarray | None:
        """Capture a single utterance asynchronously.

        Args:
            timeout: Maximum seconds to wait

        Returns:
            Audio numpy array or None if timeout
        """
        result_queue: asyncio.Queue[np.ndarray] = asyncio.Queue()

        def on_utterance(audio: np.ndarray) -> None:
            asyncio.get_event_loop().call_soon_threadsafe(
                result_queue.put_nowait, audio
            )

        old_callback = self._on_utterance
        self._on_utterance = on_utterance

        try:
            return await asyncio.wait_for(result_queue.get(), timeout=timeout)
        except asyncio.TimeoutError:
            return None
        finally:
            self._on_utterance = old_callback

    @property
    def is_running(self) -> bool:
        """Check if pipeline is running."""
        return self._running

    @property
    def is_speaking(self) -> bool:
        """Check if speech is currently detected."""
        return self._is_speaking
