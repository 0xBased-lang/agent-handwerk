"""Tests for Gastro industry module.

Tests reservation workflows, triage, scheduling, and conversation management.
"""

import pytest
from datetime import datetime, timedelta

from phone_agent.industry.gastro import (
    # Workflows
    RequestType,
    ServicePeriod,
    classify_request,
    get_service_period,
    extract_party_size,
    extract_date_time,
    format_available_slots,
    # Triage
    TriageEngine,
    GuestContext,
    GuestPriority,
    RequestUrgency,
    SpecialRequest,
    SpecialRequestType,
    get_triage_engine,
    # Scheduling
    SchedulingService,
    ReservationStatus,
    get_scheduling_service,
    # Conversation
    GastroConversationManager,
    ConversationState,
    GuestIntent,
    get_conversation_manager,
    # Prompts
    SYSTEM_PROMPT,
    SMS_RESERVATION_CONFIRMATION,
)


class TestWorkflows:
    """Test basic workflow functions."""

    def test_classify_reservation_request(self):
        """Test classification of reservation requests."""
        result = classify_request("Ich möchte einen Tisch für heute Abend reservieren")
        assert result.request_type == RequestType.RESERVATION
        assert result.confidence >= 0.5

    def test_classify_cancellation_request(self):
        """Test classification of cancellation requests."""
        result = classify_request("Ich muss leider meine Reservierung absagen")
        assert result.request_type == RequestType.CANCELLATION

    def test_classify_modification_request(self):
        """Test classification of modification requests."""
        result = classify_request("Kann ich meine Reservierung auf morgen verschieben?")
        assert result.request_type == RequestType.MODIFICATION

    def test_classify_information_request(self):
        """Test classification of information requests."""
        result = classify_request("Was sind eure Öffnungszeiten?")
        assert result.request_type == RequestType.INFORMATION

    def test_classify_complaint_high_priority(self):
        """Test that complaints get high priority."""
        result = classify_request("Ich habe eine Beschwerde über den Service")
        assert result.request_type == RequestType.COMPLAINT
        assert result.priority == 1  # High priority

    def test_classify_group_booking(self):
        """Test classification of group bookings."""
        result = classify_request("Wir möchten unsere Weihnachtsfeier bei euch machen")
        assert result.request_type == RequestType.GROUP_BOOKING
        assert result.requires_callback is True

    def test_get_service_period_monday_closed(self):
        """Test that Monday returns closed."""
        assert get_service_period(12, 0) == ServicePeriod.CLOSED  # Monday

    def test_get_service_period_lunch(self):
        """Test lunch service detection."""
        assert get_service_period(12, 2) == ServicePeriod.LUNCH  # Wednesday noon

    def test_get_service_period_dinner(self):
        """Test dinner service detection."""
        assert get_service_period(19, 4) == ServicePeriod.DINNER  # Friday evening

    def test_get_service_period_sunday(self):
        """Test Sunday service detection."""
        assert get_service_period(15, 6) == ServicePeriod.SUNDAY

    def test_extract_party_size_numeric(self):
        """Test extraction of numeric party sizes."""
        assert extract_party_size("für 4 Personen") == 4
        assert extract_party_size("Tisch für 6") == 6
        assert extract_party_size("8 Gäste") == 8

    def test_extract_party_size_word(self):
        """Test extraction of word-based party sizes."""
        assert extract_party_size("zu zweit") == 2
        assert extract_party_size("zu viert") == 4
        assert extract_party_size("zu sechst") == 6

    def test_extract_party_size_not_found(self):
        """Test when no party size is found."""
        assert extract_party_size("möchte reservieren") is None

    def test_extract_date_time_today(self):
        """Test extraction of relative dates."""
        result = extract_date_time("heute um 19 Uhr")
        assert "date" in result
        assert result["date"] == datetime.now().strftime("%Y-%m-%d")
        assert result.get("time") == "19:00"

    def test_extract_date_time_tomorrow(self):
        """Test extraction of tomorrow."""
        result = extract_date_time("morgen")
        tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
        assert result.get("date") == tomorrow

    def test_extract_date_time_weekday(self):
        """Test extraction of weekday names."""
        result = extract_date_time("am Samstag")
        assert "date" in result

    def test_format_available_slots_empty(self):
        """Test formatting with no slots."""
        result = format_available_slots([])
        assert "keine freien Tische" in result

    def test_format_available_slots_with_data(self):
        """Test formatting with available slots."""
        slots = [
            {"date": "2024-12-15", "time": "19:00"},
            {"date": "2024-12-15", "time": "20:00", "capacity": 4},
        ]
        result = format_available_slots(slots)
        assert "2024-12-15" in result
        assert "19:00" in result


