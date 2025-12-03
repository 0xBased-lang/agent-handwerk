"""Tests for Freie Berufe industry module.

Tests lead intake, qualification, scheduling, and conversation management
for professional services (lawyers, tax consultants, etc.).
"""

import pytest
from datetime import datetime, timedelta

from phone_agent.industry.freie_berufe import (
    # Workflows
    InquiryType,
    ServiceArea,
    UrgencyLevel,
    classify_inquiry,
    extract_contact_info,
    detect_deadline,
    format_available_slots,
    calculate_lead_score,
    # Triage
    TriageEngine,
    ContactContext,
    InquiryContext,
    LeadPriority,
    QualificationStatus,
    ClientType,
    get_triage_engine,
    # Scheduling
    SchedulingService,
    AppointmentType,
    AppointmentStatus,
    AdvisorRole,
    get_scheduling_service,
    # Conversation
    FreieBerufeConversationManager,
    ConversationState,
    ClientIntent,
    get_conversation_manager,
    # Prompts
    SYSTEM_PROMPT,
    SMS_APPOINTMENT_CONFIRMATION,
    EMAIL_APPOINTMENT_CONFIRMATION,
)


class TestWorkflows:
    """Test basic workflow functions."""

    def test_classify_legal_inquiry(self):
        """Test classification of legal inquiries."""
        result = classify_inquiry("Ich brauche einen Anwalt wegen einer Kündigung")
        assert result.service_area == ServiceArea.LEGAL
        assert result.confidence >= 0.5

    def test_classify_tax_inquiry(self):
        """Test classification of tax inquiries."""
        result = classify_inquiry("Ich brauche Hilfe bei meiner Steuererklärung")
        assert result.service_area == ServiceArea.TAX

    def test_classify_consulting_inquiry(self):
        """Test classification of consulting inquiries."""
        result = classify_inquiry("Wir brauchen Unternehmensberatung für Digitalisierung")
        assert result.service_area == ServiceArea.CONSULTING

    def test_classify_existing_client(self):
        """Test detection of existing clients."""
        result = classify_inquiry("Ich bin schon Mandant bei Ihnen")
        assert result.inquiry_type == InquiryType.EXISTING_CLIENT
        assert result.requires_callback is True

    def test_classify_callback_request(self):
        """Test detection of callback requests."""
        result = classify_inquiry("Können Sie mich bitte zurückrufen?")
        assert result.inquiry_type == InquiryType.CALLBACK

    def test_classify_urgent_inquiry(self):
        """Test urgency detection."""
        result = classify_inquiry("Ich habe morgen einen Gerichtstermin!")
        assert result.urgency == UrgencyLevel.URGENT or result.urgency == UrgencyLevel.CRITICAL

    def test_classify_critical_deadline(self):
        """Test critical deadline detection."""
        result = classify_inquiry("Heute läuft die Klagefrist ab!")
        assert result.urgency == UrgencyLevel.CRITICAL
        assert result.priority_score >= 70

    def test_extract_contact_phone(self):
        """Test phone number extraction."""
        result = extract_contact_info("Meine Nummer ist 0171 1234567")
        assert "phone" in result
        assert "01711234567" in result["phone"]

    def test_extract_contact_email(self):
        """Test email extraction."""
        result = extract_contact_info("Meine E-Mail ist test@example.com")
        assert result.get("email") == "test@example.com"

    def test_extract_contact_name(self):
        """Test name extraction."""
        result = extract_contact_info("Mein Name ist Schmidt")
        assert "name" in result
        assert "Schmidt" in result["name"]

    def test_extract_company(self):
        """Test company name extraction."""
        result = extract_contact_info("Ich bin von der Musterfirma GmbH")
        assert "company" in result

    def test_detect_deadline_today(self):
        """Test today deadline detection."""
        result = detect_deadline("Die Frist ist heute")
        assert result["has_deadline"] is True
        assert result.get("urgency") == "today"

    def test_detect_deadline_tomorrow(self):
        """Test tomorrow deadline detection."""
        result = detect_deadline("Der Termin ist morgen")
        assert result["has_deadline"] is True
        assert result.get("urgency") == "tomorrow"

    def test_detect_deadline_date(self):
        """Test specific date deadline detection."""
        result = detect_deadline("Die Frist endet am 15.12.2024")
        assert result["has_deadline"] is True
        assert "deadline_text" in result

    def test_format_slots_empty(self):
        """Test formatting with no slots."""
        result = format_available_slots([])
        assert "keine freien Termine" in result

    def test_format_slots_with_advisor(self):
        """Test formatting with advisor names."""
        slots = [
            {"date": "2024-12-15", "time": "10:00", "advisor": "Dr. Schmidt", "type": "Persönlich"}
        ]
        result = format_available_slots(slots)
        assert "2024-12-15" in result
        assert "10:00" in result
        assert "Dr. Schmidt" in result

    def test_calculate_lead_score_basic(self):
        """Test basic lead score calculation."""
        score = calculate_lead_score(
            service_area=ServiceArea.LEGAL,
            urgency=UrgencyLevel.STANDARD,
            has_company=False,
            is_decision_maker=False,
        )
        assert 0 <= score <= 100

    def test_calculate_lead_score_high_value(self):
        """Test high-value lead scoring."""
        score = calculate_lead_score(
            service_area=ServiceArea.LEGAL,
            urgency=UrgencyLevel.URGENT,
            has_company=True,
            is_decision_maker=True,
            referral_source="Empfehlung",
        )
        assert score >= 70  # Should be high priority

    def test_calculate_lead_score_referral_boost(self):
        """Test referral bonus in lead scoring."""
        with_referral = calculate_lead_score(
            service_area=ServiceArea.TAX,
            urgency=UrgencyLevel.STANDARD,
            has_company=True,
            is_decision_maker=True,
            referral_source="Empfehlung",
        )
        without_referral = calculate_lead_score(
            service_area=ServiceArea.TAX,
            urgency=UrgencyLevel.STANDARD,
            has_company=True,
            is_decision_maker=True,
        )
        assert with_referral > without_referral


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

    def test_contact_score_minimal(self):
        """Test contact score with minimal info."""
        contact = ContactContext()
        score = contact.calculate_contact_score()
        assert score < 30

    def test_contact_score_complete(self):
        """Test contact score with complete info."""
        contact = ContactContext(
            name="Test Person",
            phone="0171 1234567",
            email="test@example.com",
            company="Test GmbH",
            client_type=ClientType.MEDIUM_BUSINESS,
            is_decision_maker=True,
        )
        score = contact.calculate_contact_score()
        assert score >= 60

    def test_contact_score_referral_bonus(self):
        """Test referral bonus in contact scoring."""
        with_referral = ContactContext(referred_by="Herr Müller")
        without_referral = ContactContext()
        assert with_referral.calculate_contact_score() > without_referral.calculate_contact_score()

    def test_inquiry_urgency_score_basic(self):
        """Test basic urgency score calculation."""
        inquiry = InquiryContext()
        score = inquiry.calculate_urgency_score()
        assert score == 20  # Base score

    def test_inquiry_urgency_score_court_date(self):
        """Test urgency with court date."""
        inquiry = InquiryContext(court_date=True)
        score = inquiry.calculate_urgency_score()
        assert score >= 60

    def test_inquiry_urgency_score_deadline(self):
        """Test urgency with deadline."""
        tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
        inquiry = InquiryContext(has_deadline=True, deadline_date=tomorrow)
        score = inquiry.calculate_urgency_score()
        assert score >= 50

    def test_triage_assess_hot_lead(self):
        """Test assessment of hot lead."""
        engine = TriageEngine()
        contact = ContactContext(
            name="Test CEO",
            company="Big Corp GmbH",
            is_decision_maker=True,
            client_type=ClientType.MEDIUM_BUSINESS,
        )
        inquiry = InquiryContext(
            service_area="legal",
            court_date=True,
        )
        result = engine.assess(contact, inquiry)
        assert result.priority == LeadPriority.HOT
        assert result.callback_priority is True

    def test_triage_assess_cold_lead(self):
        """Test assessment of cold lead."""
        engine = TriageEngine()
        contact = ContactContext(name="Test Person")
        inquiry = InquiryContext(estimated_value="low")
        result = engine.assess(contact, inquiry)
        assert result.priority in [LeadPriority.COOL, LeadPriority.COLD]

    def test_triage_extract_decision_maker(self):
        """Test decision maker extraction from text."""
        engine = TriageEngine()
        contact = ContactContext()
        inquiry = InquiryContext()
        engine.assess(contact, inquiry, free_text="Ich bin der Geschäftsführer")
        assert contact.is_decision_maker is True

    def test_triage_not_qualified(self):
        """Test not qualified status for non-matching service."""
        engine = TriageEngine()
        contact = ContactContext()
        inquiry = InquiryContext(service_area="unknown_service")
        result = engine.assess(contact, inquiry)
        assert result.qualification == QualificationStatus.NOT_QUALIFIED

    def test_triage_result_serialization(self):
        """Test triage result to_dict."""
        engine = TriageEngine()
        contact = ContactContext(name="Test")
        inquiry = InquiryContext(service_area="legal")
        result = engine.assess(contact, inquiry)
        data = result.to_dict()
        assert "priority" in data
        assert "lead_score" in data
        assert "recommended_action" in data


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

    def test_find_available_slots_weekday(self):
        """Test finding available slots on a weekday."""
        service = SchedulingService()
        # Find next Tuesday (not weekend)
        today = datetime.now()
        days_until_tuesday = (1 - today.weekday()) % 7
        if days_until_tuesday == 0:
            days_until_tuesday = 7
        next_tuesday = today + timedelta(days=days_until_tuesday)
        date_str = next_tuesday.strftime("%Y-%m-%d")

        slots = service.find_available_slots(date_str)
        assert len(slots) > 0

    def test_find_slots_weekend_closed(self):
        """Test that weekend returns no slots."""
        service = SchedulingService()
        # Find next Saturday
        today = datetime.now()
        days_until_saturday = (5 - today.weekday()) % 7
        if days_until_saturday == 0:
            days_until_saturday = 7
        next_saturday = today + timedelta(days=days_until_saturday)
        date_str = next_saturday.strftime("%Y-%m-%d")

        slots = service.find_available_slots(date_str)
        assert len(slots) == 0

    def test_create_appointment(self):
        """Test creating an appointment."""
        service = SchedulingService()
        today = datetime.now()
        days_until_tuesday = (1 - today.weekday()) % 7
        if days_until_tuesday == 0:
            days_until_tuesday = 7
        next_tuesday = today + timedelta(days=days_until_tuesday)
        date_str = next_tuesday.strftime("%Y-%m-%d")

        appointment = service.create_appointment(
            client_name="Test Client",
            client_phone="0171 1234567",
            date=date_str,
            time="10:00",
            service_area="legal",
            topic="Arbeitsrecht Beratung",
        )
        assert appointment is not None
        assert appointment.client_name == "Test Client"
        assert appointment.status == AppointmentStatus.CONFIRMED

    def test_appointment_has_required_documents(self):
        """Test that appointments include required documents."""
        service = SchedulingService()
        today = datetime.now()
        days_until_tuesday = (1 - today.weekday()) % 7
        if days_until_tuesday == 0:
            days_until_tuesday = 7
        next_tuesday = today + timedelta(days=days_until_tuesday)
        date_str = next_tuesday.strftime("%Y-%m-%d")

        appointment = service.create_appointment(
            client_name="Doc Test",
            client_phone="0171 9876543",
            date=date_str,
            time="11:00",
            service_area="tax",
        )
        assert len(appointment.documents_required) > 0
        assert any("Personalausweis" in doc for doc in appointment.documents_required)

    def test_cancel_appointment(self):
        """Test canceling an appointment."""
        service = SchedulingService()
        today = datetime.now()
        days_until_tuesday = (1 - today.weekday()) % 7
        if days_until_tuesday == 0:
            days_until_tuesday = 7
        next_tuesday = today + timedelta(days=days_until_tuesday)
        date_str = next_tuesday.strftime("%Y-%m-%d")

        appointment = service.create_appointment(
            client_name="Cancel Test",
            client_phone="0171 1111111",
            date=date_str,
            time="09:00",
        )
        assert appointment is not None

        result = service.cancel_appointment(appointment.id)
        assert result is True

    def test_reschedule_appointment(self):
        """Test rescheduling an appointment."""
        service = SchedulingService()
        today = datetime.now()
        days_until_tuesday = (1 - today.weekday()) % 7
        if days_until_tuesday == 0:
            days_until_tuesday = 7
        next_tuesday = today + timedelta(days=days_until_tuesday)
        next_wednesday = next_tuesday + timedelta(days=1)
        date_str = next_tuesday.strftime("%Y-%m-%d")
        new_date_str = next_wednesday.strftime("%Y-%m-%d")

        appointment = service.create_appointment(
            client_name="Reschedule Test",
            client_phone="0171 2222222",
            date=date_str,
            time="14:00",
        )
        assert appointment is not None

        new_appointment = service.reschedule_appointment(
            appointment.id,
            new_date_str,
            "15:00",
        )
        assert new_appointment is not None
        assert new_appointment.date == new_date_str

    def test_find_appointment_by_name(self):
        """Test finding appointment by client name."""
        service = SchedulingService()
        today = datetime.now()
        days_until_tuesday = (1 - today.weekday()) % 7
        if days_until_tuesday == 0:
            days_until_tuesday = 7
        next_tuesday = today + timedelta(days=days_until_tuesday)
        date_str = next_tuesday.strftime("%Y-%m-%d")

        service.create_appointment(
            client_name="Findable Client",
            client_phone="0171 3333333",
            date=date_str,
            time="16:00",
        )

        found = service.find_appointment(client_name="Findable")
        assert found is not None
        assert "Findable" in found.client_name

    def test_appointment_to_dict(self):
        """Test appointment serialization."""
        service = SchedulingService()
        today = datetime.now()
        days_until_tuesday = (1 - today.weekday()) % 7
        if days_until_tuesday == 0:
            days_until_tuesday = 7
        next_tuesday = today + timedelta(days=days_until_tuesday)
        date_str = next_tuesday.strftime("%Y-%m-%d")

        appointment = service.create_appointment(
            client_name="Dict Test",
            client_phone="0171 4444444",
            date=date_str,
            time="17:00",
        )
        data = appointment.to_dict()
        assert "id" in data
        assert "client_name" in data
        assert data["status"] == "confirmed"

    def test_get_advisor(self):
        """Test getting advisor by ID."""
        service = SchedulingService()
        advisor = service.get_advisor("adv1")
        assert advisor is not None
        assert advisor.role == AdvisorRole.LAWYER


