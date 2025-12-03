"""Contact Repository for Phone Agent.

Specialized repository for CRM contact operations.
Extends BaseRepository with contact-specific queries.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Sequence, Any
from uuid import UUID

from sqlalchemy import select, func, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from phone_agent.db.models.crm import ContactModel, CompanyModel
from phone_agent.db.repositories.base import BaseRepository


class ContactRepository(BaseRepository[ContactModel]):
    """Repository for contact database operations.

    Provides specialized queries for contact management,
    search, and CRM analytics.
    """

    def __init__(self, session: AsyncSession):
        """Initialize with session.

        Args:
            session: Async database session
        """
        super().__init__(ContactModel, session)

    # ========================================================================
    # Search Operations
    # ========================================================================

    async def search_by_name(
        self,
        query: str,
        *,
        industry: str | None = None,
        skip: int = 0,
        limit: int = 50,
    ) -> Sequence[ContactModel]:
        """Search contacts by name (first or last).

        Args:
            query: Search string
            industry: Optional industry filter
            skip: Pagination offset
            limit: Maximum results

        Returns:
            List of matching contacts
        """
        search_pattern = f"%{query}%"
        conditions = [
            or_(
                self._model.first_name.ilike(search_pattern),
                self._model.last_name.ilike(search_pattern),
            ),
            self._model.is_deleted == False,
        ]

        if industry:
            conditions.append(self._model.industry == industry)

        stmt = (
            select(self._model)
            .where(and_(*conditions))
            .order_by(self._model.last_name, self._model.first_name)
            .offset(skip)
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return result.scalars().all()

    async def search_by_phone(
        self,
        phone: str,
        *,
        industry: str | None = None,
    ) -> Sequence[ContactModel]:
        """Search contacts by phone number.

        Searches primary, secondary, and mobile phone fields.

        Args:
            phone: Phone number (partial or full)
            industry: Optional industry filter

        Returns:
            List of matching contacts
        """
        # Normalize phone for search (remove common separators)
        normalized = phone.replace(" ", "").replace("-", "").replace("/", "")
        search_pattern = f"%{normalized}%"

        conditions = [
            or_(
                self._model.phone_primary.like(search_pattern),
                self._model.phone_secondary.like(search_pattern),
                self._model.phone_mobile.like(search_pattern),
            ),
            self._model.is_deleted == False,
        ]

        if industry:
            conditions.append(self._model.industry == industry)

        stmt = select(self._model).where(and_(*conditions))
        result = await self._session.execute(stmt)
        return result.scalars().all()

    async def find_by_phone(
        self,
        phone: str,
        industry: str | None = None,
    ) -> ContactModel | None:
        """Find exact contact by primary phone number.

        Args:
            phone: Phone number
            industry: Optional industry filter

        Returns:
            Contact or None
        """
        conditions = [
            self._model.phone_primary == phone,
            self._model.is_deleted == False,
        ]

        if industry:
            conditions.append(self._model.industry == industry)

        stmt = select(self._model).where(and_(*conditions))
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def find_by_email(
        self,
        email: str,
        industry: str | None = None,
    ) -> ContactModel | None:
        """Find contact by email address.

        Args:
            email: Email address
            industry: Optional industry filter

        Returns:
            Contact or None
        """
        conditions = [
            self._model.email == email,
            self._model.is_deleted == False,
        ]

        if industry:
            conditions.append(self._model.industry == industry)

        stmt = select(self._model).where(and_(*conditions))
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def search_full_text(
        self,
        query: str,
        *,
        industry: str | None = None,
        skip: int = 0,
        limit: int = 50,
    ) -> Sequence[ContactModel]:
        """Full-text search across multiple fields.

        Searches name, email, phone, address, and notes.

        Args:
            query: Search string
            industry: Optional industry filter
            skip: Pagination offset
            limit: Maximum results

        Returns:
            List of matching contacts
        """
        search_pattern = f"%{query}%"
        conditions = [
            or_(
                self._model.first_name.ilike(search_pattern),
                self._model.last_name.ilike(search_pattern),
                self._model.email.ilike(search_pattern),
                self._model.phone_primary.like(search_pattern),
                self._model.phone_mobile.like(search_pattern),
                self._model.city.ilike(search_pattern),
                self._model.notes.ilike(search_pattern),
            ),
            self._model.is_deleted == False,
        ]

        if industry:
            conditions.append(self._model.industry == industry)

        stmt = (
            select(self._model)
            .where(and_(*conditions))
            .order_by(self._model.last_contact_at.desc().nullslast())
            .offset(skip)
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return result.scalars().all()

    # ========================================================================
    # Type/Classification Queries
    # ========================================================================

    async def get_by_type(
        self,
        contact_type: str,
        *,
        industry: str | None = None,
        skip: int = 0,
        limit: int = 100,
    ) -> Sequence[ContactModel]:
        """Get contacts by type.

        Args:
            contact_type: Contact type (patient, customer, lead, prospect)
            industry: Optional industry filter
            skip: Pagination offset
            limit: Maximum results

        Returns:
            List of contacts of given type
        """
        conditions = [
            self._model.contact_type == contact_type,
            self._model.is_deleted == False,
        ]

        if industry:
            conditions.append(self._model.industry == industry)

        stmt = (
            select(self._model)
            .where(and_(*conditions))
            .order_by(self._model.last_name, self._model.first_name)
            .offset(skip)
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return result.scalars().all()

    async def get_by_industry(
        self,
        industry: str,
        *,
        skip: int = 0,
        limit: int = 100,
    ) -> Sequence[ContactModel]:
        """Get contacts by industry.

        Args:
            industry: Industry vertical
            skip: Pagination offset
            limit: Maximum results

        Returns:
            List of contacts in industry
        """
        stmt = (
            select(self._model)
            .where(
                and_(
                    self._model.industry == industry,
                    self._model.is_deleted == False,
                )
            )
            .order_by(self._model.last_name, self._model.first_name)
            .offset(skip)
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return result.scalars().all()

    async def get_leads(
        self,
        industry: str | None = None,
        *,
        skip: int = 0,
        limit: int = 100,
    ) -> Sequence[ContactModel]:
        """Get all leads and prospects.

        Args:
            industry: Optional industry filter
            skip: Pagination offset
            limit: Maximum results

        Returns:
            List of lead contacts
        """
        conditions = [
            self._model.contact_type.in_(["lead", "prospect"]),
            self._model.is_deleted == False,
        ]

        if industry:
            conditions.append(self._model.industry == industry)

        stmt = (
            select(self._model)
            .where(and_(*conditions))
            .order_by(self._model.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return result.scalars().all()

    # ========================================================================
    # Engagement Queries
    # ========================================================================

    async def get_recent_contacts(
        self,
        days: int = 7,
        *,
        industry: str | None = None,
        limit: int = 50,
    ) -> Sequence[ContactModel]:
        """Get contacts with recent activity.

        Args:
            days: Number of days to look back
            industry: Optional industry filter
            limit: Maximum results

        Returns:
            List of recently active contacts
        """
        cutoff = datetime.utcnow() - timedelta(days=days)
        conditions = [
            self._model.last_contact_at >= cutoff,
            self._model.is_deleted == False,
        ]

        if industry:
            conditions.append(self._model.industry == industry)

        stmt = (
            select(self._model)
            .where(and_(*conditions))
            .order_by(self._model.last_contact_at.desc())
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return result.scalars().all()

    async def get_inactive_contacts(
        self,
        days: int = 90,
        *,
        industry: str | None = None,
        skip: int = 0,
        limit: int = 100,
    ) -> Sequence[ContactModel]:
        """Get contacts without recent activity.

        Args:
            days: Number of days for inactivity threshold
            industry: Optional industry filter
            skip: Pagination offset
            limit: Maximum results

        Returns:
            List of inactive contacts
        """
        cutoff = datetime.utcnow() - timedelta(days=days)
        conditions = [
            or_(
                self._model.last_contact_at < cutoff,
                self._model.last_contact_at.is_(None),
            ),
            self._model.is_deleted == False,
        ]

        if industry:
            conditions.append(self._model.industry == industry)

        stmt = (
            select(self._model)
            .where(and_(*conditions))
            .order_by(self._model.last_contact_at.asc().nullsfirst())
            .offset(skip)
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return result.scalars().all()

    async def get_new_contacts(
        self,
        days: int = 7,
        *,
        industry: str | None = None,
        limit: int = 50,
    ) -> Sequence[ContactModel]:
        """Get recently created contacts.

        Args:
            days: Number of days to look back
            industry: Optional industry filter
            limit: Maximum results

        Returns:
            List of new contacts
        """
        cutoff = datetime.utcnow() - timedelta(days=days)
        conditions = [
            self._model.created_at >= cutoff,
            self._model.is_deleted == False,
        ]

        if industry:
            conditions.append(self._model.industry == industry)

        stmt = (
            select(self._model)
            .where(and_(*conditions))
            .order_by(self._model.created_at.desc())
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return result.scalars().all()

    # ========================================================================
    # Healthcare-specific Queries
    # ========================================================================

    async def get_patients_due_for_recall(
        self,
        days_since_last_appointment: int = 180,
        *,
        limit: int = 100,
    ) -> Sequence[ContactModel]:
        """Get patients due for recall (healthcare).

        Args:
            days_since_last_appointment: Days threshold
            limit: Maximum results

        Returns:
            List of patients due for recall
        """
        cutoff = datetime.utcnow() - timedelta(days=days_since_last_appointment)
        stmt = (
            select(self._model)
            .where(
                and_(
                    self._model.industry == "gesundheit",
                    self._model.contact_type == "patient",
                    self._model.last_appointment_at < cutoff,
                    self._model.is_deleted == False,
                )
            )
            .order_by(self._model.last_appointment_at.asc())
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return result.scalars().all()

    async def get_patients_by_insurance(
        self,
        insurance_type: str,
        *,
        skip: int = 0,
        limit: int = 100,
    ) -> Sequence[ContactModel]:
        """Get patients by insurance type.

        Args:
            insurance_type: Insurance type (GKV, PKV, etc.)
            skip: Pagination offset
            limit: Maximum results

        Returns:
            List of patients with insurance type
        """
        stmt = (
            select(self._model)
            .where(
                and_(
                    self._model.industry == "gesundheit",
                    self._model.insurance_type == insurance_type,
                    self._model.is_deleted == False,
                )
            )
            .order_by(self._model.last_name, self._model.first_name)
            .offset(skip)
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return result.scalars().all()

    # ========================================================================
    # Analytics
    # ========================================================================

    async def count_by_type(self, industry: str | None = None) -> dict[str, int]:
        """Count contacts grouped by type.

        Args:
            industry: Optional industry filter

        Returns:
            Dictionary of type -> count
        """
        stmt = (
            select(self._model.contact_type, func.count().label("count"))
            .where(self._model.is_deleted == False)
            .group_by(self._model.contact_type)
        )

        if industry:
            stmt = stmt.where(self._model.industry == industry)

        result = await self._session.execute(stmt)
        return {row[0]: row[1] for row in result.all()}

    async def count_by_industry(self) -> dict[str, int]:
        """Count contacts grouped by industry.

        Returns:
            Dictionary of industry -> count
        """
        stmt = (
            select(self._model.industry, func.count().label("count"))
            .where(self._model.is_deleted == False)
            .group_by(self._model.industry)
        )
        result = await self._session.execute(stmt)
        return {row[0]: row[1] for row in result.all()}

    async def get_statistics(self, industry: str | None = None) -> dict[str, Any]:
        """Get contact statistics summary.

        Args:
            industry: Optional industry filter

        Returns:
            Dictionary with contact statistics
        """
        conditions = [self._model.is_deleted == False]
        if industry:
            conditions.append(self._model.industry == industry)

        # Total count
        total_stmt = select(func.count()).select_from(self._model).where(and_(*conditions))
        total_result = await self._session.execute(total_stmt)
        total = total_result.scalar() or 0

        # New this week
        week_ago = datetime.utcnow() - timedelta(days=7)
        new_conditions = conditions + [self._model.created_at >= week_ago]
        new_stmt = select(func.count()).select_from(self._model).where(and_(*new_conditions))
        new_result = await self._session.execute(new_stmt)
        new_this_week = new_result.scalar() or 0

        # Active (contacted in last 30 days)
        month_ago = datetime.utcnow() - timedelta(days=30)
        active_conditions = conditions + [self._model.last_contact_at >= month_ago]
        active_stmt = select(func.count()).select_from(self._model).where(and_(*active_conditions))
        active_result = await self._session.execute(active_stmt)
        active = active_result.scalar() or 0

        return {
            "total_contacts": total,
            "new_this_week": new_this_week,
            "active_30_days": active,
            "by_type": await self.count_by_type(industry),
        }

    # ========================================================================
    # Contact Interaction Timeline
    # ========================================================================

    async def get_with_timeline(
        self,
        contact_id: UUID,
    ) -> ContactModel | None:
        """Get contact with related calls and appointments.

        Args:
            contact_id: Contact UUID

        Returns:
            Contact with eager-loaded relationships
        """
        stmt = (
            select(self._model)
            .where(self._model.id == contact_id)
            .options(
                selectinload(self._model.calls),
                selectinload(self._model.appointments),
                selectinload(self._model.consents),
            )
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    # ========================================================================
    # Update Helpers
    # ========================================================================

    async def record_contact(self, contact_id: UUID) -> ContactModel | None:
        """Record a contact interaction.

        Updates last_contact_at and total_calls counter.

        Args:
            contact_id: Contact UUID

        Returns:
            Updated contact or None
        """
        contact = await self.get(contact_id)
        if contact is None:
            return None

        contact.last_contact_at = datetime.utcnow()
        contact.total_calls += 1

        if contact.first_contact_at is None:
            contact.first_contact_at = datetime.utcnow()

        await self._session.flush()
        return contact

    async def record_appointment(self, contact_id: UUID) -> ContactModel | None:
        """Record an appointment booking.

        Updates appointment counters.

        Args:
            contact_id: Contact UUID

        Returns:
            Updated contact or None
        """
        contact = await self.get(contact_id)
        if contact is None:
            return None

        contact.total_appointments += 1
        contact.last_appointment_at = datetime.utcnow()

        await self._session.flush()
        return contact

    async def record_no_show(self, contact_id: UUID) -> ContactModel | None:
        """Record a no-show for a contact.

        Args:
            contact_id: Contact UUID

        Returns:
            Updated contact or None
        """
        contact = await self.get(contact_id)
        if contact is None:
            return None

        contact.total_no_shows += 1

        await self._session.flush()
        return contact


class CompanyRepository(BaseRepository[CompanyModel]):
    """Repository for company database operations."""

    def __init__(self, session: AsyncSession):
        """Initialize with session.

        Args:
            session: Async database session
        """
        super().__init__(CompanyModel, session)

    async def search_by_name(
        self,
        query: str,
        *,
        skip: int = 0,
        limit: int = 50,
    ) -> Sequence[CompanyModel]:
        """Search companies by name.

        Args:
            query: Search string
            skip: Pagination offset
            limit: Maximum results

        Returns:
            List of matching companies
        """
        search_pattern = f"%{query}%"
        stmt = (
            select(self._model)
            .where(
                and_(
                    or_(
                        self._model.name.ilike(search_pattern),
                        self._model.legal_name.ilike(search_pattern),
                    ),
                    self._model.is_deleted == False,
                )
            )
            .order_by(self._model.name)
            .offset(skip)
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return result.scalars().all()

    async def find_by_tax_id(self, tax_id: str) -> CompanyModel | None:
        """Find company by tax ID.

        Args:
            tax_id: Tax identification number

        Returns:
            Company or None
        """
        stmt = select(self._model).where(
            and_(
                self._model.tax_id == tax_id,
                self._model.is_deleted == False,
            )
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_with_contacts(self, company_id: UUID) -> CompanyModel | None:
        """Get company with all contacts.

        Args:
            company_id: Company UUID

        Returns:
            Company with eager-loaded contacts
        """
        stmt = (
            select(self._model)
            .where(self._model.id == company_id)
            .options(selectinload(self._model.contacts))
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()