class TestTriage:
    """Test triage engine."""

    def test_triage_engine_initialization(self):
        """Test triage engine can be initialized."""
        engine = TriageEngine()
        assert engine is not None

    def test_triage_engine_singleton(self):
        """Test singleton pattern."""
        engine1 = get_triage_engine()
        engine2 = get_triage_engine()
        assert engine1 is engine2

    def test_guest_priority_new(self):
        """Test new guest priority calculation."""
        guest = GuestContext(visit_count=0)
        assert guest.calculate_priority() == GuestPriority.NEW

    def test_guest_priority_regular(self):
        """Test regular guest priority calculation."""
        guest = GuestContext(visit_count=5)
        assert guest.calculate_priority() == GuestPriority.REGULAR

    def test_guest_priority_vip(self):
        """Test VIP guest priority calculation."""
        guest = GuestContext(is_vip=True)
        assert guest.calculate_priority() == GuestPriority.VIP

    def test_guest_priority_group(self):
        """Test group booking priority."""
        guest = GuestContext(party_size=10)
        assert guest.calculate_priority() == GuestPriority.GROUP

    def test_no_show_risk_new_guest(self):
        """Test no-show risk for new guests."""
        guest = GuestContext(visit_count=0)
        risk = guest.calculate_no_show_risk()
        assert 0 < risk < 1

    def test_no_show_risk_loyal_guest(self):
        """Test lower no-show risk for loyal guests."""
        loyal = GuestContext(visit_count=10)
        new = GuestContext(visit_count=0)
        assert loyal.calculate_no_show_risk() < new.calculate_no_show_risk()

    def test_no_show_risk_history(self):
        """Test increased risk with no-show history."""
        good = GuestContext(no_show_history=0)
        bad = GuestContext(no_show_history=2)
        assert bad.calculate_no_show_risk() > good.calculate_no_show_risk()

    def test_triage_assess_simple_request(self):
        """Test assessment of simple reservation request."""
        engine = TriageEngine()
        guest = GuestContext(
            name="Test",
            party_size=4,
            preferred_date="2024-12-20",
            preferred_time="19:00",
        )
        result = engine.assess(guest)
        assert result is not None
        assert result.guest_priority == GuestPriority.NEW

    def test_triage_extract_allergies(self):
        """Test allergy extraction from text."""
        engine = TriageEngine()
        guest = GuestContext(party_size=2)
        engine.assess(guest, free_text="Wir brauchen glutenfreie Optionen")
        assert len(guest.special_requests) > 0

    def test_triage_extract_occasion(self):
        """Test occasion extraction from text."""
        engine = TriageEngine()
        guest = GuestContext(party_size=4)
        engine.assess(guest, free_text="Wir feiern Geburtstag")
        assert guest.occasion == "Geburtstag"

    def test_triage_large_party_requires_deposit(self):
        """Test that large parties require deposit."""
        engine = TriageEngine()
        guest = GuestContext(party_size=10)
        result = engine.assess(guest)
        assert result.requires_deposit is True


