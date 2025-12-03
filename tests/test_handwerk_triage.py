"""Simple triage workflow tests for Handwerk.

Tests the basic keyword-based triage from workflows.py.
"""
import pytest

from phone_agent.industry.handwerk import (
    UrgencyLevel,
    TradeCategory,
    perform_triage,
    is_emergency,
    detect_trade_category,
)


class TestEmergencyDetection:
    """Tests for emergency keyword detection."""

    # Gas emergencies
    @pytest.mark.parametrize("text", [
        "Es riecht nach Gas",
        "Ich rieche Gasgeruch in der Wohnung",
        "Gasleck in der Küche",
        "Gas strömt aus",
    ])
    def test_gas_emergency(self, text):
        """Test gas emergency detection."""
        assert is_emergency(text)

    # Water emergencies
    @pytest.mark.parametrize("text", [
        "Das Wasserrohr ist geplatzt",
        "Wasserrohrbruch im Keller",
        "Wasser spritzt aus der Leitung",
        "Rohr geplatzt, Wasser überall",
    ])
    def test_water_emergency(self, text):
        """Test water emergency detection."""
        assert is_emergency(text)

    # Electrical emergencies
    @pytest.mark.parametrize("text", [
        "Ein Kabel brennt",
        "Steckdose raucht",
        "Kurzschluss mit Funken",
        "Es brennt am Stromkasten",
    ])
    def test_electrical_emergency(self, text):
        """Test electrical emergency detection."""
        assert is_emergency(text)

    # Non-emergencies
    @pytest.mark.parametrize("text", [
        "Der Wasserhahn tropft",
        "Ich brauche einen Wartungstermin",
        "Die Heizung macht Geräusche",
        "Können Sie mir ein Angebot machen?",
        "Wann können Sie vorbeikommen?",
    ])
    def test_not_emergency(self, text):
        """Test non-emergency situations."""
        assert not is_emergency(text)


class TestTradeCategoryDetection:
    """Tests for trade category detection."""

    # SHK (Sanitär, Heizung, Klima)
    @pytest.mark.parametrize("text,expected", [
        ("Die Heizung ist kaputt", TradeCategory.SHK),
        ("Wasserhahn tropft", TradeCategory.SHK),
        ("Toilette verstopft", TradeCategory.SHK),
        ("Klimaanlage funktioniert nicht", TradeCategory.SHK),
        ("Therme defekt", TradeCategory.SHK),
        ("Warmwasser kommt nicht", TradeCategory.SHK),
    ])
    def test_shk_category(self, text, expected):
        """Test SHK category detection."""
        assert detect_trade_category(text) == expected

    # Electrical
    @pytest.mark.parametrize("text,expected", [
        ("Steckdose funktioniert nicht", TradeCategory.ELEKTRO),
        ("Lichtschalter defekt", TradeCategory.ELEKTRO),
        ("Sicherung fliegt immer raus", TradeCategory.ELEKTRO),
        ("Brauche neue Steckdosen", TradeCategory.ELEKTRO),
    ])
    def test_elektro_category(self, text, expected):
        """Test electrical category detection."""
        assert detect_trade_category(text) == expected

    # Locksmith
    @pytest.mark.parametrize("text,expected", [
        ("Ich habe mich ausgesperrt", TradeCategory.SCHLOSSER),
        ("Schlüssel abgebrochen", TradeCategory.SCHLOSSER),
        ("Türschloss klemmt", TradeCategory.SCHLOSSER),
        ("Neues Schloss einbauen", TradeCategory.SCHLOSSER),
    ])
    def test_schlosser_category(self, text, expected):
        """Test locksmith category detection."""
        assert detect_trade_category(text) == expected


class TestTriageWorkflow:
    """Tests for the complete triage workflow."""

    def test_emergency_triage(self):
        """Test emergency triage result."""
        result = perform_triage("Es riecht stark nach Gas in der Küche")

        assert result.urgency == UrgencyLevel.SICHERHEIT
        assert result.is_emergency is True
        assert "112" in result.recommended_action or "Notdienst" in result.recommended_action

    def test_urgent_triage(self):
        """Test urgent triage result."""
        result = perform_triage("Die Toilette ist komplett verstopft")

        assert result.urgency == UrgencyLevel.DRINGEND
        assert result.trade_category == TradeCategory.SHK

    def test_normal_triage(self):
        """Test normal triage result."""
        result = perform_triage("Der Wasserhahn in der Küche tropft ein bisschen")

        assert result.urgency in [UrgencyLevel.NORMAL, UrgencyLevel.ROUTINE]
        assert result.trade_category == TradeCategory.SHK

    def test_routine_triage(self):
        """Test routine/maintenance triage result."""
        result = perform_triage("Ich möchte einen Termin für die Heizungswartung")

        assert result.urgency == UrgencyLevel.ROUTINE
        assert result.trade_category == TradeCategory.SHK

    def test_triage_returns_recommended_action(self):
        """Test that triage always returns a recommended action."""
        test_cases = [
            "Die Heizung geht nicht",
            "Steckdose kaputt",
            "Wartungstermin",
            "Gasgeruch",
        ]

        for text in test_cases:
            result = perform_triage(text)
            assert result.recommended_action is not None
            assert len(result.recommended_action) > 0

    def test_triage_returns_trade_category(self):
        """Test that triage always returns a trade category."""
        test_cases = [
            "Heizung defekt",
            "Steckdose funktioniert nicht",
            "Schlüssel abgebrochen",
        ]

        for text in test_cases:
            result = perform_triage(text)
            assert result.trade_category is not None
            assert result.trade_category in TradeCategory


class TestUrgencyLevels:
    """Tests for urgency level mappings."""

    def test_urgency_level_values(self):
        """Test urgency level enum values."""
        assert UrgencyLevel.SICHERHEIT.value == "sicherheit"
        assert UrgencyLevel.DRINGEND.value == "dringend"
        assert UrgencyLevel.NORMAL.value == "normal"
        assert UrgencyLevel.ROUTINE.value == "routine"

    def test_urgency_level_ordering(self):
        """Test that urgency levels have logical ordering."""
        # SICHERHEIT is most urgent, ROUTINE is least urgent
        levels = [UrgencyLevel.SICHERHEIT, UrgencyLevel.DRINGEND,
                  UrgencyLevel.NORMAL, UrgencyLevel.ROUTINE]

        # Just verify we have 4 distinct levels
        assert len(set(levels)) == 4
