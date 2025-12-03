"""Tests for email integration functionality."""

from __future__ import annotations

from datetime import datetime, date, time
from unittest.mock import MagicMock, AsyncMock, patch
from uuid import uuid4

import pytest

from phone_agent.integrations.email.base import (
    EmailMessage,
    EmailResult,
    EmailStatus,
    EmailPriority,
    EmailAttachment,
)


class TestEmailMessage:
    """Test EmailMessage dataclass."""

    def test_create_simple_message(self):
        """Test creating a simple email message."""
        msg = EmailMessage(
            to="test@example.com",
            subject="Test Subject",
            body_text="Test body",
        )

        assert msg.to == ["test@example.com"]
        assert msg.subject == "Test Subject"
        assert msg.body_text == "Test body"
        assert msg.priority == EmailPriority.NORMAL

    def test_create_message_with_multiple_recipients(self):
        """Test creating message with multiple recipients."""
        msg = EmailMessage(
            to=["user1@example.com", "user2@example.com"],
            subject="Test",
            body_text="Body",
            cc=["cc@example.com"],
            bcc=["bcc@example.com"],
        )

        assert len(msg.to) == 2
        assert len(msg.recipients) == 4

    def test_create_message_with_html(self):
        """Test creating message with HTML body."""
        msg = EmailMessage(
            to="test@example.com",
            subject="Test",
            body_html="<p>HTML Body</p>",
        )

        assert msg.body_html == "<p>HTML Body</p>"
        assert msg.body_text is None

    def test_create_message_with_attachments(self):
        """Test creating message with attachments."""
        attachment = EmailAttachment(
            filename="document.pdf",
            content=b"PDF content",
            content_type="application/pdf",
        )

        msg = EmailMessage(
            to="test@example.com",
            subject="Test",
            body_text="See attached",
            attachments=[attachment],
        )

        assert len(msg.attachments) == 1
        assert msg.attachments[0].filename == "document.pdf"

    def test_high_priority_message(self):
        """Test creating high priority message."""
        msg = EmailMessage(
            to="urgent@example.com",
            subject="Urgent",
            body_text="Important",
            priority=EmailPriority.HIGH,
        )

        assert msg.priority == EmailPriority.HIGH


class TestSMTPEmailGateway:
    """Test SMTP email gateway."""

    @pytest.mark.asyncio
    async def test_send_email_success(self, smtp_gateway, sample_email_message):
        """Test successful email sending via SMTP."""
        result = await smtp_gateway.send(sample_email_message)

        assert result.success is True
        assert result.status == EmailStatus.SENT
        assert result.provider == "smtp"
        assert result.message_id is not None
        assert result.recipients_accepted == 1

    @pytest.mark.asyncio
    async def test_send_email_with_tls(self, smtp_gateway, sample_email_message, mock_smtp_client):
        """Test SMTP with STARTTLS."""
        await smtp_gateway.send(sample_email_message)

        mock_smtp_client.starttls.assert_called_once()
        mock_smtp_client.login.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_email_validation_error(self, smtp_gateway):
        """Test email validation errors."""
        # Invalid email format
        msg = EmailMessage(
            to="invalid-email",
            subject="Test",
            body_text="Body",
        )

        result = await smtp_gateway.send(msg)

        assert result.success is False
        assert result.status == EmailStatus.FAILED
        assert "Invalid recipient email" in result.error_message

    @pytest.mark.asyncio
    async def test_send_email_missing_body(self, smtp_gateway):
        """Test email without body fails validation."""
        msg = EmailMessage(
            to="test@example.com",
            subject="Test",
        )

        result = await smtp_gateway.send(msg)

        assert result.success is False
        assert "body is required" in result.error_message

    @pytest.mark.asyncio
    async def test_send_email_auth_failure(self, smtp_gateway, sample_email_message, mock_smtp_client):
        """Test SMTP authentication failure."""
        import aiosmtplib

        mock_smtp_client.login.side_effect = aiosmtplib.SMTPAuthenticationError(
            535, "Authentication failed"
        )

        result = await smtp_gateway.send(sample_email_message)

        assert result.success is False
        assert result.error_code == "AUTH_FAILED"

    @pytest.mark.asyncio
    async def test_send_email_timeout(self, smtp_gateway, sample_email_message):
        """Test SMTP timeout."""
        import asyncio

        with patch("aiosmtplib.SMTP") as mock:
            mock.side_effect = asyncio.TimeoutError()

            result = await smtp_gateway.send(sample_email_message)

            assert result.success is False
            assert result.error_code == "TIMEOUT"