class TestScheduling:
    """Test scheduling service."""

    def test_scheduling_service_initialization(self):
        """Test scheduling service can be initialized."""
        service = SchedulingService()
        assert service is not None

    def test_scheduling_service_singleton(self):
        """Test singleton pattern."""
        service1 = get_scheduling_service()
        service2 = get_scheduling_service()
        assert service1 is service2

    def test_find_available_slots(self):
        """Test finding available slots."""
        service = SchedulingService()
        # Use next Tuesday (not Monday/closed)
        today = datetime.now()
        days_until_tuesday = (1 - today.weekday()) % 7
        if days_until_tuesday == 0:
            days_until_tuesday = 7
        next_tuesday = today + timedelta(days=days_until_tuesday)
        date_str = next_tuesday.strftime("%Y-%m-%d")

        slots = service.find_available_slots(2, date_str)
        assert len(slots) > 0

    def test_find_slots_monday_closed(self):
        """Test that Monday returns no slots."""
        service = SchedulingService()
        # Find next Monday
        today = datetime.now()
        days_until_monday = (0 - today.weekday()) % 7
        if days_until_monday == 0:
            days_until_monday = 7
        next_monday = today + timedelta(days=days_until_monday)
        date_str = next_monday.strftime("%Y-%m-%d")

        slots = service.find_available_slots(2, date_str)
        assert len(slots) == 0

    def test_create_reservation(self):
        """Test creating a reservation."""
        service = SchedulingService()
        today = datetime.now()
        days_until_tuesday = (1 - today.weekday()) % 7
        if days_until_tuesday == 0:
            days_until_tuesday = 7
        next_tuesday = today + timedelta(days=days_until_tuesday)
        date_str = next_tuesday.strftime("%Y-%m-%d")

        reservation = service.create_reservation(
            guest_name="Test Guest",
            phone="0123456789",
            party_size=4,
            date=date_str,
            time="19:00",
        )
        assert reservation is not None
        assert reservation.guest_name == "Test Guest"
        assert reservation.status == ReservationStatus.CONFIRMED

    def test_cancel_reservation(self):
        """Test canceling a reservation."""
        service = SchedulingService()
        today = datetime.now()
        days_until_tuesday = (1 - today.weekday()) % 7
        if days_until_tuesday == 0:
            days_until_tuesday = 7
        next_tuesday = today + timedelta(days=days_until_tuesday)
        date_str = next_tuesday.strftime("%Y-%m-%d")

        reservation = service.create_reservation(
            guest_name="Cancel Test",
            phone="0123456789",
            party_size=2,
            date=date_str,
            time="18:00",
        )
        assert reservation is not None

        result = service.cancel_reservation(reservation.id)
        assert result is True

    def test_find_reservation_by_name(self):
        """Test finding reservation by guest name."""
        service = SchedulingService()
        today = datetime.now()
        days_until_tuesday = (1 - today.weekday()) % 7
        if days_until_tuesday == 0:
            days_until_tuesday = 7
        next_tuesday = today + timedelta(days=days_until_tuesday)
        date_str = next_tuesday.strftime("%Y-%m-%d")

        service.create_reservation(
            guest_name="Findable Guest",
            phone="9876543210",
            party_size=3,
            date=date_str,
            time="20:00",
        )

        found = service.find_reservation(guest_name="Findable")
        assert found is not None
        assert "Findable" in found.guest_name

    def test_reservation_to_dict(self):
        """Test reservation serialization."""
        service = SchedulingService()
        today = datetime.now()
        days_until_tuesday = (1 - today.weekday()) % 7
        if days_until_tuesday == 0:
            days_until_tuesday = 7
        next_tuesday = today + timedelta(days=days_until_tuesday)
        date_str = next_tuesday.strftime("%Y-%m-%d")

        reservation = service.create_reservation(
            guest_name="Dict Test",
            phone="1111111111",
            party_size=2,
            date=date_str,
            time="19:30",
        )
        data = reservation.to_dict()
        assert "id" in data
        assert "guest_name" in data
        assert data["status"] == "confirmed"


