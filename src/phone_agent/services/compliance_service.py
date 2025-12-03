"""Compliance Service for Phone Agent.

Provides business logic for DSGVO compliance including:
- Consent verification and management
- Audit trail logging
- Data access authorization

Integrates with ConsentRepository and AuditLogRepository.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

from itf_shared import get_logger

from phone_agent.db.models.compliance import AuditLogModel, ConsentModel
from phone_agent.db.repositories.compliance import (
    AuditLogRepository,
    ConsentRepository,
)

log = get_logger(__name__)


class ComplianceServiceError(Exception):
    """Compliance service error."""

    pass


class ConsentNotFoundError(ComplianceServiceError):
    """Consent record not found."""

    pass


class ConsentDeniedError(ComplianceServiceError):
    """Consent not granted or expired."""

    pass


class ComplianceService:
    """Service for DSGVO compliance operations.

    Provides consent verification, audit logging, and compliance
    checks for healthcare and other regulated operations.

    Usage:
        service = ComplianceService(consent_repo, audit_repo)

        # Record consent
        consent = await service.record_consent_with_audit(
            contact_id=uuid,
            consent_type="voice_recording",
            granted_by="phone_agent",
            actor_id="system",
            industry="gesundheit",
        )

        # Verify before access
        allowed, reason = await service.verify_consent_for_recording_access(
            contact_id=uuid,
            actor_id="api_user_123",
        )
    """

    def __init__(
        self,
        consent_repo: ConsentRepository,
        audit_repo: AuditLogRepository,
    ) -> None:
        """Initialize service with repositories.

        Args:
            consent_repo: Consent repository instance
            audit_repo: Audit log repository instance
        """
        self._consent_repo = consent_repo
        self._audit_repo = audit_repo

    # =========================================================================
    # Consent Verification
    # =========================================================================

    async def verify_consent_for_recording_access(
        self,
        contact_id: UUID,
        actor_id: str,
        ip_address: str | None = None,
    ) -> tuple[bool, str | None]:
        """Verify consent before allowing recording access.

        DSGVO Art. 6 - Lawfulness of processing

        Args:
            contact_id: Contact UUID
            actor_id: ID of actor requesting access
            ip_address: Optional IP address of requester

        Returns:
            Tuple of (allowed: bool, reason_if_denied: str | None)
        """
        has_consent = await self._consent_repo.check_consent(
            contact_id, "voice_recording"
        )

        if not has_consent:
            log.warning(
                "Recording access denied - no consent",
                contact_id=str(contact_id),
                actor_id=actor_id,
            )
            return False, "No valid voice_recording consent found"

        return True, None

    async def verify_consent(
        self,
        contact_id: UUID,
        consent_type: str,
    ) -> bool:
        """Check if contact has valid consent for a purpose.

        Args:
            contact_id: Contact UUID
            consent_type: Type of consent to verify

        Returns:
            True if valid consent exists
        """
        return await self._consent_repo.check_consent(contact_id, consent_type)

    # =========================================================================
    # Consent Management
    # =========================================================================

    async def record_consent_with_audit(
        self,
        contact_id: UUID,
        consent_type: str,
        granted_by: str,
        actor_id: str,
        actor_type: str = "system",
        ip_address: str | None = None,
        version: str = "1.0",
        duration_days: int | None = None,
        legal_text: str | None = None,
        reference_id: UUID | None = None,
        reference_type: str | None = None,
        notes: str | None = None,
        industry: str = "gesundheit",
    ) -> ConsentModel:
        """Record consent and create audit log entry.

        DSGVO Art. 7 - Conditions for consent

        Args:
            contact_id: Contact UUID
            consent_type: Type of consent being granted
            granted_by: How consent was obtained (phone_agent, web_form, etc.)
            actor_id: ID of actor recording consent
            actor_type: Type of actor (system, user, ai_agent)
            ip_address: Optional IP address
            version: Version of consent form
            duration_days: Optional consent duration (None = indefinite)
            legal_text: Optional legal text shown to user
            reference_id: Optional reference to related entity
            reference_type: Optional type of reference
            notes: Optional notes
            industry: Industry vertical

        Returns:
            Created consent record
        """
        from uuid import uuid4

        # Check if consent already exists
        existing = await self._consent_repo.get_by_contact_and_type(
            contact_id, consent_type
        )

        if existing:
            # Update existing consent
            existing.grant(
                granted_by=granted_by,
                duration_days=duration_days,
                version=version,
                legal_text=legal_text,
                notes=notes,
            )
            consent = existing
            action = "consent_updated"
        else:
            # Create new consent
            consent = ConsentModel(
                id=uuid4(),
                contact_id=contact_id,
                consent_type=consent_type,
                industry=industry,
                reference_id=reference_id,
                reference_type=reference_type,
            )
            consent.grant(
                granted_by=granted_by,
                duration_days=duration_days,
                version=version,
                legal_text=legal_text,
                notes=notes,
            )
            consent = await self._consent_repo.create(consent)
            action = "consent_granted"

        # Create audit log entry
        await self._log_action(
            action=action,
            actor_id=actor_id,
            actor_type=actor_type,
            resource_type="consent",
            resource_id=str(consent.id),
            contact_id=contact_id,
            details={
                "consent_type": consent_type,
                "version": version,
                "duration_days": duration_days,
                "granted_by": granted_by,
            },
            ip_address=ip_address,
            industry=industry,
        )

        log.info(
            "Consent recorded",
            contact_id=str(contact_id),
            consent_type=consent_type,
            action=action,
        )

        return consent

    async def revoke_consent_with_audit(
        self,
        contact_id: UUID,
        consent_type: str,
        actor_id: str,
        actor_type: str = "system",
        ip_address: str | None = None,
        notes: str | None = None,
        industry: str = "gesundheit",
    ) -> ConsentModel:
        """Revoke consent and create audit log entry.

        DSGVO Art. 7(3) - Right to withdraw consent

        Args:
            contact_id: Contact UUID
            consent_type: Type of consent to revoke
            actor_id: ID of actor revoking consent
            actor_type: Type of actor
            ip_address: Optional IP address
            notes: Optional notes about revocation
            industry: Industry vertical

        Returns:
            Updated consent record

        Raises:
            ConsentNotFoundError: If consent not found
        """
        consent = await self._consent_repo.revoke_consent(
            contact_id, consent_type, notes
        )

        if consent is None:
            raise ConsentNotFoundError(
                f"No {consent_type} consent found for contact {contact_id}"
            )

        # Create audit log entry
        await self._log_action(
            action="consent_withdrawn",
            actor_id=actor_id,
            actor_type=actor_type,
            resource_type="consent",
            resource_id=str(consent.id),
            contact_id=contact_id,
            details={
                "consent_type": consent_type,
                "notes": notes,
            },
            ip_address=ip_address,
            industry=industry,
        )

        log.info(
            "Consent revoked",
            contact_id=str(contact_id),
            consent_type=consent_type,
        )

        return consent

    # =========================================================================
    # Audit Logging
    # =========================================================================

    async def log_data_access(
        self,
        actor_id: str,
        resource_type: str,
        resource_id: str | None,
        contact_id: UUID | None,
        action: str,
        actor_type: str = "user",
        action_category: str = "data_access",
        details: dict[str, Any] | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
        session_id: str | None = None,
        industry: str = "gesundheit",
    ) -> AuditLogModel:
        """Log a data access event with chain integrity.

        DSGVO Art. 30 - Records of processing activities

        Args:
            actor_id: ID of actor accessing data
            resource_type: Type of resource accessed
            resource_id: Optional specific resource ID
            contact_id: Optional related contact
            action: Action performed
            actor_type: Type of actor
            action_category: Category of action
            details: Optional additional details
            ip_address: Optional IP address
            user_agent: Optional user agent
            session_id: Optional session ID
            industry: Industry vertical

        Returns:
            Created audit log entry
        """
        return await self._log_action(
            action=action,
            actor_id=actor_id,
            actor_type=actor_type,
            resource_type=resource_type,
            resource_id=resource_id,
            contact_id=contact_id,
            details=details,
            ip_address=ip_address,
            user_agent=user_agent,
            session_id=session_id,
            industry=industry,
        )

    async def _log_action(
        self,
        action: str,
        actor_id: str,
        actor_type: str,
        resource_type: str,
        resource_id: str | None = None,
        contact_id: UUID | None = None,
        details: dict[str, Any] | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
        session_id: str | None = None,
        industry: str | None = None,
    ) -> AuditLogModel:
        """Internal method to create audit log entry with chain.

        Args:
            action: Action performed
            actor_id: ID of actor
            actor_type: Type of actor
            resource_type: Type of resource
            resource_id: Optional resource ID
            contact_id: Optional contact ID
            details: Optional details dict
            ip_address: Optional IP address
            user_agent: Optional user agent
            session_id: Optional session ID
            industry: Optional industry

        Returns:
            Created audit log entry
        """
        entry = AuditLogModel.create(
            action=action,
            actor_id=actor_id,
            actor_type=actor_type,
            resource_type=resource_type,
            resource_id=resource_id,
            contact_id=contact_id,
            details=details,
            ip_address=ip_address,
            user_agent=user_agent,
            session_id=session_id,
            industry=industry,
        )

        return await self._audit_repo.create_with_chain(entry)

    # =========================================================================
    # Audit Log Queries
    # =========================================================================

    async def get_contact_audit_trail(
        self,
        contact_id: UUID,
        actor_id: str,
        ip_address: str | None = None,
        skip: int = 0,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Get audit trail for a contact (DSGVO Art. 15 - Right of access).

        Args:
            contact_id: Contact UUID
            actor_id: ID of actor requesting access
            ip_address: Optional IP address
            skip: Pagination offset
            limit: Maximum results

        Returns:
            List of audit entries as dictionaries
        """
        # Log this access request
        await self._log_action(
            action="audit_log_viewed",
            actor_id=actor_id,
            actor_type="user",
            resource_type="audit_log",
            resource_id=None,
            contact_id=contact_id,
            details={"query_type": "contact_audit_trail"},
            ip_address=ip_address,
            industry="gesundheit",
        )

        entries = await self._audit_repo.get_by_contact(
            contact_id, skip=skip, limit=limit
        )
        return [entry.to_dict() for entry in entries]

    async def verify_audit_integrity(
        self,
        sample_size: int = 100,
    ) -> dict[str, Any]:
        """Verify audit log chain integrity.

        Args:
            sample_size: Number of entries to verify

        Returns:
            Integrity verification result
        """
        return await self._audit_repo.verify_chain_integrity(sample_size)