class TestConversation:
    """Test conversation management."""

    def test_conversation_manager_initialization(self):
        """Test conversation manager can be initialized."""
        manager = FreieBerufeConversationManager()
        assert manager is not None

    def test_start_conversation(self):
        """Test starting a new conversation."""
        manager = FreieBerufeConversationManager("Test Kanzlei")
        context = manager.start_conversation("call-001")
        assert context is not None
        assert context.state == ConversationState.GREETING

    def test_process_greeting_turn(self):
        """Test processing first turn (greeting)."""
        manager = FreieBerufeConversationManager("Test Kanzlei")
        manager.start_conversation("call-002")
        response = manager.process_turn("call-002", "Hallo")
        assert response is not None
        assert "Test Kanzlei" in response.message or "Telefonassistent" in response.message

    def test_process_new_inquiry_intent(self):
        """Test new inquiry intent detection."""
        manager = FreieBerufeConversationManager()
        manager.start_conversation("call-003")
        manager.process_turn("call-003", "Hallo")
        response = manager.process_turn("call-003", "Ich brauche rechtliche Beratung")
        assert response.intent == ClientIntent.NEW_INQUIRY

    def test_process_existing_client_intent(self):
        """Test existing client intent detection."""
        manager = FreieBerufeConversationManager()
        manager.start_conversation("call-004")
        manager.process_turn("call-004", "Hallo")
        response = manager.process_turn("call-004", "Ich bin schon Mandant bei Ihnen")
        assert response.intent == ClientIntent.EXISTING_CLIENT

    def test_process_callback_intent(self):
        """Test callback request intent detection."""
        manager = FreieBerufeConversationManager()
        manager.start_conversation("call-005")
        manager.process_turn("call-005", "Hallo")
        response = manager.process_turn("call-005", "Können Sie mich bitte zurückrufen?")
        assert response.intent == ClientIntent.CALLBACK_REQUEST

    def test_conversation_data_extraction(self):
        """Test that lead data is extracted."""
        manager = FreieBerufeConversationManager()
        context = manager.start_conversation("call-006")
        manager.process_turn("call-006", "Hallo")
        manager.process_turn("call-006", "Ich brauche Hilfe bei einer Kündigung")
        assert context.lead_data.service_area is not None

    def test_conversation_state_transitions(self):
        """Test state transitions through conversation."""
        manager = FreieBerufeConversationManager()
        context = manager.start_conversation("call-007")

        # Initial state
        assert context.state == ConversationState.GREETING

        # After greeting
        manager.process_turn("call-007", "Hallo")
        assert context.state == ConversationState.INTENT_DETECTION

        # After new inquiry
        manager.process_turn("call-007", "Ich brauche einen Steuerberater")
        assert context.state == ConversationState.LEAD_INTAKE

    def test_conversation_escalation(self):
        """Test escalation for complaints."""
        manager = FreieBerufeConversationManager()
        manager.start_conversation("call-008")
        manager.process_turn("call-008", "Hallo")
        response = manager.process_turn("call-008", "Ich habe eine Beschwerde")
        assert response.needs_escalation is True
        assert response.intent == ClientIntent.COMPLAINT

    def test_conversation_referral_tracking(self):
        """Test referral source tracking."""
        manager = FreieBerufeConversationManager()
        context = manager.start_conversation("call-009")
        manager.process_turn("call-009", "Hallo")
        manager.process_turn("call-009", "Sie wurden mir empfohlen")
        assert context.lead_data.referral_source == "Empfehlung"

    def test_end_conversation(self):
        """Test conversation cleanup."""
        manager = FreieBerufeConversationManager()
        manager.start_conversation("call-010")
        manager.end_conversation("call-010")
        assert manager.get_context("call-010") is None


