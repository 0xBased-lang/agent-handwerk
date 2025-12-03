"""AI Pipeline stress testing for Phone Agent.

Tests the STT → LLM → TTS pipeline under concurrent load to find:
- Maximum concurrent calls supported
- Latency under load
- Memory usage patterns
- Bottlenecks in the AI processing chain

Run with:
    python tests/load/ai_pipeline_stress.py --calls 10 --duration 60

Requirements:
    pip install psutil
"""
from __future__ import annotations

import argparse
import asyncio
import gc
import os
import random
import statistics
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False
    print("Warning: psutil not installed. Memory monitoring disabled.")


@dataclass
class PipelineMetrics:
    """Metrics for a single AI pipeline execution."""
    call_id: str
    stt_latency_ms: float = 0.0
    llm_latency_ms: float = 0.0
    tts_latency_ms: float = 0.0
    total_latency_ms: float = 0.0
    audio_duration_ms: float = 0.0
    success: bool = True
    error: str | None = None

    @property
    def real_time_factor(self) -> float:
        """Ratio of processing time to audio duration (<1 means real-time)."""
        if self.audio_duration_ms <= 0:
            return 0.0
        return self.total_latency_ms / self.audio_duration_ms


@dataclass
class LoadTestResults:
    """Aggregate load test results."""
    start_time: float
    end_time: float = 0.0
    concurrent_calls: int = 0
    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    pipeline_metrics: list[PipelineMetrics] = field(default_factory=list)
    memory_samples: list[float] = field(default_factory=list)  # MB

    @property
    def duration(self) -> float:
        return (self.end_time or time.time()) - self.start_time

    @property
    def success_rate(self) -> float:
        if self.total_requests == 0:
            return 0.0
        return self.successful_requests / self.total_requests * 100

    @property
    def throughput(self) -> float:
        if self.duration <= 0:
            return 0.0
        return self.successful_requests / self.duration

    def get_latency_stats(self, key: str) -> dict[str, float]:
        """Get latency statistics for a specific metric."""
        values = [getattr(m, key) for m in self.pipeline_metrics if m.success]
        if not values:
            return {"avg": 0, "min": 0, "max": 0, "p50": 0, "p95": 0, "p99": 0}

        values.sort()
        return {
            "avg": statistics.mean(values),
            "min": min(values),
            "max": max(values),
            "p50": values[len(values) // 2],
            "p95": values[int(len(values) * 0.95)],
            "p99": values[int(len(values) * 0.99)],
        }


# Sample utterances for testing (varying complexity)
SAMPLE_UTTERANCES = [
    # Short responses (fast processing)
    "Ja.",
    "Nein.",
    "Okay.",
    "Danke.",
    "Bis bald.",

    # Medium responses (typical)
    "Ich möchte bitte einen Termin vereinbaren.",
    "Können Sie mir den nächsten freien Termin nennen?",
    "Am Dienstag um 14 Uhr wäre perfekt.",
    "Ich habe Rückenschmerzen seit einer Woche.",
    "Meine Telefonnummer ist null eins fünf eins, eins zwei drei vier fünf sechs.",

    # Long responses (stress test)
    "Ich rufe an wegen meiner Heizung, die funktioniert seit gestern Abend nicht mehr richtig, es ist kalt in der Wohnung und ich würde gerne einen Techniker beauftragen.",
    "Guten Tag, mein Name ist Müller, ich bin Patient bei Ihnen und möchte meinen Termin am Freitag absagen und einen neuen Termin für nächste Woche vereinbaren, wenn das möglich ist.",
]

# Realistic audio chunk durations (ms)
AUDIO_DURATIONS = [500, 1000, 1500, 2000, 2500, 3000, 4000, 5000]


class MockAudioProcessor:
    """Simulates audio processing for load testing.

    In a real test, this would be replaced with actual AI services.
    This mock adds realistic delays based on audio length.
    """

    def __init__(self, use_real_services: bool = False):
        self.use_real_services = use_real_services
        self._stt_base_latency = 50  # ms
        self._llm_base_latency = 100  # ms
        self._tts_base_latency = 75  # ms

    async def process_audio(self, audio_duration_ms: float, utterance: str) -> PipelineMetrics:
        """Process a simulated audio utterance through the pipeline.

        Args:
            audio_duration_ms: Duration of input audio in ms
            utterance: Text utterance for LLM processing

        Returns:
            Pipeline metrics including latencies
        """
        metrics = PipelineMetrics(
            call_id=f"test-{random.randint(10000, 99999)}",
            audio_duration_ms=audio_duration_ms,
        )

        try:
            # STT Phase - latency proportional to audio length
            stt_start = time.time()
            await self._simulate_stt(audio_duration_ms)
            metrics.stt_latency_ms = (time.time() - stt_start) * 1000

            # LLM Phase - latency proportional to input/output tokens
            llm_start = time.time()
            await self._simulate_llm(utterance)
            metrics.llm_latency_ms = (time.time() - llm_start) * 1000

            # TTS Phase - latency proportional to response length
            tts_start = time.time()
            await self._simulate_tts(len(utterance))
            metrics.tts_latency_ms = (time.time() - tts_start) * 1000

            metrics.total_latency_ms = (
                metrics.stt_latency_ms + metrics.llm_latency_ms + metrics.tts_latency_ms
            )
            metrics.success = True

        except Exception as e:
            metrics.success = False
            metrics.error = str(e)

        return metrics

    async def _simulate_stt(self, audio_duration_ms: float) -> None:
        """Simulate STT processing delay."""
        # STT typically processes faster than real-time
        # ~0.3x real-time for good STT services
        latency = self._stt_base_latency + (audio_duration_ms * 0.3)
        # Add some variance
        latency *= random.uniform(0.8, 1.2)
        await asyncio.sleep(latency / 1000)

    async def _simulate_llm(self, text: str) -> None:
        """Simulate LLM processing delay."""
        # LLM latency depends on input + output tokens
        # ~50ms per 100 tokens for fast models
        input_tokens = len(text.split()) * 1.3  # rough token estimate
        output_tokens = input_tokens * 2  # assume 2x output
        latency = self._llm_base_latency + ((input_tokens + output_tokens) * 0.5)
        latency *= random.uniform(0.8, 1.3)
        await asyncio.sleep(latency / 1000)

    async def _simulate_tts(self, text_length: int) -> None:
        """Simulate TTS processing delay."""
        # TTS latency depends on text length
        # ~10ms per character for good TTS
        latency = self._tts_base_latency + (text_length * 0.5)
        latency *= random.uniform(0.8, 1.2)
        await asyncio.sleep(latency / 1000)


async def simulate_call(
    processor: MockAudioProcessor,
    duration_seconds: float,
    results: LoadTestResults,
) -> None:
    """Simulate a single phone call with multiple turns.

    Args:
        processor: Audio processor instance
        duration_seconds: How long to simulate the call
        results: Shared results object
    """
    end_time = time.time() + duration_seconds

    while time.time() < end_time:
        # Pick random utterance and audio duration
        utterance = random.choice(SAMPLE_UTTERANCES)
        audio_duration = random.choice(AUDIO_DURATIONS)

        # Process through pipeline
        metrics = await processor.process_audio(audio_duration, utterance)

        results.total_requests += 1
        if metrics.success:
            results.successful_requests += 1
        else:
            results.failed_requests += 1

        results.pipeline_metrics.append(metrics)

        # Brief pause between turns (simulates conversation flow)
        await asyncio.sleep(random.uniform(0.5, 1.5))


async def memory_monitor(results: LoadTestResults, interval: float = 1.0) -> None:
    """Monitor memory usage during the test.

    Args:
        results: Shared results object
        interval: Sampling interval in seconds
    """
    if not HAS_PSUTIL:
        return

    process = psutil.Process(os.getpid())

    while True:
        try:
            memory_mb = process.memory_info().rss / 1024 / 1024
            results.memory_samples.append(memory_mb)
            await asyncio.sleep(interval)
        except asyncio.CancelledError:
            break
        except Exception:
            break


async def run_ai_pipeline_test(
    concurrent_calls: int,
    duration_seconds: float,
    ramp_up_seconds: float = 5.0,
) -> LoadTestResults:
    """Run AI pipeline load test.

    Args:
        concurrent_calls: Number of concurrent simulated calls
        duration_seconds: Duration of each call
        ramp_up_seconds: Time to ramp up to full concurrency

    Returns:
        Aggregate test results
    """
    results = LoadTestResults(
        start_time=time.time(),
        concurrent_calls=concurrent_calls,
    )

    processor = MockAudioProcessor()

    # Start memory monitoring
    monitor_task = asyncio.create_task(memory_monitor(results))

    # Create call tasks with staggered start
    delay = ramp_up_seconds / concurrent_calls if concurrent_calls > 1 else 0
    tasks = []

    for i in range(concurrent_calls):
        task = asyncio.create_task(simulate_call(processor, duration_seconds, results))
        tasks.append(task)

        if delay > 0 and i < concurrent_calls - 1:
            await asyncio.sleep(delay)

    # Wait for all calls to complete
    await asyncio.gather(*tasks, return_exceptions=True)

    # Stop monitoring
    monitor_task.cancel()
    try:
        await monitor_task
    except asyncio.CancelledError:
        pass

    results.end_time = time.time()

    # Force garbage collection and record final memory
    gc.collect()
    if HAS_PSUTIL:
        final_memory = psutil.Process(os.getpid()).memory_info().rss / 1024 / 1024
        results.memory_samples.append(final_memory)

    return results


def print_results(results: LoadTestResults) -> None:
    """Print formatted test results."""
    print("\n" + "=" * 70)
    print("AI PIPELINE LOAD TEST RESULTS")
    print("=" * 70)

    print(f"\n📊 Test Summary:")
    print(f"   Duration: {results.duration:.2f}s")
    print(f"   Concurrent Calls: {results.concurrent_calls}")
    print(f"   Total Requests: {results.total_requests}")
    print(f"   Successful: {results.successful_requests}")
    print(f"   Failed: {results.failed_requests}")
    print(f"   Success Rate: {results.success_rate:.1f}%")
    print(f"   Throughput: {results.throughput:.2f} req/s")

    # Latency breakdown
    print(f"\n⏱️  Latency Breakdown (ms):")

    for name, key in [
        ("STT", "stt_latency_ms"),
        ("LLM", "llm_latency_ms"),
        ("TTS", "tts_latency_ms"),
        ("Total", "total_latency_ms"),
    ]:
        stats = results.get_latency_stats(key)
        print(f"\n   {name}:")
        print(f"     Avg: {stats['avg']:.1f}  Min: {stats['min']:.1f}  Max: {stats['max']:.1f}")
        print(f"     p50: {stats['p50']:.1f}  p95: {stats['p95']:.1f}  p99: {stats['p99']:.1f}")

    # Real-time factor analysis
    rtf_values = [m.real_time_factor for m in results.pipeline_metrics if m.success and m.audio_duration_ms > 0]
    if rtf_values:
        print(f"\n📈 Real-Time Factor (< 1.0 = real-time capable):")
        print(f"   Average: {statistics.mean(rtf_values):.2f}x")
        print(f"   95th Percentile: {rtf_values[int(len(rtf_values) * 0.95)]:.2f}x")

        # Check if system can handle real-time
        realtime_capable = sum(1 for r in rtf_values if r < 1.0) / len(rtf_values) * 100
        print(f"   Real-time Capable: {realtime_capable:.1f}% of requests")

    # Memory analysis
    if results.memory_samples:
        print(f"\n💾 Memory Usage (MB):")
        print(f"   Initial: {results.memory_samples[0]:.1f}")
        print(f"   Peak: {max(results.memory_samples):.1f}")
        print(f"   Final: {results.memory_samples[-1]:.1f}")
        print(f"   Growth: {results.memory_samples[-1] - results.memory_samples[0]:.1f}")

    # Error analysis
    errors = [m.error for m in results.pipeline_metrics if m.error]
    if errors:
        print(f"\n⚠️  Errors ({len(errors)} total):")
        error_counts: dict[str, int] = {}
        for err in errors:
            error_counts[err] = error_counts.get(err, 0) + 1

        for err, count in sorted(error_counts.items(), key=lambda x: -x[1])[:5]:
            print(f"   - {err}: {count}")

    # Performance verdict
    print(f"\n{'=' * 70}")
    total_stats = results.get_latency_stats("total_latency_ms")

    if results.success_rate >= 99 and total_stats["p95"] < 500:
        print("✅ EXCELLENT - Pipeline performs well under load")
        print(f"   Can handle {results.concurrent_calls} concurrent calls at {results.throughput:.1f} req/s")
    elif results.success_rate >= 95 and total_stats["p95"] < 1000:
        print("✅ GOOD - Pipeline handles load with acceptable latency")
    elif results.success_rate >= 90:
        print("⚠️  WARNING - Some degradation under load")
        print("   Consider adding more resources or reducing concurrent calls")
    else:
        print("❌ FAILED - Pipeline cannot handle this load")
        print("   Reduce concurrent calls or optimize AI services")

    # Recommendations
    print("\n💡 Recommendations:")
    if total_stats["p95"] > 500:
        print("   - Consider caching LLM responses for common queries")
    if rtf_values and statistics.mean(rtf_values) > 0.8:
        print("   - Pipeline is near real-time limit, optimize STT/TTS")
    if results.memory_samples and max(results.memory_samples) > 1000:
        print("   - High memory usage, consider streaming responses")
    if results.success_rate < 99:
        print("   - Implement retry logic for transient failures")

    print("=" * 70)


async def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="AI Pipeline stress testing for Phone Agent"
    )
    parser.add_argument(
        "-c", "--calls",
        type=int,
        default=5,
        help="Number of concurrent calls (default: 5)",
    )
    parser.add_argument(
        "-d", "--duration",
        type=float,
        default=30.0,
        help="Duration of each call in seconds (default: 30)",
    )
    parser.add_argument(
        "--ramp-up",
        type=float,
        default=5.0,
        help="Ramp-up time in seconds (default: 5)",
    )

    args = parser.parse_args()

    print(f"\n🧠 Starting AI Pipeline Load Test")
    print(f"   Concurrent Calls: {args.calls}")
    print(f"   Call Duration: {args.duration}s")
    print(f"   Ramp-up Time: {args.ramp_up}s")
    print(f"\n   This simulates {args.calls} concurrent calls processing")
    print(f"   audio through STT → LLM → TTS pipeline.\n")

    results = await run_ai_pipeline_test(
        concurrent_calls=args.calls,
        duration_seconds=args.duration,
        ramp_up_seconds=args.ramp_up,
    )

    print_results(results)


if __name__ == "__main__":
    asyncio.run(main())
