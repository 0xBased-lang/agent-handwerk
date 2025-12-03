"""Text-to-Speech using Piper TTS.

Supports multilingual speech synthesis with language-specific voices.
Optimized for Raspberry Pi 5 with low latency and natural-sounding output.

Supported languages and voices:
- German (de): de_DE-thorsten-medium
- Turkish (tr): tr_TR-dfki-medium
- Russian (ru): ru_RU-denis-medium
"""

from __future__ import annotations

import asyncio
import io
import wave
from functools import partial
from pathlib import Path
from typing import Any

import numpy as np
from itf_shared import get_logger

log = get_logger(__name__)


# Default voice models per language (Piper TTS)
VOICE_REGISTRY: dict[str, str] = {
    "de": "de_DE-thorsten-medium",
    "tr": "tr_TR-dfki-medium",
    "ru": "ru_RU-denis-medium",
    "en": "en_US-amy-medium",
}


def get_voice_for_language(language: str) -> str:
    """Get the default voice model for a language.

    Args:
        language: Language code (de, tr, ru, en)

    Returns:
        Piper voice model name
    """
    return VOICE_REGISTRY.get(language, VOICE_REGISTRY["de"])


class TextToSpeech:
    """Text-to-Speech engine using Piper TTS.

    Supports multilingual speech synthesis with language-specific voices.
    Optimized for low-latency generation on Raspberry Pi 5.

    Features LRU caching for voice models to avoid reloading on language switch.
    """

    def __init__(
        self,
        model: str = "de_DE-thorsten-medium",
        model_path: str | Path = "models/tts",
        speaker_id: int = 0,
        sample_rate: int = 22050,
        voices: dict[str, str] | None = None,
        max_cached_voices: int = 2,
    ) -> None:
        """Initialize TTS engine.

        Args:
            model: Default Piper voice model name
            model_path: Directory containing model files
            speaker_id: Speaker ID for multi-speaker models
            sample_rate: Output audio sample rate
            voices: Language-to-voice mapping (optional)
            max_cached_voices: Maximum voice models to keep loaded (LRU eviction)
        """
        self.model_name = model
        self.model_path = Path(model_path)
        self.speaker_id = speaker_id
        self.sample_rate = sample_rate
        self.voices = voices or VOICE_REGISTRY.copy()
        self.max_cached_voices = max_cached_voices

        # Current language
        self._current_language = "de"

        # LRU voice cache: model_name → PiperVoice instance
        self._voice_cache: dict[str, Any] = {}
        self._voice_usage: list[str] = []  # LRU order (most recent last)

        # Legacy compatibility
        self._voice: Any = None
        self._loaded = False
        self._loaded_model: str | None = None

    def _get_or_load_voice(self, model_name: str) -> Any:
        """Get voice from cache or load it with LRU eviction.

        Args:
            model_name: Piper voice model name

        Returns:
            Loaded PiperVoice instance
        """
        # Check cache
        if model_name in self._voice_cache:
            # Update LRU order
            if model_name in self._voice_usage:
                self._voice_usage.remove(model_name)
            self._voice_usage.append(model_name)
            return self._voice_cache[model_name]

        # Evict oldest voice if at capacity
        while len(self._voice_cache) >= self.max_cached_voices:
            oldest = self._voice_usage.pop(0)
            log.info("Evicting TTS voice (LRU)", model=oldest)
            del self._voice_cache[oldest]

        # Load new voice
        from piper import PiperVoice

        model_file = self.model_path / f"{model_name}.onnx"
        config_file = self.model_path / f"{model_name}.onnx.json"

        if not model_file.exists():
            log.info(
                "TTS model not found locally, will attempt download",
                model=model_name,
            )
            model_file = model_name

        log.info(
            "Loading TTS model",
            model=model_name,
            sample_rate=self.sample_rate,
        )

        voice = PiperVoice.load(
            str(model_file),
            config_path=str(config_file) if config_file.exists() else None,
        )

        # Cache and track
        self._voice_cache[model_name] = voice
        self._voice_usage.append(model_name)

        log.info("TTS model loaded successfully", model=model_name)
        return voice

    def load(self, language: str | None = None) -> None:
        """Load the TTS model for a specific language.

        Called lazily on first synthesis or explicitly for preloading.

        Args:
            language: Language code (de, tr, ru) or None for default
        """
        target_language = language or self._current_language
        target_model = self.voices.get(target_language, self.model_name)

        try:
            voice = self._get_or_load_voice(target_model)

            # Update current state
            self._voice = voice
            self._loaded = True
            self._loaded_model = target_model
            self._current_language = target_language

        except ImportError:
            log.error("piper-tts not installed")
            raise
        except Exception as e:
            log.error(
                "Failed to load TTS model",
                error=str(e),
                model=target_model,
                language=target_language,
            )
            raise

    def set_language(self, language: str) -> None:
        """Change the TTS language/voice.

        This will load the appropriate voice model for the language.

        Args:
            language: Language code (de, tr, ru, en)
        """
        if language not in self.voices:
            log.warning(
                "Unsupported language for TTS, using German",
                requested=language,
                supported=list(self.voices.keys()),
            )
            language = "de"

        if language != self._current_language:
            log.debug(
                "Switching TTS language",
                from_lang=self._current_language,
                to_lang=language,
            )
            self._current_language = language
            # Will load on next synthesis

    def synthesize(
        self,
        text: str,
        output_format: str = "wav",
        language: str | None = None,
    ) -> bytes:
        """Synthesize speech from text.

        Args:
            text: Text to convert to speech
            output_format: Output format (wav, raw)
            language: Language code (de, tr, ru) or None for current language

        Returns:
            Audio data as bytes
        """
        # Load model for requested language
        target_lang = language or self._current_language
        self.load(target_lang)

        log.debug("Synthesizing speech", text_length=len(text))

        # Generate audio
        audio_buffer = io.BytesIO()

        if output_format == "wav":
            # Write WAV format
            with wave.open(audio_buffer, "wb") as wav_file:
                wav_file.setnchannels(1)
                wav_file.setsampwidth(2)  # 16-bit
                wav_file.setframerate(self.sample_rate)

                for audio_bytes in self._voice.synthesize_stream_raw(text):
                    wav_file.writeframes(audio_bytes)
        else:
            # Write raw PCM
            for audio_bytes in self._voice.synthesize_stream_raw(text):
                audio_buffer.write(audio_bytes)

        audio_data = audio_buffer.getvalue()

        log.debug(
            "Synthesis complete",
            audio_size=len(audio_data),
            format=output_format,
        )

        return audio_data

    def synthesize_to_array(
        self,
        text: str,
        language: str | None = None,
    ) -> np.ndarray:
        """Synthesize speech and return as numpy array.

        Args:
            text: Text to convert to speech
            language: Language code (de, tr, ru) or None for current language

        Returns:
            Audio samples as float32 numpy array (-1 to 1)
        """
        # Load model for requested language
        target_lang = language or self._current_language
        self.load(target_lang)

        # Collect raw audio chunks
        audio_chunks = []
        for audio_bytes in self._voice.synthesize_stream_raw(text):
            # Convert bytes to int16 array
            chunk = np.frombuffer(audio_bytes, dtype=np.int16)
            audio_chunks.append(chunk)

        # Combine chunks
        audio = np.concatenate(audio_chunks)

        # Convert to float32 normalized
        audio = audio.astype(np.float32) / 32768.0

        return audio

    async def synthesize_async(
        self,
        text: str,
        output_format: str = "wav",
        language: str | None = None,
    ) -> bytes:
        """Async wrapper for synthesis.

        Runs synthesis in a thread pool to avoid blocking.
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            partial(self.synthesize, text, output_format, language),
        )

    def unload(self) -> None:
        """Unload all cached voice models to free memory."""
        # Clear voice cache
        for model_name in list(self._voice_cache.keys()):
            log.debug("Unloading TTS voice", model=model_name)
            del self._voice_cache[model_name]

        self._voice_cache.clear()
        self._voice_usage.clear()

        # Clear current voice reference
        self._voice = None
        self._loaded = False
        self._loaded_model = None

        log.info("All TTS models unloaded")

    def preload_voice(self, language: str) -> None:
        """Preload a voice model for a language.

        Args:
            language: Language code to preload
        """
        model_name = self.voices.get(language, self.model_name)
        self._get_or_load_voice(model_name)

    def preload_voices(self, languages: list[str]) -> None:
        """Preload voice models for multiple languages.

        Args:
            languages: List of language codes to preload
        """
        for language in languages:
            self.preload_voice(language)

    @property
    def cached_voices(self) -> list[str]:
        """Get list of currently cached voice models."""
        return list(self._voice_cache.keys())

    @property
    def is_loaded(self) -> bool:
        """Check if any model is currently loaded."""
        return self._loaded or len(self._voice_cache) > 0

    def get_stats(self) -> dict[str, Any]:
        """Get TTS cache statistics.

        Returns:
            Dict with cache info and current state
        """
        return {
            "cached_voices": self.cached_voices,
            "cache_size": len(self._voice_cache),
            "max_cache_size": self.max_cached_voices,
            "current_language": self._current_language,
            "current_model": self._loaded_model,
        }


# Utility functions for audio playback
def play_audio(audio_data: bytes, sample_rate: int = 22050) -> None:
    """Play audio through the default output device.

    Args:
        audio_data: WAV audio data
        sample_rate: Audio sample rate
    """
    try:
        import sounddevice as sd

        # Parse WAV data
        with io.BytesIO(audio_data) as f:
            with wave.open(f, "rb") as wav:
                frames = wav.readframes(wav.getnframes())
                audio = np.frombuffer(frames, dtype=np.int16)
                audio = audio.astype(np.float32) / 32768.0

        sd.play(audio, sample_rate)
        sd.wait()

    except ImportError:
        log.error("sounddevice not installed")
        raise
    except Exception as e:
        log.error("Failed to play audio", error=str(e))
        raise
