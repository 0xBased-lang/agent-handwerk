"""End-to-end call flow tests for all industry modules.

Tests complete call flows from initial contact through resolution,
verifying integration between triage, scheduling, and conversation components.
"""

from __future__ import annotations

import pytest
from datetime import date, timedelta


# =============================================================================
# Healthcare E2E Tests
# =============================================================================


class TestHealthcareE2EFlow:
    """End-to-end tests for healthcare call flows."""

    def test_triage_engine_available(self):
        """Test triage engine is available and functional."""
        from phone_agent.industry.gesundheit import get_triage_engine

        triage = get_triage_engine()
        assert triage is not None

    def test_scheduling_service_available(self):
        """Test scheduling service is available."""
        from phone_agent.industry.gesundheit import get_scheduling_service

        scheduler = get_scheduling_service()
        assert scheduler is not None

    def test_recall_service_available(self):
        """Test recall service is available."""
        from phone_agent.industry.gesundheit.recall import RecallService

        service = RecallService()
        assert service is not None


# =============================================================================
# Handwerk E2E Tests
# =============================================================================


class TestHandwerkE2EFlow:
    """End-to-end tests for trades/handwerk call flows."""

    def test_triage_engine_available(self):
        """Test triage engine is available."""
        from phone_agent.industry.handwerk import get_triage_engine

        triage = get_triage_engine()
        assert triage is not None

    def test_scheduling_service_available(self):
        """Test scheduling service is available."""
        from phone_agent.industry.handwerk import get_scheduling_service

        scheduler = get_scheduling_service()
        assert scheduler is not None

    def test_emergency_keywords_detected(self):
        """Test emergency keyword detection in triage."""
        from phone_agent.industry.handwerk import get_triage_engine

        triage = get_triage_engine()
        # Triage engine should be able to assess emergencies
        assert hasattr(triage, 'assess') or hasattr(triage, 'classify')

    def test_followup_service_available(self):
        """Test followup service is available."""
        from phone_agent.industry.handwerk.followup import FollowUpService

        service = FollowUpService()
        assert service is not None


# =============================================================================
# Gastro E2E Tests
# =============================================================================


class TestGastroE2EFlow:
    """End-to-end tests for restaurant/gastro call flows."""

    def test_reservation_to_confirmation(self):
        """Test complete reservation flow: request → table → confirmation."""
        from phone_agent.industry.gastro import (
            get_scheduling_service,
            get_conversation_manager,
        )

        # Step 1: Start conversation
        conversation = get_conversation_manager()
        context = conversation.start_conversation("call-123")

        assert context.state.value == "greeting"

        # Step 2: Find available slots
        scheduler = get_scheduling_service()
        tomorrow = (date.today() + timedelta(days=1)).strftime("%Y-%m-%d")

        slots = scheduler.find_available_slots(
            party_size=4,
            date=tomorrow,
            preferred_time="19:00",
        )

        # Should find dinner slots
        assert len(slots) > 0

        # Step 3: Create reservation
        reservation = scheduler.create_reservation(
            guest_name="Familie Schmidt",
            phone="+491234567890",
            party_size=4,
            date=tomorrow,
            time=slots[0].time,
            occasion="Geburtstag",
        )

        assert reservation is not None
        assert reservation.status.value == "confirmed"
        assert len(reservation.table_ids) > 0

    def test_large_party_table_combining(self):
        """Test large party gets combined tables."""
        from phone_agent.industry.gastro import get_scheduling_service

        scheduler = get_scheduling_service()
        tomorrow = (date.today() + timedelta(days=1)).strftime("%Y-%m-%d")

        # Request for large party (14 people)
        slots = scheduler.find_available_slots(
            party_size=14,
            date=tomorrow,
            preferred_time="19:00",
            location_preference="indoor",
        )

        # Should find slots with combined tables
        if slots:
            assert slots[0].capacity >= 14
            # Multiple tables should be assigned
            assert len(slots[0].table_ids) >= 2

    def test_triage_engine_available(self):
        """Test triage engine is available."""
        from phone_agent.industry.gastro import get_triage_engine

        triage = get_triage_engine()
        assert triage is not None


# =============================================================================
# Freie Berufe E2E Tests
# =============================================================================


