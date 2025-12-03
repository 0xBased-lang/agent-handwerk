"""Tests for German dialect detection and STT routing.

Tests the dialect detector's ability to identify:
- Schwäbisch (Alemannic)
- Bavarian
- Low German (Plattdeutsch)
- Standard German (Hochdeutsch)
"""

import pytest

from phone_agent.ai.dialect_detector import (
    ALEMANNIC_PATTERNS,
    BAVARIAN_PATTERNS,
    DIALECT_MODELS,
    LOW_GERMAN_PATTERNS,
    DialectResult,
    GermanDialectDetector,
    detect_german_dialect,
    get_model_for_dialect,
)


class TestDialectPatterns:
    """Test dialect pattern matching."""

    def test_alemannic_patterns_exist(self):
        """Verify Alemannic patterns are defined."""
        assert len(ALEMANNIC_PATTERNS) > 10
        # Patterns are now tuples of (compiled_pattern, feature)
        assert any("han" in p.pattern for p, _ in ALEMANNIC_PATTERNS)
        assert any("mädle" in p.pattern for p, _ in ALEMANNIC_PATTERNS)

    def test_bavarian_patterns_exist(self):
        """Verify Bavarian patterns are defined."""
        assert len(BAVARIAN_PATTERNS) > 10
        assert any("hob" in p.pattern for p, _ in BAVARIAN_PATTERNS)
        assert any("servus" in p.pattern for p, _ in BAVARIAN_PATTERNS)

    def test_low_german_patterns_exist(self):
        """Verify Low German patterns are defined."""
        assert len(LOW_GERMAN_PATTERNS) > 5
        assert any("moin" in p.pattern for p, _ in LOW_GERMAN_PATTERNS)


class TestDialectDetectorInit:
    """Test dialect detector initialization."""

    def test_default_init(self):
        """Test default initialization."""
        detector = GermanDialectDetector()
        assert detector.probe_duration == 3.0
        assert detector.confidence_threshold == 0.6

    def test_custom_init(self):
        """Test custom initialization."""
        detector = GermanDialectDetector(
            probe_duration=5.0,
            confidence_threshold=0.8,
        )
        assert detector.probe_duration == 5.0
        assert detector.confidence_threshold == 0.8


class TestSchwaebischDetection:
    """Test Schwäbisch (Swabian) dialect detection."""

    @pytest.fixture
    def detector(self):
        return GermanDialectDetector()

    @pytest.mark.parametrize(
        "text,expected_dialect",
        [
            # Classic Schwäbisch phrases
            ("I han koi Zeit", "de_alemannic"),
            ("Des isch aber schee", "de_alemannic"),
            ("Wo goht's na?", "de_alemannic"),
            ("I han a Mädle gsehe", "de_alemannic"),
            ("Des kannsch net macha", "de_alemannic"),
            ("A bissle schwätza", "de_alemannic"),
            # Mixed Schwäbisch
            ("Ich habe heute i han gsagt", "de_alemannic"),
            # Schwäbisch vocabulary
            ("Mir hent Grombira gessa", "de_alemannic"),
            ("Komm, mir lugga des a", "de_alemannic"),
            ("Heut muss i schaffe", "de_alemannic"),
        ],
    )
    def test_schwaebisch_phrases(self, detector, text, expected_dialect):
        """Test detection of Schwäbisch phrases."""
        result = detector.detect_from_text(text)
        assert result.dialect == expected_dialect
        assert result.confidence > 0.5
        assert len(result.features_detected) > 0

    def test_schwaebisch_uses_swiss_model(self, detector):
        """Test that Schwäbisch routes to Swiss German model."""
        result = detector.detect_from_text("I han des net gwusst")
        assert result.recommended_model == "Flurin17/whisper-large-v3-turbo-swiss-german"


class TestBavarianDetection:
    """Test Bavarian dialect detection."""

    @pytest.fixture
    def detector(self):
        return GermanDialectDetector()

    @pytest.mark.parametrize(
        "text,expected_dialect",
        [
            # Classic Bavarian phrases
            ("I hob koa Zeit ned", "de_bavarian"),
            ("Servus, wia geht's?", "de_bavarian"),
            ("Des is fei gscheid", "de_bavarian"),
            ("Ja mei, des is scho so", "de_bavarian"),
            ("Griaß di, Bua!", "de_bavarian"),
            # Bavarian vocabulary
            ("I mog a Deandl", "de_bavarian"),
            ("Wo bist heid?", "de_bavarian"),
        ],
    )
    def test_bavarian_phrases(self, detector, text, expected_dialect):
        """Test detection of Bavarian phrases."""
        result = detector.detect_from_text(text)
        assert result.dialect == expected_dialect
        assert len(result.features_detected) > 0


class TestLowGermanDetection:
    """Test Low German (Plattdeutsch) detection."""

    @pytest.fixture
    def detector(self):
        return GermanDialectDetector()

    @pytest.mark.parametrize(
        "text,expected_dialect",
        [
            # Low German greetings and phrases
            ("Moin moin, wie geht's?", "de_low"),
            ("Ik kann dat nich", "de_low"),
            ("Wat is dat denn?", "de_low"),
            ("Snacken wi plattdüütsch", "de_low"),
        ],
    )
    def test_low_german_phrases(self, detector, text, expected_dialect):
        """Test detection of Low German phrases."""
        result = detector.detect_from_text(text)
        assert result.dialect == expected_dialect


