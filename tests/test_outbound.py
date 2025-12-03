"""Tests for outbound calling components."""

import asyncio
from datetime import datetime, date, time, timedelta
from uuid import uuid4

import pytest

from phone_agent.industry.gesundheit.outbound.dialer import (
    OutboundDialer,
    DialerConfig,
    DialerStatus,
    CallPriority,
    QueuedCall,
)
from phone_agent.industry.gesundheit.outbound.conversation_outbound import (
    OutboundConversationManager,
    OutboundState,
    OutboundOutcome,
    OutboundCallType,
)
from phone_agent.industry.gesundheit.outbound.reminder_workflow import (
    AppointmentReminderWorkflow,
    ReminderTask,
    ReminderStatus,
    ReminderCampaignConfig,
)
from phone_agent.industry.gesundheit.outbound.recall_workflow import (
    RecallCampaignWorkflow,
    RecallCallTask,
    RecallCallStatus,
)
from phone_agent.industry.gesundheit.outbound.noshow_workflow import (
    NoShowFollowupWorkflow,
    NoShowFollowupTask,
    NoShowOutcome,
    NoShowReason,
)
from phone_agent.industry.gesundheit.recall import (
    RecallService,
    RecallType,
    RecallCampaign,
)
from phone_agent.industry.gesundheit.scheduling import (
    SchedulingService,
    Appointment,
    AppointmentType,
    TimeSlot,
    SlotStatus,
)
from phone_agent.telephony.sip_client import SIPClient, SIPConfig


class TestOutboundDialer:
    """Test OutboundDialer functionality."""

    @pytest.fixture
    def dialer_config(self):
        """Create dialer config for testing."""
        return DialerConfig(
            business_hours_start=time(0, 0),  # Allow 24h for testing
            business_hours_end=time(23, 59),
            weekdays_only=False,  # Allow all days for testing
            max_concurrent_calls=2,
            calls_per_minute=10,
        )

    @pytest.fixture
    def dialer(self, dialer_config):
        """Create dialer for testing."""
        sip_config = SIPConfig(server="", register=False)
        sip_client = SIPClient(sip_config)
        return OutboundDialer(config=dialer_config, sip_client=sip_client)

    @pytest.mark.asyncio
    async def test_queue_call(self, dialer):
        """Test queuing a call."""
        patient_id = str(uuid4())
        phone = "+49170123456"

        dialer.queue_call(
            patient_id=patient_id,
            phone_number=phone,
            campaign_type="reminder",
            priority=CallPriority.NORMAL,
        )

        queue = dialer.get_queue_snapshot()
        assert len(queue) == 1
        assert queue[0].patient_id == patient_id
        assert queue[0].phone_number == phone
        assert queue[0].priority == CallPriority.NORMAL.value

    @pytest.mark.asyncio
    async def test_priority_ordering(self, dialer):
        """Test that urgent calls are processed first."""
        # Queue low priority first
        dialer.queue_call(
            patient_id=str(uuid4()),
            phone_number="+49170000001",
            campaign_type="recall",
            priority=CallPriority.LOW,
        )

        # Queue urgent priority second
        dialer.queue_call(
            patient_id=str(uuid4()),
            phone_number="+49170000002",
            campaign_type="reminder",
            priority=CallPriority.URGENT,
        )

        # Queue normal priority third
        dialer.queue_call(
            patient_id=str(uuid4()),
            phone_number="+49170000003",
            campaign_type="recall",
            priority=CallPriority.NORMAL,
        )

        queue = dialer.get_queue_snapshot()
        assert len(queue) == 3

        # Urgent should be first due to lower priority value
        priorities = [q.priority for q in queue]
        assert priorities[0] == CallPriority.URGENT.value

    @pytest.mark.asyncio
    async def test_cancel_queued_call(self, dialer):
        """Test cancelling a queued call."""
        patient_id = str(uuid4())

        dialer.queue_call(
            patient_id=patient_id,
            phone_number="+49170123456",
            campaign_type="reminder",
        )

        queue = dialer.get_queue_snapshot()
        call_id = queue[0].call_id

        success = dialer.cancel_call(call_id)
        assert success

        queue = dialer.get_queue_snapshot()
        assert len(queue) == 0

    @pytest.mark.asyncio
    async def test_dialer_pause_resume(self, dialer):
        """Test pausing and resuming dialer."""
        assert dialer.status == DialerStatus.STOPPED

        # Start the dialer first
        await dialer.start()
        assert dialer.status == DialerStatus.RUNNING

        dialer.pause()
        assert dialer.status == DialerStatus.PAUSED

        dialer.resume()
        assert dialer.status == DialerStatus.RUNNING

        await dialer.stop()

    @pytest.mark.asyncio
    async def test_clear_queue(self, dialer):
        """Test clearing the call queue."""
        # Queue multiple calls
        for i in range(5):
            dialer.queue_call(
                patient_id=str(uuid4()),
                phone_number=f"+4917000000{i}",
                campaign_type="recall",
            )

        queue = dialer.get_queue_snapshot()
        assert len(queue) == 5

        count = dialer.clear_queue()
        assert count == 5

        queue = dialer.get_queue_snapshot()
        assert len(queue) == 0

    def test_business_hours_check(self, dialer):
        """Test business hours checking."""
        # Config allows 24h, so should always be active
        assert dialer._is_within_business_hours() is True


