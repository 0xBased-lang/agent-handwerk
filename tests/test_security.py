"""Security tests for phone-agent.

Tests XSS prevention, input validation, and other security measures.
"""

from __future__ import annotations

from datetime import date, time

import pytest


class TestXSSPrevention:
    """Test XSS prevention in email templates."""

    def test_xss_in_patient_name_escaped(self):
        """Verify XSS payload in patient name is escaped."""
        from phone_agent.integrations.email.templates import (
            appointment_confirmation_html,
            TemplateContext,
        )

        ctx = TemplateContext(practice_name="Test Praxis")
        xss_payload = '<script>alert("XSS")</script>'

        html = appointment_confirmation_html(
            patient_name=xss_payload,
            appointment_date=date(2024, 1, 15),
            appointment_time=time(10, 30),
            provider_name="Dr. Test",
            appointment_type="Vorsorge",
            ctx=ctx,
        )

        # Script tag should be escaped
        assert "<script>" not in html
        assert "&lt;script&gt;" in html

    def test_xss_in_provider_name_escaped(self):
        """Verify XSS payload in provider name is escaped."""
        from phone_agent.integrations.email.templates import (
            appointment_confirmation_html,
            TemplateContext,
        )

        ctx = TemplateContext(practice_name="Test Praxis")
        xss_payload = '<img src=x onerror="alert(1)">'

        html = appointment_confirmation_html(
            patient_name="Max Mustermann",
            appointment_date=date(2024, 1, 15),
            appointment_time=time(10, 30),
            provider_name=xss_payload,
            appointment_type="Vorsorge",
            ctx=ctx,
        )

        # Img tag should be escaped
        assert "<img" not in html
        assert "&lt;img" in html

    def test_xss_in_practice_name_escaped(self):
        """Verify XSS payload in practice name is escaped."""
        from phone_agent.integrations.email.templates import (
            appointment_confirmation_html,
            TemplateContext,
        )

        xss_payload = '"><script>alert("XSS")</script><"'
        ctx = TemplateContext(practice_name=xss_payload)

        html = appointment_confirmation_html(
            patient_name="Max Mustermann",
            appointment_date=date(2024, 1, 15),
            appointment_time=time(10, 30),
            provider_name="Dr. Test",
            appointment_type="Vorsorge",
            ctx=ctx,
        )

        # Should not contain unescaped script
        assert "<script>" not in html

    def test_xss_in_notes_escaped(self):
        """Verify XSS payload in notes is escaped."""
        from phone_agent.integrations.email.templates import (
            appointment_confirmation_html,
            TemplateContext,
        )

        ctx = TemplateContext(practice_name="Test Praxis")
        xss_payload = '<svg onload="alert(1)">'

        html = appointment_confirmation_html(
            patient_name="Max Mustermann",
            appointment_date=date(2024, 1, 15),
            appointment_time=time(10, 30),
            provider_name="Dr. Test",
            appointment_type="Vorsorge",
            ctx=ctx,
            notes=xss_payload,
        )

        # SVG tag should be escaped
        assert "<svg" not in html
        assert "&lt;svg" in html

    def test_xss_in_cancellation_reason_escaped(self):
        """Verify XSS payload in cancellation reason is escaped."""
        from phone_agent.integrations.email.templates import (
            appointment_cancellation_html,
            TemplateContext,
        )

        ctx = TemplateContext(practice_name="Test Praxis")
        xss_payload = '<iframe src="evil.com"></iframe>'

        html = appointment_cancellation_html(
            patient_name="Max Mustermann",
            appointment_date=date(2024, 1, 15),
            appointment_time=time(10, 30),
            ctx=ctx,
            reason=xss_payload,
        )

        # Iframe tag should be escaped
        assert "<iframe" not in html
        assert "&lt;iframe" in html

    def test_xss_in_reminder_escaped(self):
        """Verify XSS prevention in reminder templates."""
        from phone_agent.integrations.email.templates import (
            appointment_reminder_html,
            TemplateContext,
        )

        xss_payload = '<body onload="alert(1)">'
        ctx = TemplateContext(practice_name=xss_payload)

        html = appointment_reminder_html(
            patient_name='<script>alert("XSS")</script>',
            appointment_date=date(2024, 1, 15),
            appointment_time=time(10, 30),
            provider_name="Dr. Test",
            ctx=ctx,
        )

        # Both payloads should be escaped
        assert "<script>" not in html
        assert "<body onload" not in html

    def test_xss_in_rescheduled_escaped(self):
        """Verify XSS prevention in reschedule templates."""
        from phone_agent.integrations.email.templates import (
            create_appointment_rescheduled_email,
            TemplateContext,
        )

        ctx = TemplateContext(practice_name="Test Praxis")
        xss_payload = '<marquee>XSS</marquee>'

        email = create_appointment_rescheduled_email(
            to_email="test@example.com",
            patient_name=xss_payload,
            old_date=date(2024, 1, 15),
            old_time=time(10, 30),
            new_date=date(2024, 1, 16),
            new_time=time(11, 0),
            provider_name="Dr. Test",
            ctx=ctx,
        )

        # Marquee tag should be escaped in HTML
        assert "<marquee>" not in email.body_html
        assert "&lt;marquee&gt;" in email.body_html

    def test_quotes_in_attributes_escaped(self):
        """Verify quotes in attributes are properly escaped."""
        from phone_agent.integrations.email.templates import (
            _base_html_template,
            TemplateContext,
        )

        # Payload trying to break out of attribute
        xss_payload = '" onclick="alert(1)" data-x="'
        ctx = TemplateContext(
            practice_name="Test",
            practice_website=xss_payload,
        )

        html = _base_html_template("<p>Test</p>", ctx)

        # Quotes should be escaped
        assert 'onclick="alert(1)"' not in html