class TestSendGridEmailGateway:
    """Test SendGrid email gateway."""

    @pytest.mark.asyncio
    async def test_send_email_success(self, sendgrid_gateway, sample_email_message):
        """Test successful email sending via SendGrid."""
        result = await sendgrid_gateway.send(sample_email_message)

        assert result.success is True
        assert result.status == EmailStatus.QUEUED
        assert result.provider == "sendgrid"
        assert result.message_id == "sendgrid_msg_123"

    @pytest.mark.asyncio
    async def test_send_email_with_tags(self, sendgrid_gateway, mock_sendgrid_client):
        """Test SendGrid with tags/categories."""
        msg = EmailMessage(
            to="test@example.com",
            subject="Test",
            body_text="Body",
            tags=["appointment", "confirmation"],
        )

        await sendgrid_gateway.send(msg)

        # Verify tags were included in payload
        call_args = mock_sendgrid_client.post.call_args
        payload = call_args[1]["json"]
        assert payload["categories"] == ["appointment", "confirmation"]

    @pytest.mark.asyncio
    async def test_send_email_scheduled(self, sendgrid_gateway, mock_sendgrid_client):
        """Test scheduled email sending."""
        future_time = datetime(2024, 1, 20, 10, 0, 0)

        msg = EmailMessage(
            to="test@example.com",
            subject="Scheduled Test",
            body_text="Body",
            scheduled_at=future_time,
        )

        await sendgrid_gateway.send(msg)

        call_args = mock_sendgrid_client.post.call_args
        payload = call_args[1]["json"]
        assert "send_at" in payload

    @pytest.mark.asyncio
    async def test_send_email_api_error(self, sendgrid_gateway, mock_sendgrid_client, sample_email_message):
        """Test SendGrid API error response."""
        error_response = MagicMock()
        error_response.status_code = 400
        error_response.content = b'{"errors": [{"message": "Invalid request"}]}'
        error_response.json.return_value = {"errors": [{"message": "Invalid request"}]}
        mock_sendgrid_client.post.return_value = error_response

        result = await sendgrid_gateway.send(sample_email_message)

        assert result.success is False
        assert result.status == EmailStatus.FAILED
        assert "Invalid request" in result.error_message

    @pytest.mark.asyncio
    async def test_bulk_send(self, sendgrid_gateway):
        """Test bulk email sending."""
        messages = [
            EmailMessage(to=f"user{i}@example.com", subject="Test", body_text="Body")
            for i in range(5)
        ]

        results = await sendgrid_gateway.send_bulk(messages)

        assert len(results) == 5
        assert all(r.success for r in results)


class TestSendGridWebhookHandler:
    """Test SendGrid webhook handling."""

    def test_parse_delivered_event(self, sample_sendgrid_webhook_events):
        """Test parsing delivered webhook event."""
        from phone_agent.integrations.email.sendgrid import SendGridWebhookHandler

        parsed = SendGridWebhookHandler.parse_webhook(sample_sendgrid_webhook_events)

        assert len(parsed) == 2
        assert parsed[0]["status"] == "delivered"
        assert parsed[0]["provider_message_id"] == "sendgrid_msg_123"

    def test_parse_open_event(self, sample_sendgrid_webhook_events):
        """Test parsing open webhook event."""
        from phone_agent.integrations.email.sendgrid import SendGridWebhookHandler

        parsed = SendGridWebhookHandler.parse_webhook(sample_sendgrid_webhook_events)

        assert parsed[1]["status"] == "opened"
        assert parsed[1]["event_type"] == "open"

    def test_parse_bounce_event(self, sample_sendgrid_bounce_event):
        """Test parsing bounce webhook event."""
        from phone_agent.integrations.email.sendgrid import SendGridWebhookHandler

        parsed = SendGridWebhookHandler.parse_webhook([sample_sendgrid_bounce_event])

        assert parsed[0]["status"] == "bounced"
        assert parsed[0]["bounce_type"] == "hard"
        assert parsed[0]["bounce_reason"] == "550 User unknown"

    def test_should_retry_soft_bounce(self):
        """Test retry logic for soft bounce."""
        from phone_agent.integrations.email.sendgrid import SendGridWebhookHandler

        assert SendGridWebhookHandler.should_retry("bounce", "soft") is True
        assert SendGridWebhookHandler.should_retry("bounce", "hard") is False
        assert SendGridWebhookHandler.should_retry("deferred") is True
        assert SendGridWebhookHandler.should_retry("delivered") is False

    def test_get_event_severity(self):
        """Test event severity classification."""
        from phone_agent.integrations.email.sendgrid import SendGridWebhookHandler

        assert SendGridWebhookHandler.get_event_severity("delivered") == "info"
        assert SendGridWebhookHandler.get_event_severity("deferred") == "warning"
        assert SendGridWebhookHandler.get_event_severity("bounce") == "error"


