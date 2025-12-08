#!/usr/bin/env python3
"""CLI tools for testing Phone Agent components.

Usage:
    python -m phone_agent.cli test-stt        # Test speech-to-text
    python -m phone_agent.cli test-llm        # Test language model
    python -m phone_agent.cli test-tts        # Test text-to-speech
    python -m phone_agent.cli test-pipeline   # Test full pipeline
    python -m phone_agent.cli chat            # Interactive text chat
    python -m phone_agent.cli voice-chat      # Interactive VOICE chat
    python -m phone_agent.cli list-devices    # List audio devices
    python -m phone_agent.cli benchmark       # Benchmark latency
"""

from __future__ import annotations

import argparse
import asyncio
import io
import subprocess
import sys
import time
import wave
from pathlib import Path

import numpy as np
from itf_shared import setup_logging, get_logger

setup_logging(level="INFO")
log = get_logger(__name__)


def test_stt(args: argparse.Namespace) -> int:
    """Test speech-to-text component."""
    print("\n=== Testing Speech-to-Text ===\n")

    from phone_agent.ai import SpeechToText
    from phone_agent.config import get_settings

    settings = get_settings()

    stt = SpeechToText(
        model=settings.ai.stt.model,
        model_path=settings.ai.stt.model_path,
        device=settings.ai.stt.device,
        compute_type=settings.ai.stt.compute_type,
    )

    print(f"Model: {settings.ai.stt.model}")
    print(f"Device: {settings.ai.stt.device}")
    print(f"Compute type: {settings.ai.stt.compute_type}")
    print()

    # Load model
    print("Loading model...")
    start = time.time()
    stt.load()
    load_time = time.time() - start
    print(f"Model loaded in {load_time:.2f}s")

    if args.audio_file:
        # Test with audio file
        import numpy as np
        import wave

        print(f"\nProcessing: {args.audio_file}")
        with wave.open(args.audio_file, "rb") as wav:
            frames = wav.readframes(wav.getnframes())
            audio = np.frombuffer(frames, dtype=np.int16)
            audio = audio.astype(np.float32) / 32768.0
            sample_rate = wav.getframerate()

        start = time.time()
        text = stt.transcribe(audio, sample_rate)
        transcribe_time = time.time() - start

        print(f"\nTranscription ({transcribe_time:.2f}s):")
        print(f"  {text}")
    else:
        # Test with microphone
        print("\nNo audio file provided. Testing with synthetic audio...")
        import numpy as np

        # Generate 3 seconds of silence (placeholder)
        audio = np.zeros(16000 * 3, dtype=np.float32)
        text = stt.transcribe(audio, 16000)
        print(f"Transcription: {text or '(silence)'}")

    print("\n[OK] STT test complete")
    return 0


def test_llm(args: argparse.Namespace) -> int:
    """Test language model component."""
    print("\n=== Testing Language Model ===\n")

    from phone_agent.ai import LanguageModel
    from phone_agent.config import get_settings

    settings = get_settings()

    llm = LanguageModel(
        model=settings.ai.llm.model,
        model_path=settings.ai.llm.model_path,
        n_ctx=settings.ai.llm.n_ctx,
        n_threads=settings.ai.llm.n_threads,
    )

    print(f"Model: {settings.ai.llm.model}")
    print(f"Context: {settings.ai.llm.n_ctx}")
    print(f"Threads: {settings.ai.llm.n_threads}")
    print()

    # Load model
    print("Loading model...")
    start = time.time()
    llm.load()
    load_time = time.time() - start
    print(f"Model loaded in {load_time:.2f}s")

    # Test generation
    test_prompts = [
        "Hallo, ich möchte einen Termin vereinbaren.",
        "Ich habe starke Kopfschmerzen seit heute morgen.",
        "Wann haben Sie geöffnet?",
    ]

    system_prompt = "Du bist ein freundlicher Telefonassistent einer Arztpraxis. Antworte kurz und auf Deutsch."

    for prompt in test_prompts:
        print(f"\n>>> {prompt}")
        start = time.time()
        response = llm.generate(prompt, system_prompt=system_prompt, max_tokens=100)
        gen_time = time.time() - start
        print(f"<<< {response}")
        print(f"    ({gen_time:.2f}s)")

    print("\n[OK] LLM test complete")
    return 0


