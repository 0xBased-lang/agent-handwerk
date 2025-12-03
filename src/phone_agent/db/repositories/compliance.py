"""Compliance Repositories for Phone Agent.

Specialized repositories for DSGVO compliance operations:
- Consent management
- Audit log queries

Extends BaseRepository with compliance-specific queries.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Sequence, Any
from uuid import UUID

from sqlalchemy import select, func, and_, or_, desc
from sqlalchemy.ext.asyncio import AsyncSession

from phone_agent.db.models.compliance import ConsentModel, AuditLogModel
from phone_agent.db.repositories.base import BaseRepository


class ConsentRepository(BaseRepository[ConsentModel]):
    """Repository for consent database operations.

    Provides specialized queries for DSGVO consent management.
    """

    def __init__(self, session: AsyncSession):
        """Initialize with session.

        Args:
            session: Async database session
        """
        super().__init__(ConsentModel, session)

    # ========================================================================
    # Consent Queries
    # ========================================================================

    async def get_by_contact(
        self,
        contact_id: UUID,
        *,
        skip: int = 0,
        limit: int = 100,
    ) -> Sequence[ConsentModel]:
        """Get all consent records for a contact.

        Args:
            contact_id: Contact UUID
            skip: Pagination offset
            limit: Maximum results

        Returns:
            List of consent records
        """
        stmt = (
            select(self._model)
            .where(self._model.contact_id == contact_id)
            .order_by(desc(self._model.created_at))
            .offset(skip)
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return result.scalars().all()

    async def get_by_contact_and_type(
        self,
        contact_id: UUID,
        consent_type: str,
    ) -> ConsentModel | None:
        """Get specific consent type for a contact.

        Args:
            contact_id: Contact UUID
            consent_type: Type of consent

        Returns:
            Consent record or None
        """
        stmt = select(self._model).where(
            and_(
                self._model.contact_id == contact_id,
                self._model.consent_type == consent_type,
            )
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_active_consents(
        self,
        contact_id: UUID,
    ) -> Sequence[ConsentModel]:
        """Get only valid (non-expired, non-withdrawn) consents.

        Args:
            contact_id: Contact UUID

        Returns:
            List of active consent records
        """
        now = datetime.now(timezone.utc)
        stmt = (
            select(self._model)
            .where(
                and_(
                    self._model.contact_id == contact_id,
                    self._model.status == "granted",
                    or_(
                        self._model.expires_at.is_(None),
                        self._model.expires_at > now,
                    ),
                )
            )
            .order_by(self._model.consent_type)
        )
        result = await self._session.execute(stmt)
        return result.scalars().all()

    async def check_consent(
        self,
        contact_id: UUID,
        consent_type: str,
    ) -> bool:
        """Check if contact has valid consent for a purpose.

        Args:
            contact_id: Contact UUID
            consent_type: Type of consent to check

        Returns:
            True if valid consent exists
        """
        now = datetime.now(timezone.utc)
        stmt = (
            select(func.count())
            .select_from(self._model)
            .where(
                and_(
                    self._model.contact_id == contact_id,
                    self._model.consent_type == consent_type,
                    self._model.status == "granted",
                    or_(
                        self._model.expires_at.is_(None),
                        self._model.expires_at > now,
                    ),
                )
            )
        )
        result = await self._session.execute(stmt)
        return (result.scalar() or 0) > 0

    async def revoke_consent(
        self,
        contact_id: UUID,
        consent_type: str,
        notes: str | None = None,
    ) -> ConsentModel | None:
        """Withdraw consent - set status to 'withdrawn'.

        Args:
            contact_id: Contact UUID
            consent_type: Type of consent to revoke
            notes: Optional notes about revocation

        Returns:
            Updated consent record or None if not found
        """
        consent = await self.get_by_contact_and_type(contact_id, consent_type)
        if consent is None:
            return None

        consent.withdraw(notes)
        await self._session.flush()
        await self._session.refresh(consent)
        return consent

    async def get_expiring_consents(
        self,
        days_ahead: int = 30,
    ) -> Sequence[ConsentModel]:
        """Get consents expiring within specified days.

        Args:
            days_ahead: Number of days to look ahead

        Returns:
            List of expiring consent records
        """
        now = datetime.now(timezone.utc)
        future = now + timedelta(days=days_ahead)

        stmt = (
            select(self._model)
            .where(
                and_(
                    self._model.status == "granted",
                    self._model.expires_at.is_not(None),
                    self._model.expires_at > now,
                    self._model.expires_at <= future,
                )
            )
            .order_by(self._model.expires_at)
        )
        result = await self._session.execute(stmt)
        return result.scalars().all()

    async def count_by_contact(self, contact_id: UUID) -> dict[str, int]:
        """Count consents by status for a contact.

        Args:
            contact_id: Contact UUID

        Returns:
            Dictionary of status counts
        """
        stmt = (
            select(self._model.status, func.count())
            .where(self._model.contact_id == contact_id)
            .group_by(self._model.status)
        )
        result = await self._session.execute(stmt)
        counts = {row[0]: row[1] for row in result.all()}
        return counts


class AuditLogRepository(BaseRepository[AuditLogModel]):
    """Repository for audit log database operations.

    Provides specialized queries for DSGVO audit trail management.
    Note: Audit logs are immutable - only create operations are supported.
    """

    def __init__(self, session: AsyncSession):
        """Initialize with session.

        Args:
            session: Async database session
        """
        super().__init__(AuditLogModel, session)

    # ========================================================================
    # Audit Log Queries
    # ========================================================================

    async def get_by_contact(
        self,
        contact_id: UUID,
        *,
        skip: int = 0,
        limit: int = 100,
    ) -> Sequence[AuditLogModel]:
        """Get audit entries for a contact.

        Args:
            contact_id: Contact UUID
            skip: Pagination offset
            limit: Maximum results

        Returns:
            List of audit entries
        """
        stmt = (
            select(self._model)
            .where(self._model.contact_id == contact_id)
            .order_by(desc(self._model.timestamp))
            .offset(skip)
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return result.scalars().all()

    async def get_by_date_range(
        self,
        start: datetime,
        end: datetime,
        *,
        actor_id: str | None = None,
        action: str | None = None,
        action_category: str | None = None,
        resource_type: str | None = None,
        contact_id: UUID | None = None,
        industry: str | None = None,
        skip: int = 0,
        limit: int = 1000,
    ) -> Sequence[AuditLogModel]:
        """Query audit log with filters.

        Args:
            start: Start datetime (inclusive)
            end: End datetime (inclusive)
            actor_id: Optional actor filter
            action: Optional action filter
            action_category: Optional category filter
            resource_type: Optional resource type filter
            contact_id: Optional contact filter
            industry: Optional industry filter
            skip: Pagination offset
            limit: Maximum results

        Returns:
            List of audit entries matching filters
        """
        conditions = [
            self._model.timestamp >= start,
            self._model.timestamp <= end,
        ]

        if actor_id:
            conditions.append(self._model.actor_id == actor_id)
        if action:
            conditions.append(self._model.action == action)
        if action_category:
            conditions.append(self._model.action_category == action_category)
        if resource_type:
            conditions.append(self._model.resource_type == resource_type)
        if contact_id:
            conditions.append(self._model.contact_id == contact_id)
        if industry:
            conditions.append(self._model.industry == industry)

        stmt = (
            select(self._model)
            .where(and_(*conditions))
            .order_by(desc(self._model.timestamp))
            .offset(skip)
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return result.scalars().all()

    async def get_by_resource(
        self,
        resource_type: str,
        resource_id: str | None = None,
        *,
        skip: int = 0,
        limit: int = 100,
    ) -> Sequence[AuditLogModel]:
        """Get audit entries for a specific resource.

        Args:
            resource_type: Type of resource
            resource_id: Optional specific resource ID
            skip: Pagination offset
            limit: Maximum results

        Returns:
            List of audit entries
        """
        conditions = [self._model.resource_type == resource_type]

        if resource_id:
            conditions.append(self._model.resource_id == resource_id)

        stmt = (
            select(self._model)
            .where(and_(*conditions))
            .order_by(desc(self._model.timestamp))
            .offset(skip)
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return result.scalars().all()

    async def get_last_checksum(self) -> str | None:
        """Get the checksum of the most recent entry for chain integrity.

        Returns:
            Checksum of most recent entry or None
        """
        stmt = (
            select(self._model.checksum)
            .order_by(desc(self._model.timestamp))
            .limit(1)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def create_with_chain(
        self,
        entry: AuditLogModel,
    ) -> AuditLogModel:
        """Create entry with automatic checksum chain linking.

        Gets the last checksum and sets previous_checksum before creation.
        Recalculates the entry's checksum with the chain link.

        Args:
            entry: Audit log entry to create

        Returns:
            Created audit log entry with chain link
        """
        # Get last checksum for chain
        last_checksum = await self.get_last_checksum()

        # Update entry with chain link
        entry.previous_checksum = last_checksum
        entry.checksum = entry.calculate_checksum(last_checksum)

        # Create entry
        return await self.create(entry)

    async def count_with_filters(
        self,
        start: datetime | None = None,
        end: datetime | None = None,
        actor_id: str | None = None,
        action: str | None = None,
        action_category: str | None = None,
        resource_type: str | None = None,
        contact_id: UUID | None = None,
        industry: str | None = None,
    ) -> int:
        """Count entries matching filters for pagination.

        Args:
            start: Optional start datetime
            end: Optional end datetime
            actor_id: Optional actor filter
            action: Optional action filter
            action_category: Optional category filter
            resource_type: Optional resource type filter
            contact_id: Optional contact filter
            industry: Optional industry filter

        Returns:
            Count of matching entries
        """
        conditions = []

        if start:
            conditions.append(self._model.timestamp >= start)
        if end:
            conditions.append(self._model.timestamp <= end)
        if actor_id:
            conditions.append(self._model.actor_id == actor_id)
        if action:
            conditions.append(self._model.action == action)
        if action_category:
            conditions.append(self._model.action_category == action_category)
        if resource_type:
            conditions.append(self._model.resource_type == resource_type)
        if contact_id:
            conditions.append(self._model.contact_id == contact_id)
        if industry:
            conditions.append(self._model.industry == industry)

        stmt = select(func.count()).select_from(self._model)
        if conditions:
            stmt = stmt.where(and_(*conditions))

        result = await self._session.execute(stmt)
        return result.scalar() or 0

    async def verify_chain_integrity(
        self,
        sample_size: int = 100,
    ) -> dict[str, Any]:
        """Verify audit log chain integrity.

        Checks checksum chain for tamper detection.

        Args:
            sample_size: Number of recent entries to verify

        Returns:
            Integrity verification result
        """
        # Get recent entries
        stmt = (
            select(self._model)
            .order_by(desc(self._model.timestamp))
            .limit(sample_size)
        )
        result = await self._session.execute(stmt)
        entries = list(result.scalars().all())

        if not entries:
            return {
                "verified": True,
                "total_checked": 0,
                "valid_count": 0,
                "invalid_count": 0,
                "broken_chains": [],
            }

        # Verify each entry
        valid_count = 0
        invalid_entries = []
        broken_chains = []

        # Entries are in reverse chronological order
        for i, entry in enumerate(entries):
            if entry.verify_checksum():
                valid_count += 1
            else:
                invalid_entries.append(str(entry.id))

            # Check chain link (if not the oldest in sample)
            if i < len(entries) - 1:
                next_entry = entries[i + 1]  # Older entry
                if entry.previous_checksum != next_entry.checksum:
                    broken_chains.append({
                        "entry_id": str(entry.id),
                        "expected_prev": next_entry.checksum,
                        "actual_prev": entry.previous_checksum,
                    })

        return {
            "verified": len(invalid_entries) == 0 and len(broken_chains) == 0,
            "total_checked": len(entries),
            "valid_count": valid_count,
            "invalid_count": len(invalid_entries),
            "invalid_entries": invalid_entries,
            "broken_chains": broken_chains,
        }

    async def export_for_contact(
        self,
        contact_id: UUID,
    ) -> list[dict[str, Any]]:
        """Export all audit entries for a contact (DSGVO data portability).

        Args:
            contact_id: Contact UUID

        Returns:
            List of audit entries as dictionaries
        """
        entries = await self.get_by_contact(contact_id, limit=10000)
        return [entry.to_dict() for entry in entries]
