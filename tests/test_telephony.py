"""Tests for telephony components."""

import asyncio
from uuid import uuid4

import pytest

from phone_agent.telephony.sip_client import SIPClient, SIPConfig, SIPCallState
from phone_agent.telephony.audio_bridge import AudioBridge, AudioBridgeConfig


class TestSIPClient:
    """Test SIP client functionality."""

    @pytest.fixture
    def sip_client(self):
        """Create SIP client for testing."""
        config = SIPConfig(
            server="",  # No server for tests
            register=False,
        )
        return SIPClient(config)

    @pytest.mark.asyncio
    async def test_start_stop(self, sip_client):
        """Test client start and stop."""
        await sip_client.start()
        assert sip_client.is_running

        await sip_client.stop()
        assert not sip_client.is_running

    @pytest.mark.asyncio
    async def test_handle_incoming_call(self, sip_client):
        """Test handling incoming call."""
        await sip_client.start()

        call = await sip_client.handle_incoming_call(
            sip_call_id="test-call-123",
            caller_id="+4930123456789",
            callee_id="+4940987654321",
        )

        assert call.sip_call_id == "test-call-123"
        assert call.caller_id == "+4930123456789"
        assert call.state == SIPCallState.RINGING
        assert call.direction == "inbound"

        await sip_client.stop()

    @pytest.mark.asyncio
    async def test_answer_call(self, sip_client):
        """Test answering a call."""
        await sip_client.start()

        call = await sip_client.handle_incoming_call(
            sip_call_id="test-call-456",
            caller_id="+4930123456789",
            callee_id="+4940987654321",
        )

        success = await sip_client.answer(call.call_id)
        assert success

        updated_call = sip_client.get_call(call.call_id)
        assert updated_call.state == SIPCallState.CONFIRMED
        assert updated_call.answered_at is not None

        await sip_client.stop()

    @pytest.mark.asyncio
    async def test_hangup_call(self, sip_client):
        """Test hanging up a call."""
        await sip_client.start()

        call = await sip_client.handle_incoming_call(
            sip_call_id="test-call-789",
            caller_id="+4930123456789",
            callee_id="+4940987654321",
        )

        await sip_client.answer(call.call_id)
        success = await sip_client.hangup(call.call_id)
        assert success

        # Call should be removed from active calls
        assert sip_client.get_call(call.call_id) is None

        await sip_client.stop()

    @pytest.mark.asyncio
    async def test_call_not_found(self, sip_client):
        """Test operations on non-existent call."""
        await sip_client.start()

        fake_id = uuid4()
        assert not await sip_client.answer(fake_id)
        assert not await sip_client.hangup(fake_id)

        await sip_client.stop()

    @pytest.mark.asyncio
    async def test_callback_on_incoming(self, sip_client):
        """Test callback is called on incoming call."""
        await sip_client.start()

        callback_called = False
        received_call = None

        async def on_incoming(call):
            nonlocal callback_called, received_call
            callback_called = True
            received_call = call

        sip_client.on_incoming_call(on_incoming)

        await sip_client.handle_incoming_call(
            sip_call_id="test-call-callback",
            caller_id="+4930123456789",
            callee_id="+4940987654321",
        )

        assert callback_called
        assert received_call is not None
        assert received_call.sip_call_id == "test-call-callback"

        await sip_client.stop()

    @pytest.mark.asyncio
    async def test_active_calls(self, sip_client):
        """Test active calls list."""
        await sip_client.start()

        # No active calls initially
        assert len(sip_client.active_calls) == 0

        # Add a call
        call1 = await sip_client.handle_incoming_call(
            sip_call_id="call-1",
            caller_id="+491111111111",
            callee_id="+492222222222",
        )

        assert len(sip_client.active_calls) == 1

        # Answer it
        await sip_client.answer(call1.call_id)
        assert len(sip_client.active_calls) == 1

        # Hangup
        await sip_client.hangup(call1.call_id)
        assert len(sip_client.active_calls) == 0

        await sip_client.stop()


