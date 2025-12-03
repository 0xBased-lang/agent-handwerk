"""Tests for compliance repositories (ConsentRepository, AuditLogRepository)."""

from __future__ import annotations

from datetime import datetime, timedelta
from uuid import uuid4

import pytest


# ============================================================================
# Consent Repository Tests
# ============================================================================


class TestConsentRepository:
    """Tests for ConsentRepository."""

    @pytest.mark.asyncio
    async def test_create_consent(self, db_session, consent_repository, sample_contact):
        """Test creating a consent record."""
        from phone_agent.db.models.compliance import ConsentModel

        consent = ConsentModel(
            id=uuid4(),
            contact_id=sample_contact.id,
            consent_type="phone_contact",
            industry="gesundheit",
        )
        consent.grant(granted_by="test", version="1.0")

        created = await consent_repository.create(consent)
        await db_session.commit()

        assert created.id is not None
        assert created.consent_type == "phone_contact"
        assert created.status == "granted"
        assert created.is_valid()

    @pytest.mark.asyncio
    async def test_get_by_contact(self, db_session, consent_repository, sample_consent):
        """Test getting all consents for a contact."""
        consents = await consent_repository.get_by_contact(sample_consent.contact_id)

        assert len(consents) >= 1
        assert any(c.id == sample_consent.id for c in consents)

    @pytest.mark.asyncio
    async def test_get_by_contact_and_type(
        self, db_session, consent_repository, sample_consent
    ):
        """Test getting specific consent type for a contact."""
        consent = await consent_repository.get_by_contact_and_type(
            sample_consent.contact_id, "voice_recording"
        )

        assert consent is not None
        assert consent.consent_type == "voice_recording"

    @pytest.mark.asyncio
    async def test_get_by_contact_and_type_not_found(
        self, db_session, consent_repository, sample_contact
    ):
        """Test getting non-existent consent type returns None."""
        consent = await consent_repository.get_by_contact_and_type(
            sample_contact.id, "nonexistent_type"
        )

        assert consent is None

    @pytest.mark.asyncio
    async def test_get_active_consents(
        self, db_session, consent_repository, sample_consent
    ):
        """Test getting only active consents."""
        active = await consent_repository.get_active_consents(sample_consent.contact_id)

        assert len(active) >= 1
        assert all(c.status == "granted" for c in active)
        assert all(c.is_valid() for c in active)

    @pytest.mark.asyncio
    async def test_check_consent_valid(
        self, db_session, consent_repository, sample_consent
    ):
        """Test checking valid consent returns True."""
        has_consent = await consent_repository.check_consent(
            sample_consent.contact_id, "voice_recording"
        )

        assert has_consent is True

    @pytest.mark.asyncio
    async def test_check_consent_invalid(
        self, db_session, consent_repository, sample_contact
    ):
        """Test checking non-existent consent returns False."""
        has_consent = await consent_repository.check_consent(
            sample_contact.id, "nonexistent_type"
        )

        assert has_consent is False

    @pytest.mark.asyncio
    async def test_revoke_consent(self, db_session, consent_repository, sample_consent):
        """Test revoking consent."""
        revoked = await consent_repository.revoke_consent(
            sample_consent.contact_id, "voice_recording", notes="User requested"
        )
        await db_session.commit()

        assert revoked is not None
        assert revoked.status == "withdrawn"
        assert revoked.withdrawn_at is not None
        assert not revoked.is_valid()

    @pytest.mark.asyncio
    async def test_revoke_nonexistent_consent(
        self, db_session, consent_repository, sample_contact
    ):
        """Test revoking non-existent consent returns None."""
        result = await consent_repository.revoke_consent(
            sample_contact.id, "nonexistent_type"
        )

        assert result is None

    @pytest.mark.asyncio
    async def test_consent_expiry(self, db_session, consent_repository, sample_contact):
        """Test consent expiry detection."""
        from phone_agent.db.models.compliance import ConsentModel

        # Create consent that expires in the past
        consent = ConsentModel(
            id=uuid4(),
            contact_id=sample_contact.id,
            consent_type="expired_test",
            industry="gesundheit",
        )
        consent.grant(granted_by="test", duration_days=-1)  # Already expired

        await consent_repository.create(consent)
        await db_session.commit()

        # Should not be valid
        assert not consent.is_valid()

        # Should not appear in check
        has_consent = await consent_repository.check_consent(
            sample_contact.id, "expired_test"
        )
        assert has_consent is False

    @pytest.mark.asyncio
    async def test_get_expiring_consents(
        self, db_session, consent_repository, sample_contact
    ):
        """Test getting consents expiring soon."""
        from phone_agent.db.models.compliance import ConsentModel

        # Create consent expiring in 7 days
        consent = ConsentModel(
            id=uuid4(),
            contact_id=sample_contact.id,
            consent_type="expiring_soon",
            industry="gesundheit",
        )
        consent.grant(granted_by="test", duration_days=7)

        await consent_repository.create(consent)
        await db_session.commit()

        # Should appear in expiring list
        expiring = await consent_repository.get_expiring_consents(days_ahead=30)

        assert len(expiring) >= 1
        assert any(c.consent_type == "expiring_soon" for c in expiring)

    @pytest.mark.asyncio
    async def test_count_by_contact(
        self, db_session, consent_repository, sample_consent
    ):
        """Test counting consents by status for a contact."""
        counts = await consent_repository.count_by_contact(sample_consent.contact_id)

        assert "granted" in counts
        assert counts["granted"] >= 1


