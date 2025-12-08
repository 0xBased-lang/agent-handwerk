"""Text-to-Speech using ElevenLabs API.

Cloud TTS provider with ultra-low latency (~75ms) and natural German voices.
Implements the same interface as local TextToSpeech for seamless switching.
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


# German voice options in ElevenLabs
# See: https://elevenlabs.io/voice-library
GERMAN_VOICES = {
    # Multilingual v2 voices with good German support
    "adam": "pNInz6obpgDQGcFmaJgB",  # Adam - deep male
    "antoni": "ErXwobaYiN019PkySvjV",  # Antoni - warm male
    "elli": "MF3mGyEYCl7XYWbV9V6O",  # Elli - young female
    "josh": "TxGEqnHWrfWFTfGW9XjX",  # Josh - deep male
    "rachel": "21m00Tcm4TlvDq8ikWAM",  # Rachel - calm female
    "domi": "AZnzlk1XvdvUeBnXmlld",  # Domi - confident female
    "bella": "EXAVITQu4vr4xnSDxMaL",  # Bella - soft female
    "callum": "N2lVS1w4EtoT3dr4eOWO",  # Callum - mature male
}

# Default voice for German
DEFAULT_VOICE_ID = "pNInz6obpgDQGcFmaJgB"  # Adam


class ElevenLabsTTS:
    """Text-to-Speech engine using ElevenLabs API.

    Uses ElevenLabs Flash model for ultra-low latency (~75ms).
    Compatible with local TextToSpeech interface.
    """

    def __init__(
        self,
        api_key: str,
        voice_id: str = DEFAULT_VOICE_ID,
        model: str = "eleven_flash_v2_5",
        sample_rate: int = 22050,
    ) -> None:
        """Initialize ElevenLabs TTS client.

        Args:
            api_key: ElevenLabs API key
            voice_id: Voice ID to use (see GERMAN_VOICES)
            model: Model name (eleven_flash_v2_5 for speed, eleven_multilingual_v2 for quality)
            sample_rate: Output audio sample rate
        """
        self.api_key = api_key
        self.voice_id = voice_id
        self.model = model
        self.sample_rate = sample_rate

        # Current language (for interface compatibility)
        self._current_language = "de"

        self._client: Any = None
        self._loaded = False

    def load(self, language: str | None = None) -> None:
        """Initialize the ElevenLabs client.

        Called lazily on first synthesis or explicitly for preloading.

        Args:
            language: Language code (ignored for ElevenLabs, voice handles language)
        """
        if self._loaded:
            return

        try:
            from elevenlabs import ElevenLabs

            log.info(
                "Initializing ElevenLabs client",
                model=self.model,
                voice_id=self.voice_id,
            )

            self._client = ElevenLabs(api_key=self.api_key)
            self._loaded = True

            if language:
                self._current_language = language

            log.info("ElevenLabs client initialized successfully")

        except ImportError:
            log.error("elevenlabs package not installed. Run: pip install elevenlabs")
            raise
        except Exception as e:
            log.error("Failed to initialize ElevenLabs client", error=str(e))
            raise

    def set_language(self, language: str) -> None:
        """Change the TTS language.

        Note: ElevenLabs uses the same voice for multiple languages.
        The voice will speak in the language of the input text.

        Args:
            language: Language code (de, tr, ru, en)
        """
        self._current_language = language
        log.debug("ElevenLabs language updated", language=language)

    def set_voice(self, voice_id: str) -> None:
        """Change the voice.

        Args:
            voice_id: Voice ID from GERMAN_VOICES or custom voice ID
        """
        self.voice_id = voice_id
        log.debug("ElevenLabs voice updated", voice_id=voice_id)

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
            language: Language code (ignored, voice auto-detects from text)

        Returns:
            Audio data as bytes
        """
        if not self._loaded:
            self.load(language)

        log.debug(
            "Synthesizing speech via ElevenLabs",
            text_length=len(text),
            voice_id=self.voice_id,
            model=self.model,
        )

        # Generate audio using ElevenLabs
        audio_generator = self._client.text_to_speech.convert(
            voice_id=self.voice_id,
            text=text,
            model_id=self.model,
            output_format="mp3_22050_32",  # ElevenLabs format
        )

        # Collect audio chunks
        audio_chunks = []
        for chunk in audio_generator:
            if chunk:
                audio_chunks.append(chunk)

        mp3_data = b"".join(audio_chunks)

        # Convert MP3 to WAV if needed
        if output_format == "wav":
            audio_data = self._mp3_to_wav(mp3_data)
        else:
            # For raw format, decode MP3 and return PCM
            audio_data = self._mp3_to_pcm(mp3_data)

        log.debug(
            "ElevenLabs synthesis complete",
            audio_size=len(audio_data),
            format=output_format,
        )

        return audio_data

    def _mp3_to_wav(self, mp3_data: bytes) -> bytes:
        """Convert MP3 audio to WAV format.

        Args:
            mp3_data: MP3 audio bytes

        Returns:
            WAV audio bytes
        """
        try:
            from pydub import AudioSegment

            # Load MP3 from bytes
            audio = AudioSegment.from_mp3(io.BytesIO(mp3_data))

            # Export as WAV
            buffer = io.BytesIO()
            audio.export(buffer, format="wav")
            return buffer.getvalue()

        except ImportError:
            log.warning(
                "pydub not installed, returning raw MP3. Install: pip install pydub"
            )
            return mp3_data

    def _mp3_to_pcm(self, mp3_data: bytes) -> bytes:
        """Convert MP3 audio to raw PCM format.

        Args:
            mp3_data: MP3 audio bytes

        Returns:
            Raw PCM audio bytes (16-bit, mono)
        """
        try:
            from pydub import AudioSegment

            # Load MP3 from bytes
            audio = AudioSegment.from_mp3(io.BytesIO(mp3_data))

            # Convert to mono, 16-bit, target sample rate
            audio = audio.set_channels(1)
            audio = audio.set_sample_width(2)
            audio = audio.set_frame_rate(self.sample_rate)

            return audio.raw_data

        except ImportError:
            log.warning(
                "pydub not installed, returning raw MP3. Install: pip install pydub"
            )
            return mp3_data

    def synthesize_to_array(
        self,
        text: str,
        language: str | None = None,
    ) -> np.ndarray:
        """Synthesize speech and return as numpy array.

        Args:
            text: Text to convert to speech
            language: Language code (ignored, voice auto-detects)

        Returns:
            Audio samples as float32 numpy array (-1 to 1)
        """
        # Get raw PCM data
        pcm_data = self.synthesize(text, output_format="raw", language=language)

        # Convert to numpy array
        audio = np.frombuffer(pcm_data, dtype=np.int16)

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
        """Unload the client to free resources."""
        if self._client is not None:
            self._client = None
            self._loaded = False
            log.info("ElevenLabs client unloaded")

    @property
    def is_loaded(self) -> bool:
        """Check if client is currently loaded."""
        return self._loaded

    @property
    def cached_voices(self) -> list[str]:
        """Get list of available voice IDs."""
        return list(GERMAN_VOICES.keys())

    def get_stats(self) -> dict[str, Any]:
        """Get TTS statistics.

        Returns:
            Dict with current state info
        """
        return {
            "voice_id": self.voice_id,
            "model": self.model,
            "current_language": self._current_language,
            "sample_rate": self.sample_rate,
            "loaded": self._loaded,
        }
