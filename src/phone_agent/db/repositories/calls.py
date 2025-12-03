"""Call Repository for Phone Agent.

Specialized repository for call-related database operations.
Extends BaseRepository with call-specific queries.
"""
from __future__ import annotations

from datetime import datetime, date, timedelta
from typing import Sequence, Any
from uuid import UUID

from sqlalchemy import select, func, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from phone_agent.db.models.core import CallModel
from phone_agent.db.repositories.base import BaseRepository


class CallRepository(BaseRepository[CallModel]):
    """Repository for call database operations.

    Provides specialized queries for call analytics,
    filtering by status, direction, and time ranges.
    """

    def __init__(self, session: AsyncSession):
        """Initialize with session.

        Args:
            session: Async database session
        """
        super().__init__(CallModel, session)

    # ========================================================================
    # Query by Status/Direction
    # ========================================================================

    async def get_by_status(
        self,
        status: str,
        *,
        skip: int = 0,
        limit: int = 100,
    ) -> Sequence[CallModel]:
        """Get calls by status.

        Args:
            status: Call status (ringing, in_progress, completed, etc.)
            skip: Pagination offset
            limit: Maximum results

        Returns:
            List of calls with given status
        """
        stmt = (
            select(self._model)
            .where(self._model.status == status)
            .order_by(self._model.started_at.desc())
            .offset(skip)
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return result.scalars().all()

    async def get_by_direction(
        self,
        direction: str,
        *,
        skip: int = 0,
        limit: int = 100,
    ) -> Sequence[CallModel]:
        """Get calls by direction.

        Args:
            direction: Call direction (inbound, outbound)
            skip: Pagination offset
            limit: Maximum results

        Returns:
            List of calls with given direction
        """
        stmt = (
            select(self._model)
            .where(self._model.direction == direction)
            .order_by(self._model.started_at.desc())
            .offset(skip)
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return result.scalars().all()

    async def get_active_calls(self) -> Sequence[CallModel]:
        """Get all currently active calls.

        Returns:
            List of calls in ringing or in_progress status
        """
        stmt = (
            select(self._model)
            .where(self._model.status.in_(["ringing", "in_progress"]))
            .order_by(self._model.started_at)
        )
        result = await self._session.execute(stmt)
        return result.scalars().all()

    async def get_by_phone_number(
        self,
        phone: str,
        *,
        skip: int = 0,
        limit: int = 50,
    ) -> Sequence[CallModel]:
        """Get calls involving a phone number (caller or callee).

        Args:
            phone: Phone number to search
            skip: Pagination offset
            limit: Maximum results

        Returns:
            List of calls involving the phone number
        """
        stmt = (
            select(self._model)
            .where(or_(self._model.caller_id == phone, self._model.callee_id == phone))
            .order_by(self._model.started_at.desc())
            .offset(skip)
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return result.scalars().all()

    # ========================================================================
    # Contact-based Queries
    # ========================================================================

    async def get_by_contact(
        self,
        contact_id: UUID,
        *,
        skip: int = 0,
        limit: int = 50,
    ) -> Sequence[CallModel]:
        """Get calls for a specific contact.

        Args:
            contact_id: Contact UUID
            skip: Pagination offset
            limit: Maximum results

        Returns:
            List of calls for the contact
        """
        # Contact_id is stored as string, convert for comparison
        contact_id_str = str(contact_id)
        stmt = (
            select(self._model)
            .where(self._model.contact_id == contact_id_str)
            .order_by(self._model.started_at.desc())
            .offset(skip)
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return result.scalars().all()

    async def get_recent_for_contact(
        self,
        contact_id: UUID,
        days: int = 30,
    ) -> Sequence[CallModel]:
        """Get recent calls for a contact.

        Args:
            contact_id: Contact UUID
            days: Number of days to look back

        Returns:
            List of recent calls
        """
        cutoff = datetime.utcnow() - timedelta(days=days)
        stmt = (
            select(self._model)
            .where(
                and_(
                    self._model.contact_id == contact_id,
                    self._model.started_at >= cutoff,
                )
            )
            .order_by(self._model.started_at.desc())
        )
        result = await self._session.execute(stmt)
        return result.scalars().all()

    # ========================================================================
    # Time-based Queries
    # ========================================================================

    async def get_by_date_range(
        self,
        start_date: date,
        end_date: date,
        *,
        industry: str | None = None,
        skip: int = 0,
        limit: int = 1000,
    ) -> Sequence[CallModel]:
        """Get calls within a date range.

        Args:
            start_date: Start date (inclusive)
            end_date: End date (inclusive)
            industry: Optional industry filter
            skip: Pagination offset
            limit: Maximum results

        Returns:
            List of calls in date range
        """
        start_datetime = datetime.combine(start_date, datetime.min.time())
        end_datetime = datetime.combine(end_date, datetime.max.time())

        conditions = [
            self._model.started_at >= start_datetime,
            self._model.started_at <= end_datetime,
        ]

        if industry:
            conditions.append(self._model.industry == industry)

        stmt = (
            select(self._model)
            .where(and_(*conditions))
            .order_by(self._model.started_at.desc())
            .offset(skip)
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return result.scalars().all()

    async def get_today(self, industry: str | None = None) -> Sequence[CallModel]:
        """Get all calls from today.

        Args:
            industry: Optional industry filter

        Returns:
            List of today's calls
        """
        today = date.today()
        return await self.get_by_date_range(today, today, industry=industry)

    async def get_this_week(self, industry: str | None = None) -> Sequence[CallModel]:
        """Get all calls from the current week.

        Args:
            industry: Optional industry filter

        Returns:
            List of this week's calls
        """
        today = date.today()
        start_of_week = today - timedelta(days=today.weekday())
        return await self.get_by_date_range(start_of_week, today, industry=industry)

    # ========================================================================
    # Analytics Queries
    # ========================================================================

    async def count_by_status(
        self,
        start_date: date | None = None,
        end_date: date | None = None,
        industry: str | None = None,
    ) -> dict[str, int]:
        """Count calls grouped by status.

        Args:
            start_date: Optional start date filter
            end_date: Optional end date filter
            industry: Optional industry filter

        Returns:
            Dictionary of status -> count
        """
        stmt = (
            select(self._model.status, func.count().label("count"))
            .group_by(self._model.status)
        )

        conditions = []
        if start_date:
            conditions.append(
                self._model.started_at >= datetime.combine(start_date, datetime.min.time())
            )
        if end_date:
            conditions.append(
                self._model.started_at <= datetime.combine(end_date, datetime.max.time())
            )
        if industry:
            conditions.append(self._model.industry == industry)

        if conditions:
            stmt = stmt.where(and_(*conditions))

        result = await self._session.execute(stmt)
        return {row[0]: row[1] for row in result.all()}

    async def count_by_direction(
        self,
        start_date: date | None = None,
        end_date: date | None = None,
        industry: str | None = None,
    ) -> dict[str, int]:
        """Count calls grouped by direction.

        Args:
            start_date: Optional start date filter
            end_date: Optional end date filter
            industry: Optional industry filter

        Returns:
            Dictionary of direction -> count
        """
        stmt = (
            select(self._model.direction, func.count().label("count"))
            .group_by(self._model.direction)
        )

        conditions = []
        if start_date:
            conditions.append(
                self._model.started_at >= datetime.combine(start_date, datetime.min.time())
            )
        if end_date:
            conditions.append(
                self._model.started_at <= datetime.combine(end_date, datetime.max.time())
            )
        if industry:
            conditions.append(self._model.industry == industry)

        if conditions:
            stmt = stmt.where(and_(*conditions))

        result = await self._session.execute(stmt)
        return {row[0]: row[1] for row in result.all()}

    async def get_hourly_distribution(
        self,
        target_date: date | None = None,
        industry: str | None = None,
    ) -> dict[int, int]:
        """Get call count distribution by hour.

        Args:
            target_date: Date to analyze (default: today)
            industry: Optional industry filter

        Returns:
            Dictionary of hour (0-23) -> call count
        """
        if target_date is None:
            target_date = date.today()

        start = datetime.combine(target_date, datetime.min.time())
        end = datetime.combine(target_date, datetime.max.time())

        # SQLite-compatible hour extraction
        stmt = (
            select(
                func.strftime("%H", self._model.started_at).label("hour"),
                func.count().label("count"),
            )
            .where(
                and_(
                    self._model.started_at >= start,
                    self._model.started_at <= end,
                )
            )
            .group_by("hour")
        )

        if industry:
            stmt = stmt.where(self._model.industry == industry)

        result = await self._session.execute(stmt)
        return {int(row[0]): row[1] for row in result.all()}

    async def get_average_duration(
        self,
        start_date: date | None = None,
        end_date: date | None = None,
        status: str = "completed",
        industry: str | None = None,
    ) -> float:
        """Get average call duration in seconds.

        Args:
            start_date: Optional start date filter
            end_date: Optional end date filter
            status: Call status to filter (default: completed)
            industry: Optional industry filter

        Returns:
            Average duration in seconds
        """
        stmt = select(func.avg(self._model.duration_seconds)).where(
            self._model.status == status
        )

        conditions = []
        if start_date:
            conditions.append(
                self._model.started_at >= datetime.combine(start_date, datetime.min.time())
            )
        if end_date:
            conditions.append(
                self._model.started_at <= datetime.combine(end_date, datetime.max.time())
            )
        if industry:
            conditions.append(self._model.industry == industry)

        if conditions:
            stmt = stmt.where(and_(*conditions))

        result = await self._session.execute(stmt)
        avg = result.scalar()
        return float(avg) if avg else 0.0

    async def get_daily_stats(
        self,
        target_date: date | None = None,
        industry: str | None = None,
    ) -> dict[str, Any]:
        """Get comprehensive daily statistics.

        Args:
            target_date: Date to analyze (default: today)
            industry: Optional industry filter

        Returns:
            Dictionary with daily statistics
        """
        if target_date is None:
            target_date = date.today()

        calls = await self.get_by_date_range(target_date, target_date, industry=industry)

        total = len(calls)
        if total == 0:
            return {
                "date": target_date.isoformat(),
                "total_calls": 0,
                "inbound": 0,
                "outbound": 0,
                "completed": 0,
                "missed": 0,
                "failed": 0,
                "avg_duration": 0.0,
                "total_duration": 0,
                "appointments_booked": 0,
            }

        inbound = sum(1 for c in calls if c.direction == "inbound")
        outbound = sum(1 for c in calls if c.direction == "outbound")
        completed = sum(1 for c in calls if c.status == "completed")
        missed = sum(1 for c in calls if c.status == "missed")
        failed = sum(1 for c in calls if c.status == "failed")

        durations = [c.duration_seconds or 0 for c in calls if c.status == "completed"]
        total_duration = sum(durations)
        avg_duration = total_duration / len(durations) if durations else 0.0

        appointments = sum(1 for c in calls if c.appointment_id is not None)

        return {
            "date": target_date.isoformat(),
            "total_calls": total,
            "inbound": inbound,
            "outbound": outbound,
            "completed": completed,
            "missed": missed,
            "failed": failed,
            "avg_duration": round(avg_duration, 2),
            "total_duration": total_duration,
            "appointments_booked": appointments,
            "completion_rate": round((completed / total) * 100, 2) if total else 0.0,
            "appointment_conversion_rate": round((appointments / total) * 100, 2) if total else 0.0,
        }

    # ========================================================================
    # Campaign-related Queries
    # ========================================================================

    async def get_by_campaign(
        self,
        campaign_id: UUID,
        *,
        skip: int = 0,
        limit: int = 100,
    ) -> Sequence[CallModel]:
        """Get calls for a specific campaign.

        Args:
            campaign_id: Campaign UUID
            skip: Pagination offset
            limit: Maximum results

        Returns:
            List of campaign calls
        """
        stmt = (
            select(self._model)
            .where(self._model.campaign_id == campaign_id)
            .order_by(self._model.started_at.desc())
            .offset(skip)
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return result.scalars().all()

    async def get_campaign_stats(self, campaign_id: UUID) -> dict[str, Any]:
        """Get statistics for a campaign's calls.

        Args:
            campaign_id: Campaign UUID

        Returns:
            Dictionary with campaign call statistics
        """
        calls = await self.get_by_campaign(campaign_id, limit=10000)

        total = len(calls)
        if total == 0:
            return {
                "campaign_id": str(campaign_id),
                "total_calls": 0,
                "successful": 0,
                "failed": 0,
                "no_answer": 0,
                "appointments_booked": 0,
                "success_rate": 0.0,
            }

        successful = sum(1 for c in calls if c.status == "completed")
        failed = sum(1 for c in calls if c.status == "failed")
        no_answer = sum(1 for c in calls if c.status == "missed" or c.status == "no_answer")
        appointments = sum(1 for c in calls if c.appointment_id is not None)

        return {
            "campaign_id": str(campaign_id),
            "total_calls": total,
            "successful": successful,
            "failed": failed,
            "no_answer": no_answer,
            "appointments_booked": appointments,
            "success_rate": round((successful / total) * 100, 2) if total else 0.0,
            "appointment_rate": round((appointments / successful) * 100, 2) if successful else 0.0,
        }
