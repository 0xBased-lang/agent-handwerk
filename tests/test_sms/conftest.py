"""Test fixtures for SMS integration tests."""

from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import MagicMock, AsyncMock, patch
from uuid import uuid4

import pytest


@pytest.fixture
def mock_twilio_client():
    """Mock Twilio HTTP client."""
    with patch("httpx.AsyncClient") as mock:
        client = MagicMock()
        client.post = AsyncMock()
        client.get = AsyncMock()
        client.aclose = AsyncMock()

        # Mock successful send response
        mock_response = MagicMock()
        mock_response.status_code = 201
        mock_response.json.return_value = {
            "sid": "SM123456789",
            "status": "queued",
            "to": "+49123456789",
            "from": "+4930123456",
            "body": "Test message",
            "num_segments": "1",
            "price": None,
            "date_created": datetime.now().isoformat(),
        }
        client.post.return_value = mock_response

        # Mock status check response
        status_response = MagicMock()
        status_response.status_code = 200
        status_response.json.return_value = {
            "sid": "SM123456789",
            "status": "delivered",
            "to": "+49123456789",
            "from": "+4930123456",
        }
        client.get.return_value = status_response

        mock.return_value = client
        yield client


@pytest.fixture
def twilio_gateway(mock_twilio_client):
    """Create TwilioSMSGateway with mocked client."""
    from phone_agent.integrations.sms.twilio import TwilioSMSGateway

    gateway = TwilioSMSGateway(
        account_sid="AC123456789",
        auth_token="test_auth_token",
        from_number="+4930123456",
        status_callback_url="https://example.com/webhooks/sms/twilio/status",
    )
    gateway._client = mock_twilio_client
    return gateway


@pytest.fixture
def mock_sipgate_client():
    """Mock sipgate HTTP client."""
    with patch("httpx.AsyncClient") as mock:
        client = MagicMock()
        client.post = AsyncMock()
        client.get = AsyncMock()
        client.aclose = AsyncMock()

        # Mock successful send response (sipgate returns 204 No Content)
        mock_response = MagicMock()
        mock_response.status_code = 204
        client.post.return_value = mock_response

        mock.return_value = client
        yield client


@pytest.fixture
def sipgate_gateway(mock_sipgate_client):
    """Create SipgateSMSGateway with mocked client."""
    from phone_agent.integrations.sms.sipgate import SipgateSMSGateway

    gateway = SipgateSMSGateway(
        token_id="test_token_id",
        token="test_token",
        sms_id="s0",
    )
    gateway._client = mock_sipgate_client
    return gateway


@pytest.fixture
def sample_sms_message():
    """Create a sample SMS message."""
    from phone_agent.integrations.sms.base import SMSMessage

    return SMSMessage(
        to="+49123456789",
        body="Terminbestätigung: Ihr Termin am 15.01.2024 um 10:00 Uhr wurde bestätigt.",
        from_number="+4930123456",
        reference="confirmation_2024-01-15_10:00",
    )


@pytest.fixture
def sample_twilio_webhook_data():
    """Sample Twilio status callback webhook data."""
    return {
        "MessageSid": "SM123456789",
        "MessageStatus": "delivered",
        "To": "+49123456789",
        "From": "+4930123456",
        "ApiVersion": "2010-04-01",
        "AccountSid": "AC123456789",
        "SmsSid": "SM123456789",
        "SmsStatus": "delivered",
        "NumSegments": "1",
        "Price": "-0.0075",
        "PriceUnit": "USD",
    }


@pytest.fixture
def sample_twilio_failed_webhook_data():
    """Sample Twilio failed status callback webhook data."""
    return {
        "MessageSid": "SM123456789",
        "MessageStatus": "failed",
        "To": "+49123456789",
        "From": "+4930123456",
        "ErrorCode": "30003",
        "ErrorMessage": "Unreachable destination handset",
        "ApiVersion": "2010-04-01",
        "AccountSid": "AC123456789",
    }


@pytest.fixture
def db_session():
    """Create an in-memory SQLite database session for testing."""
    import asyncio
    from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
    from sqlalchemy.orm import sessionmaker

    from phone_agent.db.base import Base
    from phone_agent.db.models.sms import SMSMessageModel
    from phone_agent.db.models.core import CallModel, AppointmentModel
    from phone_agent.db.models.crm import ContactModel

    # Create async engine
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
    )

    async_session = sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )

    async def setup():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        return async_session()

    return asyncio.get_event_loop().run_until_complete(setup())


@pytest.fixture
def sms_repository(db_session):
    """Create SMSMessageRepository with test session."""
    from phone_agent.db.repositories.sms import SMSMessageRepository

    return SMSMessageRepository(db_session)