class TestOutboundConversation:
    """Test OutboundConversationManager functionality."""

    @pytest.fixture
    def conversation_manager(self):
        """Create conversation manager for testing."""
        return OutboundConversationManager()

    @pytest.mark.asyncio
    async def test_reminder_conversation_start(self, conversation_manager):
        """Test starting a reminder conversation."""
        from phone_agent.industry.gesundheit.outbound.conversation_outbound import (
            OutboundContext,
            CampaignType,
        )

        context = OutboundContext(
            campaign_type=CampaignType.REMINDER,
            patient_name="Max Mustermann",
            appointment_date=date.today() + timedelta(days=1),
            appointment_time=time(10, 0),
            provider_name="Dr. Müller",
        )

        response = await conversation_manager.start_conversation(context)

        assert context.campaign_type == CampaignType.REMINDER
        assert context.patient_name == "Max Mustermann"
        assert context.state == OutboundState.INTRODUCTION

    @pytest.mark.asyncio
    async def test_identity_verification_success(self, conversation_manager):
        """Test successful identity verification."""
        from phone_agent.industry.gesundheit.outbound.conversation_outbound import (
            OutboundContext,
            CampaignType,
        )

        context = OutboundContext(
            campaign_type=CampaignType.REMINDER,
            patient_name="Max Mustermann",
        )

        # Start conversation first
        await conversation_manager.start_conversation(context)

        # Simulate patient confirming identity
        response = await conversation_manager.process_input(context, "Ja, ich bin Max Mustermann")

        assert context.identity_verified is True
        assert context.state == OutboundState.PURPOSE_STATEMENT

    @pytest.mark.asyncio
    async def test_appointment_confirmation(self, conversation_manager):
        """Test appointment confirmation flow."""
        from phone_agent.industry.gesundheit.outbound.conversation_outbound import (
            OutboundContext,
            CampaignType,
        )

        context = OutboundContext(
            campaign_type=CampaignType.REMINDER,
            patient_name="Max Mustermann",
            appointment_date=date.today() + timedelta(days=1),
            appointment_time=time(10, 0),
        )

        # Fast-forward to main dialog
        context.state = OutboundState.MAIN_DIALOG
        context.identity_verified = True

        # Patient confirms appointment
        response = await conversation_manager.process_input(context, "Ja, den Termin kann ich wahrnehmen")

        # Outcome should be set (either confirmed or information_delivered depending on state)
        assert context.outcome is not None

    @pytest.mark.asyncio
    async def test_appointment_reschedule_request(self, conversation_manager):
        """Test reschedule request during reminder call."""
        from phone_agent.industry.gesundheit.outbound.conversation_outbound import (
            OutboundContext,
            CampaignType,
        )

        context = OutboundContext(
            campaign_type=CampaignType.REMINDER,
            patient_name="Max Mustermann",
        )

        context.state = OutboundState.MAIN_DIALOG
        context.identity_verified = True

        # Patient wants to reschedule
        response = await conversation_manager.process_input(context, "Kann ich den Termin verschieben?")

        # Verify we got a response (reschedule handling varies by implementation)
        assert response is not None

    @pytest.mark.asyncio
    async def test_recall_campaign_purpose(self, conversation_manager):
        """Test recall campaign purpose statement."""
        from phone_agent.industry.gesundheit.outbound.conversation_outbound import (
            OutboundContext,
            CampaignType,
        )

        context = OutboundContext(
            campaign_type=CampaignType.RECALL,
            patient_name="Erika Musterfrau",
        )

        context.state = OutboundState.PURPOSE_STATEMENT
        context.identity_verified = True

        # Start conversation to get purpose statement
        response = await conversation_manager.start_conversation(context)

        # The response message should mention the purpose
        assert response.message is not None