def test_tts(args: argparse.Namespace) -> int:
    """Test text-to-speech component."""
    print("\n=== Testing Text-to-Speech ===\n")

    from phone_agent.ai import TextToSpeech
    from phone_agent.config import get_settings

    settings = get_settings()

    tts = TextToSpeech(
        model=settings.ai.tts.model,
        model_path=settings.ai.tts.model_path,
    )

    print(f"Model: {settings.ai.tts.model}")
    print()

    # Load model
    print("Loading model...")
    start = time.time()
    tts.load()
    load_time = time.time() - start
    print(f"Model loaded in {load_time:.2f}s")

    # Test synthesis
    test_texts = [
        "Guten Tag, Praxis Müller, wie kann ich Ihnen helfen?",
        "Ich kann Ihnen einen Termin am Dienstag um 10 Uhr anbieten.",
        "Vielen Dank für Ihren Anruf. Auf Wiederhören!",
    ]

    for text in test_texts:
        print(f"\nSynthesizing: {text[:50]}...")
        start = time.time()
        audio = tts.synthesize(text)
        synth_time = time.time() - start
        print(f"  Generated {len(audio)} bytes in {synth_time:.2f}s")

        if args.play:
            print("  Playing...")
            from phone_agent.ai.tts import play_audio

            play_audio(audio)

    print("\n[OK] TTS test complete")
    return 0


def test_pipeline(args: argparse.Namespace) -> int:
    """Test full STT → LLM → TTS pipeline."""
    print("\n=== Testing Full Pipeline ===\n")

    from phone_agent.core import ConversationEngine
    from phone_agent.config import get_settings

    settings = get_settings()

    print("Initializing conversation engine...")
    engine = ConversationEngine()

    print("Preloading models...")
    start = time.time()
    engine.preload_models()
    load_time = time.time() - start
    print(f"Models loaded in {load_time:.2f}s")

    # Start conversation
    conversation = engine.start_conversation()
    print(f"\nConversation ID: {conversation.id}")

    # Test with text (since we may not have audio)
    test_inputs = [
        "Hallo, ich möchte einen Termin vereinbaren.",
        "Ich habe seit gestern Halsschmerzen.",
        "Haben Sie morgen noch einen Termin frei?",
    ]

    async def run_tests():
        for user_input in test_inputs:
            print(f"\n>>> User: {user_input}")

            start = time.time()
            response = await engine.process_text(user_input, conversation.id)
            elapsed = time.time() - start

            print(f"<<< Assistant: {response}")
            print(f"    (Total: {elapsed:.2f}s)")

    asyncio.run(run_tests())

    # Show conversation summary
    print(f"\n--- Conversation Summary ---")
    print(f"Turns: {len(conversation.turns)}")
    if conversation.triage_result:
        print(f"Triage: {conversation.triage_result.level.value}")

    print("\n[OK] Pipeline test complete")
    return 0


def interactive_chat(args: argparse.Namespace) -> int:
    """Interactive chat mode."""
    print("\n=== Interactive Chat Mode ===")
    print("Type 'quit' or 'exit' to end.\n")

    from phone_agent.core import ConversationEngine

    engine = ConversationEngine()

    print("Loading models (this may take a moment)...")
    engine.preload_models()

    conversation = engine.start_conversation()
    print(f"Conversation started. ID: {conversation.id}\n")

    async def run_chat():
        while True:
            try:
                user_input = input("You: ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\nGoodbye!")
                break

            if not user_input:
                continue

            if user_input.lower() in ("quit", "exit", "q"):
                print("Goodbye!")
                break

            try:
                response = await engine.process_text(user_input, conversation.id)
                print(f"Assistant: {response}\n")
            except Exception as e:
                print(f"Error: {e}\n")

    asyncio.run(run_chat())

    # Show summary
    engine.end_conversation(conversation.id)
    print(f"\n--- Session Summary ---")
    print(f"Turns: {len(conversation.turns)}")

    return 0


