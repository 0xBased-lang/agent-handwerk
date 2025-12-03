"""Analytics ORM Models for Phone Agent.

Contains models for aggregated metrics and dashboard data:
- CallMetrics: Daily/hourly call statistics
- CampaignMetrics: Recall campaign performance
- DashboardSnapshot: Point-in-time KPI snapshots
"""
from __future__ import annotations

from datetime import datetime, date, timezone
from typing import TYPE_CHECKING, Any
from uuid import UUID

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from phone_agent.db.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    pass


# ============================================================================
# Call Metrics Model (Daily Aggregates)
# ============================================================================

class CallMetricsModel(Base, UUIDMixin, TimestampMixin):
    """Daily and hourly aggregated call metrics.

    Pre-aggregated statistics for fast dashboard queries.
    One row per date (or date+hour if hourly breakdown).
    """

    __tablename__ = "call_metrics"

    # Time period
    date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    hour: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        index=True,
        doc="Hour of day (0-23) for hourly breakdown, NULL for daily aggregate",
    )

    # Industry context
    industry: Mapped[str | None] = mapped_column(
        String(32),
        nullable=True,
        index=True,
        doc="Industry vertical: gesundheit, handwerk, etc.",
    )

    # Tenant context (for multi-tenant deployments)
    tenant_id: Mapped[UUID | None] = mapped_column(
        nullable=True,
        index=True,
    )

    # Call volume metrics
    total_calls: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    inbound_calls: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    outbound_calls: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Call outcome metrics
    completed_calls: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    missed_calls: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    failed_calls: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    transferred_calls: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Duration metrics (in seconds)
    total_duration: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
        doc="Total call duration in seconds",
    )
    avg_duration: Mapped[float] = mapped_column(
        Float,
        default=0.0,
        nullable=False,
        doc="Average call duration in seconds",
    )
    min_duration: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_duration: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Wait time metrics (for inbound)
    avg_wait_time: Mapped[float] = mapped_column(
        Float,
        default=0.0,
        nullable=False,
        doc="Average wait time before answer in seconds",
    )
    max_wait_time: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Appointment conversion
    appointments_booked: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    appointments_modified: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    appointments_cancelled: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Service metrics (for handwerk)
    service_calls_created: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    quotes_sent: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # AI performance
    ai_handled_calls: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
        doc="Calls fully handled by AI without human intervention",
    )
    human_escalations: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Calculated rates (stored for fast queries)
    completion_rate: Mapped[float] = mapped_column(
        Float,
        default=0.0,
        nullable=False,
        doc="Percentage of calls completed successfully",
    )
    appointment_conversion_rate: Mapped[float] = mapped_column(
        Float,
        default=0.0,
        nullable=False,
        doc="Percentage of calls resulting in appointments",
    )
    ai_resolution_rate: Mapped[float] = mapped_column(
        Float,
        default=0.0,
        nullable=False,
        doc="Percentage of calls resolved by AI without escalation",
    )

    # Unique constraint to prevent duplicates
    __table_args__ = (
        UniqueConstraint("date", "hour", "industry", "tenant_id", name="uq_call_metrics_period"),
        Index("ix_call_metrics_date_industry", "date", "industry"),
        Index("ix_call_metrics_date_tenant", "date", "tenant_id"),
    )

    def __repr__(self) -> str:
        period = f"{self.date} H{self.hour}" if self.hour is not None else str(self.date)
        return f"<CallMetrics {period}: {self.total_calls} calls>"

    def calculate_rates(self) -> None:
        """Recalculate derived rate metrics."""
        if self.total_calls > 0:
            self.completion_rate = (self.completed_calls / self.total_calls) * 100
            self.appointment_conversion_rate = (self.appointments_booked / self.total_calls) * 100
            self.ai_resolution_rate = (self.ai_handled_calls / self.total_calls) * 100
        else:
            self.completion_rate = 0.0
            self.appointment_conversion_rate = 0.0
            self.ai_resolution_rate = 0.0

        if self.completed_calls > 0:
            self.avg_duration = self.total_duration / self.completed_calls
        else:
            self.avg_duration = 0.0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for API responses."""
        return {
            "id": str(self.id),
            "date": self.date.isoformat(),
            "hour": self.hour,
            "industry": self.industry,
            "tenant_id": str(self.tenant_id) if self.tenant_id else None,
            "total_calls": self.total_calls,
            "inbound_calls": self.inbound_calls,
            "outbound_calls": self.outbound_calls,
            "completed_calls": self.completed_calls,
            "missed_calls": self.missed_calls,
            "failed_calls": self.failed_calls,
            "transferred_calls": self.transferred_calls,
            "total_duration": self.total_duration,
            "avg_duration": round(self.avg_duration, 2),
            "min_duration": self.min_duration,
            "max_duration": self.max_duration,
            "avg_wait_time": round(self.avg_wait_time, 2),
            "appointments_booked": self.appointments_booked,
            "appointments_modified": self.appointments_modified,
            "appointments_cancelled": self.appointments_cancelled,
            "service_calls_created": self.service_calls_created,
            "quotes_sent": self.quotes_sent,
            "ai_handled_calls": self.ai_handled_calls,
            "human_escalations": self.human_escalations,
            "completion_rate": round(self.completion_rate, 2),
            "appointment_conversion_rate": round(self.appointment_conversion_rate, 2),
            "ai_resolution_rate": round(self.ai_resolution_rate, 2),
        }


# ============================================================================
# Campaign Metrics Model
# ============================================================================

class CampaignMetricsModel(Base, UUIDMixin, TimestampMixin):
    """Per-campaign performance metrics.

    Tracks recall campaign effectiveness and ROI.
    Updated after each campaign call or daily batch.
    """

    __tablename__ = "campaign_metrics"

    # Campaign reference
    campaign_id: Mapped[UUID] = mapped_column(
        ForeignKey("recall_campaigns.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Date for daily breakdown
    date: Mapped[date] = mapped_column(Date, nullable=False, index=True)

    # Campaign execution metrics
    contacts_targeted: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
        doc="Total contacts in campaign target list",
    )
    contacts_attempted: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
        doc="Contacts where call was attempted",
    )
    contacts_reached: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
        doc="Contacts successfully reached",
    )
    contacts_converted: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
        doc="Contacts who took desired action (appointment, etc.)",
    )

    # Call metrics
    total_calls: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    successful_calls: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    failed_calls: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    voicemail_left: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    no_answer: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Attempt distribution
    first_attempt_success: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    second_attempt_success: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    third_plus_attempt_success: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Duration metrics
    total_talk_time: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
        doc="Total talk time in seconds",
    )
    avg_call_duration: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)

    # Conversion metrics
    appointments_booked: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    appointments_kept: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
        doc="Appointments that were actually attended",
    )
    appointments_no_show: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Cost metrics (if tracking)
    estimated_cost: Mapped[float] = mapped_column(
        Float,
        default=0.0,
        nullable=False,
        doc="Estimated cost of campaign calls",
    )

    # Calculated rates
    contact_rate: Mapped[float] = mapped_column(
        Float,
        default=0.0,
        nullable=False,
        doc="Percentage of targeted contacts reached",
    )
    conversion_rate: Mapped[float] = mapped_column(
        Float,
        default=0.0,
        nullable=False,
        doc="Percentage of reached contacts converted",
    )
    success_rate: Mapped[float] = mapped_column(
        Float,
        default=0.0,
        nullable=False,
        doc="Overall campaign success rate",
    )
    show_rate: Mapped[float] = mapped_column(
        Float,
        default=0.0,
        nullable=False,
        doc="Percentage of booked appointments attended",
    )
    avg_attempts_to_reach: Mapped[float] = mapped_column(
        Float,
        default=0.0,
        nullable=False,
        doc="Average call attempts needed to reach a contact",
    )

    __table_args__ = (
        UniqueConstraint("campaign_id", "date", name="uq_campaign_metrics_date"),
        Index("ix_campaign_metrics_campaign_date", "campaign_id", "date"),
    )

    # Relationships
    campaign: Mapped["RecallCampaignModel"] = relationship(
        "RecallCampaignModel",
        back_populates="metrics",
        lazy="selectin",
    )

    def __repr__(self) -> str:
        return f"<CampaignMetrics {self.campaign_id} on {self.date}: {self.contacts_reached} reached>"

    def calculate_rates(self) -> None:
        """Recalculate derived rate metrics."""
        if self.contacts_targeted > 0:
            self.contact_rate = (self.contacts_reached / self.contacts_targeted) * 100
            self.success_rate = (self.contacts_converted / self.contacts_targeted) * 100

        if self.contacts_reached > 0:
            self.conversion_rate = (self.contacts_converted / self.contacts_reached) * 100

        if self.appointments_booked > 0:
            kept = self.appointments_kept
            total = self.appointments_kept + self.appointments_no_show
            self.show_rate = (kept / total * 100) if total > 0 else 0.0

        if self.successful_calls > 0:
            self.avg_call_duration = self.total_talk_time / self.successful_calls

        # Calculate average attempts
        total_success = (
            self.first_attempt_success
            + self.second_attempt_success
            + self.third_plus_attempt_success
        )
        if total_success > 0:
            weighted_attempts = (
                self.first_attempt_success * 1
                + self.second_attempt_success * 2
                + self.third_plus_attempt_success * 3.5  # Estimate for 3+ attempts
            )
            self.avg_attempts_to_reach = weighted_attempts / total_success

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for API responses."""
        return {
            "id": str(self.id),
            "campaign_id": str(self.campaign_id),
            "date": self.date.isoformat(),
            "contacts_targeted": self.contacts_targeted,
            "contacts_attempted": self.contacts_attempted,
            "contacts_reached": self.contacts_reached,
            "contacts_converted": self.contacts_converted,
            "total_calls": self.total_calls,
            "successful_calls": self.successful_calls,
            "failed_calls": self.failed_calls,
            "voicemail_left": self.voicemail_left,
            "no_answer": self.no_answer,
            "total_talk_time": self.total_talk_time,
            "avg_call_duration": round(self.avg_call_duration, 2),
            "appointments_booked": self.appointments_booked,
            "appointments_kept": self.appointments_kept,
            "appointments_no_show": self.appointments_no_show,
            "estimated_cost": round(self.estimated_cost, 2),
            "contact_rate": round(self.contact_rate, 2),
            "conversion_rate": round(self.conversion_rate, 2),
            "success_rate": round(self.success_rate, 2),
            "show_rate": round(self.show_rate, 2),
            "avg_attempts_to_reach": round(self.avg_attempts_to_reach, 2),
        }


