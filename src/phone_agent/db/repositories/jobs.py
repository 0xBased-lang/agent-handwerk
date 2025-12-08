"""Job Repository for Handwerk jobs.

Specialized repository for Handwerk job operations.
Extends BaseRepository with job-specific queries.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Sequence, Any
from uuid import UUID

from sqlalchemy import select, func, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from phone_agent.db.models.handwerk import JobModel, JobStatus, JobUrgency
from phone_agent.db.repositories.base import BaseRepository


class JobRepository(BaseRepository[JobModel]):
    """Repository for job database operations.

    Provides specialized queries for job management,
    scheduling, and analytics.
    """

    def __init__(self, session: AsyncSession):
        """Initialize with session.

        Args:
            session: Async database session
        """
        super().__init__(JobModel, session)

    # ========================================================================
    # Search Operations
    # ========================================================================

    async def get_by_number(self, job_number: str) -> JobModel | None:
        """Get job by job number.

        Args:
            job_number: Job number (e.g., JOB-2024-0001)

        Returns:
            JobModel or None if not found
        """
        stmt = select(self._model).where(self._model.job_number == job_number)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def search_by_customer(
        self,
        contact_id: UUID,
        *,
        status: str | None = None,
        skip: int = 0,
        limit: int = 50,
    ) -> Sequence[JobModel]:
        """Get jobs for a specific customer.

        Args:
            contact_id: Customer contact ID
            status: Optional status filter
            skip: Pagination offset
            limit: Maximum results

        Returns:
            List of matching jobs
        """
        conditions = [
            self._model.contact_id == contact_id,
            self._model.is_deleted == False,
        ]

        if status:
            conditions.append(self._model.status == status)

        stmt = (
            select(self._model)
            .where(and_(*conditions))
            .order_by(self._model.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return result.scalars().all()

    async def search_by_technician(
        self,
        technician_id: UUID,
        *,
        status: str | None = None,
        scheduled_date: date | None = None,
        skip: int = 0,
        limit: int = 50,
    ) -> Sequence[JobModel]:
        """Get jobs assigned to a specific technician.

        Args:
            technician_id: Technician contact ID
            status: Optional status filter
            scheduled_date: Optional date filter
            skip: Pagination offset
            limit: Maximum results

        Returns:
            List of matching jobs
        """
        conditions = [
            self._model.technician_id == technician_id,
            self._model.is_deleted == False,
        ]

        if status:
            conditions.append(self._model.status == status)
        if scheduled_date:
            conditions.append(self._model.scheduled_date == scheduled_date)

        stmt = (
            select(self._model)
            .where(and_(*conditions))
            .order_by(self._model.scheduled_date, self._model.scheduled_time)
            .offset(skip)
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return result.scalars().all()

    async def get_by_status(
        self,
        status: str,
        *,
        trade_category: str | None = None,
        urgency: str | None = None,
        skip: int = 0,
        limit: int = 100,
    ) -> Sequence[JobModel]:
        """Get jobs by status.

        Args:
            status: Job status (requested, scheduled, completed, etc.)
            trade_category: Optional trade filter
            urgency: Optional urgency filter
            skip: Pagination offset
            limit: Maximum results

        Returns:
            List of matching jobs
        """
        conditions = [
            self._model.status == status,
            self._model.is_deleted == False,
        ]

        if trade_category:
            conditions.append(self._model.trade_category == trade_category)
        if urgency:
            conditions.append(self._model.urgency == urgency)

        stmt = (
            select(self._model)
            .where(and_(*conditions))
            .order_by(self._model.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return result.scalars().all()

    async def get_scheduled_jobs(
        self,
        start_date: date,
        end_date: date,
        *,
        technician_id: UUID | None = None,
    ) -> Sequence[JobModel]:
        """Get jobs scheduled within a date range.

        Args:
            start_date: Start of date range
            end_date: End of date range
            technician_id: Optional technician filter

        Returns:
            List of scheduled jobs
        """
        conditions = [
            self._model.scheduled_date.between(start_date, end_date),
            self._model.is_deleted == False,
        ]

        if technician_id:
            conditions.append(self._model.technician_id == technician_id)

        stmt = (
            select(self._model)
            .where(and_(*conditions))
            .order_by(self._model.scheduled_date, self._model.scheduled_time)
        )
        result = await self._session.execute(stmt)
        return result.scalars().all()

    async def get_urgent_jobs(
        self,
        *,
        trade_category: str | None = None,
    ) -> Sequence[JobModel]:
        """Get urgent and emergency jobs (notfall, dringend).

        Args:
            trade_category: Optional trade filter

        Returns:
            List of urgent jobs
        """
        conditions = [
            self._model.urgency.in_([JobUrgency.NOTFALL, JobUrgency.DRINGEND]),
            self._model.status.in_([JobStatus.REQUESTED, JobStatus.ACCEPTED]),
            self._model.is_deleted == False,
        ]

        if trade_category:
            conditions.append(self._model.trade_category == trade_category)

        stmt = (
            select(self._model)
            .where(and_(*conditions))
            .order_by(
                # Notfall first, then by creation time
                self._model.urgency.desc(),
                self._model.created_at,
            )
        )
        result = await self._session.execute(stmt)
        return result.scalars().all()

    # ========================================================================
    # Analytics Operations
    # ========================================================================

    async def count_by_status(self, status: str) -> int:
        """Count jobs with specific status.

        Args:
            status: Job status

        Returns:
            Count of jobs
        """
        stmt = (
            select(func.count())
            .select_from(self._model)
            .where(
                and_(
                    self._model.status == status,
                    self._model.is_deleted == False,
                )
            )
        )
        result = await self._session.execute(stmt)
        return result.scalar() or 0

    async def count_by_trade(self, trade_category: str) -> int:
        """Count jobs for specific trade category.

        Args:
            trade_category: Trade category

        Returns:
            Count of jobs
        """
        stmt = (
            select(func.count())
            .select_from(self._model)
            .where(
                and_(
                    self._model.trade_category == trade_category,
                    self._model.is_deleted == False,
                )
            )
        )
        result = await self._session.execute(stmt)
        return result.scalar() or 0

    async def get_revenue_stats(
        self,
        start_date: datetime,
        end_date: datetime,
    ) -> dict[str, Any]:
        """Get revenue statistics for date range.

        Args:
            start_date: Start of date range
            end_date: End of date range

        Returns:
            Dict with total revenue, job count, average cost
        """
        stmt = (
            select(
                func.sum(self._model.actual_cost),
                func.count(),
                func.avg(self._model.actual_cost),
            )
            .where(
                and_(
                    self._model.completed_at.between(start_date, end_date),
                    self._model.status == JobStatus.COMPLETED,
                    self._model.is_deleted == False,
                )
            )
        )
        result = await self._session.execute(stmt)
        row = result.one_or_none()

        if not row or not row[0]:
            return {
                "total_revenue": 0.0,
                "job_count": 0,
                "average_cost": 0.0,
            }

        return {
            "total_revenue": float(row[0] or 0),
            "job_count": int(row[1] or 0),
            "average_cost": float(row[2] or 0),
        }
