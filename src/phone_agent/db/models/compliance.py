"""Compliance ORM Models for Phone Agent.

Persistent storage for audit logs and consent records.
Supports DSGVO/GDPR compliance requirements across all industry verticals.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Any
from uuid import UUID
import hashlib
import json

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum as SAEnum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from phone_agent.db.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from phone_agent.db.models.crm import ContactModel


# ============================================================================
# Audit Log Model
# ============================================================================

class AuditLogModel(Base, UUIDMixin):
    """Persistent audit log for compliance tracking.

    Immutable log entries for all auditable actions.
    Includes SHA256 checksum for tamper detection.

    Note: This model intentionally does NOT use TimestampMixin
    because audit logs should never be updated. The timestamp
    is set once at creation time.
    """

    __tablename__ = "audit_logs"

    # Timestamp (immutable - no updated_at)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )

    # Action classification
    action: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    action_category: Mapped[str] = mapped_column(
        String(32),
        nullable=True,
        index=True,
        doc="Category: data_access, data_modification, communication, consent, etc.",
    )

    # Actor information
    actor_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    actor_type: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        doc="Actor type: user, system, ai_agent, technician",
    )

    # Resource information
    resource_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    resource_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)

    # Related entities (optional, for quick filtering)
    contact_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("contacts.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Additional context
    details_json: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        doc="JSON-encoded additional details",
    )

    # Request context
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(512), nullable=True)
    session_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)

    # Industry context
    industry: Mapped[str | None] = mapped_column(
        String(32),
        nullable=True,
        index=True,
        doc="Industry vertical: gesundheit, handwerk, etc.",
    )

    # Integrity verification
    checksum: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        doc="SHA256 checksum for tamper detection",
    )
    previous_checksum: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
        doc="Checksum of previous log entry (chain integrity)",
    )

    # Indexes for common compliance queries
    __table_args__ = (
        Index("ix_audit_logs_contact_timestamp", "contact_id", "timestamp"),
        Index("ix_audit_logs_action_timestamp", "action", "timestamp"),
        Index("ix_audit_logs_resource_timestamp", "resource_type", "resource_id", "timestamp"),
        Index("ix_audit_logs_industry_timestamp", "industry", "timestamp"),
    )

    # Relationships
    contact: Mapped["ContactModel | None"] = relationship(
        "ContactModel",
        back_populates="audit_logs",
        lazy="selectin",
    )

    def __repr__(self) -> str:
        return f"<AuditLog {self.action} by {self.actor_id} at {self.timestamp}>"

    @property
    def details(self) -> dict[str, Any]:
        """Get details as dictionary."""
        if self.details_json:
            return json.loads(self.details_json)
        return {}

    @details.setter
    def details(self, value: dict[str, Any]) -> None:
        """Set details from dictionary."""
        self.details_json = json.dumps(value, ensure_ascii=False) if value else None

    def calculate_checksum(self, previous_checksum: str | None = None) -> str:
        """Calculate SHA256 checksum for integrity verification.

        Includes key fields in checksum to detect tampering.
        Optionally chains to previous entry's checksum.
        """
        # Normalize timestamp to naive UTC for consistent checksum
        # This ensures checksum is stable regardless of timezone handling
        if self.timestamp:
            ts = self.timestamp
            if ts.tzinfo is not None:
                # Convert to UTC and strip timezone for consistent format
                ts = ts.replace(tzinfo=None)
            timestamp_str = ts.isoformat()
        else:
            timestamp_str = ""

        data_parts = [
            str(self.id),
            timestamp_str,
            self.action,
            self.actor_id,
            self.resource_type,
            self.resource_id or "",
            str(self.contact_id) if self.contact_id else "",
            self.details_json or "",
            previous_checksum or "",
        ]
        data = "|".join(data_parts)
        return hashlib.sha256(data.encode()).hexdigest()

    def verify_checksum(self) -> bool:
        """Verify that the stored checksum matches calculated checksum."""
        expected = self.calculate_checksum(self.previous_checksum)
        return self.checksum == expected

    @classmethod
    def create(
        cls,
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
        previous_checksum: str | None = None,
    ) -> "AuditLogModel":
        """Create a new audit log entry with automatic checksum.

        Factory method that ensures checksum is always calculated.
        """
        from uuid import uuid4

        entry = cls(
            id=uuid4(),
            timestamp=datetime.now(timezone.utc),
            action=action,
            actor_id=actor_id,
            actor_type=actor_type,
            resource_type=resource_type,
            resource_id=resource_id,
            contact_id=contact_id,
            ip_address=ip_address,
            user_agent=user_agent,
            session_id=session_id,
            industry=industry,
            previous_checksum=previous_checksum,
        )

        # Set details via property
        if details:
            entry.details = details

        # Determine action category
        action_lower = action.lower()
        if action_lower.startswith("data_"):
            entry.action_category = "data_access" if "view" in action_lower or "search" in action_lower else "data_modification"
        elif action_lower.startswith("call_"):
            entry.action_category = "communication"
        elif action_lower.startswith("consent_"):
            entry.action_category = "consent"
        elif action_lower.startswith("appointment_") or action_lower.startswith("service_call_"):
            entry.action_category = "scheduling"
        else:
            entry.action_category = "system"

        # Calculate checksum
        entry.checksum = entry.calculate_checksum(previous_checksum)

        return entry

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for API responses."""
        return {
            "id": str(self.id),
            "timestamp": self.timestamp.isoformat(),
            "action": self.action,
            "action_category": self.action_category,
            "actor_id": self.actor_id,
            "actor_type": self.actor_type,
            "resource_type": self.resource_type,
            "resource_id": self.resource_id,
            "contact_id": str(self.contact_id) if self.contact_id else None,
            "details": self.details,
            "ip_address": self.ip_address,
            "session_id": self.session_id,
            "industry": self.industry,
            "checksum": self.checksum,
            "checksum_valid": self.verify_checksum(),
        }