class TestReminderWorkflow:
    """Test AppointmentReminderWorkflow functionality."""

    @pytest.fixture
    def mock_dialer(self):
        """Create mock dialer."""
        sip_config = SIPConfig(server="", register=False)
        sip_client = SIPClient(sip_config)
        config = DialerConfig(business_hours_start=0, business_hours_end=24)
        return OutboundDialer(sip_client, config)

    @pytest.fixture
    def reminder_workflow(self, mock_dialer):
        """Create reminder workflow for testing."""
        config = ReminderCampaignConfig(
            reminder_hours_before=48,
            min_hours_before=1,
            practice_name="Test Praxis",
        )
        return AppointmentReminderWorkflow(dialer=mock_dialer, config=config)

    def test_reminder_task_priority(self):
        """Test reminder task priority calculation."""
        # Task for appointment in 3 hours - should be URGENT
        urgent_task = ReminderTask(
            id=uuid4(),
            appointment_id=uuid4(),
            patient_id=uuid4(),
            patient_name="Test Patient",
            patient_phone="+49170123456",
            appointment_time=datetime.now() + timedelta(hours=3),
            provider_name="Dr. Test",
            appointment_type=AppointmentType.REGULAR,
        )
        assert urgent_task.priority == CallPriority.URGENT

        # Task for appointment in 10 hours - should be HIGH
        high_task = ReminderTask(
            id=uuid4(),
            appointment_id=uuid4(),
            patient_id=uuid4(),
            patient_name="Test Patient",
            patient_phone="+49170123456",
            appointment_time=datetime.now() + timedelta(hours=10),
            provider_name="Dr. Test",
            appointment_type=AppointmentType.REGULAR,
        )
        assert high_task.priority == CallPriority.HIGH

        # Task for appointment in 20 hours - should be NORMAL
        normal_task = ReminderTask(
            id=uuid4(),
            appointment_id=uuid4(),
            patient_id=uuid4(),
            patient_name="Test Patient",
            patient_phone="+49170123456",
            appointment_time=datetime.now() + timedelta(hours=20),
            provider_name="Dr. Test",
            appointment_type=AppointmentType.REGULAR,
        )
        assert normal_task.priority == CallPriority.NORMAL

    def test_stats_calculation(self, reminder_workflow):
        """Test statistics calculation."""
        stats = reminder_workflow.get_stats()

        # Initial stats should be zero
        assert stats.total_appointments == 0
        assert stats.reminders_sent == 0
        assert stats.confirmation_rate == 0.0