class TestConversation:
    """Test conversation management."""

    def test_conversation_manager_initialization(self):
        """Test conversation manager can be initialized."""
        manager = GastroConversationManager()
        assert manager is not None

    def test_start_conversation(self):
        """Test starting a new conversation."""
        manager = GastroConversationManager("Test Restaurant")
        context = manager.start_conversation("call-001")
        assert context is not None
        assert context.state == ConversationState.GREETING

    def test_process_greeting_turn(self):
        """Test processing first turn (greeting)."""
        manager = GastroConversationManager("Test Restaurant")
        manager.start_conversation("call-002")
        response = manager.process_turn("call-002", "Hallo")
        assert response is not None
        assert "Test Restaurant" in response.message or "Reservierungsassistent" in response.message

    def test_process_reservation_intent(self):
        """Test reservation intent detection."""
        manager = GastroConversationManager()
        manager.start_conversation("call-003")
        manager.process_turn("call-003", "Hallo")  # Greeting
        response = manager.process_turn("call-003", "Ich möchte einen Tisch reservieren")
        assert response.intent == GuestIntent.NEW_RESERVATION

    def test_process_cancellation_intent(self):
        """Test cancellation intent detection."""
        manager = GastroConversationManager()
        manager.start_conversation("call-004")
        manager.process_turn("call-004", "Hallo")
        response = manager.process_turn("call-004", "Ich muss absagen")
        assert response.intent == GuestIntent.CANCEL_RESERVATION

    def test_conversation_data_extraction(self):
        """Test that reservation data is extracted."""
        manager = GastroConversationManager()
        context = manager.start_conversation("call-005")
        manager.process_turn("call-005", "Hallo")
        manager.process_turn("call-005", "Tisch für 4 Personen morgen um 19 Uhr")
        assert context.reservation_data.party_size == 4

    def test_conversation_state_transitions(self):
        """Test state transitions through conversation."""
        manager = GastroConversationManager()
        context = manager.start_conversation("call-006")

        # Initial state
        assert context.state == ConversationState.GREETING

        # After greeting
        manager.process_turn("call-006", "Hallo")
        assert context.state == ConversationState.INTENT_DETECTION

        # After reservation request
        manager.process_turn("call-006", "Reservieren bitte")
        assert context.state == ConversationState.RESERVATION_INTAKE

    def test_conversation_escalation(self):
        """Test escalation for complaints."""
        manager = GastroConversationManager()
        manager.start_conversation("call-007")
        manager.process_turn("call-007", "Hallo")
        response = manager.process_turn("call-007", "Ich habe eine Beschwerde")
        assert response.needs_escalation is True

    def test_conversation_information_handling(self):
        """Test information request handling."""
        manager = GastroConversationManager()
        manager.start_conversation("call-008")
        manager.process_turn("call-008", "Hallo")
        response = manager.process_turn("call-008", "Was sind eure Öffnungszeiten?")
        assert response.intent == GuestIntent.GET_INFORMATION
        assert "Dienstag" in response.message or "geöffnet" in response.message

    def test_end_conversation(self):
        """Test conversation cleanup."""
        manager = GastroConversationManager()
        manager.start_conversation("call-009")
        manager.end_conversation("call-009")
        assert manager.get_context("call-009") is None


class TestPrompts:
    """Test prompt templates."""

    def test_system_prompt_exists(self):
        """Test that system prompt is defined."""
        assert SYSTEM_PROMPT is not None
        assert len(SYSTEM_PROMPT) > 100

    def test_system_prompt_content(self):
        """Test system prompt contains key elements."""
        assert "Restaurant" in SYSTEM_PROMPT or "Telefonassistent" in SYSTEM_PROMPT
        assert "Reservierung" in SYSTEM_PROMPT

    def test_sms_template_placeholders(self):
        """Test SMS templates have correct placeholders."""
        assert "{restaurant_name}" in SMS_RESERVATION_CONFIRMATION
        assert "{date}" in SMS_RESERVATION_CONFIRMATION
        assert "{time}" in SMS_RESERVATION_CONFIRMATION
        assert "{party_size}" in SMS_RESERVATION_CONFIRMATION


class TestIntegration:
    """Integration tests combining multiple components."""

    def test_full_reservation_flow(self):
        """Test complete reservation flow."""
        # Start conversation
        manager = GastroConversationManager("Test Restaurant")
        manager.start_conversation("full-flow-001")

        # Greeting
        response = manager.process_turn("full-flow-001", "Hallo, guten Tag")
        assert "Test Restaurant" in response.message or "behilflich" in response.message

        # Reservation request with details
        response = manager.process_turn(
            "full-flow-001",
            "Ich möchte für 4 Personen morgen um 19 Uhr reservieren"
        )
        assert response.intent == GuestIntent.NEW_RESERVATION

    def test_triage_with_scheduling(self):
        """Test triage integrated with scheduling."""
        triage = get_triage_engine()
        scheduling = get_scheduling_service()

        # Get available slots
        today = datetime.now()
        days_until_tuesday = (1 - today.weekday()) % 7
        if days_until_tuesday == 0:
            days_until_tuesday = 7
        next_tuesday = today + timedelta(days=days_until_tuesday)
        date_str = next_tuesday.strftime("%Y-%m-%d")

        slots = scheduling.find_available_slots(4, date_str)

        # Create guest context
        guest = GuestContext(
            name="Integration Test",
            party_size=4,
            preferred_date=date_str,
            preferred_time="19:00",
        )

        # Run triage with available slots
        from phone_agent.industry.gastro.triage import ReservationSlot
        reservation_slots = [
            ReservationSlot(
                date=s.date,
                time=s.time,
                capacity=s.capacity,
                table_ids=s.table_ids,
            )
            for s in slots[:5]
        ]

        result = triage.assess(guest, available_slots=reservation_slots)
        assert result is not None
        assert len(result.recommended_slots) > 0 or not slots