# ============================================================================
# Consent Model
# ============================================================================

class ConsentModel(Base, UUIDMixin, TimestampMixin):
    """Persistent consent records for DSGVO/GDPR compliance.

    Tracks all consent grants, denials, and withdrawals.
    Supports industry-specific consent types.
    """

    __tablename__ = "consents"

    # Contact reference
    contact_id: Mapped[UUID] = mapped_column(
        ForeignKey("contacts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Consent classification
    consent_type: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        index=True,
        doc="Type of consent: phone_contact, sms_contact, ai_processing, etc.",
    )

    status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default="pending",
        index=True,
        doc="Status: granted, denied, withdrawn, expired, pending",
    )

    # Timestamps
    granted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        index=True,
    )
    withdrawn_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # Context
    granted_by: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
        doc="How consent was obtained: phone_agent, web_form, in_person, paper",
    )
    version: Mapped[str] = mapped_column(
        String(16),
        default="1.0",
        nullable=False,
        doc="Version of consent form used",
    )

    # Industry context
    industry: Mapped[str | None] = mapped_column(
        String(32),
        nullable=True,
        index=True,
        doc="Industry vertical: gesundheit, handwerk, etc.",
    )

    # Additional reference (e.g., job_id for photo consent)
    reference_id: Mapped[UUID | None] = mapped_column(
        nullable=True,
        doc="Optional reference to related entity (e.g., job for photo consent)",
    )
    reference_type: Mapped[str | None] = mapped_column(
        String(32),
        nullable=True,
        doc="Type of reference: job, appointment, etc.",
    )

    # Notes
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Legal text version used
    legal_text_hash: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
        doc="Hash of consent text shown to user",
    )

    # Indexes for common queries
    __table_args__ = (
        Index("ix_consents_contact_type", "contact_id", "consent_type"),
        Index("ix_consents_contact_status", "contact_id", "status"),
        Index("ix_consents_expiry", "expires_at", "status"),
    )

    # Relationships
    contact: Mapped["ContactModel"] = relationship(
        "ContactModel",
        back_populates="consents",
        lazy="selectin",
    )

    def __repr__(self) -> str:
        return f"<Consent {self.consent_type} ({self.status}) for contact {self.contact_id}>"

    def is_valid(self) -> bool:
        """Check if consent is currently valid."""
        if self.status != "granted":
            return False

        if self.expires_at and datetime.now(timezone.utc) > self.expires_at.replace(tzinfo=None):
            return False

        return True

    def grant(
        self,
        granted_by: str = "phone_agent",
        duration_days: int | None = None,
        version: str = "1.0",
        legal_text: str | None = None,
        notes: str | None = None,
    ) -> None:
        """Grant consent."""
        self.status = "granted"
        self.granted_at = datetime.now(timezone.utc)
        self.granted_by = granted_by
        self.version = version
        self.notes = notes
        self.withdrawn_at = None

        if duration_days:
            self.expires_at = datetime.now(timezone.utc) + timedelta(days=duration_days)

        if legal_text:
            self.legal_text_hash = hashlib.sha256(legal_text.encode()).hexdigest()[:32]

    def withdraw(self, notes: str | None = None) -> None:
        """Withdraw consent."""
        self.status = "withdrawn"
        self.withdrawn_at = datetime.now(timezone.utc)
        if notes:
            self.notes = notes

    def deny(self, notes: str | None = None) -> None:
        """Deny consent."""
        self.status = "denied"
        if notes:
            self.notes = notes

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for API responses."""
        return {
            "id": str(self.id),
            "contact_id": str(self.contact_id),
            "consent_type": self.consent_type,
            "status": self.status,
            "is_valid": self.is_valid(),
            "granted_at": self.granted_at.isoformat() if self.granted_at else None,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "withdrawn_at": self.withdrawn_at.isoformat() if self.withdrawn_at else None,
            "granted_by": self.granted_by,
            "version": self.version,
            "industry": self.industry,
            "reference_id": str(self.reference_id) if self.reference_id else None,
            "reference_type": self.reference_type,
            "notes": self.notes,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


# ============================================================================
# Data Retention Policy Model
# ============================================================================

class DataRetentionPolicyModel(Base, UUIDMixin, TimestampMixin):
    """Configurable data retention policies.

    Allows per-tenant and per-industry customization of retention periods.
    """

    __tablename__ = "data_retention_policies"

    # Policy identification
    resource_type: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        index=True,
        doc="Resource type: call_recordings, medical_records, invoices, etc.",
    )

    industry: Mapped[str | None] = mapped_column(
        String(32),
        nullable=True,
        index=True,
        doc="Industry-specific policy override",
    )

    tenant_id: Mapped[UUID | None] = mapped_column(
        nullable=True,
        index=True,
        doc="Tenant-specific policy override",
    )

    # Retention configuration
    retention_days: Mapped[int] = mapped_column(Integer, nullable=False)
    archive_after_days: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Legal basis
    legal_basis: Mapped[str | None] = mapped_column(
        String(256),
        nullable=True,
        doc="Legal reference: § 257 HGB, Art. 6 DSGVO, etc.",
    )
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Policy status
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Priority for policy resolution
    priority: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
        doc="Higher priority overrides lower. Tenant > Industry > Default",
    )

    __table_args__ = (
        Index("ix_retention_resource_industry", "resource_type", "industry"),
        Index("ix_retention_resource_tenant", "resource_type", "tenant_id"),
    )

    def __repr__(self) -> str:
        context = self.industry or (f"tenant:{self.tenant_id}" if self.tenant_id else "default")
        return f"<RetentionPolicy {self.resource_type} ({context}): {self.retention_days} days>"

    def is_expired(self, created_at: datetime) -> bool:
        """Check if data created at given time has exceeded retention period."""
        expiry = created_at + timedelta(days=self.retention_days)
        return datetime.now(timezone.utc) > expiry

    def should_archive(self, created_at: datetime) -> bool:
        """Check if data should be archived (but not deleted)."""
        if not self.archive_after_days:
            return False
        archive_date = created_at + timedelta(days=self.archive_after_days)
        return datetime.now(timezone.utc) > archive_date

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for API responses."""
        return {
            "id": str(self.id),
            "resource_type": self.resource_type,
            "industry": self.industry,
            "tenant_id": str(self.tenant_id) if self.tenant_id else None,
            "retention_days": self.retention_days,
            "archive_after_days": self.archive_after_days,
            "legal_basis": self.legal_basis,
            "description": self.description,
            "is_active": self.is_active,
            "priority": self.priority,
        }
