"""AI components for speech and language processing."""

from phone_agent.ai.stt import SpeechToText, TranscriptionResult, SUPPORTED_LANGUAGES
from phone_agent.ai.llm import LanguageModel
from phone_agent.ai.tts import TextToSpeech
from phone_agent.ai.language_detector import (
    LanguageDetector,
    LanguageDetectionResult,
    detect_language_from_greeting,
)
from phone_agent.ai.dialect_detector import (
    GermanDialectDetector,
    DialectResult,
    detect_german_dialect,
    get_model_for_dialect,
    DIALECT_MODELS,
)
from phone_agent.ai.stt_router import DialectAwareSTT
from phone_agent.ai.status import (
    AIModelRegistry,
    ModelInfo,
    ModelStatus,
    get_model_registry,
    reset_registry,
)
from phone_agent.ai.vad import (
    BaseVAD,
    SimpleVAD,
    SileroVAD,
    VADSegment,
    VADFrame,
    VADFactory,
    get_vad,
)

__all__ = [
    # STT
    "SpeechToText",
    "TranscriptionResult",
    "SUPPORTED_LANGUAGES",
    # Dialect-Aware STT
    "DialectAwareSTT",
    "GermanDialectDetector",
    "DialectResult",
    "detect_german_dialect",
    "get_model_for_dialect",
    "DIALECT_MODELS",
    # LLM
    "LanguageModel",
    # TTS
    "TextToSpeech",
    # Language Detection
    "LanguageDetector",
    "LanguageDetectionResult",
    "detect_language_from_greeting",
    # Model Registry
    "AIModelRegistry",
    "ModelInfo",
    "ModelStatus",
    "get_model_registry",
    "reset_registry",
    # Voice Activity Detection
    "BaseVAD",
    "SimpleVAD",
    "SileroVAD",
    "VADSegment",
    "VADFrame",
    "VADFactory",
    "get_vad",
]
