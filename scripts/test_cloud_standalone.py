#!/usr/bin/env python3
"""Standalone test script for cloud AI providers.

Tests Groq, Deepgram, and ElevenLabs independently before integration.

Usage:
    # Set API keys as environment variables:
    export GROQ_API_KEY=your_key
    export DEEPGRAM_API_KEY=your_key
    export ELEVENLABS_API_KEY=your_key

    # Test individual providers:
    python scripts/test_cloud_standalone.py groq --prompt "Hallo, wie geht es dir?"
    python scripts/test_cloud_standalone.py deepgram --record 5
    python scripts/test_cloud_standalone.py elevenlabs --text "Guten Tag!"

    # Test all providers:
    python scripts/test_cloud_standalone.py all
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


def test_groq(api_key: str, prompt: str, model: str = "llama-3.3-70b-versatile") -> bool:
    """Test Groq LLM provider.

    Args:
        api_key: Groq API key
        prompt: Test prompt
        model: Model to use

    Returns:
        True if test passed
    """
    print("\n" + "=" * 60)
    print("TESTING GROQ LLM")
    print("=" * 60)

    try:
        from phone_agent.ai.cloud.groq_client import GroqLanguageModel, HANDWERK_SYSTEM_PROMPT

        # Initialize client
        print(f"Model: {model}")
        client = GroqLanguageModel(api_key=api_key, model=model)

        # Test basic generation
        print(f"\nPrompt: {prompt}")
        print("-" * 40)

        start = time.time()
        response = client.generate(prompt, system_prompt=HANDWERK_SYSTEM_PROMPT)
        latency = (time.time() - start) * 1000

        print(f"Response: {response}")
        print("-" * 40)
        print(f"Latency: {latency:.0f}ms")

        # Test streaming
        print("\nTesting streaming...")
        start = time.time()
        first_token_time = None
        token_count = 0

        print("Streaming: ", end="", flush=True)
        for token in client.generate_stream(prompt, system_prompt=HANDWERK_SYSTEM_PROMPT):
            if first_token_time is None:
                first_token_time = (time.time() - start) * 1000
            print(token, end="", flush=True)
            token_count += 1
        print()

        total_time = (time.time() - start) * 1000
        print(f"First token: {first_token_time:.0f}ms")
        print(f"Total time: {total_time:.0f}ms")
        print(f"Tokens: {token_count}")

        print("\n[PASS] Groq test passed!")
        return True

    except Exception as e:
        print(f"\n[FAIL] Groq test failed: {e}")
        return False


def test_deepgram(api_key: str, record_seconds: int = 5) -> bool:
    """Test Deepgram STT provider.

    Args:
        api_key: Deepgram API key
        record_seconds: Seconds to record

    Returns:
        True if test passed
    """
    print("\n" + "=" * 60)
    print("TESTING DEEPGRAM STT")
    print("=" * 60)

    try:
        import numpy as np
        import sounddevice as sd
        from phone_agent.ai.cloud.deepgram_client import DeepgramSTT

        # Initialize client
        client = DeepgramSTT(api_key=api_key, language="de")
        print(f"Model: {client.model}")
        print(f"Language: {client.language}")

        # Record audio
        sample_rate = 16000
        print(f"\nRecording {record_seconds} seconds... (speak in German)")
        print("Recording started!")

        audio = sd.rec(
            int(record_seconds * sample_rate),
            samplerate=sample_rate,
            channels=1,
            dtype=np.float32,
        )
        sd.wait()
        audio = audio.flatten()

        print(f"Recording complete. Audio shape: {audio.shape}")
        print(f"Audio duration: {len(audio) / sample_rate:.2f}s")

        # Transcribe
        print("\nTranscribing...")
        start = time.time()
        result = client.transcribe_with_info(audio, sample_rate)
        latency = (time.time() - start) * 1000

        print("-" * 40)
        print(f"Transcript: {result.text}")
        print(f"Language: {result.language}")
        print(f"Confidence: {result.language_probability:.2%}")
        print("-" * 40)
        print(f"Latency: {latency:.0f}ms")

        if result.text.strip():
            print("\n[PASS] Deepgram test passed!")
            return True
        else:
            print("\n[WARN] No speech detected - try speaking louder")
            return False

    except ImportError as e:
        print(f"\n[FAIL] Missing dependency: {e}")
        print("Install with: pip install sounddevice numpy")
        return False
    except Exception as e:
        print(f"\n[FAIL] Deepgram test failed: {e}")
        return False


def test_elevenlabs(api_key: str, text: str, voice: str = "adam") -> bool:
    """Test ElevenLabs TTS provider.

    Args:
        api_key: ElevenLabs API key
        text: Text to synthesize
        voice: Voice name or ID

    Returns:
        True if test passed
    """
    print("\n" + "=" * 60)
    print("TESTING ELEVENLABS TTS")
    print("=" * 60)

    try:
        from phone_agent.ai.cloud.elevenlabs_client import ElevenLabsTTS, GERMAN_VOICES

        # Get voice ID
        voice_id = GERMAN_VOICES.get(voice, voice)
        print(f"Voice: {voice} ({voice_id})")

        # Initialize client
        client = ElevenLabsTTS(api_key=api_key, voice_id=voice_id)
        print(f"Model: {client.model}")

        # Synthesize
        print(f"\nText: {text}")
        print("-" * 40)

        start = time.time()
        audio_data = client.synthesize(text, output_format="wav")
        latency = (time.time() - start) * 1000

        print(f"Audio size: {len(audio_data)} bytes")
        print(f"Latency: {latency:.0f}ms")

        # Save to file
        output_file = Path("test_elevenlabs_output.wav")
        with open(output_file, "wb") as f:
            f.write(audio_data)
        print(f"Saved to: {output_file}")

        # Play audio if sounddevice available
        try:
            import io
            import wave
            import sounddevice as sd
            import numpy as np

            # Parse WAV
            with io.BytesIO(audio_data) as f:
                with wave.open(f, "rb") as wav:
                    frames = wav.readframes(wav.getnframes())
                    sample_rate = wav.getframerate()
                    audio = np.frombuffer(frames, dtype=np.int16)
                    audio = audio.astype(np.float32) / 32768.0

            print("\nPlaying audio...")
            sd.play(audio, sample_rate)
            sd.wait()
            print("Playback complete.")

        except ImportError:
            print("\n(Install sounddevice to play audio: pip install sounddevice)")

        print("\n[PASS] ElevenLabs test passed!")
        return True

    except Exception as e:
        print(f"\n[FAIL] ElevenLabs test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_all(groq_key: str, deepgram_key: str, elevenlabs_key: str) -> bool:
    """Test all providers.

    Args:
        groq_key: Groq API key
        deepgram_key: Deepgram API key
        elevenlabs_key: ElevenLabs API key

    Returns:
        True if all tests passed
    """
    print("\n" + "=" * 60)
    print("TESTING ALL CLOUD PROVIDERS")
    print("=" * 60)

    results = {}

    # Test Groq
    if groq_key:
        results["Groq"] = test_groq(groq_key, "Hallo, meine Heizung ist kaputt!")
    else:
        print("\n[SKIP] Groq - no API key set (GROQ_API_KEY)")
        results["Groq"] = None

    # Test ElevenLabs (before Deepgram so audio playback doesn't interfere with recording)
    if elevenlabs_key:
        results["ElevenLabs"] = test_elevenlabs(
            elevenlabs_key, "Guten Tag, wie kann ich Ihnen helfen?"
        )
    else:
        print("\n[SKIP] ElevenLabs - no API key set (ELEVENLABS_API_KEY)")
        results["ElevenLabs"] = None

    # Test Deepgram (requires microphone)
    if deepgram_key:
        print("\n" + "-" * 60)
        print("Deepgram requires microphone input.")
        record = input("Record audio for STT test? [y/N]: ").strip().lower()
        if record == "y":
            results["Deepgram"] = test_deepgram(deepgram_key, 5)
        else:
            print("[SKIP] Deepgram - user skipped")
            results["Deepgram"] = None
    else:
        print("\n[SKIP] Deepgram - no API key set (DEEPGRAM_API_KEY)")
        results["Deepgram"] = None

    # Summary
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)

    for provider, passed in results.items():
        if passed is None:
            status = "[SKIP]"
        elif passed:
            status = "[PASS]"
        else:
            status = "[FAIL]"
        print(f"  {provider}: {status}")

    all_passed = all(v is not False for v in results.values())
    if all_passed:
        print("\nAll tests passed! Ready for integration.")
    else:
        print("\nSome tests failed. Check output above.")

    return all_passed


def main():
    parser = argparse.ArgumentParser(
        description="Test cloud AI providers (Groq, Deepgram, ElevenLabs)"
    )
    subparsers = parser.add_subparsers(dest="command", help="Provider to test")

    # Groq subcommand
    groq_parser = subparsers.add_parser("groq", help="Test Groq LLM")
    groq_parser.add_argument(
        "--prompt",
        default="Hallo, meine Heizung ist kaputt. Was soll ich tun?",
        help="Test prompt",
    )
    groq_parser.add_argument(
        "--model",
        default="llama-3.3-70b-versatile",
        help="Model name",
    )
    groq_parser.add_argument(
        "--api-key",
        default=os.environ.get("GROQ_API_KEY"),
        help="Groq API key (or set GROQ_API_KEY)",
    )

    # Deepgram subcommand
    deepgram_parser = subparsers.add_parser("deepgram", help="Test Deepgram STT")
    deepgram_parser.add_argument(
        "--record",
        type=int,
        default=5,
        help="Seconds to record",
    )
    deepgram_parser.add_argument(
        "--api-key",
        default=os.environ.get("DEEPGRAM_API_KEY"),
        help="Deepgram API key (or set DEEPGRAM_API_KEY)",
    )

    # ElevenLabs subcommand
    elevenlabs_parser = subparsers.add_parser("elevenlabs", help="Test ElevenLabs TTS")
    elevenlabs_parser.add_argument(
        "--text",
        default="Guten Tag, wie kann ich Ihnen helfen?",
        help="Text to synthesize",
    )
    elevenlabs_parser.add_argument(
        "--voice",
        default="adam",
        help="Voice name (adam, rachel, josh, etc.)",
    )
    elevenlabs_parser.add_argument(
        "--api-key",
        default=os.environ.get("ELEVENLABS_API_KEY"),
        help="ElevenLabs API key (or set ELEVENLABS_API_KEY)",
    )

    # All subcommand
    all_parser = subparsers.add_parser("all", help="Test all providers")
    all_parser.add_argument(
        "--groq-key",
        default=os.environ.get("GROQ_API_KEY"),
        help="Groq API key",
    )
    all_parser.add_argument(
        "--deepgram-key",
        default=os.environ.get("DEEPGRAM_API_KEY"),
        help="Deepgram API key",
    )
    all_parser.add_argument(
        "--elevenlabs-key",
        default=os.environ.get("ELEVENLABS_API_KEY"),
        help="ElevenLabs API key",
    )

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        print("\n" + "=" * 60)
        print("QUICK START")
        print("=" * 60)
        print("""
1. Get free API keys:
   - Groq: https://console.groq.com/
   - Deepgram: https://console.deepgram.com/ (free $200 credit)
   - ElevenLabs: https://elevenlabs.io/ (10K chars/month free)

2. Set environment variables:
   export GROQ_API_KEY=your_key
   export DEEPGRAM_API_KEY=your_key
   export ELEVENLABS_API_KEY=your_key

3. Run tests:
   python scripts/test_cloud_standalone.py all
""")
        return

    # Run appropriate test
    if args.command == "groq":
        if not args.api_key:
            print("Error: GROQ_API_KEY not set")
            sys.exit(1)
        success = test_groq(args.api_key, args.prompt, args.model)

    elif args.command == "deepgram":
        if not args.api_key:
            print("Error: DEEPGRAM_API_KEY not set")
            sys.exit(1)
        success = test_deepgram(args.api_key, args.record)

    elif args.command == "elevenlabs":
        if not args.api_key:
            print("Error: ELEVENLABS_API_KEY not set")
            sys.exit(1)
        success = test_elevenlabs(args.api_key, args.text, args.voice)

    elif args.command == "all":
        success = test_all(args.groq_key, args.deepgram_key, args.elevenlabs_key)

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