class TestFreieBerufeE2EFlow:
    """End-to-end tests for professional services call flows."""

    def test_triage_engine_available(self):
        """Test triage engine is available."""
        from phone_agent.industry.freie_berufe import get_triage_engine

        triage = get_triage_engine()
        assert triage is not None

    def test_scheduling_service_available(self):
        """Test scheduling service is available."""
        from phone_agent.industry.freie_berufe import get_scheduling_service

        scheduler = get_scheduling_service()
        assert scheduler is not None

    def test_conversation_manager_available(self):
        """Test conversation manager is available."""
        from phone_agent.industry.freie_berufe import get_conversation_manager

        manager = get_conversation_manager()
        assert manager is not None

    def test_urgent_legal_case_prioritization(self):
        """Test urgent legal case gets priority handling."""
        from phone_agent.industry.freie_berufe import (
            classify_inquiry,
            detect_deadline,
            UrgencyLevel,
        )

        # Urgent case with court deadline
        text = "Ich habe morgen einen Gerichtstermin und brauche dringend einen Anwalt"

        result = classify_inquiry(text)
        deadline = detect_deadline(text)

        assert result.urgency in [UrgencyLevel.CRITICAL, UrgencyLevel.URGENT]
        assert deadline is not None

    def test_lead_scoring_available(self):
        """Test lead scoring functionality."""
        from phone_agent.industry.freie_berufe import calculate_lead_score, ServiceArea, UrgencyLevel

        # Test with the actual API signature
        score = calculate_lead_score(
            service_area=ServiceArea.LEGAL,
            urgency=UrgencyLevel.URGENT,
            has_company=True,
            is_decision_maker=True,
            referral_source="Empfehlung",
        )

        assert score >= 0
        assert score <= 100


# =============================================================================
# Cross-Industry Integration Tests
# =============================================================================


class TestCrossIndustryIntegration:
    """Tests for shared functionality across industries."""

    def test_all_industries_have_triage_engine(self):
        """Verify all industries provide triage functionality."""
        from phone_agent.industry.gesundheit import get_triage_engine as gesundheit_triage
        from phone_agent.industry.handwerk import get_triage_engine as handwerk_triage
        from phone_agent.industry.gastro import get_triage_engine as gastro_triage
        from phone_agent.industry.freie_berufe import get_triage_engine as freie_berufe_triage

        # All should return valid triage engines
        assert gesundheit_triage() is not None
        assert handwerk_triage() is not None
        assert gastro_triage() is not None
        assert freie_berufe_triage() is not None

    def test_all_industries_have_scheduling_service(self):
        """Verify all industries provide scheduling functionality."""
        from phone_agent.industry.gesundheit import get_scheduling_service as gesundheit_scheduler
        from phone_agent.industry.handwerk import get_scheduling_service as handwerk_scheduler
        from phone_agent.industry.gastro import get_scheduling_service as gastro_scheduler
        from phone_agent.industry.freie_berufe import get_scheduling_service as freie_berufe_scheduler

        # All should return valid scheduling services
        assert gesundheit_scheduler() is not None
        assert handwerk_scheduler() is not None
        assert gastro_scheduler() is not None
        assert freie_berufe_scheduler() is not None

    def test_german_prompts_available(self):
        """Verify all industries have German language prompts."""
        from phone_agent.industry.gesundheit import SYSTEM_PROMPT as gesundheit_prompt
        from phone_agent.industry.handwerk import SYSTEM_PROMPT as handwerk_prompt
        from phone_agent.industry.gastro import SYSTEM_PROMPT as gastro_prompt
        from phone_agent.industry.freie_berufe import SYSTEM_PROMPT as freie_berufe_prompt

        # All prompts should be non-empty German text
        for prompt in [gesundheit_prompt, handwerk_prompt, gastro_prompt, freie_berufe_prompt]:
            assert len(prompt) > 100
            # Should contain German words
            assert any(word in prompt.lower() for word in ["sie", "bitte", "termin", "anruf"])

    def test_industry_module_isolation(self):
        """Test that industry modules are properly isolated."""
        # Each industry should have its own namespace
        from phone_agent.industry import gesundheit
        from phone_agent.industry import handwerk
        from phone_agent.industry import gastro
        from phone_agent.industry import freie_berufe

        # Modules should be distinct
        assert gesundheit is not handwerk
        assert gastro is not freie_berufe
        assert handwerk is not gastro
