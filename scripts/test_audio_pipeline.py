#!/usr/bin/env python3
"""Test complete audio pipeline: STT → LLM → TTS.

End-to-end test of cloud AI providers with real audio.

Usage:
    export GROQ_API_KEY=your_key
    export DEEPGRAM_API_KEY=your_key
    export ELEVENLABS_API_KEY=your_key

    # Record and process audio
    python scripts/test_audio_pipeline.py --record 5

    # Process existing audio file
    python scripts/test_audio_pipeline.py --input audio.wav

    # Full pipeline with output
    python scripts/test_audio_pipeline.py --record 5 --output response.wav

    # Continuous conversation mode
    python scripts/test_audio_pipeline.py --continuous
"""

from __future__ import annotations

import argparse
import io
import os
import sys
import time
import wave
from pathlib import Path

import numpy as np

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


class AudioPipeline:
    """Complete audio processing pipeline using cloud providers."""

    def __init__(
        self,
        groq_key: str,
        deepgram_key: str,
        elevenlabs_key: str,
        verbose: bool = True,
    ):
        self.verbose = verbose
        self.sample_rate = 16000  # For STT
        self.tts_sample_rate = 22050  # For TTS output

        # Initialize clients lazily
        self._stt = None
        self._llm = None
        self._tts = None

        self._groq_key = groq_key
        self._deepgram_key = deepgram_key
        self._elevenlabs_key = elevenlabs_key

        # Conversation history
        self.messages = []
        self.system_prompt = None

    def _log(self, msg: str):
        if self.verbose:
            print(msg)

    def initialize(self):
        """Initialize all AI clients."""
        from phone_agent.ai.cloud.groq_client import GroqLanguageModel
        from phone_agent.ai.cloud.deepgram_client import DeepgramSTT
        from phone_agent.ai.cloud.elevenlabs_client import ElevenLabsTTS
        from phone_agent.industry.handwerk.prompts import SYSTEM_PROMPT

        self._log("Initializing cloud AI pipeline...")

        # STT
        self._log("  - Deepgram STT...")
        self._stt = DeepgramSTT(api_key=self._deepgram_key, language="de")
        self._stt.load()

        # LLM
        self._log("  - Groq LLM...")
        self._llm = GroqLanguageModel(
            api_key=self._groq_key,
            model="llama-3.3-70b-versatile",
        )
        self._llm.load()

        # TTS
        self._log("  - ElevenLabs TTS...")
        self._tts = ElevenLabsTTS(api_key=self._elevenlabs_key)
        self._tts.load()

        # Set system prompt
        self.system_prompt = SYSTEM_PROMPT
        self.messages = [{"role": "system", "content": SYSTEM_PROMPT}]

        self._log("Pipeline ready!\n")

    def record_audio(self, duration: float) -> np.ndarray:
        """Record audio from microphone.

        Args:
            duration: Recording duration in seconds

        Returns:
            Audio samples as numpy array
        """
        import sounddevice as sd

        self._log(f"Recording {duration}s... (speak in German)")

        audio = sd.rec(
            int(duration * self.sample_rate),
            samplerate=self.sample_rate,
            channels=1,
            dtype=np.float32,
        )
        sd.wait()
        audio = audio.flatten()

        self._log(f"Recording complete. Duration: {len(audio) / self.sample_rate:.2f}s")
        return audio

    def load_audio(self, file_path: str) -> np.ndarray:
        """Load audio from file.

        Args:
            file_path: Path to WAV file

        Returns:
            Audio samples as numpy array
        """
        import scipy.io.wavfile as wavfile

        self._log(f"Loading audio from {file_path}...")

        sample_rate, audio = wavfile.read(file_path)

        # Convert to float32
        if audio.dtype == np.int16:
            audio = audio.astype(np.float32) / 32768.0
        elif audio.dtype == np.int32:
            audio = audio.astype(np.float32) / 2147483648.0

        # Convert stereo to mono
        if len(audio.shape) > 1:
            audio = audio.mean(axis=1)

        # Resample if needed
        if sample_rate != self.sample_rate:
            from scipy import signal
            samples = int(len(audio) * self.sample_rate / sample_rate)
            audio = signal.resample(audio, samples)

        self._log(f"Loaded {len(audio) / self.sample_rate:.2f}s of audio")
        return audio

    def transcribe(self, audio: np.ndarray) -> str:
        """Transcribe audio to text.

        Args:
            audio: Audio samples

        Returns:
            Transcribed text
        """
        self._log("Transcribing...")
        start = time.time()

        result = self._stt.transcribe_with_info(audio, self.sample_rate)

        latency = (time.time() - start) * 1000
        self._log(f"  Transcript: \"{result.text}\"")
        self._log(f"  Confidence: {result.language_probability:.0%}")
        self._log(f"  Latency: {latency:.0f}ms")

        return result.text

    def generate_response(self, text: str) -> str:
        """Generate LLM response.

        Args:
            text: User input text

        Returns:
            Assistant response text
        """
        self._log("Generating response...")
        start = time.time()

        # Add user message to history
        self.messages.append({"role": "user", "content": text})

        # Generate response
        response = self._llm.generate_with_history(self.messages)

        # Add to history
        self.messages.append({"role": "assistant", "content": response})

        latency = (time.time() - start) * 1000
        self._log(f"  Response: \"{response}\"")
        self._log(f"  Latency: {latency:.0f}ms")

        return response

    def synthesize(self, text: str) -> bytes:
        """Synthesize speech from text.

        Args:
            text: Text to speak

        Returns:
            WAV audio bytes
        """
        self._log("Synthesizing speech...")
        start = time.time()

        audio_data = self._tts.synthesize(text, output_format="wav")

        latency = (time.time() - start) * 1000
        self._log(f"  Audio size: {len(audio_data)} bytes")
        self._log(f"  Latency: {latency:.0f}ms")

        return audio_data

    def play_audio(self, audio_data: bytes):
        """Play audio through speakers.

        Args:
            audio_data: Audio bytes (WAV or MP3)
        """
        import subprocess
        import tempfile
        import platform

        # Check if it's WAV or MP3
        is_wav = audio_data[:4] == b'RIFF'
        ext = ".wav" if is_wav else ".mp3"

        # Save to temp file and play with system player
        with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as f:
            f.write(audio_data)
            temp_path = f.name

        try:
            self._log("Playing response...")
            if platform.system() == "Darwin":  # macOS
                subprocess.run(["afplay", temp_path], check=True)
            elif platform.system() == "Linux":
                subprocess.run(["aplay", temp_path] if is_wav else ["mpg123", temp_path], check=True)
            else:  # Windows
                import os
                os.startfile(temp_path)
            self._log("Playback complete.")
        finally:
            import os
            os.unlink(temp_path)

    def save_audio(self, audio_data: bytes, file_path: str):
        """Save audio to file.

        Args:
            audio_data: WAV audio bytes
            file_path: Output file path
        """
        with open(file_path, "wb") as f:
            f.write(audio_data)
        self._log(f"Saved to: {file_path}")

    def process(
        self,
        audio: np.ndarray,
        play: bool = True,
        output_file: str | None = None,
    ) -> tuple[str, str, bytes]:
        """Process audio through complete pipeline.

        Args:
            audio: Input audio samples
            play: Play response audio
            output_file: Save response to file

        Returns:
            Tuple of (transcript, response_text, response_audio)
        """
        print("\n" + "=" * 60)
        print("AUDIO PIPELINE PROCESSING")
        print("=" * 60)

        total_start = time.time()

        # Step 1: Transcribe
        print("\n[1/3] SPEECH-TO-TEXT (Deepgram)")
        print("-" * 40)
        transcript = self.transcribe(audio)

        if not transcript.strip():
            print("\n[WARN] No speech detected!")
            return "", "", b""

        # Step 2: Generate response
        print("\n[2/3] LLM RESPONSE (Groq)")
        print("-" * 40)
        response_text = self.generate_response(transcript)

        # Step 3: Synthesize
        print("\n[3/3] TEXT-TO-SPEECH (ElevenLabs)")
        print("-" * 40)
        response_audio = self.synthesize(response_text)

        # Total latency
        total_latency = (time.time() - total_start) * 1000
        print("\n" + "=" * 60)
        print(f"TOTAL PIPELINE LATENCY: {total_latency:.0f}ms")
        print("=" * 60)

        # Play audio
        if play and response_audio:
            print()
            self.play_audio(response_audio)

        # Save to file
        if output_file and response_audio:
            self.save_audio(response_audio, output_file)

        return transcript, response_text, response_audio

    def continuous_mode(self, record_duration: float = 5.0):
        """Run continuous conversation mode.

        Args:
            record_duration: Duration for each recording
        """
        print("\n" + "=" * 60)
        print("CONTINUOUS CONVERSATION MODE")
        print("=" * 60)
        print("\nPress Enter to record, 'q' to quit.")
        print(f"Each recording is {record_duration}s.\n")

        # Generate initial greeting
        print("Generating greeting...")
        greeting = self._llm.generate(
            "Der Anrufer hat gerade angerufen. Begrüße ihn kurz.",
            system_prompt=self.system_prompt,
        )
        self.messages.append({"role": "assistant", "content": greeting})

        greeting_audio = self.synthesize(greeting)
        print(f"\n[Assistant]: {greeting}\n")
        self.play_audio(greeting_audio)

        while True:
            try:
                user_input = input("\n[Press Enter to speak, 'q' to quit]: ").strip()
            except (KeyboardInterrupt, EOFError):
                print("\n\nAuf Wiederhören!")
                break

            if user_input.lower() in ("q", "quit", "exit"):
                print("\nAuf Wiederhören!")
                break

            # Record
            audio = self.record_audio(record_duration)

            # Process
            transcript, response_text, response_audio = self.process(
                audio, play=True, output_file=None
            )

            if not transcript:
                print("(No speech detected, try again)")


