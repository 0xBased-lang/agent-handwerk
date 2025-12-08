"""Cloud AI providers for speech and language processing.

Provides cloud-based alternatives to local AI models:
- Groq: Fast LLM inference with Llama 3.1
- Deepgram: Speech-to-text with excellent German support
- ElevenLabs: High-quality text-to-speech

All clients implement the same interfaces as local providers for seamless switching.

Usage:
    # Direct usage
    from phone_agent.ai.cloud import GroqLanguageModel, DeepgramSTT, ElevenLabsTTS

    # Factory pattern (recommended)
    from phone_agent.ai.cloud import AIFactory, CloudAIConfig, AIProvider

    config = CloudAIConfig(enabled=True, provider=AIProvider.CLOUD, ...)
    factory = AIFactory(config)
    stt, llm, tts = factory.create_all()
"""

from phone_agent.ai.cloud.groq_client import GroqLanguageModel
from phone_agent.ai.cloud.deepgram_client import DeepgramSTT, DeepgramTranscriptionResult
from phone_agent.ai.cloud.elevenlabs_client import ElevenLabsTTS
from phone_agent.ai.cloud.factory import (
    AIFactory,
    AIProvider,
    CloudAIConfig,
    create_ai_factory_from_env,
    get_cloud_pipeline,
)

__all__ = [
    # Clients
    "GroqLanguageModel",
    "DeepgramSTT",
    "DeepgramTranscriptionResult",
    "ElevenLabsTTS",
    # Factory
    "AIFactory",
    "AIProvider",
    "CloudAIConfig",
    "create_ai_factory_from_env",
    "get_cloud_pipeline",
]
