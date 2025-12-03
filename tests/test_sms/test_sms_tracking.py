"""Tests for SMS delivery tracking functionality."""

from __future__ import annotations

from datetime import datetime, date, timedelta, timezone
from unittest.mock import MagicMock, AsyncMock, patch
from uuid import uuid4

import pytest

from phone_agent.integrations.sms.base import SMSMessage, SMSResult, SMSStatus


class TestTwilioSMSGateway:
    """Test Twilio SMS gateway."""

    @pytest.mark.asyncio
    async def test_send_sms_success(self, twilio_gateway, sample_sms_message):
        """Test successful SMS sending via Twilio."""
        result = await twilio_gateway.send(sample_sms_message)

        assert result.success is True
        assert result.message_id == "SM123456789"
        assert result.status == SMSStatus.PENDING  # queued maps to pending
        assert result.provider == "twilio"
        assert result.segments == 1
        assert result.sent_at is not None

    @pytest.mark.asyncio
    async def test_send_sms_failure(self, twilio_gateway, sample_sms_message):
        """Test failed SMS sending via Twilio."""
        # Mock error response
        error_response = MagicMock()
        error_response.status_code = 400
        error_response.content = b'{"code": 21211, "message": "Invalid phone number"}'
        error_response.json.return_value = {
            "code": 21211,
            "message": "Invalid phone number",
        }
        twilio_gateway._client.post.return_value = error_response

        result = await twilio_gateway.send(sample_sms_message)

        assert result.success is False
        assert result.status == SMSStatus.FAILED
        assert result.provider == "twilio"
        assert "21211" in result.error_message

    @pytest.mark.asyncio
    async def test_send_sms_timeout(self, twilio_gateway, sample_sms_message):
        """Test SMS sending with timeout."""
        import httpx

        twilio_gateway._client.post.side_effect = httpx.TimeoutException("timeout")

        result = await twilio_gateway.send(sample_sms_message)

        assert result.success is False
        assert result.status == SMSStatus.FAILED
        assert "timeout" in result.error_message.lower()

    @pytest.mark.asyncio
    async def test_get_status(self, twilio_gateway):
        """Test getting message status from Twilio."""
        status = await twilio_gateway.get_status("SM123456789")

        assert status == SMSStatus.DELIVERED

    @pytest.mark.asyncio
    async def test_get_status_unknown(self, twilio_gateway):
        """Test getting status for unknown message."""
        error_response = MagicMock()
        error_response.status_code = 404
        twilio_gateway._client.get.return_value = error_response

        status = await twilio_gateway.get_status("SM_UNKNOWN")

        assert status == SMSStatus.UNKNOWN

    @pytest.mark.asyncio
    async def test_bulk_send(self, twilio_gateway):
        """Test bulk SMS sending."""
        messages = [
            SMSMessage(to="+49123456001", body="Message 1"),
            SMSMessage(to="+49123456002", body="Message 2"),
            SMSMessage(to="+49123456003", body="Message 3"),
        ]

        results = await twilio_gateway.send_bulk(messages)

        assert len(results) == 3
        assert all(r.success for r in results)

    @pytest.mark.asyncio
    async def test_phone_normalization(self, twilio_gateway):
        """Test phone number normalization to E.164."""
        # German format without country code
        assert twilio_gateway.normalize_phone("0171 1234567") == "+491711234567"

        # With 0049 prefix
        assert twilio_gateway.normalize_phone("0049171-1234567") == "+491711234567"

        # Already E.164
        assert twilio_gateway.normalize_phone("+491711234567") == "+491711234567"

    def test_calculate_segments_short(self, twilio_gateway):
        """Test segment calculation for short message."""
        short_message = "Termin bestätigt."
        segments = twilio_gateway.calculate_segments(short_message)

        assert segments == 1

    def test_calculate_segments_long(self, twilio_gateway):
        """Test segment calculation for long message."""
        long_message = "A" * 200  # Over 160 chars
        segments = twilio_gateway.calculate_segments(long_message)

        assert segments == 2

    def test_calculate_segments_unicode(self, twilio_gateway):
        """Test segment calculation for unicode message."""
        unicode_message = "你好世界" * 20  # Chinese characters, 80 chars
        segments = twilio_gateway.calculate_segments(unicode_message)

        assert segments == 2  # 80 chars / 67 = 2 segments