def benchmark(args: argparse.Namespace) -> int:
    """Benchmark latency of components."""
    print("\n=== Latency Benchmark ===\n")

    from phone_agent.ai import SpeechToText, LanguageModel, TextToSpeech
    from phone_agent.config import get_settings
    import numpy as np

    settings = get_settings()
    results = {}

    # Benchmark STT
    print("Benchmarking STT...")
    stt = SpeechToText(
        model=settings.ai.stt.model,
        model_path=settings.ai.stt.model_path,
        device=settings.ai.stt.device,
        compute_type=settings.ai.stt.compute_type,
    )
    stt.load()

    # Generate 5 seconds of random audio
    audio = np.random.randn(16000 * 5).astype(np.float32) * 0.1

    times = []
    for i in range(args.iterations):
        start = time.time()
        stt.transcribe(audio, 16000)
        times.append(time.time() - start)

    results["STT (5s audio)"] = {
        "mean": np.mean(times),
        "std": np.std(times),
        "min": np.min(times),
        "max": np.max(times),
    }
    stt.unload()

    # Benchmark LLM
    print("Benchmarking LLM...")
    llm = LanguageModel(
        model=settings.ai.llm.model,
        model_path=settings.ai.llm.model_path,
        n_ctx=settings.ai.llm.n_ctx,
        n_threads=settings.ai.llm.n_threads,
    )
    llm.load()

    prompt = "Ich möchte einen Termin vereinbaren."
    system = "Du bist ein Telefonassistent. Antworte kurz."

    times = []
    for i in range(args.iterations):
        start = time.time()
        llm.generate(prompt, system_prompt=system, max_tokens=50)
        times.append(time.time() - start)

    results["LLM (50 tokens)"] = {
        "mean": np.mean(times),
        "std": np.std(times),
        "min": np.min(times),
        "max": np.max(times),
    }
    llm.unload()

    # Benchmark TTS
    print("Benchmarking TTS...")
    tts = TextToSpeech(
        model=settings.ai.tts.model,
        model_path=settings.ai.tts.model_path,
    )
    tts.load()

    text = "Ich kann Ihnen einen Termin am Dienstag um zehn Uhr anbieten."

    times = []
    for i in range(args.iterations):
        start = time.time()
        tts.synthesize(text)
        times.append(time.time() - start)

    results["TTS (short)"] = {
        "mean": np.mean(times),
        "std": np.std(times),
        "min": np.min(times),
        "max": np.max(times),
    }
    tts.unload()

    # Print results
    print("\n" + "=" * 60)
    print(f"{'Component':<20} {'Mean':>10} {'Std':>10} {'Min':>10} {'Max':>10}")
    print("=" * 60)

    total_mean = 0
    for name, stats in results.items():
        print(
            f"{name:<20} {stats['mean']:>9.2f}s {stats['std']:>9.2f}s "
            f"{stats['min']:>9.2f}s {stats['max']:>9.2f}s"
        )
        total_mean += stats["mean"]

    print("-" * 60)
    print(f"{'Total Pipeline':<20} {total_mean:>9.2f}s")
    print("=" * 60)

    print("\n[OK] Benchmark complete")
    return 0


def list_devices(args: argparse.Namespace) -> int:
    """List available audio devices."""
    print("\n=== Audio Devices ===\n")

    # Try sounddevice first
    try:
        import sounddevice as sd

        print("Using sounddevice:\n")
        print(sd.query_devices())
        return 0
    except ImportError:
        pass

    # Fallback to ALSA (Linux/Pi)
    try:
        print("Capture devices (arecord -l):")
        result = subprocess.run(["arecord", "-l"], capture_output=True, text=True)
        print(result.stdout or "(none found)")

        print("\nPlayback devices (aplay -l):")
        result = subprocess.run(["aplay", "-l"], capture_output=True, text=True)
        print(result.stdout or "(none found)")
        return 0
    except FileNotFoundError:
        print("No audio tools found (sounddevice or ALSA)")
        return 1


