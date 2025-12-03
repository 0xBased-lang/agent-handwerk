"""Analytics and Dashboard Endpoints.

Provides API endpoints for dashboard KPIs, metrics aggregation,
and analytics data retrieval.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from phone_agent.db import get_db
from phone_agent.db.repositories.analytics import (
    AnalyticsService,
    CallMetricsRepository,
    CampaignMetricsRepository,
    RecallCampaignRepository,
    DashboardSnapshotRepository,
)


router = APIRouter()


# ============================================================================
# Pydantic Schemas
# ============================================================================

class CallKPIs(BaseModel):
    """Call-related KPIs."""

    today: int
    this_week: int
    this_month: int
    completion_rate: float
    avg_duration: float


class AppointmentKPIs(BaseModel):
    """Appointment-related KPIs."""

    today: int
    this_week: int
    conversion_rate: float


class CampaignKPIs(BaseModel):
    """Campaign-related KPIs."""

    active: int
    total_contacts: int


class AIPerformanceKPIs(BaseModel):
    """AI performance KPIs."""

    resolution_rate: float
    escalations_today: int


class DashboardKPIs(BaseModel):
    """Complete dashboard KPIs response."""

    calls: CallKPIs
    appointments: AppointmentKPIs
    campaigns: CampaignKPIs
    ai_performance: AIPerformanceKPIs


class DailyMetrics(BaseModel):
    """Daily metrics summary."""

    date: str
    hour: int | None = None
    total_calls: int
    inbound_calls: int
    outbound_calls: int
    completed_calls: int
    missed_calls: int
    failed_calls: int
    avg_duration: float
    appointments_booked: int
    completion_rate: float
    appointment_conversion_rate: float


class WeeklySummary(BaseModel):
    """Weekly metrics summary."""

    start_date: str
    end_date: str
    total_calls: int
    inbound_calls: int
    outbound_calls: int
    completed_calls: int
    appointments_booked: int
    avg_duration: float
    completion_rate: float
    appointment_conversion_rate: float


class CampaignSummary(BaseModel):
    """Campaign summary for listing."""

    id: UUID
    name: str
    campaign_type: str
    status: str
    industry: str
    start_date: str
    total_contacts: int
    contacts_reached: int
    appointments_booked: int
    progress_percent: float
    reach_rate: float
    conversion_rate: float


class CampaignMetricsSummary(BaseModel):
    """Campaign metrics aggregation."""

    campaign_id: str
    total_targeted: int
    total_attempted: int
    total_reached: int
    total_converted: int
    total_calls: int
    total_appointments: int
    total_talk_time: int
    contact_rate: float
    conversion_rate: float


# ============================================================================
# Dependencies
# ============================================================================

async def get_analytics_service(
    session: Annotated[AsyncSession, Depends(get_db)]
) -> AnalyticsService:
    """Get analytics service instance."""
    return AnalyticsService(session)


async def get_call_metrics_repo(
    session: Annotated[AsyncSession, Depends(get_db)]
) -> CallMetricsRepository:
    """Get call metrics repository."""
    return CallMetricsRepository(session)


async def get_campaign_repo(
    session: Annotated[AsyncSession, Depends(get_db)]
) -> RecallCampaignRepository:
    """Get campaign repository."""
    return RecallCampaignRepository(session)


async def get_campaign_metrics_repo(
    session: Annotated[AsyncSession, Depends(get_db)]
) -> CampaignMetricsRepository:
    """Get campaign metrics repository."""
    return CampaignMetricsRepository(session)


# ============================================================================
# Dashboard Endpoints
# ============================================================================

@router.get("/analytics/dashboard", response_model=DashboardKPIs)
async def get_dashboard_kpis(
    service: Annotated[AnalyticsService, Depends(get_analytics_service)],
    industry: str | None = None,
) -> DashboardKPIs:
    """Get real-time dashboard KPIs.

    Args:
        industry: Optional industry filter

    Returns:
        Complete dashboard KPIs
    """
    kpis = await service.get_dashboard_kpis(industry=industry)

    return DashboardKPIs(
        calls=CallKPIs(**kpis["calls"]),
        appointments=AppointmentKPIs(**kpis["appointments"]),
        campaigns=CampaignKPIs(**kpis["campaigns"]),
        ai_performance=AIPerformanceKPIs(**kpis["ai_performance"]),
    )


# ============================================================================
# Call Metrics Endpoints
# ============================================================================

@router.get("/analytics/calls/daily", response_model=DailyMetrics | None)
async def get_daily_call_metrics(
    repo: Annotated[CallMetricsRepository, Depends(get_call_metrics_repo)],
    target_date: date | None = None,
    industry: str | None = None,
) -> DailyMetrics | None:
    """Get daily call metrics.

    Args:
        target_date: Date to query (default: today)
        industry: Optional industry filter

    Returns:
        Daily metrics or None if no data
    """
    if target_date is None:
        target_date = date.today()

    metrics = await repo.get_daily_metrics(target_date, industry=industry)

    if metrics is None:
        return None

    return DailyMetrics(
        date=metrics.date.isoformat(),
        hour=metrics.hour,
        total_calls=metrics.total_calls,
        inbound_calls=metrics.inbound_calls,
        outbound_calls=metrics.outbound_calls,
        completed_calls=metrics.completed_calls,
        missed_calls=metrics.missed_calls,
        failed_calls=metrics.failed_calls,
        avg_duration=metrics.avg_duration,
        appointments_booked=metrics.appointments_booked,
        completion_rate=metrics.completion_rate,
        appointment_conversion_rate=metrics.appointment_conversion_rate,
    )


@router.get("/analytics/calls/hourly", response_model=list[DailyMetrics])
async def get_hourly_call_metrics(
    repo: Annotated[CallMetricsRepository, Depends(get_call_metrics_repo)],
    target_date: date | None = None,
    industry: str | None = None,
) -> list[DailyMetrics]:
    """Get hourly call metrics breakdown.

    Args:
        target_date: Date to query (default: today)
        industry: Optional industry filter

    Returns:
        List of hourly metrics (0-23)
    """
    if target_date is None:
        target_date = date.today()

    metrics_list = await repo.get_hourly_metrics(target_date, industry=industry)

    return [
        DailyMetrics(
            date=m.date.isoformat(),
            hour=m.hour,
            total_calls=m.total_calls,
            inbound_calls=m.inbound_calls,
            outbound_calls=m.outbound_calls,
            completed_calls=m.completed_calls,
            missed_calls=m.missed_calls,
            failed_calls=m.failed_calls,
            avg_duration=m.avg_duration,
            appointments_booked=m.appointments_booked,
            completion_rate=m.completion_rate,
            appointment_conversion_rate=m.appointment_conversion_rate,
        )
        for m in metrics_list
    ]


@router.get("/analytics/calls/range", response_model=list[DailyMetrics])
async def get_call_metrics_range(
    repo: Annotated[CallMetricsRepository, Depends(get_call_metrics_repo)],
    start_date: date,
    end_date: date,
    industry: str | None = None,
) -> list[DailyMetrics]:
    """Get call metrics for a date range.

    Args:
        start_date: Start date (inclusive)
        end_date: End date (inclusive)
        industry: Optional industry filter

    Returns:
        List of daily metrics
    """
    metrics_list = await repo.get_date_range_metrics(start_date, end_date, industry=industry)

    return [
        DailyMetrics(
            date=m.date.isoformat(),
            hour=m.hour,
            total_calls=m.total_calls,
            inbound_calls=m.inbound_calls,
            outbound_calls=m.outbound_calls,
            completed_calls=m.completed_calls,
            missed_calls=m.missed_calls,
            failed_calls=m.failed_calls,
            avg_duration=m.avg_duration,
            appointments_booked=m.appointments_booked,
            completion_rate=m.completion_rate,
            appointment_conversion_rate=m.appointment_conversion_rate,
        )
        for m in metrics_list
    ]


@router.get("/analytics/calls/weekly", response_model=WeeklySummary)
async def get_weekly_call_summary(
    repo: Annotated[CallMetricsRepository, Depends(get_call_metrics_repo)],
    industry: str | None = None,
) -> WeeklySummary:
    """Get weekly call summary.

    Args:
        industry: Optional industry filter

    Returns:
        Weekly summary statistics
    """
    summary = await repo.get_weekly_summary(industry=industry)
    return WeeklySummary(**summary)


@router.post("/analytics/calls/aggregate")
async def aggregate_daily_metrics(
    service: Annotated[AnalyticsService, Depends(get_analytics_service)],
    db: Annotated[AsyncSession, Depends(get_db)],
    target_date: date | None = None,
    industry: str | None = None,
) -> dict[str, Any]:
    """Trigger daily metrics aggregation from call records.

    This endpoint aggregates raw call data into daily metrics.
    Typically run as a scheduled job.

    Args:
        target_date: Date to aggregate (default: today)
        industry: Optional industry filter

    Returns:
        Aggregation status
    """
    if target_date is None:
        target_date = date.today()

    metrics = await service.aggregate_daily_metrics_from_calls(
        target_date, industry=industry
    )
    await db.commit()

    return {
        "status": "success",
        "date": target_date.isoformat(),
        "total_calls": metrics.total_calls,
    }


# ============================================================================
# Campaign Endpoints
# ============================================================================

@router.get("/analytics/campaigns", response_model=list[CampaignSummary])
async def list_campaigns(
    repo: Annotated[RecallCampaignRepository, Depends(get_campaign_repo)],
    status: str | None = None,
    industry: str | None = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
) -> list[CampaignSummary]:
    """List recall campaigns with summary info.

    Args:
        status: Filter by status (draft, scheduled, active, completed)
        industry: Optional industry filter
        skip: Pagination offset
        limit: Maximum results

    Returns:
        List of campaign summaries
    """
    if status:
        campaigns = await repo.get_by_status(status, industry=industry, skip=skip, limit=limit)
    else:
        campaigns = await repo.get_multi(skip=skip, limit=limit)

    return [
        CampaignSummary(
            id=c.id,
            name=c.name,
            campaign_type=c.campaign_type,
            status=c.status,
            industry=c.industry,
            start_date=c.start_date.isoformat(),
            total_contacts=c.total_contacts,
            contacts_reached=c.contacts_reached,
            appointments_booked=c.appointments_booked,
            progress_percent=c.calculate_progress()["progress_percent"],
            reach_rate=c.calculate_progress()["reach_rate"],
            conversion_rate=c.calculate_progress()["conversion_rate"],
        )
        for c in campaigns
    ]


@router.get("/analytics/campaigns/active", response_model=list[CampaignSummary])
async def list_active_campaigns(
    repo: Annotated[RecallCampaignRepository, Depends(get_campaign_repo)],
    industry: str | None = None,
) -> list[CampaignSummary]:
    """List all active campaigns.

    Args:
        industry: Optional industry filter

    Returns:
        List of active campaign summaries
    """
    campaigns = await repo.get_active_campaigns(industry=industry)

    return [
        CampaignSummary(
            id=c.id,
            name=c.name,
            campaign_type=c.campaign_type,
            status=c.status,
            industry=c.industry,
            start_date=c.start_date.isoformat(),
            total_contacts=c.total_contacts,
            contacts_reached=c.contacts_reached,
            appointments_booked=c.appointments_booked,
            progress_percent=c.calculate_progress()["progress_percent"],
            reach_rate=c.calculate_progress()["reach_rate"],
            conversion_rate=c.calculate_progress()["conversion_rate"],
        )
        for c in campaigns
    ]


@router.get("/analytics/campaigns/{campaign_id}/metrics", response_model=CampaignMetricsSummary)
async def get_campaign_metrics(
    campaign_id: UUID,
    repo: Annotated[CampaignMetricsRepository, Depends(get_campaign_metrics_repo)],
) -> CampaignMetricsSummary:
    """Get aggregated metrics for a campaign.

    Args:
        campaign_id: Campaign UUID

    Returns:
        Campaign metrics summary
    """
    totals = await repo.get_campaign_totals(campaign_id)
    return CampaignMetricsSummary(**totals)


@router.get("/analytics/campaigns/{campaign_id}/history")
async def get_campaign_metrics_history(
    campaign_id: UUID,
    repo: Annotated[CampaignMetricsRepository, Depends(get_campaign_metrics_repo)],
    days: int = Query(30, ge=1, le=90),
) -> list[dict[str, Any]]:
    """Get campaign metrics history by day.

    Args:
        campaign_id: Campaign UUID
        days: Number of days to look back

    Returns:
        List of daily campaign metrics
    """
    metrics_list = await repo.get_campaign_history(campaign_id, days=days)

    return [m.to_dict() for m in metrics_list]


# ============================================================================
# Trend Analysis Endpoints
# ============================================================================

@router.get("/analytics/trends/calls")
async def get_call_trends(
    repo: Annotated[CallMetricsRepository, Depends(get_call_metrics_repo)],
    days: int = Query(30, ge=7, le=90),
    industry: str | None = None,
) -> dict[str, Any]:
    """Get call volume trends over time.

    Args:
        days: Number of days to analyze
        industry: Optional industry filter

    Returns:
        Trend data with day-over-day changes
    """
    end_date = date.today()
    start_date = end_date - timedelta(days=days)

    metrics = await repo.get_date_range_metrics(start_date, end_date, industry=industry)

    # Calculate trends
    daily_totals = [m.total_calls for m in metrics]
    avg_daily = sum(daily_totals) / len(daily_totals) if daily_totals else 0

    # Week-over-week comparison
    this_week_metrics = [m for m in metrics if m.date >= end_date - timedelta(days=7)]
    last_week_metrics = [
        m for m in metrics
        if end_date - timedelta(days=14) <= m.date < end_date - timedelta(days=7)
    ]

    this_week_total = sum(m.total_calls for m in this_week_metrics)
    last_week_total = sum(m.total_calls for m in last_week_metrics)

    wow_change = (
        ((this_week_total - last_week_total) / last_week_total * 100)
        if last_week_total > 0 else 0
    )

    return {
        "period": {
            "start": start_date.isoformat(),
            "end": end_date.isoformat(),
            "days": days,
        },
        "totals": {
            "calls": sum(daily_totals),
            "avg_daily": round(avg_daily, 2),
        },
        "trends": {
            "week_over_week_change": round(wow_change, 2),
            "this_week_total": this_week_total,
            "last_week_total": last_week_total,
        },
        "daily_data": [
            {
                "date": m.date.isoformat(),
                "total_calls": m.total_calls,
                "completion_rate": m.completion_rate,
            }
            for m in metrics
        ],
    }


@router.get("/analytics/trends/appointments")
async def get_appointment_trends(
    repo: Annotated[CallMetricsRepository, Depends(get_call_metrics_repo)],
    days: int = Query(30, ge=7, le=90),
    industry: str | None = None,
) -> dict[str, Any]:
    """Get appointment booking trends.

    Args:
        days: Number of days to analyze
        industry: Optional industry filter

    Returns:
        Appointment trend data
    """
    end_date = date.today()
    start_date = end_date - timedelta(days=days)

    metrics = await repo.get_date_range_metrics(start_date, end_date, industry=industry)

    # Calculate trends
    daily_appointments = [m.appointments_booked for m in metrics]
    avg_daily = sum(daily_appointments) / len(daily_appointments) if daily_appointments else 0

    # Conversion rates
    conversion_rates = [m.appointment_conversion_rate for m in metrics]
    avg_conversion = sum(conversion_rates) / len(conversion_rates) if conversion_rates else 0

    return {
        "period": {
            "start": start_date.isoformat(),
            "end": end_date.isoformat(),
            "days": days,
        },
        "totals": {
            "appointments_booked": sum(daily_appointments),
            "avg_daily": round(avg_daily, 2),
            "avg_conversion_rate": round(avg_conversion, 2),
        },
        "daily_data": [
            {
                "date": m.date.isoformat(),
                "appointments_booked": m.appointments_booked,
                "conversion_rate": m.appointment_conversion_rate,
            }
            for m in metrics
        ],
    }