class TestAudioBridge:
    """Test audio bridge functionality."""

    @pytest.fixture
    def bridge_config(self):
        """Create bridge config for testing."""
        return AudioBridgeConfig(
            host="127.0.0.1",
            port=19090,  # Use different port for tests
            sample_rate=16000,
            chunk_size=320,
        )

    def test_config_defaults(self):
        """Test default configuration."""
        config = AudioBridgeConfig()
        assert config.host == "0.0.0.0"
        assert config.port == 9090
        assert config.sample_rate == 16000
        assert config.channels == 1

    def test_bridge_initialization(self, bridge_config):
        """Test bridge initialization."""
        bridge = AudioBridge(bridge_config)
        assert bridge.config == bridge_config
        assert bridge.active_connections == 0

    @pytest.mark.asyncio
    async def test_callback_registration(self, bridge_config):
        """Test callback registration."""
        bridge = AudioBridge(bridge_config)

        audio_received = False

        def on_audio(call_id, audio):
            nonlocal audio_received
            audio_received = True

        bridge.on_audio_received(on_audio)

        # Callback is registered (actual test would need socket connection)
        assert bridge._on_audio_received is not None


class TestFreeSwitchClient:
    """Test FreeSWITCH client functionality."""

    def test_event_parsing(self):
        """Test FreeSWITCH event parsing."""
        from phone_agent.telephony.freeswitch import FreeSwitchClient, FreeSwitchConfig

        client = FreeSwitchClient(FreeSwitchConfig())

        # Test event parsing
        event_data = """Content-Type: text/event-plain

Event-Name: CHANNEL_CREATE
Event-UUID: abc-123
Unique-ID: channel-456
Caller-Caller-ID-Number: +4930123456789
Caller-Caller-ID-Name: Test Caller
Caller-Destination-Number: +4940987654321
Channel-State: CS_ROUTING

"""
        event = client._parse_event(event_data)

        assert event is not None
        assert event.event_name == "CHANNEL_CREATE"
        assert event.channel_uuid == "channel-456"
        assert event.caller_id_number == "+4930123456789"
        assert event.destination_number == "+4940987654321"

    def test_event_handler_registration(self):
        """Test event handler registration."""
        from phone_agent.telephony.freeswitch import FreeSwitchClient, FreeSwitchConfig

        client = FreeSwitchClient(FreeSwitchConfig())

        handler_called = False

        @client.on_event("CHANNEL_CREATE")
        def handle_channel_create(event):
            nonlocal handler_called
            handler_called = True

        assert "CHANNEL_CREATE" in client._event_handlers
        assert len(client._event_handlers["CHANNEL_CREATE"]) == 1


class TestWebhooks:
    """Test webhook handlers."""

    @pytest.fixture(autouse=True)
    def setup_webhook_security(self):
        """Configure webhook security to skip validation during tests."""
        from phone_agent import dependencies
        from phone_agent.api.webhook_security import (
            WebhookSecurityConfig,
            WebhookSecurityManager,
        )

        # Reset and configure security manager with validation disabled
        dependencies.reset_dependencies()
        dependencies._security_manager = WebhookSecurityManager(
            WebhookSecurityConfig(validate_signatures=False)
        )

        yield

        # Cleanup
        dependencies.reset_dependencies()

    @pytest.mark.asyncio
    async def test_incoming_call_webhook(self):
        """Test incoming call webhook endpoint."""
        from fastapi.testclient import TestClient
        from phone_agent.main import app

        client = TestClient(app)

        # Test incoming call webhook
        response = client.post(
            "/api/v1/webhooks/call/incoming",
            json={
                "call_id": "test-webhook-call-123",
                "caller_id": "+4930123456789",
                "callee_id": "+4940987654321",
                "provider": "test",
            },
        )

        # Should return success (even without active service)
        assert response.status_code == 200
        data = response.json()
        assert "success" in data

    @pytest.mark.asyncio
    async def test_hangup_webhook(self):
        """Test hangup webhook endpoint."""
        from fastapi.testclient import TestClient
        from phone_agent.main import app

        client = TestClient(app)

        response = client.post(
            "/api/v1/webhooks/call/hangup",
            json={
                "call_id": "test-webhook-call-123",
                "event": "hangup",
            },
        )

        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_call_event_webhook(self):
        """Test generic call event webhook."""
        from fastapi.testclient import TestClient
        from phone_agent.main import app

        client = TestClient(app)

        response = client.post(
            "/api/v1/webhooks/call/event",
            json={
                "call_id": "test-webhook-call-123",
                "event": "answered",
                "data": {"user": "agent-1"},
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        # Events now return specific action types (e.g., "answered_acknowledged")
        assert data["action"] == "answered_acknowledged"