class TestSipgateSMSGateway:
    """Test sipgate SMS gateway."""

    @pytest.mark.asyncio
    async def test_send_sms_success(self, sipgate_gateway, sample_sms_message):
        """Test successful SMS sending via sipgate."""
        result = await sipgate_gateway.send(sample_sms_message)

        assert result.success is True
        assert result.message_id is not None
        assert result.message_id.startswith("sipgate_")
        assert result.status == SMSStatus.SENT
        assert result.provider == "sipgate"

    @pytest.mark.asyncio
    async def test_send_sms_failure(self, sipgate_gateway, sample_sms_message):
        """Test failed SMS sending via sipgate."""
        error_response = MagicMock()
        error_response.status_code = 401
        error_response.content = b'{"message": "Unauthorized"}'
        error_response.json.return_value = {"message": "Unauthorized"}
        sipgate_gateway._client.post.return_value = error_response

        result = await sipgate_gateway.send(sample_sms_message)

        assert result.success is False
        assert result.status == SMSStatus.FAILED
        assert result.provider == "sipgate"

    @pytest.mark.asyncio
    async def test_get_status_returns_unknown(self, sipgate_gateway):
        """Test that sipgate returns UNKNOWN for status (not supported)."""
        status = await sipgate_gateway.get_status("any_id")

        # sipgate doesn't support status queries
        assert status == SMSStatus.UNKNOWN


class TestTwilioWebhookHandler:
    """Test Twilio webhook handling."""

    def test_parse_delivered_webhook(self, sample_twilio_webhook_data):
        """Test parsing delivered status webhook."""
        from phone_agent.integrations.sms.twilio import TwilioWebhookHandler

        parsed = TwilioWebhookHandler.parse_webhook(sample_twilio_webhook_data)

        assert parsed["provider_message_id"] == "SM123456789"
        assert parsed["status"] == "delivered"
        assert parsed["to_number"] == "+49123456789"
        assert parsed["from_number"] == "+4930123456"
        assert parsed["error_code"] is None

    def test_parse_failed_webhook(self, sample_twilio_failed_webhook_data):
        """Test parsing failed status webhook."""
        from phone_agent.integrations.sms.twilio import TwilioWebhookHandler

        parsed = TwilioWebhookHandler.parse_webhook(sample_twilio_failed_webhook_data)

        assert parsed["provider_message_id"] == "SM123456789"
        assert parsed["status"] == "failed"
        assert parsed["error_code"] == "30003"
        assert parsed["error_message"] == "Unreachable destination handset"

    def test_should_retry_retryable_error(self):
        """Test retry detection for retryable error codes."""
        from phone_agent.integrations.sms.twilio import TwilioWebhookHandler

        # 30003 is "Unreachable destination" - retryable
        assert TwilioWebhookHandler.should_retry("30003") is True

        # 30001 is "Queue overflow" - retryable
        assert TwilioWebhookHandler.should_retry("30001") is True

    def test_should_not_retry_permanent_error(self):
        """Test retry detection for permanent error codes."""
        from phone_agent.integrations.sms.twilio import TwilioWebhookHandler

        # 21211 is "Invalid phone number" - not retryable
        assert TwilioWebhookHandler.should_retry("21211") is False

        # 30004 is "Message blocked" - not retryable
        assert TwilioWebhookHandler.should_retry("30004") is False

    def test_get_error_category(self):
        """Test error categorization."""
        from phone_agent.integrations.sms.twilio import TwilioWebhookHandler

        assert TwilioWebhookHandler.get_error_category("21211") == "invalid_request"
        assert TwilioWebhookHandler.get_error_category("30003") == "delivery_failure"
        assert TwilioWebhookHandler.get_error_category("32001") == "channel_error"
        assert TwilioWebhookHandler.get_error_category(None) == "unknown"


