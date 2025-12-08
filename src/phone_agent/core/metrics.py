"""Latency metrics collection and reporting for the phone agent pipeline.

Provides:
- Per-component timing (STT, LLM, TTS, VAD)
- End-to-end latency tracking
- Percentile calculations (p50, p90, p99)
- Historical data storage
- CLI and JSON reporting

Usage:
    from phone_agent.core.metrics import get_metrics, LatencyMetrics

    metrics = get_metrics()

    # Record component timing
    with metrics.measure("stt"):
        result = await stt.transcribe(audio)

    # Or manually
    metrics.record("llm", duration_seconds=1.5)

    # Get report
    report = metrics.get_report()
    print(report)
"""

from __future__ import annotations

import statistics
import threading
import time
from collections import defaultdict
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime
from typing import Iterator

from itf_shared import get_logger

log = get_logger(__name__)


@dataclass
class ComponentMetrics:
    """Metrics for a single component."""

    name: str
    samples: list[float] = field(default_factory=list)
    total_calls: int = 0
    total_time: float = 0.0
    last_recorded: datetime | None = None

    def record(self, duration: float) -> None:
        """Record a timing sample."""
        self.samples.append(duration)
        self.total_calls += 1
        self.total_time += duration
        self.last_recorded = datetime.now()

        # Keep only last 1000 samples for memory efficiency
        if len(self.samples) > 1000:
            self.samples = self.samples[-1000:]

    @property
    def mean(self) -> float:
        """Mean latency in seconds."""
        return statistics.mean(self.samples) if self.samples else 0.0

    @property
    def median(self) -> float:
        """Median latency (p50) in seconds."""
        return statistics.median(self.samples) if self.samples else 0.0

    @property
    def p90(self) -> float:
        """90th percentile latency in seconds."""
        if not self.samples:
            return 0.0
        sorted_samples = sorted(self.samples)
        idx = int(len(sorted_samples) * 0.9)
        return sorted_samples[min(idx, len(sorted_samples) - 1)]

    @property
    def p99(self) -> float:
        """99th percentile latency in seconds."""
        if not self.samples:
            return 0.0
        sorted_samples = sorted(self.samples)
        idx = int(len(sorted_samples) * 0.99)
        return sorted_samples[min(idx, len(sorted_samples) - 1)]

    @property
    def min(self) -> float:
        """Minimum latency in seconds."""
        return min(self.samples) if self.samples else 0.0

    @property
    def max(self) -> float:
        """Maximum latency in seconds."""
        return max(self.samples) if self.samples else 0.0

    @property
    def stddev(self) -> float:
        """Standard deviation in seconds."""
        return statistics.stdev(self.samples) if len(self.samples) > 1 else 0.0

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "name": self.name,
            "calls": self.total_calls,
            "total_time_s": round(self.total_time, 3),
            "mean_ms": round(self.mean * 1000, 1),
            "median_ms": round(self.median * 1000, 1),
            "p90_ms": round(self.p90 * 1000, 1),
            "p99_ms": round(self.p99 * 1000, 1),
            "min_ms": round(self.min * 1000, 1),
            "max_ms": round(self.max * 1000, 1),
            "stddev_ms": round(self.stddev * 1000, 1),
        }


@dataclass
class TurnMetrics:
    """Metrics for a complete conversation turn."""

    turn_id: int
    timestamp: datetime
    stt_time: float = 0.0
    llm_time: float = 0.0
    tts_time: float = 0.0
    vad_time: float = 0.0
    first_byte_time: float = 0.0  # Time to first TTS byte (streaming)
    total_time: float = 0.0
    audio_duration: float = 0.0  # Input audio duration
    response_length: int = 0  # Response character count

    @property
    def processing_ratio(self) -> float:
        """Ratio of processing time to audio duration."""
        if self.audio_duration > 0:
            return self.total_time / self.audio_duration
        return 0.0

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "turn_id": self.turn_id,
            "timestamp": self.timestamp.isoformat(),
            "stt_ms": round(self.stt_time * 1000, 1),
            "llm_ms": round(self.llm_time * 1000, 1),
            "tts_ms": round(self.tts_time * 1000, 1),
            "vad_ms": round(self.vad_time * 1000, 1),
            "first_byte_ms": round(self.first_byte_time * 1000, 1),
            "total_ms": round(self.total_time * 1000, 1),
            "audio_duration_s": round(self.audio_duration, 2),
            "response_chars": self.response_length,
            "processing_ratio": round(self.processing_ratio, 2),
        }