def voice_chat(args: argparse.Namespace) -> int:
    """Interactive voice chat mode with microphone input and streaming responses."""
    print("\n" + "=" * 50)
    print("  VOICE CHAT MODE (Streaming + Dialect Detection)")
    print("  Speak German into the microphone")
    print("  Schwäbisch, Bayerisch, and other dialects are supported!")
    print("  Say 'Auf Wiedersehen' or press Ctrl+C to exit")
    print("=" * 50 + "\n")

    # Determine audio device
    input_device = args.input_device or "plughw:2,0"  # Default: USB headset on Pi
    output_device = args.output_device or "plughw:2,0"
    record_duration = args.duration or 5
    use_streaming = not args.no_streaming if hasattr(args, "no_streaming") else True
    enable_dialect = not args.no_dialect if hasattr(args, "no_dialect") else True
    use_engine = args.use_engine if hasattr(args, "use_engine") else False

    # Use ConversationEngine for full memory + dialect + streaming support
    if use_engine:
        return _voice_chat_with_engine(
            input_device, output_device, record_duration, use_streaming, enable_dialect
        )

    from phone_agent.ai import DialectAwareSTT, LanguageModel, TextToSpeech
    from phone_agent.config import get_settings

    settings = get_settings()

    print("Loading AI models...")
    start = time.time()

    # Use DialectAwareSTT for dialect detection
    stt = DialectAwareSTT(
        model_path=settings.ai.stt.model_path,
        device=settings.ai.stt.device,
        compute_type=settings.ai.stt.compute_type,
        dialect_detection=enable_dialect,
        detection_mode="text",  # Post-transcription detection (faster)
    )
    stt.load()

    llm = LanguageModel(
        model=settings.ai.llm.model,
        model_path=settings.ai.llm.model_path,
        n_ctx=1024,  # Reduced for faster loading
        n_threads=settings.ai.llm.n_threads,
    )
    llm.load()

    tts = TextToSpeech(
        model=settings.ai.tts.model,
        model_path=settings.ai.tts.model_path,
    )
    tts.load()

    print(f"Models loaded in {time.time() - start:.1f}s")
    print(f"Streaming mode: {'ON' if use_streaming else 'OFF'}")
    print(f"Dialect detection: {'ON' if enable_dialect else 'OFF'}\n")

    # Optimized system prompt for brief responses
    system_prompt = (
        "Du bist der Telefonassistent der Praxis Dr. Müller. "
        "Antworte in 1-2 kurzen deutschen Sätzen. "
        "Sei freundlich und hilfsbereit. "
        "Frage nach Name und Versicherung wenn nötig."
    )

    # Play greeting
    greeting = "Guten Tag! Praxis Müller, wie kann ich Ihnen helfen?"
    print(f"Assistant: {greeting}")
    _play_audio(tts.synthesize(greeting), output_device)

    # Exit phrases
    exit_phrases = ["auf wiedersehen", "tschüss", "ende", "beenden", "goodbye"]

    try:
        while True:
            print(f"\n[Listening for {record_duration}s... speak now]")

            # Record audio
            audio = _record_audio(input_device, record_duration)
            if audio is None:
                print("[Recording failed, trying again...]")
                continue

            # Check for silence
            if np.max(np.abs(audio)) < 0.01:
                print("[No speech detected]")
                continue

            # Transcribe
            print("[Transcribing...]")
            start = time.time()
            text = stt.transcribe(audio, sample_rate=16000)
            stt_time = time.time() - start

            if not text or len(text.strip()) < 2:
                print("[Could not understand, please try again]")
                continue

            # Show dialect detection if available
            dialect_info = ""
            if enable_dialect and hasattr(stt, "_last_dialect"):
                dialect = getattr(stt, "_last_dialect", None)
                if dialect and dialect.dialect != "de_standard":
                    dialect_names = {
                        "de_alemannic": "Schwäbisch",
                        "de_bavarian": "Bayerisch",
                        "de_low": "Plattdeutsch",
                    }
                    dialect_name = dialect_names.get(dialect.dialect, dialect.dialect)
                    dialect_info = f" [{dialect_name} {dialect.confidence:.0%}]"

            print(f"\nYou ({stt_time:.1f}s){dialect_info}: {text}")

            # Check for exit
            if any(phrase in text.lower() for phrase in exit_phrases):
                farewell = "Auf Wiedersehen! Ich wünsche Ihnen einen schönen Tag."
                print(f"Assistant: {farewell}")
                _play_audio(tts.synthesize(farewell), output_device)
                break

            # Generate and speak response
            if use_streaming:
                # STREAMING MODE: Start speaking as soon as first sentence is ready
                _generate_and_speak_streaming(
                    llm, tts, text, system_prompt, output_device
                )
            else:
                # NON-STREAMING MODE: Wait for full response
                print("[Generating response...]")
                start = time.time()
                response = llm.generate(
                    text, system_prompt=system_prompt, max_tokens=60, temperature=0.3
                )
                llm_time = time.time() - start

                response = response.strip()
                if len(response) > 200:
                    response = response[:200].rsplit(".", 1)[0] + "."

                print(f"Assistant ({llm_time:.1f}s): {response}")
                print("[Speaking...]")
                _play_audio(tts.synthesize(response), output_device)

    except KeyboardInterrupt:
        print("\n\nGoodbye!")

    print("\n[OK] Voice chat ended")
    return 0