class TestSMSMessageModel:
    """Test SMS database model."""

    def test_create_model(self):
        """Test creating SMSMessageModel."""
        from phone_agent.db.models.sms import SMSMessageModel

        sms = SMSMessageModel(
            to_number="+49123456789",
            from_number="+4930123456",
            body="Test message",
            provider="twilio",
            status="pending",
            message_type="confirmation",
            retry_count=0,
            max_retries=3,
        )

        assert sms.to_number == "+49123456789"
        assert sms.body == "Test message"
        assert sms.status == "pending"
        assert sms.retry_count == 0
        assert sms.max_retries == 3

    def test_mark_sent(self):
        """Test marking message as sent."""
        from phone_agent.db.models.sms import SMSMessageModel

        sms = SMSMessageModel(
            to_number="+49123456789",
            body="Test",
            provider="twilio",
            status="pending",
        )

        sms.mark_sent("SM123456789")

        assert sms.status == "sent"
        assert sms.provider_message_id == "SM123456789"
        assert sms.sent_at is not None

    def test_mark_delivered(self):
        """Test marking message as delivered."""
        from phone_agent.db.models.sms import SMSMessageModel

        sms = SMSMessageModel(
            to_number="+49123456789",
            body="Test",
            provider="twilio",
            status="sent",
        )

        sms.mark_delivered()

        assert sms.status == "delivered"
        assert sms.delivered_at is not None

    def test_mark_failed(self):
        """Test marking message as failed."""
        from phone_agent.db.models.sms import SMSMessageModel

        sms = SMSMessageModel(
            to_number="+49123456789",
            body="Test",
            provider="twilio",
            status="sent",
        )

        sms.mark_failed("30003", "Unreachable destination")

        assert sms.status == "failed"
        assert sms.error_code == "30003"
        assert sms.error_message == "Unreachable destination"
        assert sms.failed_at is not None

    def test_can_retry(self):
        """Test retry eligibility check."""
        from phone_agent.db.models.sms import SMSMessageModel

        sms = SMSMessageModel(
            to_number="+49123456789",
            body="Test",
            provider="twilio",
            status="failed",
            retry_count=0,
            max_retries=3,
        )

        assert sms.can_retry() is True

        sms.retry_count = 3
        assert sms.can_retry() is False

        sms.retry_count = 0
        sms.status = "delivered"
        assert sms.can_retry() is False

    def test_increment_retry(self):
        """Test incrementing retry count."""
        from phone_agent.db.models.sms import SMSMessageModel

        sms = SMSMessageModel(
            to_number="+49123456789",
            body="Test",
            provider="twilio",
            status="failed",
            retry_count=0,
        )

        sms.increment_retry(next_retry_delay_seconds=120)

        assert sms.retry_count == 1
        assert sms.status == "pending"
        assert sms.next_retry_at is not None
        # Check that next_retry_at is roughly 2 minutes from now
        delta = sms.next_retry_at - datetime.now(timezone.utc)
        assert 110 <= delta.total_seconds() <= 130

    def test_to_dict(self):
        """Test model serialization."""
        from phone_agent.db.models.sms import SMSMessageModel

        sms = SMSMessageModel(
            to_number="+49123456789",
            body="Test message",
            provider="twilio",
            status="delivered",
            cost=0.0075,
        )

        data = sms.to_dict()

        assert data["to_number"] == "+49123456789"
        assert data["body"] == "Test message"
        assert data["provider"] == "twilio"
        assert data["status"] == "delivered"
        assert data["cost"] == 0.0075


class TestSMSFactory:
    """Test SMS gateway factory."""

    def test_get_mock_gateway_when_disabled(self):
        """Test that mock gateway is returned when SMS is disabled."""
        from phone_agent.integrations.sms.factory import reset_sms_gateway, get_sms_gateway
        from phone_agent.integrations.sms.base import MockSMSGateway

        reset_sms_gateway()

        with patch("phone_agent.integrations.sms.factory.get_settings") as mock_settings:
            settings = MagicMock()
            settings.integrations.sms.enabled = False
            mock_settings.return_value = settings

            gateway = get_sms_gateway()

            assert isinstance(gateway, MockSMSGateway)

    def test_get_twilio_gateway(self):
        """Test Twilio gateway initialization."""
        from phone_agent.integrations.sms.factory import reset_sms_gateway, get_sms_gateway
        from phone_agent.integrations.sms.twilio import TwilioSMSGateway

        reset_sms_gateway()

        with patch("phone_agent.integrations.sms.factory.get_settings") as mock_settings:
            settings = MagicMock()
            settings.integrations.sms.enabled = True
            settings.integrations.sms.provider = "twilio"
            settings.telephony.twilio.account_sid = "AC123456789"
            settings.telephony.twilio.auth_token = "test_token"
            settings.telephony.twilio.from_number = "+4930123456"
            settings.telephony.twilio.webhook_url = "https://example.com"
            settings.telephony.twilio.messaging_service_sid = None
            mock_settings.return_value = settings

            # Mock the TwilioSMSGateway to avoid actual HTTP client creation
            with patch("phone_agent.integrations.sms.twilio.TwilioSMSGateway") as mock_gateway:
                mock_gateway.return_value = MagicMock()
                gateway = get_sms_gateway()

                mock_gateway.assert_called_once()

    def test_get_sipgate_gateway(self):
        """Test sipgate gateway initialization."""
        from phone_agent.integrations.sms.factory import reset_sms_gateway, get_sms_gateway

        reset_sms_gateway()

        with patch("phone_agent.integrations.sms.factory.get_settings") as mock_settings:
            settings = MagicMock()
            settings.integrations.sms.enabled = True
            settings.integrations.sms.provider = "sipgate"
            settings.telephony.sipgate.api_token = "test_token"
            settings.telephony.sipgate.username = "test_user"
            mock_settings.return_value = settings

            # Mock the SipgateSMSGateway
            with patch("phone_agent.integrations.sms.sipgate.SipgateSMSGateway") as mock_gateway:
                mock_gateway.return_value = MagicMock()
                gateway = get_sms_gateway()

                mock_gateway.assert_called_once()