class TestPrompts:
    """Test prompt templates."""

    def test_system_prompt_exists(self):
        """Test that system prompt is defined."""
        assert SYSTEM_PROMPT is not None
        assert len(SYSTEM_PROMPT) > 100

    def test_system_prompt_content(self):
        """Test system prompt contains key elements."""
        assert "Telefonassistent" in SYSTEM_PROMPT
        assert "Mandant" in SYSTEM_PROMPT or "Kanzlei" in SYSTEM_PROMPT

    def test_sms_template_placeholders(self):
        """Test SMS templates have correct placeholders."""
        assert "{practice_name}" in SMS_APPOINTMENT_CONFIRMATION
        assert "{date}" in SMS_APPOINTMENT_CONFIRMATION
        assert "{time}" in SMS_APPOINTMENT_CONFIRMATION

    def test_email_template_placeholders(self):
        """Test email templates have correct placeholders."""
        assert "{contact_name}" in EMAIL_APPOINTMENT_CONFIRMATION
        assert "{advisor_name}" in EMAIL_APPOINTMENT_CONFIRMATION
        assert "{required_documents}" in EMAIL_APPOINTMENT_CONFIRMATION


class TestIntegration:
    """Integration tests combining multiple components."""

    def test_full_lead_intake_flow(self):
        """Test complete lead intake flow."""
        manager = FreieBerufeConversationManager("Test Kanzlei")
        manager.start_conversation("full-flow-001")

        # Greeting
        response = manager.process_turn("full-flow-001", "Guten Tag")
        assert "Test Kanzlei" in response.message

        # Lead inquiry
        response = manager.process_turn(
            "full-flow-001",
            "Ich brauche Hilfe bei einem Arbeitsrechtsfall. Mir wurde gekündigt."
        )
        assert response.intent == ClientIntent.NEW_INQUIRY

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

        slots = scheduling.find_available_slots(date_str, service_area="legal")

        # Create contact and inquiry
        contact = ContactContext(
            name="Integration Test",
            company="Test Corp",
            is_decision_maker=True,
            client_type=ClientType.SMALL_BUSINESS,
        )
        inquiry = InquiryContext(
            service_area="legal",
            has_deadline=True,
        )

        # Run triage
        result = triage.assess(contact, inquiry)
        assert result is not None
        assert result.recommended_advisor is not None or result.priority in [LeadPriority.COOL, LeadPriority.COLD]

    def test_urgent_legal_case_prioritization(self):
        """Test that urgent legal cases are properly prioritized."""
        triage = get_triage_engine()

        contact = ContactContext(
            name="Urgent Client",
            phone="0171 9999999",
        )
        inquiry = InquiryContext(
            service_area="legal",
            court_date=True,
            has_deadline=True,
            deadline_date=(datetime.now() + timedelta(days=2)).strftime("%Y-%m-%d"),
        )

        result = triage.assess(contact, inquiry, free_text="Ich habe übermorgen einen Gerichtstermin")

        assert result.priority == LeadPriority.HOT
        assert result.callback_priority is True
        assert "sofort" in result.recommended_action.lower() or "priorit" in result.recommended_action.lower()
