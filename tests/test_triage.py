"""Tests for healthcare triage logic."""

import pytest

from phone_agent.industry.gesundheit.workflows import (
    perform_triage,
    TriageLevel,
)


class TestTriage:
    """Test triage classification."""

    def test_akut_brustschmerzen(self):
        """Test emergency detection for chest pain."""
        result = perform_triage("Ich habe starke Brustschmerzen")
        assert result.level == TriageLevel.AKUT
        assert "brustschmerzen" in result.keywords_matched
        assert result.confidence >= 0.9

    def test_akut_atemnot(self):
        """Test emergency detection for breathing problems."""
        result = perform_triage("Ich bekomme keine Luft, habe Atemnot")
        assert result.level == TriageLevel.AKUT
        assert "atemnot" in result.keywords_matched

    def test_akut_bewusstlos(self):
        """Test emergency detection for unconsciousness."""
        result = perform_triage("Mein Mann ist gerade bewusstlos geworden")
        assert result.level == TriageLevel.AKUT

    def test_dringend_hohes_fieber(self):
        """Test urgent detection for high fever."""
        result = perform_triage("Mein Kind hat hohes Fieber über 39 Grad")
        assert result.level == TriageLevel.DRINGEND
        assert any("fieber" in kw for kw in result.keywords_matched)

    def test_dringend_starke_schmerzen(self):
        """Test urgent detection for severe pain."""
        result = perform_triage("Ich habe unerträgliche Schmerzen im Rücken")
        assert result.level == TriageLevel.DRINGEND

    def test_normal_vorsorge(self):
        """Test normal classification for checkup."""
        result = perform_triage("Ich möchte einen Termin zur Vorsorgeuntersuchung")
        assert result.level == TriageLevel.NORMAL
        assert "vorsorge" in result.keywords_matched

    def test_normal_rezept(self):
        """Test normal classification for prescription."""
        result = perform_triage("Ich brauche ein Wiederholungsrezept für mein Blutdruckmittel")
        assert result.level == TriageLevel.NORMAL

    def test_beratung_oeffnungszeiten(self):
        """Test advice classification for opening hours."""
        result = perform_triage("Wann haben Sie Sprechzeiten?")
        assert result.level == TriageLevel.BERATUNG

    def test_beratung_termin_absagen(self):
        """Test advice classification for cancellation."""
        result = perform_triage("Ich muss meinen Termin absagen")
        assert result.level == TriageLevel.BERATUNG

    def test_default_normal(self):
        """Test default classification for ambiguous input."""
        result = perform_triage("Ich brauche einen Termin")
        assert result.level == TriageLevel.NORMAL
        assert result.confidence < 0.6  # Lower confidence for default

    def test_case_insensitive(self):
        """Test that keywords are case-insensitive."""
        result = perform_triage("Ich habe BRUSTSCHMERZEN")
        assert result.level == TriageLevel.AKUT

    def test_action_includes_112(self):
        """Test that emergency action mentions 112."""
        result = perform_triage("Meine Frau hat einen Schlaganfall")
        assert result.level == TriageLevel.AKUT
        assert "112" in result.action or "Notaufnahme" in result.action