class LatencyMetrics:
    """Thread-safe latency metrics collector.

    Tracks timing for each component of the phone agent pipeline:
    - stt: Speech-to-text transcription
    - llm: Language model generation
    - tts: Text-to-speech synthesis
    - vad: Voice activity detection
    - e2e: End-to-end turn latency
    """

    def __init__(self) -> None:
        """Initialize metrics collector."""
        self._lock = threading.Lock()
        self._components: dict[str, ComponentMetrics] = {}
        self._turns: list[TurnMetrics] = []
        self._turn_counter = 0
        self._start_time = datetime.now()

        # Initialize standard components
        for name in ["stt", "llm", "tts", "vad", "e2e", "first_byte"]:
            self._components[name] = ComponentMetrics(name=name)

    def record(self, component: str, duration: float) -> None:
        """Record a timing sample for a component.

        Args:
            component: Component name (stt, llm, tts, vad, e2e)
            duration: Duration in seconds
        """
        with self._lock:
            if component not in self._components:
                self._components[component] = ComponentMetrics(name=component)
            self._components[component].record(duration)

    @contextmanager
    def measure(self, component: str) -> Iterator[None]:
        """Context manager to measure and record timing.

        Args:
            component: Component name

        Yields:
            None

        Example:
            with metrics.measure("stt"):
                result = await stt.transcribe(audio)
        """
        start = time.perf_counter()
        try:
            yield
        finally:
            duration = time.perf_counter() - start
            self.record(component, duration)

    def record_turn(
        self,
        stt_time: float = 0.0,
        llm_time: float = 0.0,
        tts_time: float = 0.0,
        vad_time: float = 0.0,
        first_byte_time: float = 0.0,
        audio_duration: float = 0.0,
        response_length: int = 0,
    ) -> TurnMetrics:
        """Record a complete conversation turn.

        Args:
            stt_time: STT duration in seconds
            llm_time: LLM duration in seconds
            tts_time: TTS duration in seconds
            vad_time: VAD duration in seconds
            first_byte_time: Time to first TTS byte in seconds
            audio_duration: Input audio duration in seconds
            response_length: Response character count

        Returns:
            TurnMetrics object
        """
        with self._lock:
            self._turn_counter += 1
            turn = TurnMetrics(
                turn_id=self._turn_counter,
                timestamp=datetime.now(),
                stt_time=stt_time,
                llm_time=llm_time,
                tts_time=tts_time,
                vad_time=vad_time,
                first_byte_time=first_byte_time,
                total_time=stt_time + llm_time + tts_time,
                audio_duration=audio_duration,
                response_length=response_length,
            )
            self._turns.append(turn)

            # Keep only last 100 turns
            if len(self._turns) > 100:
                self._turns = self._turns[-100:]

            # Record to component metrics
            if stt_time > 0:
                self._components["stt"].record(stt_time)
            if llm_time > 0:
                self._components["llm"].record(llm_time)
            if tts_time > 0:
                self._components["tts"].record(tts_time)
            if vad_time > 0:
                self._components["vad"].record(vad_time)
            if first_byte_time > 0:
                self._components["first_byte"].record(first_byte_time)
            if turn.total_time > 0:
                self._components["e2e"].record(turn.total_time)

            return turn

    def get_component(self, name: str) -> ComponentMetrics | None:
        """Get metrics for a specific component."""
        with self._lock:
            return self._components.get(name)

    def get_report(self, format: str = "text") -> str | dict:
        """Generate a metrics report.

        Args:
            format: Output format ("text" or "json")

        Returns:
            Formatted report
        """
        with self._lock:
            uptime = (datetime.now() - self._start_time).total_seconds()

            report_data = {
                "uptime_s": round(uptime, 1),
                "total_turns": len(self._turns),
                "components": {
                    name: metrics.to_dict()
                    for name, metrics in self._components.items()
                    if metrics.total_calls > 0
                },
                "recent_turns": [t.to_dict() for t in self._turns[-5:]],
            }

            if format == "json":
                return report_data

            # Text format
            lines = [
                "=" * 60,
                "  PHONE AGENT LATENCY METRICS",
                "=" * 60,
                f"  Uptime: {uptime:.1f}s | Turns: {len(self._turns)}",
                "",
                "  COMPONENT LATENCIES (ms)",
                "-" * 60,
                f"  {'Component':<12} {'Calls':>8} {'Mean':>8} {'P50':>8} {'P90':>8} {'P99':>8}",
                "-" * 60,
            ]

            for name, metrics in sorted(self._components.items()):
                if metrics.total_calls > 0:
                    lines.append(
                        f"  {name:<12} {metrics.total_calls:>8} "
                        f"{metrics.mean * 1000:>7.1f} {metrics.median * 1000:>7.1f} "
                        f"{metrics.p90 * 1000:>7.1f} {metrics.p99 * 1000:>7.1f}"
                    )

            lines.extend([
                "",
                "  RECENT TURNS",
                "-" * 60,
            ])

            for turn in self._turns[-5:]:
                lines.append(
                    f"  Turn {turn.turn_id}: "
                    f"STT={turn.stt_time * 1000:.0f}ms "
                    f"LLM={turn.llm_time * 1000:.0f}ms "
                    f"TTS={turn.tts_time * 1000:.0f}ms "
                    f"Total={turn.total_time * 1000:.0f}ms"
                )

            lines.append("=" * 60)

            return "\n".join(lines)

    def reset(self) -> None:
        """Reset all metrics."""
        with self._lock:
            self._components.clear()
            self._turns.clear()
            self._turn_counter = 0
            self._start_time = datetime.now()

            # Re-initialize standard components
            for name in ["stt", "llm", "tts", "vad", "e2e", "first_byte"]:
                self._components[name] = ComponentMetrics(name=name)


# Global metrics instance
_metrics: LatencyMetrics | None = None
_metrics_lock = threading.Lock()


def get_metrics() -> LatencyMetrics:
    """Get the global metrics instance."""
    global _metrics
    with _metrics_lock:
        if _metrics is None:
            _metrics = LatencyMetrics()
        return _metrics


def reset_metrics() -> None:
    """Reset the global metrics instance."""
    global _metrics
    with _metrics_lock:
        if _metrics is not None:
            _metrics.reset()