# ============================================================================
# Audit Log Repository Tests
# ============================================================================


class TestAuditLogRepository:
    """Tests for AuditLogRepository."""

    @pytest.mark.asyncio
    async def test_create_audit_entry(
        self, db_session, audit_repository, sample_contact
    ):
        """Test creating an audit log entry."""
        from phone_agent.db.models.compliance import AuditLogModel

        entry = AuditLogModel.create(
            action="test_create",
            actor_id="test_user",
            actor_type="user",
            resource_type="contact",
            resource_id=str(sample_contact.id),
            contact_id=sample_contact.id,
            details={"operation": "test"},
            industry="gesundheit",
        )

        created = await audit_repository.create_with_chain(entry)
        await db_session.commit()

        assert created.id is not None
        assert created.action == "test_create"
        assert created.checksum is not None
        assert created.verify_checksum()

    @pytest.mark.asyncio
    async def test_get_by_contact(
        self, db_session, audit_repository, sample_audit_log
    ):
        """Test getting audit entries for a contact."""
        entries = await audit_repository.get_by_contact(sample_audit_log.contact_id)

        assert len(entries) >= 1
        assert any(e.id == sample_audit_log.id for e in entries)

    @pytest.mark.asyncio
    async def test_get_by_date_range(
        self, db_session, audit_repository, sample_audit_log
    ):
        """Test querying audit log by date range."""
        start = datetime.utcnow() - timedelta(days=1)
        end = datetime.utcnow() + timedelta(days=1)

        entries = await audit_repository.get_by_date_range(start, end)

        assert len(entries) >= 1

    @pytest.mark.asyncio
    async def test_get_by_date_range_with_filters(
        self, db_session, audit_repository, sample_audit_log
    ):
        """Test querying audit log with filters."""
        start = datetime.utcnow() - timedelta(days=1)
        end = datetime.utcnow() + timedelta(days=1)

        entries = await audit_repository.get_by_date_range(
            start, end, action="test_action"
        )

        assert len(entries) >= 1
        assert all(e.action == "test_action" for e in entries)

    @pytest.mark.asyncio
    async def test_get_by_resource(
        self, db_session, audit_repository, sample_audit_log
    ):
        """Test getting audit entries for a resource."""
        entries = await audit_repository.get_by_resource(
            "test_resource", "test-123"
        )

        assert len(entries) >= 1
        assert all(e.resource_type == "test_resource" for e in entries)

    @pytest.mark.asyncio
    async def test_get_last_checksum(
        self, db_session, audit_repository, sample_audit_log
    ):
        """Test getting last checksum for chain integrity."""
        checksum = await audit_repository.get_last_checksum()

        assert checksum is not None
        assert checksum == sample_audit_log.checksum

    @pytest.mark.asyncio
    async def test_chain_integrity(
        self, db_session, audit_repository, sample_contact
    ):
        """Test audit log chain integrity."""
        from phone_agent.db.models.compliance import AuditLogModel

        # Create multiple entries to build a chain
        for i in range(3):
            entry = AuditLogModel.create(
                action=f"chain_test_{i}",
                actor_id="test_user",
                actor_type="system",
                resource_type="test",
                contact_id=sample_contact.id,
            )
            await audit_repository.create_with_chain(entry)

        await db_session.commit()

        # Verify chain integrity
        result = await audit_repository.verify_chain_integrity(sample_size=10)

        assert result["verified"] is True
        assert result["invalid_count"] == 0
        assert len(result["broken_chains"]) == 0

    @pytest.mark.asyncio
    async def test_count_with_filters(
        self, db_session, audit_repository, sample_audit_log
    ):
        """Test counting entries with filters."""
        start = datetime.utcnow() - timedelta(days=1)
        end = datetime.utcnow() + timedelta(days=1)

        count = await audit_repository.count_with_filters(
            start=start, end=end, action="test_action"
        )

        assert count >= 1

    @pytest.mark.asyncio
    async def test_export_for_contact(
        self, db_session, audit_repository, sample_audit_log
    ):
        """Test exporting audit entries for a contact."""
        exports = await audit_repository.export_for_contact(sample_audit_log.contact_id)

        assert len(exports) >= 1
        assert all(isinstance(e, dict) for e in exports)
        assert "action" in exports[0]
        assert "timestamp" in exports[0]

    @pytest.mark.asyncio
    async def test_checksum_verification(
        self, db_session, audit_repository, sample_audit_log
    ):
        """Test that checksum verification works."""
        # Valid checksum
        assert sample_audit_log.verify_checksum() is True

        # Tamper with data
        original_action = sample_audit_log.action
        sample_audit_log.action = "tampered_action"

        # Checksum should now fail
        assert sample_audit_log.verify_checksum() is False

        # Restore
        sample_audit_log.action = original_action

    @pytest.mark.asyncio
    async def test_action_category_auto_detection(
        self, db_session, audit_repository, sample_contact
    ):
        """Test that action category is auto-detected."""
        from phone_agent.db.models.compliance import AuditLogModel

        test_cases = [
            ("data_view", "data_access"),
            ("data_update", "data_modification"),
            ("call_started", "communication"),
            ("consent_granted", "consent"),
            ("appointment_created", "scheduling"),
            ("unknown_action", "system"),
        ]

        for action, expected_category in test_cases:
            entry = AuditLogModel.create(
                action=action,
                actor_id="test",
                actor_type="system",
                resource_type="test",
                contact_id=sample_contact.id,
            )
            await audit_repository.create_with_chain(entry)

            assert entry.action_category == expected_category

        await db_session.commit()
