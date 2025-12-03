"""Comprehensive tests for healthcare functionality."""
from datetime import date, datetime, timedelta
from uuid import uuid4

import pytest

from phone_agent.industry.gesundheit import (
    # Triage
    TriageEngine,
    Symptom,
    SymptomCategory,
    UrgencyLevel,
    PatientContext,
    get_triage_engine,
    # Scheduling
    SchedulingService,
    SchedulingPreferences,
    AppointmentType,
    Patient,
    get_scheduling_service,
    # Recall
    RecallService,
    RecallType,
    RecallStatus,
    ContactMethod,
    get_recall_service,
    # Compliance
    ConsentManager,
    ConsentType,
    ConsentStatus,
    AuditLogger,
    AuditAction,
    DataProtectionService,
    get_consent_manager,
    get_audit_logger,
    get_data_protection_service,
)


class TestTriageEngine:
    """Tests for the triage engine."""

    def test_emergency_detection_chest_pain(self):
        """Test emergency detection for chest pain."""
        engine = TriageEngine()
        result = engine.assess(
            symptoms=[],
            free_text="Ich habe starke Brustschmerzen und Atemnot",
        )

        assert result.urgency == UrgencyLevel.EMERGENCY
        assert result.risk_score == 100.0
        assert len(result.emergency_symptoms) > 0
        assert "112" in result.recommended_action

    def test_emergency_detection_stroke(self):
        """Test emergency detection for stroke symptoms."""
        engine = TriageEngine()
        result = engine.assess(
            symptoms=[],
            free_text="Mein Arm ist plötzlich taub und ich habe Sprachstörungen",
        )

        assert result.urgency == UrgencyLevel.EMERGENCY

    def test_urgent_high_fever(self):
        """Test urgent classification for high fever."""
        engine = TriageEngine()
        symptoms = [
            Symptom(
                name="fieber",
                category=SymptomCategory.GENERAL,
                severity=8,
                fever=True,
                fever_temp=39.8,
            )
        ]

        result = engine.assess(symptoms=symptoms)

        assert result.urgency in [UrgencyLevel.URGENT, UrgencyLevel.VERY_URGENT]
        assert result.risk_score >= 60

    def test_standard_cold_symptoms(self):
        """Test standard classification for common cold."""
        engine = TriageEngine()
        symptoms = [
            Symptom(name="schnupfen", category=SymptomCategory.RESPIRATORY, severity=3),
            Symptom(name="husten", category=SymptomCategory.RESPIRATORY, severity=3),
        ]

        result = engine.assess(symptoms=symptoms)

        assert result.urgency in [UrgencyLevel.NON_URGENT, UrgencyLevel.STANDARD]
        assert result.risk_score < 50

    def test_patient_risk_multiplier_elderly(self):
        """Test risk multiplier for elderly patients."""
        engine = TriageEngine()
        symptoms = [
            Symptom(name="fieber", category=SymptomCategory.GENERAL, severity=6)
        ]

        # Without age context
        result_young = engine.assess(
            symptoms=symptoms,
            patient=PatientContext(age=35),
        )

        # With elderly context
        result_elderly = engine.assess(
            symptoms=symptoms,
            patient=PatientContext(age=78),
        )

        assert result_elderly.risk_score > result_young.risk_score

    def test_patient_risk_multiplier_pregnant(self):
        """Test risk multiplier for pregnant patients."""
        engine = TriageEngine()
        symptoms = [
            Symptom(name="bauchschmerzen", category=SymptomCategory.GASTROINTESTINAL, severity=5)
        ]

        result_normal = engine.assess(
            symptoms=symptoms,
            patient=PatientContext(is_pregnant=False),
        )

        result_pregnant = engine.assess(
            symptoms=symptoms,
            patient=PatientContext(is_pregnant=True),
        )

        assert result_pregnant.risk_score > result_normal.risk_score

    def test_symptom_extraction_german(self):
        """Test symptom extraction from German text."""
        engine = TriageEngine()
        symptoms = engine.extract_symptoms_from_text(
            "Ich habe seit zwei Tagen starke Kopfschmerzen und Schwindel."
        )

        symptom_names = [s.name for s in symptoms]
        assert "kopfschmerzen" in symptom_names
        assert "schwindel" in symptom_names

    def test_symptom_extraction_with_fever(self):
        """Test symptom extraction with fever temperature."""
        engine = TriageEngine()
        symptoms = engine.extract_symptoms_from_text(
            "Ich habe 38,5 Grad Fieber und fühle mich schlapp."
        )

        fever_symptoms = [s for s in symptoms if s.fever]
        assert len(fever_symptoms) > 0
        assert fever_symptoms[0].fever_temp == 38.5

    def test_worsening_symptom_increases_score(self):
        """Test that worsening symptoms increase risk score."""
        engine = TriageEngine()

        symptom_stable = Symptom(
            name="husten",
            category=SymptomCategory.RESPIRATORY,
            severity=5,
            is_worsening=False,
        )

        symptom_worsening = Symptom(
            name="husten",
            category=SymptomCategory.RESPIRATORY,
            severity=5,
            is_worsening=True,
        )

        result_stable = engine.assess(symptoms=[symptom_stable])
        result_worsening = engine.assess(symptoms=[symptom_worsening])

        assert result_worsening.risk_score > result_stable.risk_score