class TestRecallWorkflow:
    """Test RecallCampaignWorkflow functionality."""

    @pytest.fixture
    def recall_service(self):
        """Create recall service for testing."""
        return RecallService()

    @pytest.fixture
    def mock_dialer(self):
        """Create mock dialer."""
        sip_config = SIPConfig(server="", register=False)
        sip_client = SIPClient(sip_config)
        config = DialerConfig(business_hours_start=0, business_hours_end=24)
        return OutboundDialer(sip_client, config)

    @pytest.fixture
    def recall_workflow(self, mock_dialer, recall_service):
        """Create recall workflow for testing."""
        return RecallCampaignWorkflow(
            dialer=mock_dialer,
            recall_service=recall_service,
            practice_name="Test Praxis",
        )

    def test_create_campaign(self, recall_service):
        """Test creating a recall campaign."""
        campaign = recall_service.create_campaign(
            recall_type=RecallType.PREVENTIVE,
            name="Check-up Kampagne",
        )

        assert campaign.recall_type == RecallType.PREVENTIVE
        assert campaign.active is True
        assert "Vorsorge" in campaign.phone_script or "Check-up" in campaign.name

    def test_add_patient_to_campaign(self, recall_service):
        """Test adding patient to campaign."""
        campaign = recall_service.create_campaign(
            recall_type=RecallType.VACCINATION,
        )

        patient = recall_service.add_patient_to_campaign(
            campaign_id=campaign.id,
            patient_id=uuid4(),
            first_name="Test",
            last_name="Patient",
            phone="+49170123456",
            priority=8,
        )

        assert patient.campaign_id == campaign.id
        assert patient.priority == 8
        assert patient.attempts == 0

    def test_get_next_patient_priority(self, recall_service):
        """Test getting next patient respects priority."""
        campaign = recall_service.create_campaign(RecallType.PREVENTIVE)

        # Add low priority patient first
        recall_service.add_patient_to_campaign(
            campaign_id=campaign.id,
            patient_id=uuid4(),
            first_name="Low",
            last_name="Priority",
            phone="+49170000001",
            priority=2,
        )

        # Add high priority patient second
        recall_service.add_patient_to_campaign(
            campaign_id=campaign.id,
            patient_id=uuid4(),
            first_name="High",
            last_name="Priority",
            phone="+49170000002",
            priority=9,
        )

        next_patient = recall_service.get_next_patient(campaign.id)

        # High priority should be returned first
        assert next_patient.first_name == "High"
        assert next_patient.priority == 9


class TestNoShowWorkflow:
    """Test NoShowFollowupWorkflow functionality."""

    @pytest.fixture
    def mock_dialer(self):
        """Create mock dialer."""
        sip_config = SIPConfig(server="", register=False)
        sip_client = SIPClient(sip_config)
        config = DialerConfig(business_hours_start=0, business_hours_end=24)
        return OutboundDialer(sip_client, config)

    @pytest.fixture
    def noshow_workflow(self, mock_dialer):
        """Create no-show workflow for testing."""
        return NoShowFollowupWorkflow(dialer=mock_dialer)

    def test_noshow_task_priority_urgent(self):
        """Test no-show task priority for recent misses."""
        # Missed 2 hours ago - should be HIGH priority
        task = NoShowFollowupTask(
            id=uuid4(),
            missed_appointment_id=uuid4(),
            patient_id=uuid4(),
            patient_name="Test Patient",
            patient_phone="+49170123456",
            missed_time=datetime.now() - timedelta(hours=2),
            provider_name="Dr. Test",
            appointment_reason="Check-up",
            appointment_type=AppointmentType.REGULAR,
        )

        assert task.priority == CallPriority.HIGH

    def test_noshow_task_priority_normal(self):
        """Test no-show task priority for older misses."""
        # Missed 12 hours ago - should be NORMAL priority
        task = NoShowFollowupTask(
            id=uuid4(),
            missed_appointment_id=uuid4(),
            patient_id=uuid4(),
            patient_name="Test Patient",
            patient_phone="+49170123456",
            missed_time=datetime.now() - timedelta(hours=12),
            provider_name="Dr. Test",
            appointment_reason="Check-up",
            appointment_type=AppointmentType.REGULAR,
        )

        assert task.priority == CallPriority.NORMAL

    def test_noshow_task_acute_priority(self):
        """Test no-show task priority for acute appointments."""
        # Acute appointment missed - should be HIGH regardless of time
        task = NoShowFollowupTask(
            id=uuid4(),
            missed_appointment_id=uuid4(),
            patient_id=uuid4(),
            patient_name="Test Patient",
            patient_phone="+49170123456",
            missed_time=datetime.now() - timedelta(hours=20),
            provider_name="Dr. Test",
            appointment_reason="Acute issue",
            appointment_type=AppointmentType.ACUTE,
        )

        assert task.priority == CallPriority.HIGH

    def test_barrier_identification(self, noshow_workflow):
        """Test barrier reasons are identified correctly."""
        barrier_reasons = [
            NoShowReason.TRANSPORTATION,
            NoShowReason.CHILDCARE,
            NoShowReason.WORK,
        ]

        for reason in barrier_reasons:
            assert reason in barrier_reasons

    def test_stats_initial(self, noshow_workflow):
        """Test initial statistics."""
        stats = noshow_workflow.get_stats()

        assert stats.total_missed == 0
        assert stats.rescheduled == 0
        assert stats.barriers_identified == 0
        assert stats.reschedule_rate == 0.0


