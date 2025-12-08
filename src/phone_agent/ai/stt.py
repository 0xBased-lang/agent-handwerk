"""Speech-to-Text using faster-whisper.

Supports multilingual transcription with Whisper Large v3.
Handles German dialects (Schwäbisch, Bavarian, etc.) by normalizing to Standard German.
Also supports Turkish, Russian, and 90+ other languages.

Optimized for CPU inference on Raspberry Pi 5 and optional NPU acceleration.
"""

from __future__ import annotations

import asyncio
from functools import partial
from pathlib import Path
from typing import Any

import numpy as np
from itf_shared import get_logger

log = get_logger(__name__)


# Supported languages with their Whisper codes
SUPPORTED_LANGUAGES = {
    "de": "German",
    "tr": "Turkish",
    "ru": "Russian",
    "en": "English",
}

# Model recommendations per language
# German-optimized model for German, multilingual for others
LANGUAGE_MODELS = {
    "de": "primeline/distil-whisper-large-v3-german",
    "tr": "openai/whisper-large-v3",
    "ru": "openai/whisper-large-v3",
    "en": "openai/whisper-large-v3",
}


class TranscriptionResult:
    """Result of a transcription including detected language info."""

    def __init__(
        self,
        text: str,
        language: str,
        language_probability: float,
    ) -> None:
        self.text = text
        self.language = language
        self.language_probability = language_probability

    def __str__(self) -> str:
        return self.text


class SpeechToText:
    """Speech-to-Text engine using faster-whisper.

    Supports multilingual transcription with automatic dialect handling.
    German dialects (Schwäbisch, Bavarian, etc.) are normalized to Standard German.
    """

    def __init__(
        self,
        model: str = "openai/whisper-large-v3",
        model_path: str | Path = "models/whisper",
        device: str = "cpu",
        compute_type: str = "int8",
        language: str | None = "de",
        beam_size: int = 5,
        vad_filter: bool = True,
    ) -> None:
        """Initialize STT engine.

        Args:
            model: Model name or path (use "openai/whisper-large-v3" for multilingual)
            model_path: Directory containing model files
            device: Compute device (cpu, cuda, auto)
            compute_type: Precision (int8, float16, float32)
            language: Target language code (None for auto-detection)
            beam_size: Beam search width
            vad_filter: Enable voice activity detection
        """
        self.model_name = model
        self.model_path = Path(model_path)
        self.device = device
        self.compute_type = compute_type
        self.language = language
        self.beam_size = beam_size
        self.vad_filter = vad_filter

        self._model: Any = None
        self._loaded = False

    def load(self) -> None:
        """Load the Whisper model.

        Called lazily on first transcription or explicitly for preloading.
        """
        if self._loaded:
            return

        try:
            from faster_whisper import WhisperModel

            # Use model_path as download_root for cached models
            log.info(
                "Loading STT model",
                model=self.model_name,
                download_root=str(self.model_path),
                device=self.device,
                compute_type=self.compute_type,
                language=self.language,
            )

            self._model = WhisperModel(
                self.model_name,
                device=self.device,
                compute_type=self.compute_type,
                download_root=str(self.model_path),
            )
            self._loaded = True

            log.info("STT model loaded successfully")

        except ImportError:
            log.error("faster-whisper not installed")
            raise
        except Exception as e:
            log.error("Failed to load STT model", error=str(e))
            raise

    def set_language(self, language: str | None) -> None:
        """Change the target transcription language.

        Args:
            language: Language code (de, tr, ru, en) or None for auto-detection
        """
        if language is not None and language not in SUPPORTED_LANGUAGES:
            log.warning(
                "Unsupported language, using auto-detection",
                requested=language,
                supported=list(SUPPORTED_LANGUAGES.keys()),
            )
            language = None

        self.language = language
        log.debug("STT language updated", language=language)

    def transcribe(
        self,
        audio: np.ndarray,
        sample_rate: int = 16000,
        language: str | None = None,
    ) -> str:
        """Transcribe audio to text.

        Args:
            audio: Audio samples as numpy array (float32, -1 to 1)
            sample_rate: Audio sample rate (should be 16000 for Whisper)
            language: Override language for this transcription (optional)

        Returns:
            Transcribed text
        """
        result = self.transcribe_with_info(audio, sample_rate, language)
        return result.text

    def transcribe_with_info(
        self,
        audio: np.ndarray,
        sample_rate: int = 16000,
        language: str | None = None,
    ) -> TranscriptionResult:
        """Transcribe audio to text with language detection info.

        Args:
            audio: Audio samples as numpy array (float32, -1 to 1)
            sample_rate: Audio sample rate (should be 16000 for Whisper)
            language: Override language for this transcription (optional)

        Returns:
            TranscriptionResult with text and detected language info
        """
        if not self._loaded:
            self.load()

        # Use provided language or instance default
        transcribe_language = language if language is not None else self.language

        # Ensure correct sample rate
        if sample_rate != 16000:
            from scipy import signal

            samples = int(len(audio) * 16000 / sample_rate)
            audio = signal.resample(audio, samples)

        # Ensure float32
        if audio.dtype != np.float32:
            audio = audio.astype(np.float32)

        # Normalize if needed
        if audio.max() > 1.0 or audio.min() < -1.0:
            audio = audio / max(abs(audio.max()), abs(audio.min()))

        log.debug(
            "Starting transcription",
            audio_length=len(audio) / 16000,
            language=transcribe_language,
        )

        # Transcribe with optimized VAD parameters for faster response
        segments, info = self._model.transcribe(
            audio,
            language=transcribe_language,
            beam_size=self.beam_size,
            vad_filter=self.vad_filter,
            vad_parameters=dict(
                min_silence_duration_ms=300,  # Reduced from 500 for faster response
                speech_pad_ms=100,  # Reduced from 200
            ),
        )

        # Combine segments
        text = " ".join(segment.text.strip() for segment in segments)

        log.debug(
            "Transcription complete",
            text_length=len(text),
            detected_language=info.language,
            language_probability=info.language_probability,
        )

        return TranscriptionResult(
            text=text,
            language=info.language,
            language_probability=info.language_probability,
        )

    async def transcribe_async(
        self,
        audio: np.ndarray,
        sample_rate: int = 16000,
        language: str | None = None,
    ) -> str:
        """Async wrapper for transcription.

        Runs transcription in a thread pool to avoid blocking.
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            partial(self.transcribe, audio, sample_rate, language),
        )

    async def transcribe_with_info_async(
        self,
        audio: np.ndarray,
        sample_rate: int = 16000,
        language: str | None = None,
    ) -> TranscriptionResult:
        """Async wrapper for transcription with language info.

        Runs transcription in a thread pool to avoid blocking.
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            partial(self.transcribe_with_info, audio, sample_rate, language),
        )

    def unload(self) -> None:
        """Unload the model to free memory."""
        if self._model is not None:
            del self._model
            self._model = None
            self._loaded = False
            log.info("STT model unloaded")

    @property
    def is_loaded(self) -> bool:
        """Check if model is currently loaded."""
        return self._loaded