class TestSchedulingService:
    """Tests for the scheduling service."""

    @pytest.fixture
    def service(self):
        """Create a fresh scheduling service."""
        return SchedulingService()

    @pytest.fixture
    def test_patient(self):
        """Create a test patient."""
        return Patient(
            id=uuid4(),
            first_name="Max",
            last_name="Mustermann",
            date_of_birth=date(1985, 3, 15),
            phone="+49 170 1234567",
            email="max@example.com",
            insurance_number="A123456789",
        )

    @pytest.mark.asyncio
    async def test_find_available_slots(self, service):
        """Test finding available slots."""
        prefs = SchedulingPreferences(
            preferred_date=date.today() + timedelta(days=1),
        )

        slots = await service.find_slots(prefs, limit=5)

        assert len(slots) <= 5
        for slot in slots:
            assert slot.start > datetime.now()

    @pytest.mark.asyncio
    async def test_find_slots_with_time_preference(self, service):
        """Test finding slots with morning preference."""
        prefs = SchedulingPreferences(
            preferred_time="morning",
        )

        slots = await service.find_slots(prefs, limit=10)

        # Morning slots should be scored higher
        morning_count = sum(1 for s in slots[:3] if s.start.hour < 12)
        assert morning_count >= 2  # At least 2 of top 3 should be morning

    @pytest.mark.asyncio
    async def test_book_appointment(self, service, test_patient):
        """Test booking an appointment."""
        slots = await service.find_slots(SchedulingPreferences(), limit=1)
        assert len(slots) > 0

        slot = slots[0]
        appointment = await service.book_appointment(
            slot_id=slot.id,
            patient=test_patient,
            reason="Erkältung",
            appointment_type=AppointmentType.REGULAR,
        )

        assert appointment.patient_name == "Max Mustermann"
        assert appointment.reason == "Erkältung"

    @pytest.mark.asyncio
    async def test_cancel_appointment(self, service, test_patient):
        """Test cancelling an appointment."""
        slots = await service.find_slots(SchedulingPreferences(), limit=1)
        slot = slots[0]

        appointment = await service.book_appointment(
            slot_id=slot.id,
            patient=test_patient,
            reason="Test",
        )

        result = await service.cancel_appointment(
            appointment.id,
            reason="Patient cancelled",
        )

        assert result is True

    def test_format_slot_german(self, service):
        """Test German formatting of time slots."""
        from phone_agent.industry.gesundheit.scheduling import TimeSlot, SlotStatus

        slot = TimeSlot(
            id=uuid4(),
            start=datetime(2024, 12, 16, 10, 30),  # Monday
            end=datetime(2024, 12, 16, 10, 45),
            provider_id="dr-mueller",
            provider_name="Dr. Müller",
            status=SlotStatus.AVAILABLE,
        )

        formatted = service.format_slot_for_speech(slot, "de")

        assert "Montag" in formatted
        assert "16.12." in formatted
        assert "10:30" in formatted
        assert "Dr. Müller" in formatted


