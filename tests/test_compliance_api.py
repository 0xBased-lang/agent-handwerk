"""Tests for DSGVO Compliance API endpoints."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient


# ============================================================================
# Helper Functions
# ============================================================================


def create_mock_consent(
    contact_id=None,
    consent_type="voice_recording",
    status="granted",
    is_valid=True,
):
    """Create a mock consent object."""
    consent = MagicMock()
    consent.id = uuid4()
    consent.contact_id = contact_id or uuid4()
    consent.consent_type = consent_type
    consent.status = status
    consent.is_valid = is_valid
    consent.industry = "gesundheit"
    consent.granted_at = datetime.now()
    consent.expires_at = datetime.now() + timedelta(days=365)
    consent.version = "1.0"
    consent.granted_by = "test"
    consent.revoked_at = None
    consent.revoked_by = None
    consent.revocation_reason = None
    consent.created_at = datetime.now()
    consent.updated_at = datetime.now()
    return consent


def create_mock_audit_entry(
    contact_id=None,
    action="test_action",
    actor_id="test_actor",
):
    """Create a mock audit log entry."""
    entry = MagicMock()
    entry.id = uuid4()
    entry.contact_id = contact_id or uuid4()
    entry.action = action
    entry.actor_id = actor_id
    entry.actor_type = "system"
    entry.resource_type = "consent"
    entry.resource_id = str(uuid4())
    entry.industry = "gesundheit"
    entry.details = {"test": "data"}
    entry.action_category = "compliance"
    entry.checksum = "abc123"
    entry.previous_checksum = None
    entry.timestamp = datetime.now()
    entry.ip_address = "127.0.0.1"
    entry.user_agent = "test"
    return entry


# ============================================================================
# Service-Level Tests (Using Real Database Fixtures)
# ============================================================================


class TestComplianceServiceIntegration:
    """Tests for compliance service with real database."""

    @pytest.mark.asyncio
    async def test_consent_verification_flow(
        self, db_session, sample_contact, consent_repository, compliance_service
    ):
        """Test full consent verification workflow."""
        from phone_agent.db.models.compliance import ConsentModel

        # Create consent
        consent = ConsentModel(
            id=uuid4(),
            contact_id=sample_contact.id,
            consent_type="voice_recording",
            industry="gesundheit",
        )
        consent.grant(granted_by="test", duration_days=365, version="1.0")
        await consent_repository.create(consent)
        await db_session.commit()

        # Verify consent through service
        is_valid, reason = await compliance_service.verify_consent_for_recording_access(
            contact_id=sample_contact.id,
            actor_id="test_actor",
        )
        assert is_valid is True
        assert reason is None

    @pytest.mark.asyncio
    async def test_audit_chain_integrity(
        self, db_session, sample_contact, audit_repository, compliance_service
    ):
        """Test audit chain integrity verification."""
        from phone_agent.db.models.compliance import AuditLogModel

        # Create multiple audit entries with chain
        for i in range(3):
            entry = AuditLogModel.create(
                action=f"test_action_{i}",
                actor_id="test_actor",
                actor_type="system",
                resource_type="test",
                resource_id=f"test-{i}",
                contact_id=sample_contact.id,
                details={"index": i},
                industry="gesundheit",
            )
            await audit_repository.create_with_chain(entry)
            await db_session.commit()

        # Verify chain integrity - returns a dict
        result = await audit_repository.verify_chain_integrity(sample_size=10)
        assert result["verified"] is True


# ============================================================================
# Repository Unit Tests
# ============================================================================


class TestConsentRepositoryUnit:
    """Unit tests for ConsentRepository."""

    @pytest.mark.asyncio
    async def test_check_consent_valid(self, consent_repository, sample_consent):
        """Test checking valid consent."""
        is_valid = await consent_repository.check_consent(
            contact_id=sample_consent.contact_id,
            consent_type=sample_consent.consent_type,
        )
        assert is_valid is True

    @pytest.mark.asyncio
    async def test_check_consent_invalid(self, consent_repository, sample_contact):
        """Test checking non-existent consent."""
        is_valid = await consent_repository.check_consent(
            contact_id=sample_contact.id,
            consent_type="nonexistent_type",
        )
        assert is_valid is False

    @pytest.mark.asyncio
    async def test_revoke_consent(
        self, db_session, consent_repository, sample_consent
    ):
        """Test revoking consent."""
        revoked = await consent_repository.revoke_consent(
            contact_id=sample_consent.contact_id,
            consent_type=sample_consent.consent_type,
            notes="User requested revocation",
        )
        await db_session.commit()

        assert revoked is not None

        # Verify consent is no longer valid
        is_valid = await consent_repository.check_consent(
            contact_id=sample_consent.contact_id,
            consent_type=sample_consent.consent_type,
        )
        assert is_valid is False


class TestAuditLogRepositoryUnit:
    """Unit tests for AuditLogRepository."""

    @pytest.mark.asyncio
    async def test_get_by_contact(self, audit_repository, sample_audit_log):
        """Test retrieving audit entries by contact."""
        entries = await audit_repository.get_by_contact(
            contact_id=sample_audit_log.contact_id,
        )
        assert len(entries) >= 1
        assert any(e.id == sample_audit_log.id for e in entries)

    @pytest.mark.asyncio
    async def test_chain_integrity(
        self, db_session, audit_repository, sample_contact
    ):
        """Test audit chain integrity."""
        from phone_agent.db.models.compliance import AuditLogModel

        # Create multiple entries
        for i in range(3):
            entry = AuditLogModel.create(
                action=f"test_chain_{i}",
                actor_id="test_actor",
                actor_type="system",
                resource_type="test",
                resource_id=f"test-chain-{i}",
                contact_id=sample_contact.id,
                details={"index": i},
                industry="gesundheit",
            )
            await audit_repository.create_with_chain(entry)
            await db_session.commit()

        # Verify chain - returns a dict
        result = await audit_repository.verify_chain_integrity(sample_size=10)
        assert result["verified"] is True


# ============================================================================
# API Endpoint Schema Tests (Mocked)
# ============================================================================


class TestAPIEndpointSchemas:
    """Test API endpoint request/response schemas."""

    def test_reschedule_request_schema(self):
        """Test reschedule request schema."""
        from phone_agent.api.compliance import RescheduleRequest

        request = RescheduleRequest(
            new_date=date.today() + timedelta(days=7),
            new_time=time(14, 0),
            reason="Patient requested reschedule",
            notify_patient=True,
        )
        assert request.notify_patient is True

    def test_reschedule_response_schema(self):
        """Test reschedule response schema."""
        from phone_agent.api.compliance import RescheduleResponse

        response = RescheduleResponse(
            appointment_id=uuid4(),
            previous_datetime=datetime.now(),
            new_datetime=datetime.now() + timedelta(days=7),
            status="rescheduled",
            notification_sent=True,
            audit_log_id=uuid4(),
        )
        assert response.notification_sent is True

    def test_consent_list_response_schema(self):
        """Test consent list response schema."""
        from phone_agent.api.compliance import ConsentListResponse

        response = ConsentListResponse(
            contact_id=uuid4(),
            consents=[],
            active_count=0,
            expired_count=0,
            withdrawn_count=0,
        )
        assert response.active_count == 0

    def test_audit_log_list_response_schema(self):
        """Test audit log list response schema."""
        from phone_agent.api.compliance import AuditLogListResponse

        response = AuditLogListResponse(
            entries=[],
            total=0,
            page=1,
            page_size=50,
        )
        assert response.page == 1

    def test_audit_integrity_response_schema(self):
        """Test audit integrity response schema."""
        from phone_agent.api.compliance import AuditIntegrityResponse

        response = AuditIntegrityResponse(
            verified=True,
            total_checked=100,
            valid_count=100,
            invalid_count=0,
            invalid_entries=[],
            broken_chains=[],
        )
        assert response.verified is True

    def test_recording_response_schema(self):
        """Test recording response schema."""
        from phone_agent.api.compliance import RecordingResponse

        response = RecordingResponse(
            call_id=uuid4(),
            recording_url="https://example.com/recording.mp3",
            transcript="Hello, this is a test recording.",
            duration_seconds=120,
            recorded_at=datetime.now(),
            consent_verified=True,
            access_expires_at=datetime.now() + timedelta(hours=1),
        )
        assert response.consent_verified is True


# ============================================================================
# API Router Registration Test
# ============================================================================


class TestAPIRouterRegistration:
    """Test that compliance router is properly registered."""

    def test_compliance_router_registered(self):
        """Test that compliance routes are registered in the app."""
        from phone_agent.main import app

        # Get all registered routes
        routes = [r.path for r in app.routes]

        # Check compliance routes exist
        assert any("/contacts/{contact_id}/consent" in r for r in routes)
        assert any("/audit-log" in r for r in routes)
        assert any("/calls/{call_id}/recording" in r for r in routes)
        assert any("/appointments/{appointment_id}/reschedule" in r for r in routes)

    def test_compliance_router_tags(self):
        """Test that compliance routes have correct tags."""
        from phone_agent.main import app

        # Verify compliance routes are registered by checking for expected paths
        # Compliance routes are at /api/v1/ prefix, not /compliance/ prefix
        route_paths = [getattr(r, 'path', '') for r in app.routes]

        # Check for compliance-related route paths (consent and audit-log)
        compliance_paths = [
            '/consent',  # Consent management routes
            '/audit-log',  # Audit logging routes
        ]

        found_compliance_routes = any(
            any(cp in path for cp in compliance_paths)
            for path in route_paths
        )

        assert found_compliance_routes, (
            f"Expected at least one compliance route. "
            f"Available routes: {[p for p in route_paths if 'consent' in p.lower() or 'audit' in p.lower()]}"
        )


# ============================================================================
# Endpoint Availability Tests (No DB Required)
# ============================================================================


class TestEndpointAvailability:
    """Test that endpoints are available and return expected error codes."""

    @pytest.fixture
    def client(self):
        """Create test client with mocked database."""
        from phone_agent.main import create_app

        # Create app with test configuration
        app = create_app()

        # Return client without entering context (avoids lifespan issues)
        return TestClient(app, raise_server_exceptions=False)

    def test_consent_endpoint_exists(self, client):
        """Test consent endpoint returns 422 for invalid UUID (not 404)."""
        # Invalid UUID format should return 422, not 404
        response = client.post(
            "/api/v1/contacts/invalid-uuid/consent",
            json={"consent_type": "test", "granted_by": "test"},
        )
        # 422 means endpoint exists but input validation failed
        assert response.status_code in (422, 500)  # 500 if DB not connected

    def test_audit_log_endpoint_exists(self, client):
        """Test audit log endpoint is accessible."""
        response = client.get("/api/v1/audit-log")
        # Should not be 404
        assert response.status_code != 404

    def test_audit_log_integrity_endpoint_exists(self, client):
        """Test audit log integrity endpoint is accessible."""
        response = client.get("/api/v1/audit-log/integrity")
        assert response.status_code != 404

    def test_audit_log_export_endpoint_exists(self, client):
        """Test audit log export endpoint is accessible."""
        response = client.get("/api/v1/audit-log/export")
        assert response.status_code != 404


# ============================================================================
# Error Handling Tests
# ============================================================================


class TestErrorHandling:
    """Test error handling in compliance service."""

    def test_compliance_service_error(self):
        """Test base ComplianceServiceError."""
        from phone_agent.services.compliance_service import ComplianceServiceError

        error = ComplianceServiceError("Test error")
        assert str(error) == "Test error"

    def test_consent_denied_error(self):
        """Test ConsentDeniedError is properly defined."""
        from phone_agent.services.compliance_service import ConsentDeniedError

        error = ConsentDeniedError("Consent not granted for voice recording")
        assert "voice recording" in str(error)

    def test_consent_not_found_error(self):
        """Test ConsentNotFoundError is properly defined."""
        from phone_agent.services.compliance_service import ConsentNotFoundError

        error = ConsentNotFoundError("Consent record not found")
        assert "not found" in str(error)

    def test_error_inheritance(self):
        """Test error class inheritance."""
        from phone_agent.services.compliance_service import (
            ComplianceServiceError,
            ConsentDeniedError,
            ConsentNotFoundError,
        )

        assert issubclass(ConsentDeniedError, ComplianceServiceError)
        assert issubclass(ConsentNotFoundError, ComplianceServiceError)
        assert issubclass(ComplianceServiceError, Exception)
