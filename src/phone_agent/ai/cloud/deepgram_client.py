"""Speech-to-Text using Deepgram API.

Cloud STT provider with excellent German support and low latency.
Implements the same interface as local SpeechToText for seamless switching.
"""

from __future__ import annotations

import asyncio
import io
import wave
from functools import partial
from typing import Any

import numpy as np
from itf_shared import get_logger

log = get_logger(__name__)


# Supported languages with their Deepgram codes
SUPPORTED_LANGUAGES = {
    "de": "de",
    "tr": "tr",
    "ru": "ru",
    "en": "en",
}


class DeepgramTranscriptionResult:
    """Result of a transcription including detected language info.

    Compatible with local TranscriptionResult.
    """

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


class DeepgramSTT:
    """Speech-to-Text engine using Deepgram API.

    Uses Deepgram Nova-2 model for excellent German transcription.
    Compatible with local SpeechToText interface.
    """

    def __init__(
        self,
        api_key: str,
        model: str = "nova-2",
        language: str | None = "de",
    ) -> None:
        """Initialize Deepgram STT client.

        Args:
            api_key: Deepgram API key
            model: Model name (nova-2, nova, enhanced, base)
            language: Target language code (None for auto-detection)
        """
        self.api_key = api_key
        self.model = model
        self.language = language

        self._client: Any = None
        self._loaded = False

    def load(self) -> None:
        """Initialize the Deepgram client.

        Called lazily on first transcription or explicitly for preloading.
        """
        if self._loaded:
            return

        try:
            from deepgram import DeepgramClient

            log.info(
                "Initializing Deepgram client",
                model=self.model,
                language=self.language,
            )

            self._client = DeepgramClient(api_key=self.api_key)
            self._loaded = True

            log.info("Deepgram client initialized successfully")

        except ImportError:
            log.error("deepgram-sdk not installed. Run: pip install deepgram-sdk")
            raise
        except Exception as e:
            log.error("Failed to initialize Deepgram client", error=str(e))
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
        log.debug("Deepgram language updated", language=language)

    def _audio_to_wav_bytes(self, audio: np.ndarray, sample_rate: int) -> bytes:
        """Convert numpy audio array to WAV bytes.

        Args:
            audio: Audio samples as numpy array (float32, -1 to 1)
            sample_rate: Audio sample rate

        Returns:
            WAV audio as bytes
        """
        # Ensure float32
        if audio.dtype != np.float32:
            audio = audio.astype(np.float32)

        # Normalize if needed
        if audio.max() > 1.0 or audio.min() < -1.0:
            audio = audio / max(abs(audio.max()), abs(audio.min()))

        # Convert to int16
        audio_int16 = (audio * 32767).astype(np.int16)

        # Create WAV file in memory
        buffer = io.BytesIO()
        with wave.open(buffer, "wb") as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)  # 16-bit
            wav_file.setframerate(sample_rate)
            wav_file.writeframes(audio_int16.tobytes())

        return buffer.getvalue()

    def transcribe(
        self,
        audio: np.ndarray,
        sample_rate: int = 16000,
        language: str | None = None,
    ) -> str:
        """Transcribe audio to text.

        Args:
            audio: Audio samples as numpy array (float32, -1 to 1)
            sample_rate: Audio sample rate (16000 recommended)
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
    ) -> DeepgramTranscriptionResult:
        """Transcribe audio to text with language detection info.

        Args:
            audio: Audio samples as numpy array (float32, -1 to 1)
            sample_rate: Audio sample rate (16000 recommended)
            language: Override language for this transcription (optional)

        Returns:
            DeepgramTranscriptionResult with text and detected language info
        """
        if not self._loaded:
            self.load()

        # Use provided language or instance default
        transcribe_language = language if language is not None else self.language

        # Convert audio to WAV bytes
        audio_bytes = self._audio_to_wav_bytes(audio, sample_rate)

        log.debug(
            "Starting Deepgram transcription",
            audio_length=len(audio) / sample_rate,
            language=transcribe_language,
            model=self.model,
        )

        # Transcribe using new SDK API (v5.x)
        response = self._client.listen.v1.media.transcribe_file(
            request=audio_bytes,
            model=self.model,
            language=transcribe_language,
            smart_format=True,
            punctuate=True,
        )

        # Extract result
        result = response.results
        if result and result.channels and result.channels[0].alternatives:
            alt = result.channels[0].alternatives[0]
            text = alt.transcript
            confidence = alt.confidence
            detected_lang = transcribe_language or "de"
        else:
            text = ""
            confidence = 0.0
            detected_lang = transcribe_language or "de"

        log.debug(
            "Deepgram transcription complete",
            text_length=len(text),
            confidence=confidence,
            language=detected_lang,
        )

        return DeepgramTranscriptionResult(
            text=text,
            language=detected_lang,
            language_probability=confidence,
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
    ) -> DeepgramTranscriptionResult:
        """Async wrapper for transcription with language info.

        Runs transcription in a thread pool to avoid blocking.
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            partial(self.transcribe_with_info, audio, sample_rate, language),
        )

    def unload(self) -> None:
        """Unload the client to free resources."""
        if self._client is not None:
            self._client = None
            self._loaded = False
            log.info("Deepgram client unloaded")

    @property
    def is_loaded(self) -> bool:
        """Check if client is currently loaded."""
        return self._loaded