class TestRecallService:
    """Tests for the recall campaign service."""

    @pytest.fixture
    def service(self):
        """Create a fresh recall service."""
        return RecallService()

    def test_create_preventive_campaign(self, service):
        """Test creating a preventive care campaign."""
        campaign = service.create_campaign(
            recall_type=RecallType.PREVENTIVE,
            target_age_min=35,
        )

        assert campaign.recall_type == RecallType.PREVENTIVE
        assert campaign.target_age_min == 35
        assert "Vorsorgeuntersuchung" in campaign.phone_script

    def test_create_vaccination_campaign(self, service):
        """Test creating a vaccination campaign."""
        campaign = service.create_campaign(
            recall_type=RecallType.VACCINATION,
            name="Grippeimpfung 2024",
        )

        assert campaign.name == "Grippeimpfung 2024"
        assert "Grippeimpfung" in campaign.phone_script

    def test_add_patient_to_campaign(self, service):
        """Test adding a patient to a campaign."""
        campaign = service.create_campaign(RecallType.PREVENTIVE)

        patient = service.add_patient_to_campaign(
            campaign_id=campaign.id,
            patient_id=uuid4(),
            first_name="Anna",
            last_name="Schmidt",
            phone="+49 170 9876543",
            priority=8,
        )

        assert patient.first_name == "Anna"
        assert patient.status == RecallStatus.PENDING
        assert patient.priority == 8

    def test_get_next_patient_by_priority(self, service):
        """Test getting next patient respects priority."""
        campaign = service.create_campaign(RecallType.PREVENTIVE)

        # Add low priority patient first
        service.add_patient_to_campaign(
            campaign_id=campaign.id,
            patient_id=uuid4(),
            first_name="Low",
            last_name="Priority",
            phone="+49 170 1111111",
            priority=2,
        )

        # Add high priority patient second
        service.add_patient_to_campaign(
            campaign_id=campaign.id,
            patient_id=uuid4(),
            first_name="High",
            last_name="Priority",
            phone="+49 170 2222222",
            priority=9,
        )

        next_patient = service.get_next_patient(campaign.id)

        assert next_patient.first_name == "High"

    def test_start_and_complete_attempt(self, service):
        """Test starting and completing a recall attempt."""
        campaign = service.create_campaign(RecallType.PREVENTIVE)
        patient = service.add_patient_to_campaign(
            campaign_id=campaign.id,
            patient_id=uuid4(),
            first_name="Test",
            last_name="Patient",
            phone="+49 170 3333333",
        )

        # Start attempt
        attempt = service.start_attempt(patient.id, ContactMethod.PHONE)

        assert attempt.attempt_number == 1
        assert patient.status == RecallStatus.IN_PROGRESS

        # Complete with appointment
        appointment_id = uuid4()
        completed = service.complete_attempt(
            attempt_id=attempt.id,
            outcome=RecallStatus.APPOINTMENT_MADE,
            appointment_id=appointment_id,
        )

        assert completed.outcome == RecallStatus.APPOINTMENT_MADE
        assert patient.status == RecallStatus.APPOINTMENT_MADE
        assert patient.appointment_id == appointment_id

    def test_campaign_stats(self, service):
        """Test getting campaign statistics."""
        campaign = service.create_campaign(RecallType.PREVENTIVE)

        # Add some patients
        for i in range(5):
            service.add_patient_to_campaign(
                campaign_id=campaign.id,
                patient_id=uuid4(),
                first_name=f"Patient{i}",
                last_name="Test",
                phone=f"+49 170 000000{i}",
            )

        stats = service.get_campaign_stats(campaign.id)

        assert stats["total_patients"] == 5
        assert stats["status_breakdown"]["pending"] == 5

    def test_personalized_phone_script(self, service):
        """Test personalized phone script generation."""
        campaign = service.create_campaign(RecallType.PREVENTIVE)
        patient = service.add_patient_to_campaign(
            campaign_id=campaign.id,
            patient_id=uuid4(),
            first_name="Maria",
            last_name="Weber",
            phone="+49 170 4444444",
        )

        script = service.get_phone_script(
            campaign_id=campaign.id,
            patient=patient,
            practice_name="Dr. Schmidt",
        )

        assert "Dr. Schmidt" in script


class TestConsentManager:
    """Tests for consent management."""

    @pytest.fixture
    def manager(self):
        """Create a fresh consent manager."""
        return ConsentManager()

    def test_grant_consent(self, manager):
        """Test granting consent."""
        patient_id = uuid4()

        consent = manager.grant_consent(
            patient_id=patient_id,
            consent_type=ConsentType.PHONE_CONTACT,
            granted_by="phone_agent",
        )

        assert consent.status == ConsentStatus.GRANTED
        assert consent.is_valid()

    def test_check_consent(self, manager):
        """Test checking consent status."""
        patient_id = uuid4()

        # Should be False before granting
        assert not manager.check_consent(patient_id, ConsentType.AI_PROCESSING)

        # Grant consent
        manager.grant_consent(patient_id, ConsentType.AI_PROCESSING)

        # Should be True after granting
        assert manager.check_consent(patient_id, ConsentType.AI_PROCESSING)

    def test_withdraw_consent(self, manager):
        """Test withdrawing consent."""
        patient_id = uuid4()

        manager.grant_consent(patient_id, ConsentType.SMS_CONTACT)
        assert manager.check_consent(patient_id, ConsentType.SMS_CONTACT)

        manager.withdraw_consent(patient_id, ConsentType.SMS_CONTACT)
        assert not manager.check_consent(patient_id, ConsentType.SMS_CONTACT)

    def test_consent_expiration(self, manager):
        """Test consent expiration."""
        patient_id = uuid4()

        consent = manager.grant_consent(
            patient_id=patient_id,
            consent_type=ConsentType.VOICE_RECORDING,
            duration_days=0,  # Expires immediately
        )

        # Set expires_at to past
        consent.expires_at = datetime.now() - timedelta(hours=1)

        assert not consent.is_valid()
        assert not manager.check_consent(patient_id, ConsentType.VOICE_RECORDING)

    def test_get_consent_text(self, manager):
        """Test getting consent text in German."""
        text = manager.get_consent_text(ConsentType.AI_PROCESSING, "de")

        assert "KI-gestützt" in text
        assert "widerrufen" in text.lower()