class TestMockSMSGateway:
    """Test mock SMS gateway for development."""

    @pytest.mark.asyncio
    async def test_send_logs_message(self):
        """Test that mock gateway logs messages."""
        from phone_agent.integrations.sms.base import MockSMSGateway, SMSMessage

        gateway = MockSMSGateway()
        message = SMSMessage(to="+49123456789", body="Test message")

        result = await gateway.send(message)

        assert result.success is True
        assert result.provider == "mock"
        assert result.message_id is not None

        # Check message was stored
        sent = gateway.get_sent_messages()
        assert len(sent) == 1
        assert sent[0]["to"] == "+49123456789"
        assert sent[0]["body"] == "Test message"

    @pytest.mark.asyncio
    async def test_get_status(self):
        """Test mock status retrieval."""
        from phone_agent.integrations.sms.base import MockSMSGateway, SMSMessage, SMSStatus

        gateway = MockSMSGateway()
        message = SMSMessage(to="+49123456789", body="Test")

        result = await gateway.send(message)
        status = await gateway.get_status(result.message_id)

        assert status == SMSStatus.SENT

    @pytest.mark.asyncio
    async def test_clear_sent_messages(self):
        """Test clearing sent messages."""
        from phone_agent.integrations.sms.base import MockSMSGateway, SMSMessage

        gateway = MockSMSGateway()
        await gateway.send(SMSMessage(to="+49123456789", body="Test 1"))
        await gateway.send(SMSMessage(to="+49123456789", body="Test 2"))

        assert len(gateway.get_sent_messages()) == 2

        gateway.clear_sent_messages()

        assert len(gateway.get_sent_messages()) == 0


class TestConvenienceFunctions:
    """Test SMS convenience functions."""

    @pytest.mark.asyncio
    async def test_send_appointment_confirmation(self):
        """Test appointment confirmation SMS."""
        from phone_agent.integrations.sms.factory import (
            send_appointment_confirmation,
            reset_sms_gateway,
        )

        reset_sms_gateway()

        with patch("phone_agent.integrations.sms.factory.get_settings") as mock_settings:
            settings = MagicMock()
            settings.integrations.sms.enabled = False
            mock_settings.return_value = settings

            success = await send_appointment_confirmation(
                phone="+49123456789",
                patient_name="Max Mustermann",
                appointment_date="15.01.2024",
                appointment_time="10:30",
                provider_name="Dr. Schmidt",
                practice_name="Praxis Schmidt",
            )

            assert success is True

    @pytest.mark.asyncio
    async def test_send_appointment_reminder(self):
        """Test appointment reminder SMS."""
        from phone_agent.integrations.sms.factory import (
            send_appointment_reminder,
            reset_sms_gateway,
        )

        reset_sms_gateway()

        with patch("phone_agent.integrations.sms.factory.get_settings") as mock_settings:
            settings = MagicMock()
            settings.integrations.sms.enabled = False
            mock_settings.return_value = settings

            success = await send_appointment_reminder(
                phone="+49123456789",
                patient_name="Max Mustermann",
                appointment_date="15.01.2024",
                appointment_time="10:30",
                provider_name="Dr. Schmidt",
                hours_before=24,
            )

            assert success is True

    @pytest.mark.asyncio
    async def test_send_cancellation_notification(self):
        """Test cancellation notification SMS."""
        from phone_agent.integrations.sms.factory import (
            send_cancellation_notification,
            reset_sms_gateway,
        )

        reset_sms_gateway()

        with patch("phone_agent.integrations.sms.factory.get_settings") as mock_settings:
            settings = MagicMock()
            settings.integrations.sms.enabled = False
            mock_settings.return_value = settings

            success = await send_cancellation_notification(
                phone="+49123456789",
                patient_name="Max Mustermann",
                appointment_date="15.01.2024",
                appointment_time="10:30",
            )

            assert success is True
