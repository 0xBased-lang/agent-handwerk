"""AI Model Status Tracking.

Provides centralized status tracking for all AI models (STT, LLM, TTS).
Used by health checks and monitoring.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from phone_agent.ai.stt import SpeechToText
    from phone_agent.ai.llm import LanguageModel
    from phone_agent.ai.tts import TextToSpeech


class ModelStatus(str, Enum):
    """AI model status values."""

    NOT_LOADED = "not_loaded"
    LOADING = "loading"
    LOADED = "loaded"
    ERROR = "error"
    UNLOADING = "unloading"


@dataclass
class ModelInfo:
    """Information about a single AI model."""

    name: str
    status: ModelStatus = ModelStatus.NOT_LOADED
    model_path: str = ""
    loaded_at: datetime | None = None
    error_message: str | None = None
    memory_mb: float = 0.0

    def to_dict(self) -> dict:
        """Convert to dictionary for API responses."""
        return {
            "name": self.name,
            "status": self.status.value,
            "model_path": self.model_path,
            "loaded_at": self.loaded_at.isoformat() if self.loaded_at else None,
            "error_message": self.error_message,
            "memory_mb": self.memory_mb,
        }


@dataclass
class AIModelRegistry:
    """Registry for tracking AI model status.

    Singleton pattern - use get_model_registry() to access.
    """

    stt: ModelInfo = field(default_factory=lambda: ModelInfo(name="stt"))
    llm: ModelInfo = field(default_factory=lambda: ModelInfo(name="llm"))
    tts: ModelInfo = field(default_factory=lambda: ModelInfo(name="tts"))

    def register_stt(self, stt: SpeechToText) -> None:
        """Register STT model and track its status."""
        self.stt.model_path = str(stt.model_path / stt.model_name)
        if stt.is_loaded:
            self.stt.status = ModelStatus.LOADED
            self.stt.loaded_at = datetime.now(timezone.utc)
        else:
            self.stt.status = ModelStatus.NOT_LOADED

    def register_llm(self, llm: LanguageModel) -> None:
        """Register LLM model and track its status."""
        self.llm.model_path = str(llm.model_path / llm.model_name)
        if llm.is_loaded:
            self.llm.status = ModelStatus.LOADED
            self.llm.loaded_at = datetime.now(timezone.utc)
        else:
            self.llm.status = ModelStatus.NOT_LOADED

    def register_tts(self, tts: TextToSpeech) -> None:
        """Register TTS model and track its status."""
        self.tts.model_path = str(tts.model_path / tts.model_name)
        if tts.is_loaded:
            self.tts.status = ModelStatus.LOADED
            self.tts.loaded_at = datetime.now(timezone.utc)
        else:
            self.tts.status = ModelStatus.NOT_LOADED

    def update_status(self, model_name: str, status: ModelStatus, error: str | None = None) -> None:
        """Update status for a specific model."""
        model_info = getattr(self, model_name, None)
        if model_info:
            model_info.status = status
            model_info.error_message = error
            if status == ModelStatus.LOADED:
                model_info.loaded_at = datetime.now(timezone.utc)

    def get_overall_status(self) -> str:
        """Get overall AI status for health checks.

        Returns:
            "ok" - All models loaded
            "partial" - Some models loaded
            "not_loaded" - No models loaded
            "error" - Any model has error
        """
        models = [self.stt, self.llm, self.tts]

        # Check for errors first
        if any(m.status == ModelStatus.ERROR for m in models):
            return "error"

        loaded_count = sum(1 for m in models if m.status == ModelStatus.LOADED)

        if loaded_count == 3:
            return "ok"
        elif loaded_count > 0:
            return "partial"
        else:
            return "not_loaded"

    def get_detailed_status(self) -> dict:
        """Get detailed status for all models."""
        return {
            "overall": self.get_overall_status(),
            "models": {
                "stt": self.stt.to_dict(),
                "llm": self.llm.to_dict(),
                "tts": self.tts.to_dict(),
            }
        }

    def is_ready(self) -> bool:
        """Check if all models are ready for inference."""
        return all(
            m.status == ModelStatus.LOADED
            for m in [self.stt, self.llm, self.tts]
        )


# Singleton instance
_registry: AIModelRegistry | None = None


def get_model_registry() -> AIModelRegistry:
    """Get the singleton model registry instance."""
    global _registry
    if _registry is None:
        _registry = AIModelRegistry()
    return _registry


def reset_registry() -> None:
    """Reset the registry (for testing)."""
    global _registry
    _registry = None