class TestAuditLogger:
    """Tests for audit logging."""

    @pytest.fixture
    def logger(self):
        """Create a fresh audit logger."""
        return AuditLogger()

    def test_log_action(self, logger):
        """Test logging an action."""
        entry = logger.log(
            action=AuditAction.DATA_VIEW,
            actor_id="phone_agent",
            actor_type="ai_agent",
            resource_type="patient",
            resource_id="patient-123",
        )

        assert entry.action == AuditAction.DATA_VIEW
        assert entry.checksum is not None

    def test_log_call_event(self, logger):
        """Test logging a call event."""
        entry = logger.log_call_event(
            call_id="call-456",
            action=AuditAction.CALL_STARTED,
            patient_id=uuid4(),
        )

        assert entry.resource_type == "call"
        assert entry.resource_id == "call-456"

    def test_get_patient_access_log(self, logger):
        """Test getting patient access log."""
        patient_id = uuid4()

        # Log some accesses
        logger.log_data_access(
            actor_id="phone_agent",
            resource_type="patient",
            resource_id=str(patient_id),
            patient_id=patient_id,
        )

        logger.log_data_access(
            actor_id="phone_agent",
            resource_type="appointment",
            resource_id="apt-123",
            patient_id=patient_id,
        )

        entries = logger.get_patient_access_log(patient_id)

        assert len(entries) == 2

    def test_export_audit_log_json(self, logger):
        """Test exporting audit log as JSON."""
        logger.log(
            action=AuditAction.LOGIN,
            actor_id="admin",
            actor_type="user",
            resource_type="system",
        )

        export = logger.export_audit_log(format="json")

        import json
        data = json.loads(export)
        assert len(data) == 1
        assert data[0]["action"] == "login"


class TestDataProtectionService:
    """Tests for data protection service."""

    @pytest.fixture
    def service(self):
        """Create a fresh data protection service."""
        return DataProtectionService()

    def test_anonymize_patient_data(self, service):
        """Test patient data anonymization."""
        data = {
            "first_name": "Hans",
            "last_name": "Mueller",
            "phone": "+49 170 1234567",
            "email": "hans@example.com",
            "date_of_birth": date(1985, 3, 15),
        }

        anonymized = service.anonymize_patient_data(data)

        assert anonymized["first_name"] == "***"
        assert anonymized["last_name"] == "***"
        assert anonymized["phone"].endswith("4567")
        assert anonymized["email"].startswith("***@")

    def test_pseudonymize_patient_id(self, service):
        """Test patient ID pseudonymization."""
        patient_id = uuid4()

        pseudonym = service.pseudonymize_patient_id(patient_id)

        assert len(pseudonym) == 16
        assert pseudonym != str(patient_id)

        # Same ID should produce same pseudonym
        assert service.pseudonymize_patient_id(patient_id) == pseudonym

    def test_retention_policy(self, service):
        """Test getting retention policy."""
        policy = service.get_retention_policy("medical_records")

        assert policy is not None
        assert policy.retention_days == 10 * 365
        assert "MBO-Ä" in policy.legal_basis

    def test_check_retention_expired(self, service):
        """Test checking retention expiration."""
        # Recent data
        recent = datetime.now() - timedelta(days=30)
        assert not service.check_retention_expired("medical_records", recent)

        # Old data (> 10 years)
        old = datetime.now() - timedelta(days=365 * 11)
        assert service.check_retention_expired("medical_records", old)

    def test_data_subject_rights_german(self, service):
        """Test getting data subject rights in German."""
        rights = service.get_data_subject_rights_info("de")

        assert "Auskunft" in rights["right_of_access"]
        assert "Berichtigung" in rights["right_to_rectification"]
        assert "Löschung" in rights["right_to_erasure"]