class TestStandardGermanDetection:
    """Test Standard German (Hochdeutsch) detection."""

    @pytest.fixture
    def detector(self):
        return GermanDialectDetector()

    @pytest.mark.parametrize(
        "text",
        [
            # Standard German phrases
            "Ich habe keine Zeit",
            "Das ist sehr schön",
            "Wo gehst du hin?",
            "Ich möchte einen Termin vereinbaren",
            "Guten Tag, wie kann ich Ihnen helfen?",
            "Vielen Dank für Ihren Anruf",
            "Die Praxis ist heute geschlossen",
        ],
    )
    def test_standard_german_phrases(self, detector, text):
        """Test that standard German is correctly identified."""
        result = detector.detect_from_text(text)
        assert result.dialect == "de_standard"
        assert result.confidence > 0.8  # High confidence for standard
        assert len(result.features_detected) == 0  # No dialect features


class TestDialectResult:
    """Test DialectResult dataclass."""

    def test_dialect_result_creation(self):
        """Test creating a DialectResult."""
        result = DialectResult(
            dialect="de_alemannic",
            confidence=0.85,
            features_detected=["alemannic_verb", "alemannic_word"],
            recommended_model="Flurin17/whisper-large-v3-turbo-swiss-german",
        )
        assert result.dialect == "de_alemannic"
        assert result.confidence == 0.85
        assert len(result.features_detected) == 2


class TestModelRecommendations:
    """Test model recommendations for dialects."""

    def test_dialect_models_defined(self):
        """Test that all dialects have model recommendations."""
        assert "de_standard" in DIALECT_MODELS
        assert "de_alemannic" in DIALECT_MODELS
        assert "de_bavarian" in DIALECT_MODELS
        assert "de_low" in DIALECT_MODELS

    def test_get_model_for_dialect(self):
        """Test model lookup function."""
        assert get_model_for_dialect("de_standard") == "primeline/whisper-large-v3-german"
        assert (
            get_model_for_dialect("de_alemannic")
            == "Flurin17/whisper-large-v3-turbo-swiss-german"
        )

    def test_unknown_dialect_fallback(self):
        """Test fallback for unknown dialect."""
        model = get_model_for_dialect("de_unknown")
        assert model == "primeline/whisper-large-v3-german"


class TestConvenienceFunctions:
    """Test convenience functions."""

    def test_detect_german_dialect_function(self):
        """Test the quick detection function."""
        dialect = detect_german_dialect("I han des net gwusst")
        assert dialect == "de_alemannic"

    def test_detect_standard_german(self):
        """Test detecting standard German."""
        dialect = detect_german_dialect("Ich habe das nicht gewusst")
        assert dialect == "de_standard"


class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    @pytest.fixture
    def detector(self):
        return GermanDialectDetector()

    def test_empty_text(self, detector):
        """Test handling of empty text."""
        result = detector.detect_from_text("")
        assert result.dialect == "de_standard"
        assert result.confidence > 0.8

    def test_mixed_dialect_text(self, detector):
        """Test text with mixed dialect features."""
        # Contains both Alemannic and standard features
        text = "I han gesagt, dass ich komme. Net heut, aber morgen."
        result = detector.detect_from_text(text)
        # Should lean toward dialect if features detected
        assert result.dialect in ["de_alemannic", "de_standard"]

    def test_case_insensitive(self, detector):
        """Test that detection is case-insensitive."""
        result_lower = detector.detect_from_text("i han koi zeit")
        result_upper = detector.detect_from_text("I HAN KOI ZEIT")
        assert result_lower.dialect == result_upper.dialect

    def test_confidence_threshold(self):
        """Test confidence threshold behavior."""
        detector = GermanDialectDetector(confidence_threshold=0.9)
        # Text with weak dialect signal
        result = detector.detect_from_text("Ich muss heute schaffe gehen")
        # Should fall back to standard if below threshold
        if result.confidence < 0.9:
            assert result.dialect == "de_standard"


class TestHealthcareContext:
    """Test dialect detection in healthcare context."""

    @pytest.fixture
    def detector(self):
        return GermanDialectDetector()

    @pytest.mark.parametrize(
        "text,expected_dialect",
        [
            # Schwäbisch patient phrases
            ("I han a Wehwehle am Bauch", "de_alemannic"),
            ("Mir isch net gut, i han Kopfweh", "de_alemannic"),
            ("I brauch a Rezept für mei Mädle", "de_alemannic"),
            # Standard German patient phrases
            ("Ich habe Bauchschmerzen", "de_standard"),
            ("Ich brauche einen Termin beim Arzt", "de_standard"),
        ],
    )
    def test_healthcare_phrases(self, detector, text, expected_dialect):
        """Test dialect detection for healthcare-related phrases."""
        result = detector.detect_from_text(text)
        assert result.dialect == expected_dialect