def _generate_and_speak_streaming(
    llm, tts, prompt: str, system_prompt: str, output_device: str
) -> None:
    """Generate response with streaming and speak sentences as they complete."""
    start_time = time.time()
    buffer = ""
    sentences_spoken = 0
    full_response = ""

    print("[Streaming response...]")

    for token in llm.generate_stream(
        prompt, system_prompt=system_prompt, max_tokens=60, temperature=0.3
    ):
        buffer += token
        full_response += token

        # Check for sentence completion
        for punct in [".", "!", "?"]:
            if punct in buffer:
                # Extract completed sentence
                idx = buffer.index(punct) + 1
                sentence = buffer[:idx].strip()
                buffer = buffer[idx:].strip()

                if sentence and len(sentence) > 3:
                    elapsed = time.time() - start_time
                    if sentences_spoken == 0:
                        print(f"[First sentence in {elapsed:.2f}s]")

                    # Speak this sentence immediately
                    print(f"  >> {sentence}")
                    audio = tts.synthesize(sentence)
                    _play_audio(audio, output_device)
                    sentences_spoken += 1
                break

    # Speak any remaining text
    if buffer.strip() and len(buffer.strip()) > 3:
        print(f"  >> {buffer.strip()}")
        audio = tts.synthesize(buffer.strip())
        _play_audio(audio, output_device)

    total_time = time.time() - start_time
    print(f"Assistant ({total_time:.1f}s total): {full_response.strip()[:100]}...")


def _record_audio(device: str, duration: int) -> np.ndarray | None:
    """Record audio using arecord (ALSA)."""
    try:
        result = subprocess.run(
            [
                "arecord",
                "-D", device,
                "-d", str(duration),
                "-f", "S16_LE",
                "-r", "16000",
                "-c", "1",
                "-t", "wav",
                "-q",  # Quiet mode
                "-",   # Output to stdout
            ],
            capture_output=True,
            timeout=duration + 5,
        )

        if result.returncode != 0:
            log.error("arecord failed", stderr=result.stderr.decode())
            return None

        # Parse WAV from stdout
        with io.BytesIO(result.stdout) as f:
            with wave.open(f, "rb") as wf:
                frames = wf.readframes(wf.getnframes())
                audio = np.frombuffer(frames, dtype=np.int16)
                return audio.astype(np.float32) / 32768.0

    except subprocess.TimeoutExpired:
        log.error("Recording timeout")
        return None
    except Exception as e:
        log.error("Recording error", error=str(e))
        return None