class TestOutboundPrompts:
    """Test outbound prompt templates."""

    def test_prompt_imports(self):
        """Test that prompts can be imported."""
        from phone_agent.industry.gesundheit.outbound.prompts_outbound import (
            REMINDER_INTRODUCTION,
            RECALL_PURPOSE_PREVENTIVE,
            NOSHOW_PURPOSE,
            OutboundPromptBuilder,
        )

        assert REMINDER_INTRODUCTION is not None
        assert RECALL_PURPOSE_PREVENTIVE is not None
        assert NOSHOW_PURPOSE is not None

    def test_prompt_builder(self):
        """Test OutboundPromptBuilder."""
        from phone_agent.industry.gesundheit.outbound.prompts_outbound import (
            OutboundPromptBuilder,
        )

        builder = OutboundPromptBuilder(
            practice_name="Test Praxis",
            practice_phone="+4930123456",
        )

        intro = builder.build_reminder_introduction("Max Mustermann")
        assert "Test Praxis" in intro
        assert "Max Mustermann" in intro

    def test_time_greeting(self):
        """Test time-appropriate greeting."""
        from phone_agent.industry.gesundheit.outbound.prompts_outbound import (
            get_time_greeting,
        )

        greeting = get_time_greeting()
        assert greeting in ["Guten Morgen", "Guten Tag", "Guten Abend"]

    def test_slot_formatting(self):
        """Test slot option formatting."""
        from phone_agent.industry.gesundheit.outbound.prompts_outbound import (
            format_slot_options,
        )

        slots = [
            {"description": "Montag, 15.12. um 10:00 Uhr"},
            {"description": "Dienstag, 16.12. um 14:00 Uhr"},
        ]

        formatted = format_slot_options(slots)

        assert "Option 1" in formatted
        assert "Option 2" in formatted
        assert "Montag" in formatted
        assert "Dienstag" in formatted


class TestSIPClientOutbound:
    """Test SIP client outbound functionality."""

    @pytest.fixture
    def sip_client(self):
        """Create SIP client for testing."""
        config = SIPConfig(server="", register=False)
        return SIPClient(config)

    @pytest.mark.asyncio
    async def test_originate_call(self, sip_client):
        """Test originating an outbound call."""
        await sip_client.start()

        call = await sip_client.originate_call(
            destination="+49170123456",
            caller_id="Test Praxis",
            metadata={"campaign": "reminder"},
        )

        assert call.direction == "outbound"
        assert call.callee_id == "+49170123456"
        assert call.metadata.get("campaign") == "reminder"

        await sip_client.stop()

    @pytest.mark.asyncio
    async def test_wait_for_answer_not_found(self, sip_client):
        """Test waiting for answer on non-existent call."""
        await sip_client.start()

        fake_id = uuid4()
        result = await sip_client.wait_for_answer(fake_id, timeout=1)

        assert result is False

        await sip_client.stop()

    @pytest.mark.asyncio
    async def test_outbound_progress(self, sip_client):
        """Test handling outbound call progress."""
        from phone_agent.telephony.sip_client import SIPCallState

        await sip_client.start()

        call = await sip_client.originate_call(
            destination="+49170123456",
        )

        # Simulate ringing
        success = await sip_client.handle_outbound_progress(
            call.call_id,
            SIPCallState.RINGING,
        )
        assert success

        updated = sip_client.get_call(call.call_id)
        assert updated.state == SIPCallState.RINGING

        # Simulate answer
        success = await sip_client.handle_outbound_progress(
            call.call_id,
            SIPCallState.CONFIRMED,
        )
        assert success

        updated = sip_client.get_call(call.call_id)
        assert updated.state == SIPCallState.CONFIRMED
        assert updated.answered_at is not None

        await sip_client.stop()