def main():
    parser = argparse.ArgumentParser(
        description="Test complete audio pipeline: STT → LLM → TTS"
    )

    # Input options
    input_group = parser.add_mutually_exclusive_group()
    input_group.add_argument(
        "--record",
        type=float,
        metavar="SECONDS",
        help="Record audio from microphone",
    )
    input_group.add_argument(
        "--input",
        type=str,
        metavar="FILE",
        help="Load audio from WAV file",
    )
    input_group.add_argument(
        "--continuous",
        action="store_true",
        help="Continuous conversation mode",
    )

    # Output options
    parser.add_argument(
        "--output",
        type=str,
        metavar="FILE",
        help="Save response audio to file",
    )
    parser.add_argument(
        "--no-play",
        action="store_true",
        help="Don't play response audio",
    )

    # API keys
    parser.add_argument(
        "--groq-key",
        default=os.environ.get("GROQ_API_KEY"),
        help="Groq API key",
    )
    parser.add_argument(
        "--deepgram-key",
        default=os.environ.get("DEEPGRAM_API_KEY"),
        help="Deepgram API key",
    )
    parser.add_argument(
        "--elevenlabs-key",
        default=os.environ.get("ELEVENLABS_API_KEY"),
        help="ElevenLabs API key",
    )

    parser.add_argument(
        "-q", "--quiet",
        action="store_true",
        help="Minimal output",
    )

    args = parser.parse_args()

    # Validate API keys
    missing_keys = []
    if not args.groq_key:
        missing_keys.append("GROQ_API_KEY")
    if not args.deepgram_key:
        missing_keys.append("DEEPGRAM_API_KEY")
    if not args.elevenlabs_key:
        missing_keys.append("ELEVENLABS_API_KEY")

    if missing_keys:
        print("Error: Missing API keys:")
        for key in missing_keys:
            print(f"  - {key}")
        print("\nGet free API keys at:")
        print("  - Groq: https://console.groq.com/")
        print("  - Deepgram: https://console.deepgram.com/")
        print("  - ElevenLabs: https://elevenlabs.io/")
        sys.exit(1)

    # Default to recording if no input specified
    if not args.record and not args.input and not args.continuous:
        args.record = 5.0

    # Create pipeline
    pipeline = AudioPipeline(
        groq_key=args.groq_key,
        deepgram_key=args.deepgram_key,
        elevenlabs_key=args.elevenlabs_key,
        verbose=not args.quiet,
    )

    try:
        pipeline.initialize()
    except Exception as e:
        print(f"Error initializing pipeline: {e}")
        sys.exit(1)

    # Run appropriate mode
    if args.continuous:
        pipeline.continuous_mode(record_duration=5.0)
    else:
        # Get audio
        if args.record:
            audio = pipeline.record_audio(args.record)
        else:
            audio = pipeline.load_audio(args.input)

        # Process
        transcript, response, audio_out = pipeline.process(
            audio,
            play=not args.no_play,
            output_file=args.output,
        )

        # Summary
        if transcript:
            print("\n" + "=" * 60)
            print("SUMMARY")
            print("=" * 60)
            print(f"Input:    \"{transcript}\"")
            print(f"Response: \"{response}\"")
            if args.output:
                print(f"Output:   {args.output}")
            print("\n[SUCCESS] Audio pipeline test complete!")
        else:
            print("\n[FAILED] No speech detected in audio")
            sys.exit(1)


if __name__ == "__main__":
    main()