class TestEmailTemplates:
    """Test German email templates."""

    def test_confirmation_template_text(self, sample_template_context):
        """Test appointment confirmation text template."""
        from phone_agent.integrations.email.templates import appointment_confirmation_text

        text = appointment_confirmation_text(
            patient_name="Max Mustermann",
            appointment_date=date(2024, 1, 15),
            appointment_time=time(10, 30),
            provider_name="Dr. Schmidt",
            appointment_type="Kontrolluntersuchung",
            ctx=sample_template_context,
        )

        assert "Max Mustermann" in text
        assert "Montag, 15. Januar 2024" in text
        assert "10:30 Uhr" in text
        assert "Dr. Schmidt" in text
        assert "Praxis Schmidt" in text
        assert "Versicherungskarte" in text

    def test_confirmation_template_html(self, sample_template_context):
        """Test appointment confirmation HTML template."""
        from phone_agent.integrations.email.templates import appointment_confirmation_html

        html = appointment_confirmation_html(
            patient_name="Max Mustermann",
            appointment_date=date(2024, 1, 15),
            appointment_time=time(10, 30),
            provider_name="Dr. Schmidt",
            appointment_type="Kontrolluntersuchung",
            ctx=sample_template_context,
        )

        assert "<html" in html
        assert "Max Mustermann" in html
        assert "appointment-box" in html  # CSS class
        assert "10:30 Uhr" in html

    def test_reminder_template(self, sample_template_context):
        """Test appointment reminder template."""
        from phone_agent.integrations.email.templates import appointment_reminder_text

        text = appointment_reminder_text(
            patient_name="Max Mustermann",
            appointment_date=date(2024, 1, 15),
            appointment_time=time(10, 30),
            provider_name="Dr. Schmidt",
            ctx=sample_template_context,
            hours_before=24,
        )

        assert "erinnern" in text.lower()
        assert "morgen" in text

    def test_cancellation_template(self, sample_template_context):
        """Test appointment cancellation template."""
        from phone_agent.integrations.email.templates import appointment_cancellation_text

        text = appointment_cancellation_text(
            patient_name="Max Mustermann",
            appointment_date=date(2024, 1, 15),
            appointment_time=time(10, 30),
            ctx=sample_template_context,
            reason="Auf Wunsch des Patienten",
        )

        assert "Stornierung" in text
        assert "Auf Wunsch des Patienten" in text

    def test_create_confirmation_email(self, sample_template_context):
        """Test creating complete confirmation email."""
        from phone_agent.integrations.email.templates import create_appointment_confirmation_email

        email = create_appointment_confirmation_email(
            to_email="patient@example.com",
            patient_name="Max Mustermann",
            appointment_date=date(2024, 1, 15),
            appointment_time=time(10, 30),
            provider_name="Dr. Schmidt",
            appointment_type="Kontrolluntersuchung",
            ctx=sample_template_context,
        )

        assert email.to == ["patient@example.com"]
        assert "Terminbestätigung" in email.subject
        assert "15.01.2024" in email.subject
        assert email.body_text is not None
        assert email.body_html is not None
        assert "appointment" in email.tags
        assert "confirmation" in email.tags


