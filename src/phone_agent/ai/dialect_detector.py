"""German dialect detection for intelligent model routing.

Detects whether German speech is:
- Standard German (Hochdeutsch)
- Alemannic (Schwäbisch, Badisch, Swiss German)
- Bavarian (Bayerisch, Österreichisch)
- Low German (Plattdeutsch)

Uses phonetic and lexical features from initial transcription probe.
"""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass
from functools import partial
from typing import Any

import numpy as np
from itf_shared import get_logger

log = get_logger(__name__)


@dataclass
class DialectResult:
    """Result of German dialect detection."""

    dialect: str  # de_standard, de_alemannic, de_bavarian, de_low
    confidence: float
    features_detected: list[str]
    recommended_model: str


# Dialect-specific linguistic patterns (raw strings for reference)
_ALEMANNIC_PATTERN_DEFS = {
    # Schwäbisch patterns
    r"\bi han\b": "alemannic_verb",
    r"\bi ha\b": "alemannic_verb",
    r"\bi kann? et\b": "alemannic_negation",
    r"\bnet\b": "alemannic_negation",
    r"\ble\b$": "alemannic_diminutive",
    r"\bli\b$": "alemannic_diminutive",
    r"le\b": "alemannic_diminutive",  # -le ending (Mädle, bissle)
    r"\bbissle\b": "schwaebisch_word",  # ein bisschen
    r"\bmädle\b": "alemannic_word",
    r"\bbüble\b": "alemannic_word",
    r"\bgrombira\b": "schwaebisch_word",
    r"\blugga\b": "schwaebisch_word",
    r"\bschaffe\b": "schwaebisch_word",
    r"\bschwätza\b": "schwaebisch_word",  # schwätzen (reden)
    r"\bheilig's blechle\b": "schwaebisch_phrase",
    r"\boi\b": "alemannic_vowel",  # ei → oi shift
    r"\bao\b": "alemannic_vowel",  # au → ao shift
    r"\bisch\b": "alemannic_ist",
    r"\bgoht\b": "alemannic_verb",
    r"\bwomma\b": "alemannic_contraction",
    r"\bwemma\b": "alemannic_contraction",
    r"\bso isch des\b": "alemannic_phrase",
}

_BAVARIAN_PATTERN_DEFS = {
    r"\bi hob\b": "bavarian_verb",
    r"\bhabt's\b": "bavarian_verb",
    r"\bned\b": "bavarian_negation",
    r"\bnia\b": "bavarian_negation",
    r"\b(er|sie|es)l\b": "bavarian_diminutive",
    r"\bdeandl\b": "bavarian_word",
    r"\bbua\b": "bavarian_word",
    r"\bfei\b": "bavarian_particle",
    r"\bgeh\b": "bavarian_particle",
    r"\bja mei\b": "bavarian_phrase",
    r"\bservus\b": "bavarian_greeting",
    r"\bgriaß di\b": "bavarian_greeting",
    r"\bwia\b": "bavarian_wie",
    r"\bdo\b": "bavarian_da",
    r"\bheid\b": "bavarian_heute",
}

_LOW_GERMAN_PATTERN_DEFS = {
    r"\bik\b": "low_german_ich",
    r"\bsnacken\b": "low_german_word",
    r"\blütt\b": "low_german_word",
    r"\bkieken\b": "low_german_word",
    r"\bmoin\b": "low_german_greeting",
    r"\btschüss\b": "low_german_greeting",
    r"\bdor\b": "low_german_da",
    r"\bnich\b": "low_german_nicht",
    r"\bwat\b": "low_german_was",
    r"\bun\b": "low_german_und",
}

# Pre-compiled patterns for performance (compiled once at module load)
ALEMANNIC_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(pattern, re.IGNORECASE), feature)
    for pattern, feature in _ALEMANNIC_PATTERN_DEFS.items()
]

BAVARIAN_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(pattern, re.IGNORECASE), feature)
    for pattern, feature in _BAVARIAN_PATTERN_DEFS.items()
]

LOW_GERMAN_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(pattern, re.IGNORECASE), feature)
    for pattern, feature in _LOW_GERMAN_PATTERN_DEFS.items()
]

# Model recommendations per dialect
DIALECT_MODELS = {
    "de_standard": "primeline/whisper-large-v3-german",
    "de_alemannic": "Flurin17/whisper-large-v3-turbo-swiss-german",
    "de_bavarian": "openai/whisper-large-v3",  # No specialized model yet
    "de_low": "openai/whisper-large-v3",  # No specialized model yet
}


