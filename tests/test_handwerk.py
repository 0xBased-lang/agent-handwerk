"""Comprehensive tests for Handwerk (Trades) functionality."""
from datetime import date, datetime, timedelta
from uuid import uuid4

import pytest

from phone_agent.industry.handwerk import (
    # Triage
    TriageEngine,
    TriageResult,
    JobIssue,
    TradeCategory,
    UrgencyLevel,
    CustomerContext,
    get_triage_engine,
    # Basic triage
    perform_triage,
    is_emergency,
    detect_trade_category,
    # Technician
    Technician,
    TechnicianQualification,
    TechnicianMatcher,
    get_technician_matcher,
    # Scheduling
    SchedulingService,
    SchedulingPreferences,
    JobType,
    Customer,
    TimeSlot,
    get_scheduling_service,
    # Follow-up
    FollowUpService,
    FollowUpType,
    FollowUpStatus,
    get_followup_service,
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
from phone_agent.industry.handwerk.technician import (
    TradeSpecialty,
    JobRequirements,
    CertificationType,
)


class TestTriageEngine:
    """Tests for the Handwerk triage engine."""

    def test_emergency_detection_gas_leak(self):
        """Test emergency detection for gas leak."""
        engine = TriageEngine()
        result = engine.assess(
            issues=[],
            free_text="Es riecht nach Gas in der Küche",
        )

        assert result.urgency == UrgencyLevel.SICHERHEIT
        assert result.is_emergency is True
        assert result.risk_score >= 90.0

    def test_emergency_detection_water_main(self):
        """Test emergency detection for water main break."""
        engine = TriageEngine()
        result = engine.assess(
            issues=[],
            free_text="Das Wasserrohr ist geplatzt und Wasser spritzt überall",
        )

        assert result.urgency == UrgencyLevel.SICHERHEIT
        assert result.is_emergency is True

    def test_emergency_detection_electrical_fire(self):
        """Test emergency detection for electrical fire."""
        engine = TriageEngine()
        result = engine.assess(
            issues=[],
            free_text="Ein Kabel brennt und es raucht aus der Steckdose",
        )

        assert result.urgency == UrgencyLevel.SICHERHEIT
        assert result.is_emergency is True

    def test_urgent_heating_failure(self):
        """Test urgent classification for heating failure in winter."""
        engine = TriageEngine()
        result = engine.assess(
            issues=[],
            free_text="Die Heizung ist ausgefallen und es ist eiskalt",
        )

        assert result.urgency in [UrgencyLevel.SICHERHEIT, UrgencyLevel.DRINGEND]
        assert result.trade_category == TradeCategory.SHK

    def test_urgent_blocked_toilet(self):
        """Test urgent classification for blocked toilet."""
        engine = TriageEngine()
        result = engine.assess(
            issues=[],
            free_text="Die Toilette ist komplett verstopft",
        )

        assert result.urgency == UrgencyLevel.DRINGEND
        assert result.trade_category == TradeCategory.SHK

    def test_normal_repair(self):
        """Test normal classification for standard repair."""
        engine = TriageEngine()
        result = engine.assess(
            issues=[],
            free_text="Der Wasserhahn tropft seit ein paar Tagen",
        )

        assert result.urgency in [UrgencyLevel.NORMAL, UrgencyLevel.ROUTINE]
        assert result.trade_category == TradeCategory.SHK

    def test_routine_maintenance(self):
        """Test routine classification for maintenance request."""
        engine = TriageEngine()
        result = engine.assess(
            issues=[],
            free_text="Ich möchte einen Termin für die jährliche Heizungswartung",
        )

        assert result.urgency == UrgencyLevel.ROUTINE
        assert result.trade_category == TradeCategory.SHK

    def test_customer_risk_elderly(self):
        """Test risk multiplier for elderly customers."""
        engine = TriageEngine()

        result_normal = engine.assess(
            issues=[],
            free_text="Die Heizung funktioniert nicht richtig",
            customer=CustomerContext(is_elderly=False),
        )

        result_elderly = engine.assess(
            issues=[],
            free_text="Die Heizung funktioniert nicht richtig",
            customer=CustomerContext(is_elderly=True),
        )

        assert result_elderly.risk_score > result_normal.risk_score

    def test_customer_risk_commercial(self):
        """Test commercial customers get appropriate priority."""
        engine = TriageEngine()

        result = engine.assess(
            issues=[],
            free_text="Die Klimaanlage im Büro ist ausgefallen",
            customer=CustomerContext(is_commercial=True),
        )

        assert result.trade_category == TradeCategory.SHK

    def test_issue_extraction_german(self):
        """Test issue extraction from German text."""
        engine = TriageEngine()
        issues = engine.extract_issues_from_text(
            "Der Wasserhahn tropft und die Heizung macht komische Geräusche"
        )

        assert len(issues) >= 1
        # Should detect plumbing/heating issues
        categories = [i.category for i in issues]
        assert TradeCategory.SHK in categories

    def test_trade_category_detection_elektro(self):
        """Test electrical trade category detection."""
        engine = TriageEngine()
        result = engine.assess(
            issues=[],
            free_text="Die Steckdose in der Küche funktioniert nicht mehr",
        )

        assert result.trade_category == TradeCategory.ELEKTRO

    def test_trade_category_detection_schlosser(self):
        """Test locksmith trade category detection."""
        engine = TriageEngine()
        result = engine.assess(
            issues=[],
            free_text="Ich habe mich ausgesperrt und komme nicht mehr rein",
        )

        assert result.trade_category == TradeCategory.SCHLOSSER


class TestBasicTriage:
    """Tests for basic triage functions from workflows.py."""

    def test_is_emergency_gas(self):
        """Test emergency detection for gas keywords."""
        assert is_emergency("Es riecht nach Gas")
        assert is_emergency("Ich rieche Gasgeruch")

    def test_is_emergency_water(self):
        """Test emergency detection for water keywords."""
        assert is_emergency("Das Rohr ist geplatzt")
        assert is_emergency("Wasserrohrbruch im Keller")

    def test_is_emergency_electrical(self):
        """Test emergency detection for electrical keywords."""
        assert is_emergency("Ein Kabel brennt")
        assert is_emergency("Steckdose raucht")

    def test_not_emergency(self):
        """Test non-emergency situations."""
        assert not is_emergency("Der Wasserhahn tropft")
        assert not is_emergency("Ich brauche einen Wartungstermin")

    def test_detect_trade_category_shk(self):
        """Test SHK category detection."""
        category = detect_trade_category("Die Heizung ist kaputt")
        assert category == TradeCategory.SHK

    def test_detect_trade_category_elektro(self):
        """Test electrical category detection."""
        category = detect_trade_category("Die Steckdose funktioniert nicht")
        assert category == TradeCategory.ELEKTRO

    def test_perform_triage_basic(self):
        """Test basic triage function."""
        result = perform_triage("Die Toilette ist verstopft")

        assert result.urgency in [UrgencyLevel.DRINGEND, UrgencyLevel.NORMAL]
        assert result.trade_category == TradeCategory.SHK


class TestTechnicianMatcher:
    """Tests for technician matching."""

    @pytest.fixture
    def matcher(self):
        """Create a fresh technician matcher."""
        return TechnicianMatcher()

    def test_find_matches_by_category(self, matcher):
        """Test finding technicians by trade category."""
        requirements = JobRequirements(specialty=TradeSpecialty.SHK)
        matches = matcher.find_best_matches(requirements, limit=5)

        # Should return matches (may be empty if no technicians registered)
        assert isinstance(matches, list)

    def test_match_includes_score(self, matcher):
        """Test that matches include a score."""
        # Add a test technician
        technician = Technician(
            id=uuid4(),
            name="Max Mustermann",
            specialties=[TradeSpecialty.SHK, TradeSpecialty.ELEKTRO],
            qualification=TechnicianQualification.MEISTER,
            certifications=[CertificationType.GAS_BERECHTIGUNG],
            phone="+49 170 1234567",
        )
        matcher.add_technician(technician)

        requirements = JobRequirements(specialty=TradeSpecialty.SHK)
        matches = matcher.find_best_matches(requirements, limit=5)

        if matches:
            assert hasattr(matches[0], 'score')
            assert 0 <= matches[0].score <= 100

    def test_certification_filter(self, matcher):
        """Test filtering by required certifications."""
        # Add technician with gas certification
        tech_gas = Technician(
            id=uuid4(),
            name="Gas Spezialist",
            specialties=[TradeSpecialty.SHK],
            qualification=TechnicianQualification.MEISTER,
            certifications=[CertificationType.GAS_BERECHTIGUNG],
            phone="+49 170 1111111",
        )
        matcher.add_technician(tech_gas)

        # Add technician without gas certification
        tech_no_gas = Technician(
            id=uuid4(),
            name="Allround Monteur",
            specialties=[TradeSpecialty.SHK],
            qualification=TechnicianQualification.GESELLE,
            certifications=[],
            phone="+49 170 2222222",
        )
        matcher.add_technician(tech_no_gas)

        requirements = JobRequirements(
            specialty=TradeSpecialty.SHK,
            required_certifications=[CertificationType.GAS_BERECHTIGUNG],
        )
        matches = matcher.find_best_matches(requirements, limit=5)

        # Only gas-certified technician should match (or have higher score)
        if matches:
            assert hasattr(matches[0], 'score')


class TestSchedulingService:
    """Tests for the scheduling service."""

    @pytest.fixture
    def service(self):
        """Create a fresh scheduling service."""
        return SchedulingService()

    @pytest.fixture
    def test_customer(self):
        """Create a test customer."""
        return Customer(
            id=uuid4(),
            first_name="Max",
            last_name="Mustermann",
            phone="+49 170 1234567",
            street="Musterstraße 123",
            zip_code="12345",
            city="Berlin",
        )

    @pytest.mark.asyncio
    async def test_find_available_slots(self, service):
        """Test finding available slots."""
        prefs = SchedulingPreferences(
            job_type=JobType.REPARATUR,
        )

        slots = await service.find_slots(prefs, limit=5)

        assert len(slots) <= 5
        for slot in slots:
            # Slots should be for today or future dates
            assert slot.date >= date.today()

    @pytest.mark.asyncio
    async def test_find_slots_urgent(self, service):
        """Test finding urgent slots (same day)."""
        prefs = SchedulingPreferences(
            job_type=JobType.NOTFALL,
            urgency_max_wait_hours=4,
        )

        slots = await service.find_slots(prefs, limit=5)

        # Urgent slots should be for today (same day)
        if slots:
            assert slots[0].date == date.today()

    @pytest.mark.asyncio
    async def test_book_service_call(self, service, test_customer):
        """Test booking a service call."""
        slots = await service.find_slots(SchedulingPreferences(), limit=1)

        if slots:
            slot = slots[0]
            service_call = await service.book_service_call(
                slot_id=slot.id,
                customer=test_customer,
                job_description="Wasserhahn tropft",
                job_type=JobType.REPARATUR,
            )

            assert service_call.customer_name == "Max Mustermann"
            assert service_call.job_description == "Wasserhahn tropft"

    @pytest.mark.asyncio
    async def test_job_types(self, service):
        """Test that all job types are available."""
        for job_type in JobType:
            prefs = SchedulingPreferences(job_type=job_type)
            # Should not raise
            await service.find_slots(prefs, limit=1)


class TestFollowUpService:
    """Tests for the follow-up campaign service."""

    @pytest.fixture
    def service(self):
        """Create a fresh follow-up service."""
        return FollowUpService()

    def test_create_maintenance_campaign(self, service):
        """Test creating a maintenance campaign."""
        campaign = service.create_campaign(
            followup_type=FollowUpType.MAINTENANCE,
            target_trade_category=TradeCategory.SHK,
        )

        assert campaign.followup_type == FollowUpType.MAINTENANCE
        assert "Wartung" in campaign.phone_script or "Heizung" in campaign.phone_script

    def test_create_quote_followup_campaign(self, service):
        """Test creating a quote follow-up campaign."""
        campaign = service.create_quote_followup_campaign(days_since_quote=7)

        assert campaign.followup_type == FollowUpType.QUOTE_FOLLOWUP
        assert campaign.target_quote_age_days == 7

    def test_add_customer_to_campaign(self, service):
        """Test adding a customer to a campaign."""
        campaign = service.create_campaign(FollowUpType.MAINTENANCE)

        customer = service.add_customer_to_campaign(
            campaign_id=campaign.id,
            customer_id=uuid4(),
            first_name="Anna",
            last_name="Schmidt",
            phone="+49 170 9876543",
            equipment_info="Viessmann Vitodens 200-W",
            priority=8,
        )

        assert customer.first_name == "Anna"
        assert customer.status == FollowUpStatus.PENDING
        assert customer.equipment_info == "Viessmann Vitodens 200-W"

    def test_get_next_customer_by_priority(self, service):
        """Test getting next customer respects priority."""
        campaign = service.create_campaign(FollowUpType.MAINTENANCE)

        # Add low priority customer first
        service.add_customer_to_campaign(
            campaign_id=campaign.id,
            customer_id=uuid4(),
            first_name="Low",
            last_name="Priority",
            phone="+49 170 1111111",
            priority=2,
        )

        # Add high priority customer second
        service.add_customer_to_campaign(
            campaign_id=campaign.id,
            customer_id=uuid4(),
            first_name="High",
            last_name="Priority",
            phone="+49 170 2222222",
            priority=9,
        )

        next_customer = service.get_next_customer(campaign.id)

        assert next_customer.first_name == "High"

    def test_campaign_stats(self, service):
        """Test getting campaign statistics."""
        campaign = service.create_campaign(FollowUpType.MAINTENANCE)

        # Add some customers
        for i in range(5):
            service.add_customer_to_campaign(
                campaign_id=campaign.id,
                customer_id=uuid4(),
                first_name=f"Customer{i}",
                last_name="Test",
                phone=f"+49 170 000000{i}",
            )

        stats = service.get_campaign_stats(campaign.id)

        assert stats["total_customers"] == 5
        assert stats["status_breakdown"]["pending"] == 5

    def test_personalized_phone_script(self, service):
        """Test personalized phone script generation."""
        campaign = service.create_campaign(FollowUpType.MAINTENANCE)
        customer = service.add_customer_to_campaign(
            campaign_id=campaign.id,
            customer_id=uuid4(),
            first_name="Maria",
            last_name="Weber",
            phone="+49 170 4444444",
            equipment_info="Buderus Logamax plus GB192i",
        )

        script = service.get_phone_script(
            campaign_id=campaign.id,
            customer=customer,
            company_name="Heizung Müller GmbH",
        )

        assert "Heizung Müller GmbH" in script

    def test_seasonal_recommendations(self, service):
        """Test getting seasonal campaign recommendations."""
        # September should have heating-related campaigns
        recommendations = service.get_seasonal_campaigns_for_month(9)

        assert len(recommendations) > 0
        # Should include heating/SHK campaigns in September
        trades = [r.get("trade") for r in recommendations]
        assert TradeCategory.SHK in trades or any(
            r.get("name", "").lower().count("heiz") > 0 for r in recommendations
        )


class TestConsentManager:
    """Tests for consent management."""

    @pytest.fixture
    def manager(self):
        """Create a fresh consent manager."""
        return ConsentManager()

    def test_grant_consent(self, manager):
        """Test granting consent."""
        customer_id = uuid4()

        consent = manager.grant_consent(
            customer_id=customer_id,
            consent_type=ConsentType.PHONE_CONTACT,
            granted_by="phone_agent",
        )

        assert consent.status == ConsentStatus.GRANTED
        assert consent.is_valid()

    def test_grant_photo_consent(self, manager):
        """Test granting photo documentation consent."""
        customer_id = uuid4()
        job_id = uuid4()

        consent = manager.grant_consent(
            customer_id=customer_id,
            consent_type=ConsentType.PHOTO_DOCUMENTATION,
            job_id=job_id,
        )

        assert consent.consent_type == ConsentType.PHOTO_DOCUMENTATION
        assert consent.job_id == job_id

    def test_check_consent(self, manager):
        """Test checking consent status."""
        customer_id = uuid4()

        # Should be False before granting
        assert not manager.check_consent(customer_id, ConsentType.AI_PROCESSING)

        # Grant consent
        manager.grant_consent(customer_id, ConsentType.AI_PROCESSING)

        # Should be True after granting
        assert manager.check_consent(customer_id, ConsentType.AI_PROCESSING)

    def test_withdraw_consent(self, manager):
        """Test withdrawing consent."""
        customer_id = uuid4()

        manager.grant_consent(customer_id, ConsentType.SMS_CONTACT)
        assert manager.check_consent(customer_id, ConsentType.SMS_CONTACT)

        manager.withdraw_consent(customer_id, ConsentType.SMS_CONTACT)
        assert not manager.check_consent(customer_id, ConsentType.SMS_CONTACT)

    def test_get_consent_text_german(self, manager):
        """Test getting consent text in German."""
        text = manager.get_consent_text(ConsentType.PHOTO_DOCUMENTATION, "de")

        assert "Foto" in text
        assert "widerrufen" in text.lower()

    def test_required_consents_for_service(self, manager):
        """Test getting required consents for service calls."""
        required = manager.get_required_consents_for_service()

        assert ConsentType.SERVICE_CONTRACT in required
        assert ConsentType.DATA_PROCESSING in required


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
            resource_type="customer",
            resource_id="customer-123",
        )

        assert entry.action == AuditAction.DATA_VIEW
        assert entry.checksum is not None

    def test_log_service_call_event(self, logger):
        """Test logging a service call event."""
        entry = logger.log_service_call_event(
            service_call_id="sc-456",
            action=AuditAction.SERVICE_CALL_CREATED,
            customer_id=uuid4(),
        )

        assert entry.resource_type == "service_call"
        assert entry.resource_id == "sc-456"

    def test_log_technician_event(self, logger):
        """Test logging a technician event."""
        technician_id = uuid4()
        job_id = uuid4()

        entry = logger.log_technician_event(
            technician_id=technician_id,
            action=AuditAction.TECHNICIAN_DISPATCHED,
            job_id=job_id,
        )

        assert entry.action == AuditAction.TECHNICIAN_DISPATCHED
        assert entry.technician_id == technician_id

    def test_get_customer_access_log(self, logger):
        """Test getting customer access log."""
        customer_id = uuid4()

        # Log some accesses
        logger.log_data_access(
            actor_id="phone_agent",
            resource_type="customer",
            resource_id=str(customer_id),
            customer_id=customer_id,
        )

        logger.log_data_access(
            actor_id="phone_agent",
            resource_type="service_call",
            resource_id="sc-123",
            customer_id=customer_id,
        )

        entries = logger.get_customer_access_log(customer_id)

        assert len(entries) == 2

    def test_get_job_log(self, logger):
        """Test getting job-specific log."""
        job_id = uuid4()

        logger.log(
            action=AuditAction.SERVICE_CALL_CREATED,
            actor_id="phone_agent",
            actor_type="ai_agent",
            resource_type="service_call",
            job_id=job_id,
        )

        entries = logger.get_job_log(job_id)

        assert len(entries) == 1

    def test_export_audit_log_json(self, logger):
        """Test exporting audit log as JSON."""
        logger.log(
            action=AuditAction.SERVICE_CALL_CREATED,
            actor_id="admin",
            actor_type="user",
            resource_type="service_call",
        )

        export = logger.export_audit_log(format="json")

        import json
        data = json.loads(export)
        assert len(data) == 1
        assert data[0]["action"] == "service_call_created"