class TestEmailMessageModel:
    """Test email database model."""

    def test_create_model(self):
        """Test creating EmailMessageModel."""
        from phone_agent.db.models.email import EmailMessageModel

        email = EmailMessageModel(
            to_email="test@example.com",
            from_email="noreply@praxis.de",
            subject="Test Subject",
            body_text="Test body",
            provider="smtp",
            status="pending",
            message_type="confirmation",
            retry_count=0,
            max_retries=3,
        )

        assert email.to_email == "test@example.com"
        assert email.subject == "Test Subject"
        assert email.status == "pending"

    def test_mark_sent(self):
        """Test marking message as sent."""
        from phone_agent.db.models.email import EmailMessageModel

        email = EmailMessageModel(
            to_email="test@example.com",
            subject="Test",
            provider="smtp",
            status="pending",
            retry_count=0,
            max_retries=3,
        )

        email.mark_sent("msg_123")

        assert email.status == "sent"
        assert email.provider_message_id == "msg_123"
        assert email.sent_at is not None

    def test_mark_opened(self):
        """Test marking message as opened."""
        from phone_agent.db.models.email import EmailMessageModel

        email = EmailMessageModel(
            to_email="test@example.com",
            subject="Test",
            provider="sendgrid",
            status="sent",
            open_count=0,
            retry_count=0,
            max_retries=3,
        )

        email.mark_opened()

        assert email.status == "opened"
        assert email.open_count == 1
        assert email.opened_at is not None

        # Mark opened again
        email.mark_opened()
        assert email.open_count == 2

    def test_mark_clicked(self):
        """Test marking message as clicked."""
        from phone_agent.db.models.email import EmailMessageModel

        email = EmailMessageModel(
            to_email="test@example.com",
            subject="Test",
            provider="sendgrid",
            status="opened",
            click_count=0,
            retry_count=0,
            max_retries=3,
        )

        email.mark_clicked()

        assert email.status == "clicked"
        assert email.click_count == 1
        assert email.clicked_at is not None

    def test_mark_bounced(self):
        """Test marking message as bounced."""
        from phone_agent.db.models.email import EmailMessageModel

        email = EmailMessageModel(
            to_email="test@example.com",
            subject="Test",
            provider="sendgrid",
            status="sent",
            retry_count=0,
            max_retries=3,
        )

        email.mark_bounced("550", "User unknown")

        assert email.status == "bounced"
        assert email.error_code == "550"
        assert email.error_message == "User unknown"
        assert email.bounced_at is not None

    def test_can_retry(self):
        """Test retry eligibility."""
        from phone_agent.db.models.email import EmailMessageModel

        email = EmailMessageModel(
            to_email="test@example.com",
            subject="Test",
            provider="smtp",
            status="failed",
            retry_count=0,
            max_retries=3,
        )

        assert email.can_retry() is True

        email.retry_count = 3
        assert email.can_retry() is False

        email.retry_count = 0
        email.status = "delivered"
        assert email.can_retry() is False


class TestEmailFactory:
    """Test email gateway factory."""

    def test_get_mock_gateway_when_disabled(self):
        """Test mock gateway when email is disabled."""
        from phone_agent.integrations.email.factory import reset_email_gateway, get_email_gateway
        from phone_agent.integrations.email.base import MockEmailGateway

        reset_email_gateway()

        with patch("phone_agent.integrations.email.factory.get_settings") as mock_settings:
            settings = MagicMock()
            settings.integrations.email.enabled = False
            mock_settings.return_value = settings

            gateway = get_email_gateway()

            assert isinstance(gateway, MockEmailGateway)

    def test_get_smtp_gateway(self):
        """Test SMTP gateway initialization."""
        from phone_agent.integrations.email.factory import reset_email_gateway, get_email_gateway

        reset_email_gateway()

        with patch("phone_agent.integrations.email.factory.get_settings") as mock_settings:
            settings = MagicMock()
            settings.integrations.email.enabled = True
            settings.integrations.email.provider = "smtp"
            settings.integrations.email.smtp.host = "smtp.example.com"
            settings.integrations.email.smtp.port = 587
            settings.integrations.email.smtp.username = "user"
            settings.integrations.email.smtp.password = "pass"
            settings.integrations.email.smtp.use_tls = True
            settings.integrations.email.smtp.use_ssl = False
            settings.integrations.email.from_email = "test@example.com"
            settings.integrations.email.from_name = "Test"
            mock_settings.return_value = settings

            # Import the actual module and patch the class there
            from phone_agent.integrations.email import smtp
            with patch.object(smtp, "SMTPEmailGateway") as mock_gateway:
                mock_gateway.return_value = MagicMock()
                gateway = get_email_gateway()

                mock_gateway.assert_called_once()