# ============================================================================
# Recall Campaign Model (moved here for relationship)
# ============================================================================

class RecallCampaignModel(Base, UUIDMixin, TimestampMixin):
    """Recall campaign definition and tracking.

    Represents a patient/customer recall campaign for
    appointments, follow-ups, or preventive care.
    """

    __tablename__ = "recall_campaigns"

    # Campaign identification
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Campaign type
    campaign_type: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        index=True,
        doc="Type: vorsorge, impfung, kontrolle, wartung, etc.",
    )

    # Industry context
    industry: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        index=True,
        doc="Industry: gesundheit, handwerk, etc.",
    )

    # Tenant context
    tenant_id: Mapped[UUID | None] = mapped_column(
        nullable=True,
        index=True,
    )

    # Campaign schedule
    start_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    # Status
    status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default="draft",
        index=True,
        doc="Status: draft, scheduled, active, paused, completed, cancelled",
    )

    # Target criteria (stored as JSON)
    target_criteria_json: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        doc="JSON-encoded targeting criteria",
    )

    # Call configuration
    max_attempts: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    call_interval_hours: Mapped[int] = mapped_column(
        Integer,
        default=24,
        nullable=False,
        doc="Hours between retry attempts",
    )
    priority: Mapped[int] = mapped_column(
        Integer,
        default=5,
        nullable=False,
        doc="Campaign priority (1=highest, 10=lowest)",
    )

    # Script and messaging
    call_script: Mapped[str | None] = mapped_column(Text, nullable=True)
    sms_template: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Results summary (denormalized for quick access)
    total_contacts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    contacts_called: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    contacts_reached: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    appointments_booked: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Relationships
    metrics: Mapped[list["CampaignMetricsModel"]] = relationship(
        "CampaignMetricsModel",
        back_populates="campaign",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    contacts: Mapped[list["CampaignContactModel"]] = relationship(
        "CampaignContactModel",
        back_populates="campaign",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    __table_args__ = (
        Index("ix_recall_campaigns_status_date", "status", "start_date"),
        Index("ix_recall_campaigns_industry_status", "industry", "status"),
    )

    def __repr__(self) -> str:
        return f"<RecallCampaign {self.name} ({self.status})>"

    @property
    def target_criteria(self) -> dict[str, Any]:
        """Get target criteria as dictionary."""
        import json
        if self.target_criteria_json:
            return json.loads(self.target_criteria_json)
        return {}

    @target_criteria.setter
    def target_criteria(self, value: dict[str, Any]) -> None:
        """Set target criteria from dictionary."""
        import json
        self.target_criteria_json = json.dumps(value, ensure_ascii=False) if value else None

    def calculate_progress(self) -> dict[str, Any]:
        """Calculate campaign progress metrics."""
        if self.total_contacts == 0:
            return {
                "progress_percent": 0,
                "reach_rate": 0,
                "conversion_rate": 0,
            }

        return {
            "progress_percent": (self.contacts_called / self.total_contacts) * 100,
            "reach_rate": (self.contacts_reached / self.total_contacts) * 100,
            "conversion_rate": (
                (self.appointments_booked / self.contacts_reached) * 100
                if self.contacts_reached > 0 else 0
            ),
        }

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for API responses."""
        progress = self.calculate_progress()
        return {
            "id": str(self.id),
            "name": self.name,
            "description": self.description,
            "campaign_type": self.campaign_type,
            "industry": self.industry,
            "tenant_id": str(self.tenant_id) if self.tenant_id else None,
            "start_date": self.start_date.isoformat(),
            "end_date": self.end_date.isoformat() if self.end_date else None,
            "status": self.status,
            "target_criteria": self.target_criteria,
            "max_attempts": self.max_attempts,
            "call_interval_hours": self.call_interval_hours,
            "priority": self.priority,
            "total_contacts": self.total_contacts,
            "contacts_called": self.contacts_called,
            "contacts_reached": self.contacts_reached,
            "appointments_booked": self.appointments_booked,
            "progress_percent": round(progress["progress_percent"], 2),
            "reach_rate": round(progress["reach_rate"], 2),
            "conversion_rate": round(progress["conversion_rate"], 2),
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


# ============================================================================
# Campaign Contact Model
# ============================================================================

class CampaignContactModel(Base, UUIDMixin, TimestampMixin):
    """Individual contact within a recall campaign.

    Tracks the status and call history for each contact in a campaign.
    Supports retry logic and scheduling.
    """

    __tablename__ = "campaign_contacts"

    # Campaign reference
    campaign_id: Mapped[UUID] = mapped_column(
        ForeignKey("recall_campaigns.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Contact reference (links to CRM)
    contact_id: Mapped[UUID] = mapped_column(
        ForeignKey("contacts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Status tracking
    status: Mapped[str] = mapped_column(
        String(24),
        nullable=False,
        default="pending",
        index=True,
        doc="Status: pending, scheduled, calling, reached, converted, failed, opted_out, invalid",
    )

    # Priority within campaign
    priority: Mapped[int] = mapped_column(
        Integer,
        default=5,
        nullable=False,
        doc="Contact priority (1=highest, 10=lowest)",
    )

    # Call attempt tracking
    attempts: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
        doc="Number of call attempts made",
    )
    max_attempts: Mapped[int] = mapped_column(
        Integer,
        default=3,
        nullable=False,
        doc="Maximum attempts for this contact (overrides campaign default)",
    )

    # Scheduling
    next_attempt_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        index=True,
        doc="When to attempt next call",
    )
    last_attempt_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        doc="When last call was attempted",
    )

    # Call results
    last_call_result: Mapped[str | None] = mapped_column(
        String(32),
        nullable=True,
        doc="Result: answered, voicemail, no_answer, busy, failed, invalid_number",
    )
    last_call_duration: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        doc="Duration of last call in seconds",
    )
    last_call_id: Mapped[UUID | None] = mapped_column(
        nullable=True,
        doc="Reference to last call record",
    )

    # Outcome
    outcome: Mapped[str | None] = mapped_column(
        String(32),
        nullable=True,
        doc="Final outcome: appointment_booked, callback_requested, declined, no_contact",
    )
    appointment_id: Mapped[UUID | None] = mapped_column(
        nullable=True,
        doc="Reference to booked appointment if applicable",
    )

    # Contact data snapshot (at time of adding to campaign)
    phone_number: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        doc="Phone number to call",
    )
    contact_name: Mapped[str | None] = mapped_column(
        String(128),
        nullable=True,
        doc="Contact name for personalization",
    )

    # Custom data (JSON)
    custom_data_json: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        doc="JSON-encoded custom data for call script personalization",
    )

    # Notes
    notes: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        doc="Notes from calls or manual updates",
    )

    # Opt-out tracking
    opted_out: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
        doc="Contact opted out of this campaign",
    )
    opted_out_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # Relationships
    campaign: Mapped["RecallCampaignModel"] = relationship(
        "RecallCampaignModel",
        back_populates="contacts",
        lazy="selectin",
    )

    __table_args__ = (
        UniqueConstraint("campaign_id", "contact_id", name="uq_campaign_contact"),
        Index("ix_campaign_contacts_status_next", "status", "next_attempt_at"),
        Index("ix_campaign_contacts_campaign_status", "campaign_id", "status"),
        Index("ix_campaign_contacts_phone", "phone_number"),
    )

    def __repr__(self) -> str:
        return f"<CampaignContact {self.contact_id} in {self.campaign_id}: {self.status}>"

    @property
    def custom_data(self) -> dict[str, Any]:
        """Get custom data as dictionary."""
        import json
        if self.custom_data_json:
            return json.loads(self.custom_data_json)
        return {}

    @custom_data.setter
    def custom_data(self, value: dict[str, Any]) -> None:
        """Set custom data from dictionary."""
        import json
        self.custom_data_json = json.dumps(value, ensure_ascii=False) if value else None

    def can_attempt(self) -> bool:
        """Check if another call attempt can be made."""
        if self.status in ("converted", "opted_out", "invalid"):
            return False
        if self.attempts >= self.max_attempts:
            return False
        return True

    def schedule_next_attempt(self, interval_hours: int = 24) -> None:
        """Schedule the next call attempt."""
        from datetime import timedelta
        if self.can_attempt():
            self.next_attempt_at = datetime.now(timezone.utc) + timedelta(hours=interval_hours)
            self.status = "scheduled"
        else:
            self.status = "failed" if self.attempts >= self.max_attempts else self.status

    def record_attempt(
        self,
        result: str,
        duration: int | None = None,
        call_id: UUID | None = None,
    ) -> None:
        """Record a call attempt result."""
        self.attempts += 1
        self.last_attempt_at = datetime.now(timezone.utc)
        self.last_call_result = result
        self.last_call_duration = duration
        self.last_call_id = call_id

        # Update status based on result
        if result == "answered":
            self.status = "reached"
        elif result in ("invalid_number", "disconnected"):
            self.status = "invalid"
        elif result == "opt_out":
            self.status = "opted_out"
            self.opted_out = True
            self.opted_out_at = datetime.now(timezone.utc)
        elif self.attempts >= self.max_attempts:
            self.status = "failed"
        else:
            self.status = "pending"  # Ready for retry

    def convert(self, outcome: str, appointment_id: UUID | None = None) -> None:
        """Mark contact as converted with outcome."""
        self.status = "converted"
        self.outcome = outcome
        self.appointment_id = appointment_id

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for API responses."""
        return {
            "id": str(self.id),
            "campaign_id": str(self.campaign_id),
            "contact_id": str(self.contact_id),
            "status": self.status,
            "priority": self.priority,
            "attempts": self.attempts,
            "max_attempts": self.max_attempts,
            "next_attempt_at": self.next_attempt_at.isoformat() if self.next_attempt_at else None,
            "last_attempt_at": self.last_attempt_at.isoformat() if self.last_attempt_at else None,
            "last_call_result": self.last_call_result,
            "last_call_duration": self.last_call_duration,
            "outcome": self.outcome,
            "appointment_id": str(self.appointment_id) if self.appointment_id else None,
            "phone_number": self.phone_number,
            "contact_name": self.contact_name,
            "custom_data": self.custom_data,
            "notes": self.notes,
            "opted_out": self.opted_out,
            "can_attempt": self.can_attempt(),
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


# ============================================================================
# Dashboard Snapshot Model
# ============================================================================

class DashboardSnapshotModel(Base, UUIDMixin):
    """Point-in-time dashboard KPI snapshots.

    Stores complete dashboard state for historical comparison
    and trend analysis. Created periodically (hourly/daily).
    """

    __tablename__ = "dashboard_snapshots"

    # Snapshot timestamp
    snapshot_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )

    # Snapshot type
    snapshot_type: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default="hourly",
        doc="Type: realtime, hourly, daily, weekly",
    )

    # Context
    industry: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    tenant_id: Mapped[UUID | None] = mapped_column(nullable=True, index=True)

    # KPI values (denormalized for fast retrieval)
    # Call KPIs
    calls_today: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    calls_this_week: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    calls_this_month: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    avg_call_duration: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    completion_rate: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    ai_resolution_rate: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)

    # Appointment KPIs
    appointments_today: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    appointments_this_week: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    appointment_conversion_rate: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    no_show_rate: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)

    # Campaign KPIs
    active_campaigns: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    campaign_contacts_reached: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    campaign_conversion_rate: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)

    # Contact KPIs
    total_contacts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    new_contacts_today: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    new_contacts_this_week: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Service KPIs (for handwerk)
    service_calls_today: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    quotes_sent_today: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Performance indicators
    peak_hour: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        doc="Hour with most calls today (0-23)",
    )
    avg_wait_time: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    missed_calls_today: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    __table_args__ = (
        Index("ix_dashboard_snapshots_type_time", "snapshot_type", "snapshot_at"),
        Index("ix_dashboard_snapshots_industry_time", "industry", "snapshot_at"),
    )

    def __repr__(self) -> str:
        return f"<DashboardSnapshot {self.snapshot_type} at {self.snapshot_at}>"

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for API responses."""
        return {
            "id": str(self.id),
            "snapshot_at": self.snapshot_at.isoformat(),
            "snapshot_type": self.snapshot_type,
            "industry": self.industry,
            "tenant_id": str(self.tenant_id) if self.tenant_id else None,
            "calls": {
                "today": self.calls_today,
                "this_week": self.calls_this_week,
                "this_month": self.calls_this_month,
                "avg_duration": round(self.avg_call_duration, 2),
                "completion_rate": round(self.completion_rate, 2),
                "ai_resolution_rate": round(self.ai_resolution_rate, 2),
                "missed_today": self.missed_calls_today,
                "peak_hour": self.peak_hour,
                "avg_wait_time": round(self.avg_wait_time, 2),
            },
            "appointments": {
                "today": self.appointments_today,
                "this_week": self.appointments_this_week,
                "conversion_rate": round(self.appointment_conversion_rate, 2),
                "no_show_rate": round(self.no_show_rate, 2),
            },
            "campaigns": {
                "active": self.active_campaigns,
                "contacts_reached": self.campaign_contacts_reached,
                "conversion_rate": round(self.campaign_conversion_rate, 2),
            },
            "contacts": {
                "total": self.total_contacts,
                "new_today": self.new_contacts_today,
                "new_this_week": self.new_contacts_this_week,
            },
            "service": {
                "calls_today": self.service_calls_today,
                "quotes_sent_today": self.quotes_sent_today,
            },
        }