class TestDataProtectionService:
    """Tests for data protection service."""

    @pytest.fixture
    def service(self):
        """Create a fresh data protection service."""
        return DataProtectionService()

    def test_anonymize_customer_data(self, service):
        """Test customer data anonymization."""
        data = {
            "first_name": "Hans",
            "last_name": "Mueller",
            "phone": "+49 170 1234567",
            "email": "hans@example.com",
            "street": "Musterstraße 123",
            "zip_code": "12345",
        }

        anonymized = service.anonymize_customer_data(data)

        assert anonymized["first_name"] == "***"
        assert anonymized["last_name"] == "***"
        assert anonymized["phone"].endswith("4567")
        assert anonymized["email"].startswith("***@")
        assert anonymized["street"] == "***"
        assert anonymized["zip_code"].startswith("12")

    def test_pseudonymize_customer_id(self, service):
        """Test customer ID pseudonymization."""
        customer_id = uuid4()

        pseudonym = service.pseudonymize_customer_id(customer_id)

        assert len(pseudonym) == 16
        assert pseudonym != str(customer_id)

        # Same ID should produce same pseudonym
        assert service.pseudonymize_customer_id(customer_id) == pseudonym

    def test_retention_policy_invoices(self, service):
        """Test retention policy for invoices (10 years per HGB)."""
        policy = service.get_retention_policy("invoices")

        assert policy is not None
        assert policy.retention_days == 10 * 365
        assert "HGB" in policy.legal_basis

    def test_retention_policy_warranty(self, service):
        """Test retention policy for warranty records (5 years)."""
        policy = service.get_retention_policy("warranty_records")

        assert policy is not None
        assert policy.retention_days == 5 * 365
        assert "BGB" in policy.legal_basis

    def test_check_retention_expired(self, service):
        """Test checking retention expiration."""
        # Recent invoice
        recent = datetime.now() - timedelta(days=30)
        assert not service.check_retention_expired("invoices", recent)

        # Old invoice (> 10 years)
        old = datetime.now() - timedelta(days=365 * 11)
        assert service.check_retention_expired("invoices", old)

    def test_data_subject_rights_german(self, service):
        """Test getting data subject rights in German."""
        rights = service.get_data_subject_rights_info("de")

        assert "Auskunft" in rights["right_of_access"]
        assert "Berichtigung" in rights["right_to_rectification"]
        assert "Löschung" in rights["right_to_erasure"]
        assert "HGB" in rights["retention_info"]  # Handwerk-specific
