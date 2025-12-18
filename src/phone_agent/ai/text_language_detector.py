"""Text-based language detection for chat messages.

Detects German, Russian, Turkish, and German dialects (Schwäbisch/Alemannic)
using character patterns and linguistic markers.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Set


class DetectedLanguage(str, Enum):
    """Supported languages for detection."""

    GERMAN = "de"
    RUSSIAN = "ru"
    TURKISH = "tr"
    ENGLISH = "en"
    UNKNOWN = "unknown"


@dataclass
class LanguageDetectionResult:
    """Result of language detection."""

    language: DetectedLanguage
    is_dialect: bool  # True if Schwäbisch/Alemannic detected
    confidence: float  # 0.0 to 1.0
    dialect_name: str | None = None  # e.g., "schwäbisch", "alemannic"

    @property
    def response_language(self) -> DetectedLanguage:
        """Language to use for responses.

        Dialects respond in standard German.
        """
        if self.is_dialect:
            return DetectedLanguage.GERMAN
        return self.language


class TextLanguageDetector:
    """Detect language from text using character patterns.

    Uses a multi-stage detection approach:
    1. Character set detection (Cyrillic for Russian)
    2. Turkish-specific characters
    3. German dialect patterns (Schwäbisch)
    4. Default to German
    """

    # Cyrillic character range for Russian detection
    CYRILLIC_PATTERN = re.compile(r'[\u0400-\u04FF]')

    # Turkish-specific characters not in German
    TURKISH_CHARS: Set[str] = set("şŞğĞıİçÇ")

    # Schwäbisch/Alemannic dialect patterns
    # These are distinctive markers that don't appear in standard German
    SCHWAEBISCH_PATTERNS = [
        # Diminutives with -le instead of -lein/-chen
        r'\b\w+le\b',  # häusle, mädle, bissle
        # Personal pronouns
        r'\bi\s+(?:hab|han|bin|gang|komm|mach|will|kann)',  # "i hab" instead of "ich habe"
        r'\bdu\s+hosch\b',  # "du hosch" instead of "du hast"
        # Negation
        r'\bnet\b',  # "net" instead of "nicht"
        r'\bnix\b',  # "nix" instead of "nichts"
        # Common words
        r'\bbissle\b',  # "bissle" instead of "bisschen"
        r'\bmädle\b',  # "mädle" instead of "Mädchen"
        r'\bhäusle\b',  # "häusle" instead of "Häuschen"
        r'\bgell\b',  # "gell?" confirmation particle
        r'\bgang\b',  # "gang" verb form
        r'\bgschwend\b',  # "gschwend" (quickly)
        r'\bschaffe\b',  # "schaffe" (work)
        r'\blaufe\b',  # "laufe" (walk/run)
        r'\bgugg\b',  # "gugg" (look)
        r'\bhock\b',  # "hock" (sit)
        # Phrases
        r'\bwo\s+bischt\b',  # "wo bischt" (where are you)
        r'\bdes\s+isch\b',  # "des isch" (das ist)
    ]

    # Compile patterns for efficiency
    SCHWAEBISCH_COMPILED = [re.compile(p, re.IGNORECASE) for p in SCHWAEBISCH_PATTERNS]

    # English detection patterns (common English words/phrases)
    ENGLISH_PATTERNS = [
        r'\b(?:hello|hi|hey)\b',
        r'\b(?:I have|I need|I want|I am|I\'m)\b',
        r'\b(?:please|thank you|thanks)\b',
        r'\b(?:power outage|no power|electricity|electrical)\b',
        r'\b(?:help|problem|issue|broken|repair)\b',
        r'\b(?:appointment|schedule|today|tomorrow)\b',
        r'\b(?:the|and|but|with|for|this|that)\b',
        r'\b(?:my|your|our|their)\b',
        r'\b(?:is|are|was|were|have|has)\b',
        r'\b(?:can|could|would|should)\b',
    ]

    # Compile English patterns
    ENGLISH_COMPILED = [re.compile(p, re.IGNORECASE) for p in ENGLISH_PATTERNS]

    # Minimum matches for English detection (need at least 2 to avoid false positives)
    MIN_ENGLISH_MATCHES = 2

    # Minimum matches for dialect detection (avoid false positives)
    MIN_DIALECT_MATCHES = 1

    # Confidence thresholds
    HIGH_CONFIDENCE = 0.9
    MEDIUM_CONFIDENCE = 0.7
    LOW_CONFIDENCE = 0.5

    def detect(self, text: str) -> LanguageDetectionResult:
        """Detect language from text.

        Args:
            text: Input text to analyze

        Returns:
            LanguageDetectionResult with detected language and metadata
        """
        if not text or not text.strip():
            return LanguageDetectionResult(
                language=DetectedLanguage.GERMAN,
                is_dialect=False,
                confidence=0.0,
            )

        text = text.strip()

        # Stage 1: Check for Cyrillic (Russian)
        cyrillic_count = len(self.CYRILLIC_PATTERN.findall(text))
        if cyrillic_count > 0:
            # Calculate confidence based on proportion of Cyrillic chars
            total_alpha = sum(1 for c in text if c.isalpha())
            confidence = min(cyrillic_count / max(total_alpha, 1) * 1.5, 1.0)
            return LanguageDetectionResult(
                language=DetectedLanguage.RUSSIAN,
                is_dialect=False,
                confidence=max(confidence, self.MEDIUM_CONFIDENCE),
            )

        # Stage 2: Check for Turkish-specific characters
        turkish_count = sum(1 for c in text if c in self.TURKISH_CHARS)
        if turkish_count > 0:
            confidence = min(turkish_count / len(text) * 10, 1.0)
            return LanguageDetectionResult(
                language=DetectedLanguage.TURKISH,
                is_dialect=False,
                confidence=max(confidence, self.MEDIUM_CONFIDENCE),
            )

        # Stage 3: Check for Schwäbisch/Alemannic dialect
        dialect_matches = sum(
            1 for pattern in self.SCHWAEBISCH_COMPILED
            if pattern.search(text)
        )
        if dialect_matches >= self.MIN_DIALECT_MATCHES:
            confidence = min(dialect_matches / 3, 1.0)
            return LanguageDetectionResult(
                language=DetectedLanguage.GERMAN,
                is_dialect=True,
                confidence=max(confidence, self.MEDIUM_CONFIDENCE),
                dialect_name="schwäbisch",
            )

        # Stage 4: Check for English patterns
        english_matches = sum(
            1 for pattern in self.ENGLISH_COMPILED
            if pattern.search(text)
        )
        if english_matches >= self.MIN_ENGLISH_MATCHES:
            confidence = min(english_matches / 5, 1.0)
            return LanguageDetectionResult(
                language=DetectedLanguage.ENGLISH,
                is_dialect=False,
                confidence=max(confidence, self.MEDIUM_CONFIDENCE),
            )

        # Stage 5: Default to German (most common case for this use case)
        return LanguageDetectionResult(
            language=DetectedLanguage.GERMAN,
            is_dialect=False,
            confidence=self.HIGH_CONFIDENCE,
        )

    def detect_with_language_code(self, text: str) -> tuple[str, bool, float]:
        """Convenience method returning language code, dialect flag, and confidence.

        Args:
            text: Input text to analyze

        Returns:
            Tuple of (language_code, is_dialect, confidence)
        """
        result = self.detect(text)
        return result.language.value, result.is_dialect, result.confidence

    def get_response_language(self, text: str) -> str:
        """Get the language code to use for responses.

        For dialects, returns standard German.

        Args:
            text: Input text to analyze

        Returns:
            Language code for response (de, ru, tr)
        """
        result = self.detect(text)
        return result.response_language.value


# Module-level instance for convenience
_detector: TextLanguageDetector | None = None


def get_text_language_detector() -> TextLanguageDetector:
    """Get or create the singleton detector instance."""
    global _detector
    if _detector is None:
        _detector = TextLanguageDetector()
    return _detector


def detect_language(text: str) -> LanguageDetectionResult:
    """Convenience function for language detection.

    Args:
        text: Input text to analyze

    Returns:
        LanguageDetectionResult
    """
    return get_text_language_detector().detect(text)


def get_response_language(text: str) -> str:
    """Get language code for responses.

    Args:
        text: Input text to analyze

    Returns:
        Language code (de, ru, tr)
    """
    return get_text_language_detector().get_response_language(text)
