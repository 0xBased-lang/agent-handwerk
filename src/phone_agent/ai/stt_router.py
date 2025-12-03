"""Intelligent STT model router for German dialects.

Routes audio to the most appropriate ASR model based on detected dialect.
Manages model lifecycle to balance accuracy vs memory usage.
"""

from __future__ import annotations

import asyncio
from functools import partial
from pathlib import Path
from typing import Any

import numpy as np
from itf_shared import get_logger

from .dialect_detector import (
    DIALECT_MODELS,
    DialectResult,
    GermanDialectDetector,
)
from .stt import SpeechToText, TranscriptionResult

log = get_logger(__name__)


class DialectAwareSTT:
    """Speech-to-Text with automatic German dialect routing.

    Detects German dialects and routes to specialized models:
    - Standard German → primeline/whisper-large-v3-german
    - Alemannic (Schwäbisch, Swiss) → Flurin17/whisper-large-v3-turbo-swiss-german
    - Bavarian → openai/whisper-large-v3 (fallback)
    - Other languages → openai/whisper-large-v3

    Detection Modes:
    - "text": Detect dialect from transcribed text (faster, no probe model)
    - "audio": Detect dialect from audio probe before transcription (slower, more accurate)

    Memory Management:
    - Keeps max 2 models loaded simultaneously
    - Unloads least-recently-used model when switching
    - Probe model is separate and lightweight (only in audio mode)
    """

    def __init__(
        self,
        model_path: str | Path = "models/whisper",
        device: str = "cpu",
        compute_type: str = "int8",
        beam_size: int = 5,
        vad_filter: bool = True,
        max_loaded_models: int = 2,
        dialect_detection: bool = True,
        detection_mode: str = "text",
        probe_duration: float = 1.5,
    ) -> None:
        """Initialize dialect-aware STT.

        Args:
            model_path: Directory for model files
            device: Compute device (cpu, cuda)
            compute_type: Precision (int8, float16)
            beam_size: Beam search width
            vad_filter: Enable VAD filtering
            max_loaded_models: Maximum models to keep loaded
            dialect_detection: Enable dialect detection for German
            detection_mode: "text" (post-transcription) or "audio" (pre-transcription)
            probe_duration: Seconds of audio for dialect probe (audio mode only)
        """
        self.model_path = Path(model_path)
        self.device = device
        self.compute_type = compute_type
        self.beam_size = beam_size
        self.vad_filter = vad_filter
        self.max_loaded_models = max_loaded_models
        self.dialect_detection = dialect_detection
        self.detection_mode = detection_mode

        # Dialect detector (only initialized with probe if audio mode)
        self._dialect_detector = GermanDialectDetector(
            probe_duration=probe_duration,
        )

        # Model cache: model_name → SpeechToText instance
        self._models: dict[str, SpeechToText] = {}
        self._model_usage: list[str] = []  # LRU order (most recent last)

        # Current language setting (for non-German)
        self._language: str | None = "de"

        # Last detected dialect
        self._last_dialect: DialectResult | None = None

    def _get_or_load_model(self, model_name: str) -> SpeechToText:
        """Get model from cache or load it.

        Implements LRU eviction when max_loaded_models is exceeded.

        Args:
            model_name: HuggingFace model path

        Returns:
            Loaded SpeechToText instance
        """
        # Check cache
        if model_name in self._models:
            # Update LRU order
            if model_name in self._model_usage:
                self._model_usage.remove(model_name)
            self._model_usage.append(model_name)
            return self._models[model_name]

        # Evict oldest model if at capacity
        while len(self._models) >= self.max_loaded_models:
            oldest = self._model_usage.pop(0)
            log.info("Evicting STT model (LRU)", model=oldest)
            self._models[oldest].unload()
            del self._models[oldest]

        # Load new model
        log.info("Loading STT model", model=model_name)
        stt = SpeechToText(
            model=model_name,
            model_path=self.model_path,
            device=self.device,
            compute_type=self.compute_type,
            language=self._language,
            beam_size=self.beam_size,
            vad_filter=self.vad_filter,
        )
        stt.load()

        # Cache and track
        self._models[model_name] = stt
        self._model_usage.append(model_name)

        return stt

    def set_language(self, language: str | None) -> None:
        """Set target language for non-German transcription.

        Args:
            language: Language code (de, tr, ru, en) or None for auto
        """
        self._language = language
        log.debug("STT router language set", language=language)

    def detect_dialect(
        self,
        audio: np.ndarray,
        sample_rate: int = 16000,
    ) -> DialectResult:
        """Detect German dialect from audio.

        Args:
            audio: Audio samples
            sample_rate: Audio sample rate

        Returns:
            DialectResult with detection info
        """
        result = self._dialect_detector.detect_from_audio(audio, sample_rate)
        self._last_dialect = result
        return result

    def transcribe(
        self,
        audio: np.ndarray,
        sample_rate: int = 16000,
        language: str | None = None,
        force_dialect: str | None = None,
    ) -> str:
        """Transcribe audio with intelligent dialect routing.

        Args:
            audio: Audio samples as numpy array
            sample_rate: Audio sample rate
            language: Override language (de, tr, ru, en)
            force_dialect: Force specific dialect (de_standard, de_alemannic, etc.)

        Returns:
            Transcribed text
        """
        result = self.transcribe_with_info(audio, sample_rate, language, force_dialect)
        return result.text

    def transcribe_with_info(
        self,
        audio: np.ndarray,
        sample_rate: int = 16000,
        language: str | None = None,
        force_dialect: str | None = None,
    ) -> TranscriptionResult:
        """Transcribe audio with dialect routing and metadata.

        Args:
            audio: Audio samples as numpy array
            sample_rate: Audio sample rate
            language: Override language (de, tr, ru, en)
            force_dialect: Force specific dialect

        Returns:
            TranscriptionResult with text and language info
        """
        target_language = language if language is not None else self._language

        # Determine which model to use
        if force_dialect:
            # Forced dialect
            model_name = DIALECT_MODELS.get(force_dialect, DIALECT_MODELS["de_standard"])
            log.debug("Using forced dialect model", dialect=force_dialect, model=model_name)

        elif target_language == "de" and self.dialect_detection:
            if self.detection_mode == "audio":
                # Audio-based detection: probe audio first, then transcribe
                dialect_result = self.detect_dialect(audio, sample_rate)
                log.info(
                    "Dialect detected (audio mode)",
                    dialect=dialect_result.dialect,
                    confidence=f"{dialect_result.confidence:.2f}",
                    features=len(dialect_result.features_detected),
                )
                model_name = dialect_result.recommended_model
            else:
                # Text-based detection: use standard model, detect from text after
                # This avoids double transcription!
                model_name = DIALECT_MODELS["de_standard"]

        elif target_language == "de":
            # German without dialect detection
            model_name = DIALECT_MODELS["de_standard"]

        else:
            # Non-German: use multilingual model
            model_name = "openai/whisper-large-v3"

        # Get or load the model
        stt = self._get_or_load_model(model_name)

        # Transcribe with appropriate language hint
        transcribe_lang = target_language if target_language else None
        result = stt.transcribe_with_info(audio, sample_rate, transcribe_lang)

        # Text-based dialect detection (post-transcription)
        if (
            target_language == "de"
            and self.dialect_detection
            and self.detection_mode == "text"
            and result.text
        ):
            dialect_result = self._dialect_detector.detect_from_text(result.text)
            self._last_dialect = dialect_result

            if dialect_result.features_detected:
                log.info(
                    "Dialect detected (text mode)",
                    dialect=dialect_result.dialect,
                    confidence=f"{dialect_result.confidence:.2f}",
                    features=len(dialect_result.features_detected),
                )

        return result

    async def transcribe_async(
        self,
        audio: np.ndarray,
        sample_rate: int = 16000,
        language: str | None = None,
        force_dialect: str | None = None,
    ) -> str:
        """Async wrapper for transcription."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            partial(self.transcribe, audio, sample_rate, language, force_dialect),
        )

    async def transcribe_with_info_async(
        self,
        audio: np.ndarray,
        sample_rate: int = 16000,
        language: str | None = None,
        force_dialect: str | None = None,
    ) -> TranscriptionResult:
        """Async wrapper for transcription with info."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            partial(self.transcribe_with_info, audio, sample_rate, language, force_dialect),
        )

    @property
    def last_dialect(self) -> DialectResult | None:
        """Get the last detected dialect result."""
        return self._last_dialect

    @property
    def loaded_models(self) -> list[str]:
        """Get list of currently loaded models."""
        return list(self._models.keys())

    def preload_model(self, model_name: str) -> None:
        """Preload a model for faster first transcription.

        Args:
            model_name: HuggingFace model path to preload
        """
        self._get_or_load_model(model_name)

    def preload_dialects(self, dialects: list[str]) -> None:
        """Preload models for specific dialects.

        Args:
            dialects: List of dialect codes (de_standard, de_alemannic, etc.)
        """
        for dialect in dialects:
            model = DIALECT_MODELS.get(dialect)
            if model:
                self.preload_model(model)

    def unload_all(self) -> None:
        """Unload all models to free memory."""
        for model_name, stt in self._models.items():
            log.info("Unloading STT model", model=model_name)
            stt.unload()

        self._models.clear()
        self._model_usage.clear()
        self._dialect_detector.unload()
        log.info("All STT models unloaded")

    def get_stats(self) -> dict[str, Any]:
        """Get router statistics.

        Returns:
            Dict with loaded models, cache info, and last dialect
        """
        return {
            "loaded_models": self.loaded_models,
            "model_count": len(self._models),
            "max_models": self.max_loaded_models,
            "dialect_detection_enabled": self.dialect_detection,
            "last_dialect": (
                {
                    "dialect": self._last_dialect.dialect,
                    "confidence": self._last_dialect.confidence,
                    "model": self._last_dialect.recommended_model,
                }
                if self._last_dialect
                else None
            ),
        }
