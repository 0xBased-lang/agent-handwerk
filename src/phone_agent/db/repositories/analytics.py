"""Analytics Repository for Phone Agent.

Specialized repository for analytics and dashboard data.
Provides aggregation queries and KPI calculations.
"""
from __future__ import annotations

from datetime import datetime, date, timedelta
from typing import Sequence, Any
from uuid import UUID

from sqlalchemy import select, func, and_, or_, desc
from sqlalchemy.ext.asyncio import AsyncSession

from phone_agent.db.models.analytics import (
    CallMetricsModel,
    CampaignMetricsModel,
    RecallCampaignModel,
    DashboardSnapshotModel,
)
from phone_agent.db.models.core import CallModel, AppointmentModel
from phone_agent.db.repositories.base import BaseRepository


class CallMetricsRepository(BaseRepository[CallMetricsModel]):
    """Repository for call metrics operations."""

    def __init__(self, session: AsyncSession):
        super().__init__(CallMetricsModel, session)

    async def get_daily_metrics(
        self,
        target_date: date,
        *,
        industry: str | None = None,
        tenant_id: UUID | None = None,
    ) -> CallMetricsModel | None:
        """Get daily metrics for a specific date.

        Args:
            target_date: Date to query
            industry: Optional industry filter
            tenant_id: Optional tenant filter

        Returns:
            Daily metrics or None
        """
        conditions = [
            self._model.date == target_date,
            self._model.hour.is_(None),  # Daily aggregate
        ]

        if industry:
            conditions.append(self._model.industry == industry)
        if tenant_id:
            conditions.append(self._model.tenant_id == tenant_id)

        stmt = select(self._model).where(and_(*conditions))
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_hourly_metrics(
        self,
        target_date: date,
        *,
        industry: str | None = None,
    ) -> Sequence[CallMetricsModel]:
        """Get hourly metrics breakdown for a date.

        Args:
            target_date: Date to query
            industry: Optional industry filter

        Returns:
            List of hourly metrics (0-23)
        """
        conditions = [
            self._model.date == target_date,
            self._model.hour.isnot(None),  # Hourly breakdown
        ]

        if industry:
            conditions.append(self._model.industry == industry)

        stmt = (
            select(self._model)
            .where(and_(*conditions))
            .order_by(self._model.hour)
        )
        result = await self._session.execute(stmt)
        return result.scalars().all()

    async def get_date_range_metrics(
        self,
        start_date: date,
        end_date: date,
        *,
        industry: str | None = None,
    ) -> Sequence[CallMetricsModel]:
        """Get daily metrics for a date range.

        Args:
            start_date: Start date (inclusive)
            end_date: End date (inclusive)
            industry: Optional industry filter

        Returns:
            List of daily metrics
        """
        conditions = [
            self._model.date >= start_date,
            self._model.date <= end_date,
            self._model.hour.is_(None),  # Daily aggregates only
        ]

        if industry:
            conditions.append(self._model.industry == industry)

        stmt = (
            select(self._model)
            .where(and_(*conditions))
            .order_by(self._model.date)
        )
        result = await self._session.execute(stmt)
        return result.scalars().all()

    async def get_weekly_summary(
        self,
        industry: str | None = None,
    ) -> dict[str, Any]:
        """Get summary metrics for the current week.

        Args:
            industry: Optional industry filter

        Returns:
            Weekly summary statistics
        """
        today = date.today()
        start_of_week = today - timedelta(days=today.weekday())

        metrics = await self.get_date_range_metrics(
            start_of_week, today, industry=industry
        )

        if not metrics:
            return {
                "total_calls": 0,
                "inbound_calls": 0,
                "outbound_calls": 0,
                "completed_calls": 0,
                "appointments_booked": 0,
                "avg_duration": 0.0,
                "completion_rate": 0.0,
                "appointment_conversion_rate": 0.0,
            }

        total_calls = sum(m.total_calls for m in metrics)
        inbound = sum(m.inbound_calls for m in metrics)
        outbound = sum(m.outbound_calls for m in metrics)
        completed = sum(m.completed_calls for m in metrics)
        appointments = sum(m.appointments_booked for m in metrics)
        total_duration = sum(m.total_duration for m in metrics)

        return {
            "start_date": start_of_week.isoformat(),
            "end_date": today.isoformat(),
            "total_calls": total_calls,
            "inbound_calls": inbound,
            "outbound_calls": outbound,
            "completed_calls": completed,
            "appointments_booked": appointments,
            "avg_duration": round(total_duration / completed, 2) if completed else 0.0,
            "completion_rate": round((completed / total_calls) * 100, 2) if total_calls else 0.0,
            "appointment_conversion_rate": round((appointments / total_calls) * 100, 2) if total_calls else 0.0,
        }

    async def upsert_daily_metrics(
        self,
        target_date: date,
        metrics: dict[str, Any],
        *,
        industry: str | None = None,
        tenant_id: UUID | None = None,
    ) -> CallMetricsModel:
        """Create or update daily metrics.

        Args:
            target_date: Date for metrics
            metrics: Metrics data dictionary
            industry: Optional industry
            tenant_id: Optional tenant

        Returns:
            Created or updated metrics
        """
        existing = await self.get_daily_metrics(
            target_date, industry=industry, tenant_id=tenant_id
        )

        if existing:
            # Update existing
            for key, value in metrics.items():
                if hasattr(existing, key):
                    setattr(existing, key, value)
            existing.calculate_rates()
            await self._session.flush()
            return existing
        else:
            # Create new
            from uuid import uuid4
            new_metrics = CallMetricsModel(
                id=uuid4(),
                date=target_date,
                industry=industry,
                tenant_id=tenant_id,
                **metrics,
            )
            new_metrics.calculate_rates()
            self._session.add(new_metrics)
            await self._session.flush()
            return new_metrics


