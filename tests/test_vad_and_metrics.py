"""Tests for VAD and latency metrics modules."""

import numpy as np
import pytest
import time

from phone_agent.ai.vad import (
    SimpleVAD,
    VADSegment,
    VADFrame,
    VADFactory,
    get_vad,
)
from phone_agent.core.metrics import (
    LatencyMetrics,
    ComponentMetrics,
    TurnMetrics,
    get_metrics,
    reset_metrics,
)


class TestSimpleVAD:
    """Tests for SimpleVAD."""

    def test_init_default(self):
        """Test default initialization."""
        vad = SimpleVAD()
        assert vad.threshold == 0.02
        assert vad.min_speech_duration == 0.1
        assert vad.min_silence_duration == 0.3

    def test_init_custom(self):
        """Test custom initialization."""
        vad = SimpleVAD(threshold=0.05, min_speech_duration=0.2)
        assert vad.threshold == 0.05
        assert vad.min_speech_duration == 0.2

    def test_is_speech_silence(self):
        """Test silence detection."""
        vad = SimpleVAD(threshold=0.02)
        # Generate near-silent audio
        audio = np.zeros(1024, dtype=np.float32)
        is_speech, confidence = vad.is_speech(audio)
        assert not is_speech
        assert confidence == 0.0

    def test_is_speech_loud(self):
        """Test speech detection with loud audio."""
        vad = SimpleVAD(threshold=0.02)
        # Generate loud audio
        audio = np.random.randn(1024).astype(np.float32) * 0.5
        is_speech, confidence = vad.is_speech(audio)
        assert is_speech
        assert confidence > 0.0

    def test_is_speech_borderline(self):
        """Test borderline audio."""
        vad = SimpleVAD(threshold=0.02)
        # Generate audio just above threshold
        audio = np.ones(1024, dtype=np.float32) * 0.025
        is_speech, confidence = vad.is_speech(audio)
        assert is_speech

    def test_reset(self):
        """Test reset functionality."""
        vad = SimpleVAD()
        vad._speech_frames = 10
        vad._silence_frames = 5
        vad.reset()
        assert vad._speech_frames == 0
        assert vad._silence_frames == 0


class TestVADFactory:
    """Tests for VADFactory."""

    def test_create_simple(self):
        """Test creating simple VAD."""
        vad = VADFactory.create("simple", threshold=0.03)
        assert isinstance(vad, SimpleVAD)
        assert vad.threshold == 0.03

    def test_get_vad_simple(self):
        """Test get_vad convenience function."""
        vad = get_vad("simple")
        assert isinstance(vad, SimpleVAD)

    def test_create_unknown_raises(self):
        """Test that unknown backend raises error."""
        with pytest.raises(ValueError, match="Unknown VAD backend"):
            VADFactory.create("unknown")


class TestVADSegment:
    """Tests for VADSegment dataclass."""

    def test_duration(self):
        """Test duration property."""
        segment = VADSegment(start_time=1.0, end_time=3.5, confidence=0.9)
        assert segment.duration == 2.5

    def test_creation(self):
        """Test segment creation."""
        segment = VADSegment(start_time=0.0, end_time=1.0, confidence=0.95)
        assert segment.start_time == 0.0
        assert segment.end_time == 1.0
        assert segment.confidence == 0.95


class TestVADFrame:
    """Tests for VADFrame dataclass."""

    def test_creation(self):
        """Test frame creation."""
        audio = np.zeros(512, dtype=np.float32)
        frame = VADFrame(is_speech=True, confidence=0.8, audio=audio)
        assert frame.is_speech
        assert frame.confidence == 0.8
        assert len(frame.audio) == 512


class TestComponentMetrics:
    """Tests for ComponentMetrics."""

    def test_record(self):
        """Test recording samples."""
        metrics = ComponentMetrics(name="test")
        metrics.record(0.5)
        metrics.record(1.0)
        metrics.record(1.5)

        assert metrics.total_calls == 3
        assert metrics.total_time == 3.0
        assert len(metrics.samples) == 3

    def test_mean(self):
        """Test mean calculation."""
        metrics = ComponentMetrics(name="test")
        metrics.record(1.0)
        metrics.record(2.0)
        metrics.record(3.0)

        assert metrics.mean == 2.0

    def test_median(self):
        """Test median calculation."""
        metrics = ComponentMetrics(name="test")
        for i in [1, 2, 3, 4, 5]:
            metrics.record(float(i))

        assert metrics.median == 3.0

    def test_percentiles(self):
        """Test percentile calculations."""
        metrics = ComponentMetrics(name="test")
        for i in range(100):
            metrics.record(float(i))

        assert metrics.p90 == 90.0
        assert metrics.p99 == 99.0

    def test_min_max(self):
        """Test min and max."""
        metrics = ComponentMetrics(name="test")
        metrics.record(5.0)
        metrics.record(2.0)
        metrics.record(8.0)

        assert metrics.min == 2.0
        assert metrics.max == 8.0

    def test_to_dict(self):
        """Test dictionary conversion."""
        metrics = ComponentMetrics(name="stt")
        metrics.record(0.5)

        d = metrics.to_dict()
        assert d["name"] == "stt"
        assert d["calls"] == 1
        assert "mean_ms" in d
        assert "p90_ms" in d

    def test_sample_limit(self):
        """Test that samples are limited to 1000."""
        metrics = ComponentMetrics(name="test")
        for i in range(1500):
            metrics.record(1.0)

        assert len(metrics.samples) == 1000
        assert metrics.total_calls == 1500