class GermanDialectDetector:
    """Detects German dialects from speech or text.

    Uses a combination of:
    1. Quick transcription probe with standard model
    2. Lexical feature analysis
    3. Phonetic pattern matching
    """

    def __init__(
        self,
        probe_duration: float = 3.0,
        confidence_threshold: float = 0.6,
    ) -> None:
        """Initialize dialect detector.

        Args:
            probe_duration: Seconds of audio to analyze (default 3s)
            confidence_threshold: Minimum confidence for dialect detection
        """
        self.probe_duration = probe_duration
        self.confidence_threshold = confidence_threshold
        self._probe_model: Any = None
        self._probe_loaded = False

    def _load_probe_model(self) -> None:
        """Load a lightweight model for initial transcription probe."""
        if self._probe_loaded:
            return

        try:
            from faster_whisper import WhisperModel

            log.info("Loading dialect probe model")
            # Use small model for quick probing
            self._probe_model = WhisperModel(
                "openai/whisper-small",
                device="cpu",
                compute_type="int8",
            )
            self._probe_loaded = True
            log.info("Dialect probe model loaded")
        except Exception as e:
            log.error("Failed to load probe model", error=str(e))
            raise

    def detect_from_text(self, text: str) -> DialectResult:
        """Detect German dialect from text.

        Args:
            text: Transcribed German text

        Returns:
            DialectResult with detected dialect and confidence
        """
        text_lower = text.lower()
        features: list[str] = []

        # Score each dialect
        scores = {
            "de_alemannic": 0.0,
            "de_bavarian": 0.0,
            "de_low": 0.0,
            "de_standard": 0.0,
        }

        # Check Alemannic patterns (pre-compiled)
        for compiled_pattern, feature in ALEMANNIC_PATTERNS:
            if compiled_pattern.search(text_lower):
                scores["de_alemannic"] += 1.0
                features.append(f"alemannic:{feature}")

        # Check Bavarian patterns (pre-compiled)
        for compiled_pattern, feature in BAVARIAN_PATTERNS:
            if compiled_pattern.search(text_lower):
                scores["de_bavarian"] += 1.0
                features.append(f"bavarian:{feature}")

        # Check Low German patterns (pre-compiled)
        for compiled_pattern, feature in LOW_GERMAN_PATTERNS:
            if compiled_pattern.search(text_lower):
                scores["de_low"] += 1.0
                features.append(f"low_german:{feature}")

        # Normalize scores
        total = sum(scores.values()) + 0.1  # Avoid division by zero

        # Calculate confidence for each dialect
        normalized = {k: v / total for k, v in scores.items()}

        # Determine best match
        if not features:
            # No dialect features detected → Standard German
            dialect = "de_standard"
            confidence = 0.9  # High confidence if no dialect features
        else:
            # Get highest scoring dialect
            dialect = max(normalized, key=normalized.get)  # type: ignore
            confidence = normalized[dialect]

            # Apply minimum threshold
            if confidence < self.confidence_threshold:
                # Low confidence, default to standard
                log.debug(
                    "Dialect confidence below threshold, using standard",
                    detected=dialect,
                    confidence=confidence,
                    threshold=self.confidence_threshold,
                )
                dialect = "de_standard"
                confidence = 1.0 - confidence  # Inverse confidence

        log.debug(
            "Dialect detection result",
            dialect=dialect,
            confidence=confidence,
            features=features[:5],  # Log first 5 features
        )

        return DialectResult(
            dialect=dialect,
            confidence=confidence,
            features_detected=features,
            recommended_model=DIALECT_MODELS[dialect],
        )

    def detect_from_audio(
        self,
        audio: np.ndarray,
        sample_rate: int = 16000,
    ) -> DialectResult:
        """Detect German dialect from audio.

        Uses a quick transcription probe followed by text analysis.

        Args:
            audio: Audio samples as numpy array
            sample_rate: Audio sample rate

        Returns:
            DialectResult with detected dialect
        """
        # Load probe model if needed
        if not self._probe_loaded:
            self._load_probe_model()

        # Take probe duration worth of audio
        probe_samples = int(self.probe_duration * sample_rate)
        probe_audio = audio[:probe_samples]

        # Ensure correct format
        if probe_audio.dtype != np.float32:
            probe_audio = probe_audio.astype(np.float32)

        # Resample if needed
        if sample_rate != 16000:
            from scipy import signal

            samples = int(len(probe_audio) * 16000 / sample_rate)
            probe_audio = signal.resample(probe_audio, samples)

        log.debug(
            "Running dialect probe",
            probe_duration=self.probe_duration,
            audio_samples=len(probe_audio),
        )

        # Quick transcription (no VAD for speed)
        segments, _ = self._probe_model.transcribe(
            probe_audio,
            language="de",
            beam_size=1,  # Fast
            vad_filter=False,  # Speed
        )

        # Combine segments
        probe_text = " ".join(s.text.strip() for s in segments)

        log.debug("Dialect probe transcription", text=probe_text[:100])

        # Analyze text for dialect features
        return self.detect_from_text(probe_text)

    async def detect_from_audio_async(
        self,
        audio: np.ndarray,
        sample_rate: int = 16000,
    ) -> DialectResult:
        """Async wrapper for audio dialect detection."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            partial(self.detect_from_audio, audio, sample_rate),
        )

    def unload(self) -> None:
        """Unload probe model to free memory."""
        if self._probe_model is not None:
            del self._probe_model
            self._probe_model = None
            self._probe_loaded = False
            log.info("Dialect probe model unloaded")


# Convenience function for quick dialect detection
def detect_german_dialect(text: str) -> str:
    """Quick function to detect German dialect from text.

    Args:
        text: German text to analyze

    Returns:
        Dialect code: de_standard, de_alemannic, de_bavarian, de_low
    """
    detector = GermanDialectDetector()
    result = detector.detect_from_text(text)
    return result.dialect


def get_model_for_dialect(dialect: str) -> str:
    """Get recommended ASR model for a German dialect.

    Args:
        dialect: Dialect code from detect_german_dialect()

    Returns:
        HuggingFace model path
    """
    return DIALECT_MODELS.get(dialect, DIALECT_MODELS["de_standard"])