def _play_audio(audio_bytes: bytes, device: str) -> None:
    """Play audio using aplay (ALSA)."""
    try:
        subprocess.run(
            [
                "aplay",
                "-D", device,
                "-q",  # Quiet mode
                "-",   # Input from stdin
            ],
            input=audio_bytes,
            timeout=30,
            capture_output=True,
        )
    except Exception as e:
        log.error("Playback error", error=str(e))


def _voice_chat_with_engine(
    input_device: str,
    output_device: str,
    record_duration: int,
    use_streaming: bool,
    enable_dialect: bool,
) -> int:
    """Voice chat using ConversationEngine with full memory, dialect, and streaming support.

    This mode provides:
    - Conversation memory (LLM remembers previous turns)
    - Dialect detection (Schwäbisch, Bayerisch)
    - Streaming TTS (speak first sentence while generating rest)
    """
    from phone_agent.core import ConversationEngine

    print("Loading ConversationEngine with full AI stack...")
    start = time.time()

    engine = ConversationEngine(dialect_aware=enable_dialect)
    engine.preload_models()

    print(f"Models loaded in {time.time() - start:.1f}s")
    print(f"Streaming mode: {'ON' if use_streaming else 'OFF'}")
    print(f"Dialect detection: {'ON' if enable_dialect else 'OFF'}")
    print(f"Conversation memory: ON\n")

    # Start conversation
    conversation = engine.start_conversation()
    print(f"Conversation ID: {conversation.id}")

    # Play greeting
    async def play_greeting():
        greeting, audio = await engine.generate_greeting(conversation.id)
        print(f"\nAssistant: {greeting}")
        _play_audio(audio, output_device)

    asyncio.run(play_greeting())

    # Exit phrases
    exit_phrases = ["auf wiedersehen", "tschüss", "ende", "beenden", "goodbye"]

    async def run_conversation():
        while True:
            print(f"\n[Listening for {record_duration}s... speak now]")

            # Record audio
            audio = _record_audio(input_device, record_duration)
            if audio is None:
                print("[Recording failed, trying again...]")
                continue

            # Check for silence
            if np.max(np.abs(audio)) < 0.01:
                print("[No speech detected]")
                continue

            if use_streaming:
                # STREAMING MODE: Process with sentence-by-sentence TTS
                sentences_played = []

                async def on_sentence_ready(sentence: str, audio_bytes: bytes):
                    """Callback to play audio as soon as each sentence is ready."""
                    sentences_played.append(sentence)
                    if len(sentences_played) == 1:
                        print(f"\nAssistant: ", end="", flush=True)
                    print(f"{sentence} ", end="", flush=True)
                    _play_audio(audio_bytes, output_device)

                user_text, full_response, _ = await engine.process_audio_streaming(
                    audio,
                    conversation.id,
                    on_sentence_ready=on_sentence_ready,
                    sample_rate=16000,
                )

                # Show dialect info
                state = engine.get_conversation(conversation.id)
                dialect_info = ""
                if state and state.detected_dialect and state.detected_dialect != "de_standard":
                    dialect_names = {
                        "de_alemannic": "Schwäbisch",
                        "de_bavarian": "Bayerisch",
                        "de_low": "Plattdeutsch",
                    }
                    dialect_name = dialect_names.get(state.detected_dialect, state.detected_dialect)
                    dialect_info = f" [{dialect_name}]"

                print(f"\n\nYou{dialect_info}: {user_text}")

                # Check for exit
                if any(phrase in user_text.lower() for phrase in exit_phrases):
                    farewell = "Auf Wiedersehen! Ich wünsche Ihnen einen schönen Tag."
                    print(f"Assistant: {farewell}")
                    audio = await engine.tts.synthesize_async(farewell)
                    _play_audio(audio, output_device)
                    break

            else:
                # NON-STREAMING MODE: Wait for full response
                print("[Processing...]")
                start = time.time()
                response, audio = await engine.process_audio(
                    audio, conversation.id, sample_rate=16000
                )
                elapsed = time.time() - start

                # Show dialect info
                state = engine.get_conversation(conversation.id)
                dialect_info = ""
                if state and state.detected_dialect and state.detected_dialect != "de_standard":
                    dialect_names = {
                        "de_alemannic": "Schwäbisch",
                        "de_bavarian": "Bayerisch",
                        "de_low": "Plattdeutsch",
                    }
                    dialect_name = dialect_names.get(state.detected_dialect, state.detected_dialect)
                    dialect_info = f" [{dialect_name}]"

                # Get user text from last turn
                if state and len(state.turns) >= 2:
                    user_text = state.turns[-2].content
                    print(f"\nYou{dialect_info}: {user_text}")

                print(f"Assistant ({elapsed:.1f}s): {response}")
                _play_audio(audio, output_device)

                # Check for exit
                if any(phrase in response.lower() for phrase in exit_phrases):
                    break

    try:
        asyncio.run(run_conversation())
    except KeyboardInterrupt:
        print("\n\nGoodbye!")

    # End conversation and show summary
    engine.end_conversation(conversation.id)
    print(f"\n--- Conversation Summary ---")
    print(f"Turns: {len(conversation.turns)}")
    if conversation.detected_dialect:
        print(f"Detected dialect: {conversation.detected_dialect}")

    print("\n[OK] Voice chat ended")
    return 0