class CampaignMetricsRepository(BaseRepository[CampaignMetricsModel]):
    """Repository for campaign metrics operations."""

    def __init__(self, session: AsyncSession):
        super().__init__(CampaignMetricsModel, session)

    async def get_campaign_daily(
        self,
        campaign_id: UUID,
        target_date: date,
    ) -> CampaignMetricsModel | None:
        """Get campaign metrics for a specific date.

        Args:
            campaign_id: Campaign UUID
            target_date: Date to query

        Returns:
            Campaign metrics or None
        """
        stmt = select(self._model).where(
            and_(
                self._model.campaign_id == campaign_id,
                self._model.date == target_date,
            )
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_campaign_history(
        self,
        campaign_id: UUID,
        *,
        days: int = 30,
    ) -> Sequence[CampaignMetricsModel]:
        """Get campaign metrics history.

        Args:
            campaign_id: Campaign UUID
            days: Number of days to look back

        Returns:
            List of daily campaign metrics
        """
        cutoff = date.today() - timedelta(days=days)
        stmt = (
            select(self._model)
            .where(
                and_(
                    self._model.campaign_id == campaign_id,
                    self._model.date >= cutoff,
                )
            )
            .order_by(self._model.date)
        )
        result = await self._session.execute(stmt)
        return result.scalars().all()

    async def get_campaign_totals(self, campaign_id: UUID) -> dict[str, Any]:
        """Get aggregated totals for a campaign.

        Args:
            campaign_id: Campaign UUID

        Returns:
            Aggregated campaign statistics
        """
        stmt = (
            select(
                func.sum(self._model.contacts_targeted).label("total_targeted"),
                func.sum(self._model.contacts_attempted).label("total_attempted"),
                func.sum(self._model.contacts_reached).label("total_reached"),
                func.sum(self._model.contacts_converted).label("total_converted"),
                func.sum(self._model.total_calls).label("total_calls"),
                func.sum(self._model.appointments_booked).label("total_appointments"),
                func.sum(self._model.total_talk_time).label("total_talk_time"),
            )
            .where(self._model.campaign_id == campaign_id)
        )
        result = await self._session.execute(stmt)
        row = result.one_or_none()

        # Handle case where no data exists for this campaign
        if row is None:
            return {
                "campaign_id": str(campaign_id),
                "total_targeted": 0,
                "total_attempted": 0,
                "total_reached": 0,
                "total_converted": 0,
                "total_calls": 0,
                "total_appointments": 0,
                "total_talk_time": 0,
                "contact_rate": 0.0,
                "conversion_rate": 0.0,
            }

        targeted = row.total_targeted or 0
        reached = row.total_reached or 0
        converted = row.total_converted or 0
        calls = row.total_calls or 0

        return {
            "campaign_id": str(campaign_id),
            "total_targeted": targeted,
            "total_attempted": row.total_attempted or 0,
            "total_reached": reached,
            "total_converted": converted,
            "total_calls": calls,
            "total_appointments": row.total_appointments or 0,
            "total_talk_time": row.total_talk_time or 0,
            "contact_rate": round((reached / targeted) * 100, 2) if targeted else 0.0,
            "conversion_rate": round((converted / reached) * 100, 2) if reached else 0.0,
        }


class RecallCampaignRepository(BaseRepository[RecallCampaignModel]):
    """Repository for recall campaign operations."""

    def __init__(self, session: AsyncSession):
        super().__init__(RecallCampaignModel, session)

    async def get_active_campaigns(
        self,
        industry: str | None = None,
    ) -> Sequence[RecallCampaignModel]:
        """Get all active campaigns.

        Args:
            industry: Optional industry filter

        Returns:
            List of active campaigns
        """
        conditions = [self._model.status == "active"]

        if industry:
            conditions.append(self._model.industry == industry)

        stmt = (
            select(self._model)
            .where(and_(*conditions))
            .order_by(self._model.priority, self._model.start_date)
        )
        result = await self._session.execute(stmt)
        return result.scalars().all()

    async def get_by_status(
        self,
        status: str,
        *,
        industry: str | None = None,
        skip: int = 0,
        limit: int = 50,
    ) -> Sequence[RecallCampaignModel]:
        """Get campaigns by status.

        Args:
            status: Campaign status
            industry: Optional industry filter
            skip: Pagination offset
            limit: Maximum results

        Returns:
            List of campaigns
        """
        conditions = [self._model.status == status]

        if industry:
            conditions.append(self._model.industry == industry)

        stmt = (
            select(self._model)
            .where(and_(*conditions))
            .order_by(self._model.start_date.desc())
            .offset(skip)
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return result.scalars().all()

    async def get_upcoming_campaigns(
        self,
        days: int = 7,
        *,
        industry: str | None = None,
    ) -> Sequence[RecallCampaignModel]:
        """Get campaigns scheduled to start soon.

        Args:
            days: Number of days to look ahead
            industry: Optional industry filter

        Returns:
            List of upcoming campaigns
        """
        today = date.today()
        future = today + timedelta(days=days)

        conditions = [
            self._model.status == "scheduled",
            self._model.start_date >= today,
            self._model.start_date <= future,
        ]

        if industry:
            conditions.append(self._model.industry == industry)

        stmt = (
            select(self._model)
            .where(and_(*conditions))
            .order_by(self._model.start_date)
        )
        result = await self._session.execute(stmt)
        return result.scalars().all()

    async def update_progress(
        self,
        campaign_id: UUID,
        contacts_called: int,
        contacts_reached: int,
        appointments_booked: int,
    ) -> RecallCampaignModel | None:
        """Update campaign progress counters.

        Args:
            campaign_id: Campaign UUID
            contacts_called: Total contacts called
            contacts_reached: Total contacts reached
            appointments_booked: Total appointments booked

        Returns:
            Updated campaign or None
        """
        campaign = await self.get(campaign_id)
        if campaign is None:
            return None

        campaign.contacts_called = contacts_called
        campaign.contacts_reached = contacts_reached
        campaign.appointments_booked = appointments_booked

        await self._session.flush()
        return campaign


class DashboardSnapshotRepository(BaseRepository[DashboardSnapshotModel]):
    """Repository for dashboard snapshot operations."""

    def __init__(self, session: AsyncSession):
        super().__init__(DashboardSnapshotModel, session)

    async def get_latest(
        self,
        snapshot_type: str = "hourly",
        *,
        industry: str | None = None,
    ) -> DashboardSnapshotModel | None:
        """Get most recent dashboard snapshot.

        Args:
            snapshot_type: Snapshot type (hourly, daily, weekly)
            industry: Optional industry filter

        Returns:
            Latest snapshot or None
        """
        conditions = [self._model.snapshot_type == snapshot_type]

        if industry:
            conditions.append(self._model.industry == industry)

        stmt = (
            select(self._model)
            .where(and_(*conditions))
            .order_by(self._model.snapshot_at.desc())
            .limit(1)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_history(
        self,
        snapshot_type: str = "hourly",
        *,
        hours: int = 24,
        industry: str | None = None,
    ) -> Sequence[DashboardSnapshotModel]:
        """Get snapshot history.

        Args:
            snapshot_type: Snapshot type
            hours: Number of hours to look back
            industry: Optional industry filter

        Returns:
            List of snapshots
        """
        cutoff = datetime.utcnow() - timedelta(hours=hours)
        conditions = [
            self._model.snapshot_type == snapshot_type,
            self._model.snapshot_at >= cutoff,
        ]

        if industry:
            conditions.append(self._model.industry == industry)

        stmt = (
            select(self._model)
            .where(and_(*conditions))
            .order_by(self._model.snapshot_at)
        )
        result = await self._session.execute(stmt)
        return result.scalars().all()

    async def create_snapshot(
        self,
        snapshot_type: str,
        kpis: dict[str, Any],
        *,
        industry: str | None = None,
        tenant_id: UUID | None = None,
    ) -> DashboardSnapshotModel:
        """Create a new dashboard snapshot.

        Args:
            snapshot_type: Snapshot type
            kpis: KPI values dictionary
            industry: Optional industry
            tenant_id: Optional tenant

        Returns:
            Created snapshot
        """
        from uuid import uuid4

        snapshot = DashboardSnapshotModel(
            id=uuid4(),
            snapshot_at=datetime.utcnow(),
            snapshot_type=snapshot_type,
            industry=industry,
            tenant_id=tenant_id,
            **kpis,
        )

        self._session.add(snapshot)
        await self._session.flush()
        return snapshot

    async def cleanup_old_snapshots(
        self,
        days: int = 30,
        snapshot_type: str | None = None,
    ) -> int:
        """Delete snapshots older than specified days.

        Args:
            days: Age threshold in days
            snapshot_type: Optional type filter

        Returns:
            Number of deleted snapshots
        """
        cutoff = datetime.utcnow() - timedelta(days=days)

        # Use direct SQLAlchemy delete for bulk operation
        from sqlalchemy import delete

        conditions = [self._model.snapshot_at < cutoff]
        if snapshot_type:
            conditions.append(self._model.snapshot_type == snapshot_type)

        stmt = delete(self._model).where(and_(*conditions))
        result = await self._session.execute(stmt)
        await self._session.flush()
        return result.rowcount


class AnalyticsService:
    """High-level analytics service combining multiple repositories.

    Provides dashboard KPIs and aggregated analytics.
    """

    def __init__(self, session: AsyncSession):
        """Initialize with session.

        Args:
            session: Async database session
        """
        self._session = session
        self.call_metrics = CallMetricsRepository(session)
        self.campaign_metrics = CampaignMetricsRepository(session)
        self.campaigns = RecallCampaignRepository(session)
        self.snapshots = DashboardSnapshotRepository(session)

    async def get_dashboard_kpis(
        self,
        industry: str | None = None,
    ) -> dict[str, Any]:
        """Calculate real-time dashboard KPIs.

        Args:
            industry: Optional industry filter

        Returns:
            Dictionary of dashboard KPIs
        """
        today = date.today()
        week_start = today - timedelta(days=today.weekday())
        month_start = today.replace(day=1)

        # Get metrics
        daily_metrics = await self.call_metrics.get_daily_metrics(today, industry=industry)
        weekly_metrics = await self.call_metrics.get_date_range_metrics(
            week_start, today, industry=industry
        )
        monthly_metrics = await self.call_metrics.get_date_range_metrics(
            month_start, today, industry=industry
        )

        # Calculate totals
        calls_today = daily_metrics.total_calls if daily_metrics else 0
        calls_week = sum(m.total_calls for m in weekly_metrics)
        calls_month = sum(m.total_calls for m in monthly_metrics)

        appointments_today = daily_metrics.appointments_booked if daily_metrics else 0
        appointments_week = sum(m.appointments_booked for m in weekly_metrics)

        # Get active campaigns
        active_campaigns = await self.campaigns.get_active_campaigns(industry)

        return {
            "calls": {
                "today": calls_today,
                "this_week": calls_week,
                "this_month": calls_month,
                "completion_rate": daily_metrics.completion_rate if daily_metrics else 0.0,
                "avg_duration": daily_metrics.avg_duration if daily_metrics else 0.0,
            },
            "appointments": {
                "today": appointments_today,
                "this_week": appointments_week,
                "conversion_rate": daily_metrics.appointment_conversion_rate if daily_metrics else 0.0,
            },
            "campaigns": {
                "active": len(active_campaigns),
                "total_contacts": sum(c.total_contacts for c in active_campaigns),
            },
            "ai_performance": {
                "resolution_rate": daily_metrics.ai_resolution_rate if daily_metrics else 0.0,
                "escalations_today": daily_metrics.human_escalations if daily_metrics else 0,
            },
        }

    async def aggregate_daily_metrics_from_calls(
        self,
        target_date: date,
        *,
        industry: str | None = None,
    ) -> CallMetricsModel:
        """Aggregate metrics from call records.

        Creates or updates daily metrics by scanning call records.

        Args:
            target_date: Date to aggregate
            industry: Optional industry filter

        Returns:
            Aggregated metrics
        """
        start = datetime.combine(target_date, datetime.min.time())
        end = datetime.combine(target_date, datetime.max.time())

        # Build query
        conditions = [
            CallModel.started_at >= start,
            CallModel.started_at <= end,
        ]
        if industry:
            conditions.append(CallModel.industry == industry)

        # Get all calls for the day
        stmt = select(CallModel).where(and_(*conditions))
        result = await self._session.execute(stmt)
        calls = result.scalars().all()

        # Calculate metrics
        total = len(calls)
        inbound = sum(1 for c in calls if c.direction == "inbound")
        outbound = sum(1 for c in calls if c.direction == "outbound")
        completed = sum(1 for c in calls if c.status == "completed")
        missed = sum(1 for c in calls if c.status == "missed")
        failed = sum(1 for c in calls if c.status == "failed")
        transferred = sum(1 for c in calls if c.transferred)

        durations = [c.duration_seconds or 0 for c in calls if c.status == "completed"]
        total_duration = sum(durations)
        avg_duration = total_duration / len(durations) if durations else 0.0

        appointments = sum(1 for c in calls if c.appointment_booked)
        ai_handled = sum(1 for c in calls if not c.transferred and c.status == "completed")

        metrics_data = {
            "total_calls": total,
            "inbound_calls": inbound,
            "outbound_calls": outbound,
            "completed_calls": completed,
            "missed_calls": missed,
            "failed_calls": failed,
            "transferred_calls": transferred,
            "total_duration": total_duration,
            "avg_duration": avg_duration,
            "min_duration": min(durations) if durations else 0,
            "max_duration": max(durations) if durations else 0,
            "appointments_booked": appointments,
            "ai_handled_calls": ai_handled,
            "human_escalations": transferred,
        }

        return await self.call_metrics.upsert_daily_metrics(
            target_date, metrics_data, industry=industry
        )
