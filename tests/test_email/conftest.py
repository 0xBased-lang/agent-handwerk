"""Test fixtures for email integration tests."""

from __future__ import annotations

from datetime import datetime, date, time
from unittest.mock import MagicMock, AsyncMock, patch
from uuid import uuid4

import pytest


@pytest.fixture
def mock_smtp_client():
    """Mock aiosmtplib SMTP client."""
    with patch("aiosmtplib.SMTP") as mock:
        smtp = MagicMock()
        smtp.__aenter__ = AsyncMock(return_value=smtp)
        smtp.__aexit__ = AsyncMock(return_value=None)
        smtp.starttls = AsyncMock()
        smtp.login = AsyncMock()
        smtp.send_message = AsyncMock(return_value={})

        mock.return_value = smtp
        yield smtp


@pytest.fixture
def smtp_gateway(mock_smtp_client):
    """Create SMTPEmailGateway with mocked client."""
    from phone_agent.integrations.email.smtp import SMTPEmailGateway

    return SMTPEmailGateway(
        host="smtp.example.com",
        port=587,
        username="test@example.com",
        password="testpassword",
        use_tls=True,
        from_email="noreply@praxis.de",
        from_name="Praxis Schmidt",
    )


@pytest.fixture
def mock_sendgrid_client():
    """Mock SendGrid HTTP client."""
    with patch("httpx.AsyncClient") as mock:
        client = MagicMock()
        client.post = AsyncMock()
        client.get = AsyncMock()
        client.aclose = AsyncMock()

        # Mock successful send response
        mock_response = MagicMock()
        mock_response.status_code = 202
        mock_response.headers = {"X-Message-Id": "sendgrid_msg_123"}
        mock_response.json.return_value = {}
        client.post.return_value = mock_response

        mock.return_value = client
        yield client


@pytest.fixture
def sendgrid_gateway(mock_sendgrid_client):
    """Create SendGridEmailGateway with mocked client."""
    from phone_agent.integrations.email.sendgrid import SendGridEmailGateway

    gateway = SendGridEmailGateway(
        api_key="SG.test_api_key",
        from_email="noreply@praxis.de",
        from_name="Praxis Schmidt",
        webhook_url="https://example.com/webhooks/email/sendgrid",
    )
    gateway._client = mock_sendgrid_client
    return gateway


@pytest.fixture
def sample_email_message():
    """Create a sample email message."""
    from phone_agent.integrations.email.base import EmailMessage

    return EmailMessage(
        to="patient@example.com",
        subject="Terminbestätigung - Praxis Schmidt",
        body_text="Ihr Termin am 15.01.2024 um 10:00 Uhr wurde bestätigt.",
        body_html="<p>Ihr Termin am 15.01.2024 um 10:00 Uhr wurde bestätigt.</p>",
        from_email="noreply@praxis.de",
        from_name="Praxis Schmidt",
    )


@pytest.fixture
def sample_template_context():
    """Create a sample template context."""
    from phone_agent.integrations.email.templates import TemplateContext

    return TemplateContext(
        practice_name="Praxis Schmidt",
        practice_address="Musterstraße 1, 12345 Berlin",
        practice_phone="+49 30 123456",
        practice_email="info@praxis-schmidt.de",
        practice_website="https://praxis-schmidt.de",
    )


@pytest.fixture
def sample_sendgrid_webhook_events():
    """Sample SendGrid webhook events."""
    return [
        {
            "email": "patient@example.com",
            "event": "delivered",
            "sg_event_id": "event_123",
            "sg_message_id": "sendgrid_msg_123",
            "timestamp": 1704067200,
            "category": ["appointment", "confirmation"],
        },
        {
            "email": "patient@example.com",
            "event": "open",
            "sg_event_id": "event_124",
            "sg_message_id": "sendgrid_msg_123",
            "timestamp": 1704070800,
        },
    ]


@pytest.fixture
def sample_sendgrid_bounce_event():
    """Sample SendGrid bounce event."""
    return {
        "email": "invalid@example.com",
        "event": "bounce",
        "sg_event_id": "event_125",
        "sg_message_id": "sendgrid_msg_456",
        "timestamp": 1704067200,
        "type": "hard",
        "reason": "550 User unknown",
    }