class TestMockEmailGateway:
    """Test mock email gateway."""

    @pytest.mark.asyncio
    async def test_send_logs_message(self):
        """Test mock gateway logs messages."""
        from phone_agent.integrations.email.base import MockEmailGateway, EmailMessage

        gateway = MockEmailGateway()
        message = EmailMessage(
            to="test@example.com",
            subject="Test",
            body_text="Test body",
        )

        result = await gateway.send(message)

        assert result.success is True
        assert result.provider == "mock"

        sent = gateway.get_sent_messages()
        assert len(sent) == 1
        assert sent[0]["to"] == ["test@example.com"]

    @pytest.mark.asyncio
    async def test_simulate_delivery(self):
        """Test simulating delivery status changes."""
        from phone_agent.integrations.email.base import MockEmailGateway, EmailMessage, EmailStatus

        gateway = MockEmailGateway()
        message = EmailMessage(
            to="test@example.com",
            subject="Test",
            body_text="Test",
        )

        result = await gateway.send(message)
        gateway.simulate_delivery(result.message_id)

        status = await gateway.get_status(result.message_id)
        assert status == EmailStatus.DELIVERED

    @pytest.mark.asyncio
    async def test_simulate_bounce(self):
        """Test simulating bounce."""
        from phone_agent.integrations.email.base import MockEmailGateway, EmailMessage, EmailStatus

        gateway = MockEmailGateway()
        message = EmailMessage(
            to="invalid@example.com",
            subject="Test",
            body_text="Test",
        )

        result = await gateway.send(message)
        gateway.simulate_bounce(result.message_id)

        status = await gateway.get_status(result.message_id)
        assert status == EmailStatus.BOUNCED


class TestConvenienceFunctions:
    """Test email convenience functions."""

    @pytest.mark.asyncio
    async def test_send_appointment_confirmation(self):
        """Test appointment confirmation convenience function."""
        from phone_agent.integrations.email.factory import (
            send_appointment_confirmation,
            reset_email_gateway,
        )

        reset_email_gateway()

        with patch("phone_agent.integrations.email.factory.get_settings") as mock_settings:
            settings = MagicMock()
            settings.integrations.email.enabled = False
            mock_settings.return_value = settings

            success = await send_appointment_confirmation(
                email="patient@example.com",
                patient_name="Max Mustermann",
                appointment_date=date(2024, 1, 15),
                appointment_time=time(10, 30),
                provider_name="Dr. Schmidt",
                appointment_type="Kontrolluntersuchung",
                practice_name="Praxis Schmidt",
            )

            assert success is True

    @pytest.mark.asyncio
    async def test_send_appointment_reminder(self):
        """Test appointment reminder convenience function."""
        from phone_agent.integrations.email.factory import (
            send_appointment_reminder,
            reset_email_gateway,
        )

        reset_email_gateway()

        with patch("phone_agent.integrations.email.factory.get_settings") as mock_settings:
            settings = MagicMock()
            settings.integrations.email.enabled = False
            mock_settings.return_value = settings

            success = await send_appointment_reminder(
                email="patient@example.com",
                patient_name="Max Mustermann",
                appointment_date=date(2024, 1, 15),
                appointment_time=time(10, 30),
                provider_name="Dr. Schmidt",
                practice_name="Praxis Schmidt",
            )

            assert success is True

    @pytest.mark.asyncio
    async def test_send_appointment_cancellation(self):
        """Test appointment cancellation convenience function."""
        from phone_agent.integrations.email.factory import (
            send_appointment_cancellation,
            reset_email_gateway,
        )

        reset_email_gateway()

        with patch("phone_agent.integrations.email.factory.get_settings") as mock_settings:
            settings = MagicMock()
            settings.integrations.email.enabled = False
            mock_settings.return_value = settings

            success = await send_appointment_cancellation(
                email="patient@example.com",
                patient_name="Max Mustermann",
                appointment_date=date(2024, 1, 15),
                appointment_time=time(10, 30),
                practice_name="Praxis Schmidt",
            )

            assert success is True