class TestTurnMetrics:
    """Tests for TurnMetrics."""

    def test_creation(self):
        """Test turn metrics creation."""
        from datetime import datetime

        turn = TurnMetrics(
            turn_id=1,
            timestamp=datetime.now(),
            stt_time=0.5,
            llm_time=1.0,
            tts_time=0.3,
            total_time=1.8,
            audio_duration=2.0,
            response_length=50,
        )

        assert turn.turn_id == 1
        assert turn.stt_time == 0.5
        assert turn.total_time == 1.8

    def test_processing_ratio(self):
        """Test processing ratio calculation."""
        from datetime import datetime

        turn = TurnMetrics(
            turn_id=1,
            timestamp=datetime.now(),
            total_time=2.0,
            audio_duration=4.0,
        )

        assert turn.processing_ratio == 0.5

    def test_to_dict(self):
        """Test dictionary conversion."""
        from datetime import datetime

        turn = TurnMetrics(
            turn_id=1,
            timestamp=datetime.now(),
            stt_time=0.5,
            llm_time=1.0,
            tts_time=0.3,
        )

        d = turn.to_dict()
        assert d["turn_id"] == 1
        assert "stt_ms" in d
        assert "llm_ms" in d


class TestLatencyMetrics:
    """Tests for LatencyMetrics."""

    @pytest.fixture
    def metrics(self):
        """Create fresh metrics instance."""
        return LatencyMetrics()

    def test_record(self, metrics):
        """Test recording component timing."""
        metrics.record("stt", 0.5)
        metrics.record("stt", 0.6)

        component = metrics.get_component("stt")
        assert component.total_calls == 2
        assert component.mean == 0.55

    def test_measure_context_manager(self, metrics):
        """Test measure context manager."""
        with metrics.measure("test"):
            time.sleep(0.01)

        component = metrics.get_component("test")
        assert component.total_calls == 1
        assert component.mean >= 0.01

    def test_record_turn(self, metrics):
        """Test recording complete turn."""
        turn = metrics.record_turn(
            stt_time=0.5,
            llm_time=1.0,
            tts_time=0.3,
            audio_duration=2.0,
            response_length=50,
        )

        assert turn.turn_id == 1
        assert turn.stt_time == 0.5
        assert turn.total_time == 1.8

        # Check components were updated
        assert metrics.get_component("stt").total_calls == 1
        assert metrics.get_component("llm").total_calls == 1
        assert metrics.get_component("e2e").total_calls == 1

    def test_get_report_text(self, metrics):
        """Test text report generation."""
        metrics.record("stt", 0.5)
        metrics.record("llm", 1.0)

        report = metrics.get_report(format="text")
        assert "PHONE AGENT LATENCY METRICS" in report
        assert "stt" in report
        assert "llm" in report

    def test_get_report_json(self, metrics):
        """Test JSON report generation."""
        metrics.record("stt", 0.5)

        report = metrics.get_report(format="json")
        assert isinstance(report, dict)
        assert "components" in report
        assert "stt" in report["components"]

    def test_reset(self, metrics):
        """Test metrics reset."""
        metrics.record("stt", 0.5)
        metrics.record_turn(stt_time=0.5)

        metrics.reset()

        assert metrics.get_component("stt").total_calls == 0


class TestGlobalMetrics:
    """Tests for global metrics instance."""

    def test_get_metrics_singleton(self):
        """Test that get_metrics returns same instance."""
        m1 = get_metrics()
        m2 = get_metrics()
        assert m1 is m2

    def test_reset_metrics(self):
        """Test global metrics reset."""
        metrics = get_metrics()
        metrics.record("stt", 1.0)  # Use standard component

        reset_metrics()

        # After reset, standard components are re-initialized with 0 calls
        assert metrics.get_component("stt").total_calls == 0