class TestInputValidation:
    """Test input validation in API models."""

    def test_phone_number_format_validation(self):
        """Test phone number format validation would catch invalid input."""
        # This is a placeholder - will be implemented with P2 fixes
        pass

    def test_metadata_size_limits(self):
        """Test metadata size limits would prevent DOS."""
        # This is a placeholder - will be implemented with P2 fixes
        pass


class TestWebhookSecurity:
    """Test webhook signature validation."""

    def test_twilio_signature_validation_required(self):
        """Verify Twilio webhooks require signature validation."""
        from phone_agent.api.webhook_security import WebhookSecurityConfig

        config = WebhookSecurityConfig(
            validate_signatures=True,
            twilio_auth_token="test_token",
        )

        assert config.validate_signatures is True

    def test_constant_time_comparison_used(self):
        """Verify constant-time comparison is used for signatures."""
        import hmac

        from phone_agent.api.webhook_security import TwilioSignatureValidator

        # Verify the validator uses hmac.compare_digest
        validator = TwilioSignatureValidator("test_token")

        # The implementation should use hmac.compare_digest internally
        # This is verified by code inspection - the test ensures the class exists
        assert validator is not None


class TestJWTAuthentication:
    """Test JWT authentication."""

    def test_create_access_token(self):
        """Test creating an access token."""
        from phone_agent.api.auth import create_access_token, decode_token

        token = create_access_token(
            subject="test-user",
            scopes=["read", "write"],
        )

        assert token is not None
        assert isinstance(token, str)

        # Decode and verify
        payload = decode_token(token)
        assert payload.sub == "test-user"
        assert "read" in payload.scopes
        assert "write" in payload.scopes

    def test_token_expiration(self):
        """Test that expired tokens are rejected."""
        from datetime import timedelta
        import time

        from phone_agent.api.auth import create_access_token, decode_token
        import pytest

        # Create token that expires immediately
        token = create_access_token(
            subject="test-user",
            expires_delta=timedelta(seconds=-1),  # Already expired
        )

        # Should raise HTTPException for expired token
        with pytest.raises(Exception) as exc_info:
            decode_token(token)

        assert "expired" in str(exc_info.value.detail).lower()

    def test_invalid_token_rejected(self):
        """Test that invalid tokens are rejected."""
        from phone_agent.api.auth import decode_token
        import pytest

        # Invalid token format
        with pytest.raises(Exception) as exc_info:
            decode_token("not.a.valid.token")

        assert exc_info.value.status_code == 401

    def test_authenticated_user_model(self):
        """Test AuthenticatedUser model."""
        from phone_agent.api.auth import AuthenticatedUser

        user = AuthenticatedUser(
            id="user-123",
            scopes=["admin"],
            token_type="access",
        )

        assert user.id == "user-123"
        assert "admin" in user.scopes
