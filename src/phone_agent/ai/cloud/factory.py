"""AI Provider Factory.

Factory pattern for creating AI providers (STT, LLM, TTS).
Supports seamless switching between local and cloud providers.

Usage:
    from phone_agent.ai.cloud.factory import AIFactory

    # Create with settings
    factory = AIFactory(settings)

    # Get providers
    stt = factory.create_stt()
    llm = factory.create_llm()
    tts = factory.create_tts()

    # Or get all at once
    stt, llm, tts = factory.create_all()
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Protocol, runtime_checkable

from itf_shared import get_logger

log = get_logger(__name__)


class AIProvider(str, Enum):
    """AI provider type."""
    LOCAL = "local"
    CLOUD = "cloud"
    HYBRID = "hybrid"  # Local STT/TTS, cloud LLM


@dataclass
class CloudAIConfig:
    """Configuration for cloud AI providers."""
    enabled: bool = False
    provider: AIProvider = AIProvider.LOCAL

    # Groq LLM
    groq_api_key: str = ""
    groq_model: str = "llama-3.3-70b-versatile"

    # Deepgram STT
    deepgram_api_key: str = ""
    deepgram_model: str = "nova-2"

    # ElevenLabs TTS
    elevenlabs_api_key: str = ""
    elevenlabs_voice_id: str = "pNInz6obpgDQGcFmaJgB"  # Adam
    elevenlabs_model: str = "eleven_flash_v2_5"

    # Fallback settings
    fallback_to_local: bool = True


@runtime_checkable
class STTProtocol(Protocol):
    """Protocol for Speech-to-Text providers."""

    def transcribe(self, audio: Any, sample_rate: int = 16000) -> str:
        ...

    async def transcribe_async(self, audio: Any, sample_rate: int = 16000) -> str:
        ...

    def load(self) -> None:
        ...

    @property
    def is_loaded(self) -> bool:
        ...


@runtime_checkable
class LLMProtocol(Protocol):
    """Protocol for Language Model providers."""

    def generate(
        self,
        prompt: str,
        system_prompt: str | None = None,
    ) -> str:
        ...

    async def generate_async(
        self,
        prompt: str,
        system_prompt: str | None = None,
    ) -> str:
        ...

    def generate_with_history(
        self,
        messages: list[dict[str, str]],
    ) -> str:
        ...

    def load(self) -> None:
        ...

    @property
    def is_loaded(self) -> bool:
        ...


@runtime_checkable
class TTSProtocol(Protocol):
    """Protocol for Text-to-Speech providers."""

    def synthesize(
        self,
        text: str,
        output_format: str = "wav",
    ) -> bytes:
        ...

    async def synthesize_async(
        self,
        text: str,
        output_format: str = "wav",
    ) -> bytes:
        ...

    def load(self) -> None:
        ...

    @property
    def is_loaded(self) -> bool:
        ...


class AIFactory:
    """Factory for creating AI providers.

    Supports local, cloud, and hybrid configurations.
    """

    def __init__(self, config: CloudAIConfig | None = None):
        """Initialize the factory.

        Args:
            config: Cloud AI configuration. If None, uses local providers.
        """
        self.config = config or CloudAIConfig()

        # Cache created instances
        self._stt: STTProtocol | None = None
        self._llm: LLMProtocol | None = None
        self._tts: TTSProtocol | None = None

    def create_stt(self, force_local: bool = False) -> STTProtocol:
        """Create Speech-to-Text provider.

        Args:
            force_local: Force use of local provider

        Returns:
            STT provider instance
        """
        if self._stt is not None:
            return self._stt

        use_cloud = (
            self.config.enabled
            and self.config.provider in (AIProvider.CLOUD,)
            and self.config.deepgram_api_key
            and not force_local
        )

        if use_cloud:
            try:
                from phone_agent.ai.cloud.deepgram_client import DeepgramSTT

                log.info("Creating cloud STT (Deepgram)", model=self.config.deepgram_model)
                self._stt = DeepgramSTT(
                    api_key=self.config.deepgram_api_key,
                    model=self.config.deepgram_model,
                    language="de",
                )
                return self._stt
            except Exception as e:
                log.warning("Failed to create cloud STT, falling back to local", error=str(e))
                if not self.config.fallback_to_local:
                    raise

        # Local provider
        from phone_agent.ai.stt import SpeechToText

        log.info("Creating local STT (Whisper)")
        self._stt = SpeechToText(language="de")
        return self._stt

    def create_llm(self, force_local: bool = False) -> LLMProtocol:
        """Create Language Model provider.

        Args:
            force_local: Force use of local provider

        Returns:
            LLM provider instance
        """
        if self._llm is not None:
            return self._llm

        use_cloud = (
            self.config.enabled
            and self.config.provider in (AIProvider.CLOUD, AIProvider.HYBRID)
            and self.config.groq_api_key
            and not force_local
        )

        if use_cloud:
            try:
                from phone_agent.ai.cloud.groq_client import GroqLanguageModel

                log.info("Creating cloud LLM (Groq)", model=self.config.groq_model)
                self._llm = GroqLanguageModel(
                    api_key=self.config.groq_api_key,
                    model=self.config.groq_model,
                )
                return self._llm
            except Exception as e:
                log.warning("Failed to create cloud LLM, falling back to local", error=str(e))
                if not self.config.fallback_to_local:
                    raise

        # Local provider
        from phone_agent.ai.llm import LanguageModel

        log.info("Creating local LLM (Llama)")
        self._llm = LanguageModel()
        return self._llm

    def create_tts(self, force_local: bool = False) -> TTSProtocol:
        """Create Text-to-Speech provider.

        Args:
            force_local: Force use of local provider

        Returns:
            TTS provider instance
        """
        if self._tts is not None:
            return self._tts

        use_cloud = (
            self.config.enabled
            and self.config.provider in (AIProvider.CLOUD,)
            and self.config.elevenlabs_api_key
            and not force_local
        )

        if use_cloud:
            try:
                from phone_agent.ai.cloud.elevenlabs_client import ElevenLabsTTS

                log.info(
                    "Creating cloud TTS (ElevenLabs)",
                    model=self.config.elevenlabs_model,
                    voice=self.config.elevenlabs_voice_id,
                )
                self._tts = ElevenLabsTTS(
                    api_key=self.config.elevenlabs_api_key,
                    voice_id=self.config.elevenlabs_voice_id,
                    model=self.config.elevenlabs_model,
                )
                return self._tts
            except Exception as e:
                log.warning("Failed to create cloud TTS, falling back to local", error=str(e))
                if not self.config.fallback_to_local:
                    raise

        # Local provider
        from phone_agent.ai.tts import TextToSpeech

        log.info("Creating local TTS (Piper)")
        self._tts = TextToSpeech()
        return self._tts

    def create_all(
        self,
        force_local: bool = False,
    ) -> tuple[STTProtocol, LLMProtocol, TTSProtocol]:
        """Create all AI providers.

        Args:
            force_local: Force use of local providers

        Returns:
            Tuple of (STT, LLM, TTS) providers
        """
        stt = self.create_stt(force_local=force_local)
        llm = self.create_llm(force_local=force_local)
        tts = self.create_tts(force_local=force_local)
        return stt, llm, tts

    def preload_all(self) -> None:
        """Preload all AI models."""
        stt, llm, tts = self.create_all()

        log.info("Preloading AI models...")

        if hasattr(stt, "load"):
            stt.load()
        if hasattr(llm, "load"):
            llm.load()
        if hasattr(tts, "load"):
            tts.load()

        log.info("All AI models preloaded")

    def get_status(self) -> dict[str, Any]:
        """Get status of AI providers.

        Returns:
            Dict with provider status info
        """
        return {
            "config": {
                "enabled": self.config.enabled,
                "provider": self.config.provider.value,
                "fallback_to_local": self.config.fallback_to_local,
            },
            "stt": {
                "type": type(self._stt).__name__ if self._stt else None,
                "loaded": self._stt.is_loaded if self._stt else False,
            },
            "llm": {
                "type": type(self._llm).__name__ if self._llm else None,
                "loaded": self._llm.is_loaded if self._llm else False,
            },
            "tts": {
                "type": type(self._tts).__name__ if self._tts else None,
                "loaded": self._tts.is_loaded if self._tts else False,
            },
        }


def create_ai_factory_from_env() -> AIFactory:
    """Create AI factory from environment variables.

    Environment variables:
        ITF_AI_CLOUD_ENABLED: Enable cloud AI (true/false)
        ITF_AI_CLOUD_PROVIDER: Provider type (local/cloud/hybrid)
        GROQ_API_KEY: Groq API key
        DEEPGRAM_API_KEY: Deepgram API key
        ELEVENLABS_API_KEY: ElevenLabs API key

    Returns:
        Configured AIFactory instance
    """
    import os

    enabled = os.environ.get("ITF_AI_CLOUD_ENABLED", "false").lower() == "true"
    provider_str = os.environ.get("ITF_AI_CLOUD_PROVIDER", "local").lower()

    provider = {
        "local": AIProvider.LOCAL,
        "cloud": AIProvider.CLOUD,
        "hybrid": AIProvider.HYBRID,
    }.get(provider_str, AIProvider.LOCAL)

    config = CloudAIConfig(
        enabled=enabled,
        provider=provider,
        groq_api_key=os.environ.get("GROQ_API_KEY", ""),
        deepgram_api_key=os.environ.get("DEEPGRAM_API_KEY", ""),
        elevenlabs_api_key=os.environ.get("ELEVENLABS_API_KEY", ""),
    )

    return AIFactory(config)


# Convenience function for quick setup
def get_cloud_pipeline(
    groq_key: str | None = None,
    deepgram_key: str | None = None,
    elevenlabs_key: str | None = None,
) -> tuple[STTProtocol, LLMProtocol, TTSProtocol]:
    """Get a cloud AI pipeline.

    Args:
        groq_key: Groq API key (or from env)
        deepgram_key: Deepgram API key (or from env)
        elevenlabs_key: ElevenLabs API key (or from env)

    Returns:
        Tuple of (STT, LLM, TTS) cloud providers
    """
    import os

    config = CloudAIConfig(
        enabled=True,
        provider=AIProvider.CLOUD,
        groq_api_key=groq_key or os.environ.get("GROQ_API_KEY", ""),
        deepgram_api_key=deepgram_key or os.environ.get("DEEPGRAM_API_KEY", ""),
        elevenlabs_api_key=elevenlabs_key or os.environ.get("ELEVENLABS_API_KEY", ""),
    )

    factory = AIFactory(config)
    return factory.create_all()