def show_metrics(args: argparse.Namespace) -> int:
    """Show latency metrics."""
    import json
    from phone_agent.core.metrics import get_metrics, reset_metrics

    metrics = get_metrics()
    report = metrics.get_report(format="json" if args.json else "text")

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(report)

    if args.reset:
        reset_metrics()
        print("\n[Metrics reset]")

    return 0


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Phone Agent CLI Tools",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # test-stt
    stt_parser = subparsers.add_parser("test-stt", help="Test speech-to-text")
    stt_parser.add_argument("--audio-file", type=str, help="Path to audio file")

    # test-llm
    subparsers.add_parser("test-llm", help="Test language model")

    # test-tts
    tts_parser = subparsers.add_parser("test-tts", help="Test text-to-speech")
    tts_parser.add_argument("--play", action="store_true", help="Play generated audio")

    # test-pipeline
    subparsers.add_parser("test-pipeline", help="Test full pipeline")

    # chat
    subparsers.add_parser("chat", help="Interactive text chat mode")

    # voice-chat
    voice_parser = subparsers.add_parser("voice-chat", help="Interactive VOICE chat mode")
    voice_parser.add_argument(
        "--input-device", type=str, default=None,
        help="Audio input device (default: plughw:2,0 for USB headset)"
    )
    voice_parser.add_argument(
        "--output-device", type=str, default=None,
        help="Audio output device (default: plughw:2,0 for USB headset)"
    )
    voice_parser.add_argument(
        "--duration", type=int, default=5,
        help="Recording duration in seconds (default: 5)"
    )
    voice_parser.add_argument(
        "--no-streaming", action="store_true",
        help="Disable streaming mode (wait for full response before speaking)"
    )
    voice_parser.add_argument(
        "--no-dialect", action="store_true",
        help="Disable dialect detection (Schwäbisch, Bayerisch, etc.)"
    )
    voice_parser.add_argument(
        "--use-engine", action="store_true",
        help="Use ConversationEngine with full memory, dialect, and streaming support (recommended)"
    )

    # list-devices
    subparsers.add_parser("list-devices", help="List available audio devices")

    # benchmark
    bench_parser = subparsers.add_parser("benchmark", help="Benchmark latency")
    bench_parser.add_argument(
        "--iterations", type=int, default=3, help="Number of iterations"
    )

    # metrics
    metrics_parser = subparsers.add_parser("metrics", help="Show latency metrics")
    metrics_parser.add_argument(
        "--json", action="store_true", help="Output as JSON"
    )
    metrics_parser.add_argument(
        "--reset", action="store_true", help="Reset metrics after showing"
    )

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 1

    commands = {
        "test-stt": test_stt,
        "test-llm": test_llm,
        "test-tts": test_tts,
        "test-pipeline": test_pipeline,
        "chat": interactive_chat,
        "voice-chat": voice_chat,
        "list-devices": list_devices,
        "benchmark": benchmark,
        "metrics": show_metrics,
    }

    return commands[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
