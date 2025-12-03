#!/usr/bin/env python3
"""CLI tools for testing Phone Agent components.

Usage:
    python -m phone_agent.cli test-stt        # Test speech-to-text
    python -m phone_agent.cli test-llm        # Test language model
    python -m phone_agent.cli test-tts        # Test text-to-speech
    python -m phone_agent.cli test-pipeline   # Test full pipeline
    python -m phone_agent.cli chat            # Interactive chat
    python -m phone_agent.cli benchmark       # Benchmark latency
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import time
from pathlib import Path

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
    subparsers.add_parser("chat", help="Interactive chat mode")

    # benchmark
    bench_parser = subparsers.add_parser("benchmark", help="Benchmark latency")
    bench_parser.add_argument(
        "--iterations", type=int, default=3, help="Number of iterations"
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
        "benchmark": benchmark,
    }

    return commands[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
