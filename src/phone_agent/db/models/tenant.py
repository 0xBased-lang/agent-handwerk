"""Multi-Tenant ORM Models for Phone Agent Platform.

Contains models for the multi-tenant SaaS architecture:
- TenantModel: Company/organization using the platform (the tenant root)
- DepartmentModel: Internal departments within a tenant
- WorkerModel: Employees/workers within a tenant
- TaskModel: Unified task queue (from phone, email, etc.)
- RoutingRuleModel: Custom routing rules per tenant
"""
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID

from sqlalchemy import (
    String,
    Text,
    Integer,
    Float,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
)
from sqlalchemy.dialects.sqlite import JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from phone_agent.db.base import (
    Base,
    UUIDMixin,
    TimestampMixin,
    SoftDeleteMixin,
    UUIDType,
)

if TYPE_CHECKING:
    pass


class TenantModel(Base, UUIDMixin, TimestampMixin, SoftDeleteMixin):
    """Tenant (Platform Customer) ORM model.

    Represents a company that uses the IT-Friends platform.
    This is the root of all tenant-scoped data. All other
    tenant-aware models reference this via tenant_id.

    Example: "Müller SHK GmbH" is a Handwerk company in Hechingen
    that uses our platform to handle their customer service.
    """

    __tablename__ = "tenants"

    # Company identification
    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True,
        comment="Display name (e.g., 'Müller SHK')",
    )
    legal_name: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        comment="Official registered name",
    )
    tax_id: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        comment="Steuernummer / USt-IdNr",
    )
    slug: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        unique=True,
        index=True,
        comment="URL-safe identifier (e.g., 'mueller-shk')",
    )

    # Industry classification
    industry: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="handwerk",
        index=True,
        comment="Industry module: handwerk, gesundheit, freie_berufe, gastro",
    )
    trade_category: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        comment="Handwerk: shk, elektro, sanitaer, klima, etc.",
    )

    # Contact info
    phone: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        index=True,
    )
    email: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )
    website: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    # Address (HQ for geographic routing)
    address_street: Mapped[str | None] = mapped_column(String(255), nullable=True)
    address_zip: Mapped[str | None] = mapped_column(
        String(10),
        nullable=True,
        index=True,
        comment="PLZ for radius calculation",
    )
    address_city: Mapped[str | None] = mapped_column(String(100), nullable=True)
    address_country: Mapped[str] = mapped_column(
        String(100),
        default="Germany",
        nullable=False,
    )

    # Geocoded coordinates (pre-calculated for performance)
    latitude: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
        comment="Pre-geocoded latitude",
    )
    longitude: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
        comment="Pre-geocoded longitude",
    )
    service_radius_km: Mapped[int] = mapped_column(
        Integer,
        default=50,
        nullable=False,
        comment="Service area radius in kilometers",
    )

    # Plan & limits
    plan: Mapped[str] = mapped_column(
        String(50),
        default="starter",
        nullable=False,
        comment="Subscription plan: starter, professional, enterprise",
    )
    max_users: Mapped[int] = mapped_column(
        Integer,
        default=5,
        nullable=False,
    )
    max_tasks_per_month: Mapped[int] = mapped_column(
        Integer,
        default=500,
        nullable=False,
    )
    max_storage_gb: Mapped[int] = mapped_column(
        Integer,
        default=10,
        nullable=False,
    )

    # Usage tracking (updated by background jobs)
    current_users: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    current_tasks_this_month: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    current_storage_gb: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)

    # Status
    status: Mapped[str] = mapped_column(
        String(50),
        default="active",
        nullable=False,
        index=True,
        comment="active, suspended, trial, cancelled",
    )
    trial_ends_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # Customization (JSON blobs for flexibility)
    settings_json: Mapped[dict[str, Any] | None] = mapped_column(
        JSON,
        nullable=True,
        comment="Routing rules, feature flags, prompts overrides",
    )
    branding_json: Mapped[dict[str, Any] | None] = mapped_column(
        JSON,
        nullable=True,
        comment="Logo URL, colors, custom domain",
    )
    email_config_json: Mapped[dict[str, Any] | None] = mapped_column(
        JSON,
        nullable=True,
        comment="IMAP polling configuration (encrypted password)",
    )

    # Relationships
    departments: Mapped[list["DepartmentModel"]] = relationship(
        back_populates="tenant",
        lazy="selectin",
        cascade="all, delete-orphan",
    )
    workers: Mapped[list["WorkerModel"]] = relationship(
        back_populates="tenant",
        lazy="dynamic",
        cascade="all, delete-orphan",
    )
    tasks: Mapped[list["TaskModel"]] = relationship(
        back_populates="tenant",
        lazy="dynamic",
        cascade="all, delete-orphan",
    )
    routing_rules: Mapped[list["RoutingRuleModel"]] = relationship(
        back_populates="tenant",
        lazy="selectin",
        cascade="all, delete-orphan",
    )

    # Indexes
    __table_args__ = (
        Index("ix_tenants_industry_status", "industry", "status"),
        Index("ix_tenants_zip_radius", "address_zip", "service_radius_km"),
    )

    def to_dict(self) -> dict[str, Any]:
        """Convert model to dictionary for API responses."""
        return {
            "id": str(self.id),
            "name": self.name,
            "legal_name": self.legal_name,
            "slug": self.slug,
            "industry": self.industry,
            "trade_category": self.trade_category,
            "phone": self.phone,
            "email": self.email,
            "website": self.website,
            "address": {
                "street": self.address_street,
                "zip": self.address_zip,
                "city": self.address_city,
                "country": self.address_country,
            },
            "location": {
                "latitude": self.latitude,
                "longitude": self.longitude,
                "service_radius_km": self.service_radius_km,
            },
            "plan": self.plan,
            "limits": {
                "max_users": self.max_users,
                "max_tasks_per_month": self.max_tasks_per_month,
                "max_storage_gb": self.max_storage_gb,
            },
            "usage": {
                "current_users": self.current_users,
                "current_tasks_this_month": self.current_tasks_this_month,
                "current_storage_gb": self.current_storage_gb,
            },
            "status": self.status,
            "trial_ends_at": self.trial_ends_at.isoformat() if self.trial_ends_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class DepartmentModel(Base, UUIDMixin, TimestampMixin):
    """Department ORM model.

    Represents internal departments within a tenant.
    Tasks are routed to departments based on routing rules.

    Examples: Kundendienst, Buchhaltung, Werkstatt, Außendienst
    """

    __tablename__ = "departments"

    # Tenant reference
    tenant_id: Mapped[UUID] = mapped_column(
        UUIDType(),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Department info
    name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="Display name (e.g., 'Kundendienst')",
    )
    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    # Routing configuration
    handles_task_types: Mapped[list[str] | None] = mapped_column(
        JSON,
        nullable=True,
        comment='Task types this dept handles: ["repairs", "quotes", "complaints"]',
    )
    handles_urgency_levels: Mapped[list[str] | None] = mapped_column(
        JSON,
        nullable=True,
        comment='Urgency levels: ["notfall", "dringend", "normal"]',
    )
    handles_trade_categories: Mapped[list[str] | None] = mapped_column(
        JSON,
        nullable=True,
        comment='Trade categories: ["shk", "elektro"]',
    )

    # Contact (for notifications)
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Availability
    working_hours: Mapped[dict[str, str] | None] = mapped_column(
        JSON,
        nullable=True,
        comment='{"monday": "08:00-17:00", "tuesday": "08:00-17:00", ...}',
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )

    # Display order
    sort_order: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )

    # Relationships
    tenant: Mapped["TenantModel"] = relationship(back_populates="departments")
    workers: Mapped[list["WorkerModel"]] = relationship(
        back_populates="department",
        lazy="selectin",
    )
    tasks: Mapped[list["TaskModel"]] = relationship(
        back_populates="assigned_department",
        lazy="dynamic",
        foreign_keys="TaskModel.assigned_department_id",
    )

    # Indexes
    __table_args__ = (
        Index("ix_departments_tenant_active", "tenant_id", "is_active"),
    )

    def to_dict(self) -> dict[str, Any]:
        """Convert model to dictionary for API responses."""
        return {
            "id": str(self.id),
            "tenant_id": str(self.tenant_id),
            "name": self.name,
            "description": self.description,
            "handles_task_types": self.handles_task_types or [],
            "handles_urgency_levels": self.handles_urgency_levels or [],
            "handles_trade_categories": self.handles_trade_categories or [],
            "phone": self.phone,
            "email": self.email,
            "working_hours": self.working_hours or {},
            "is_active": self.is_active,
            "sort_order": self.sort_order,
            "worker_count": len(self.workers) if self.workers else 0,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class WorkerModel(Base, UUIDMixin, TimestampMixin, SoftDeleteMixin):
    """Worker (Employee) ORM model.

    Represents employees within a tenant who can be assigned tasks.
    Workers belong to departments and have specific skills/certifications.

    Examples: Hans (Monteur), Maria (Bürokraft), Peter (Meister)
    """

    __tablename__ = "workers"

    # Tenant reference
    tenant_id: Mapped[UUID] = mapped_column(
        UUIDType(),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Department assignment
    department_id: Mapped[UUID | None] = mapped_column(
        UUIDType(),
        ForeignKey("departments.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Identity
    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    last_name: Mapped[str] = mapped_column(String(100), nullable=False)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # Role & permissions
    role: Mapped[str] = mapped_column(
        String(50),
        default="worker",
        nullable=False,
        comment="owner, admin, dispatcher, worker",
    )

    # Skills (for smart routing)
    trade_categories: Mapped[list[str] | None] = mapped_column(
        JSON,
        nullable=True,
        comment='Skills: ["shk", "elektro", "sanitaer"]',
    )
    certifications: Mapped[list[str] | None] = mapped_column(
        JSON,
        nullable=True,
        comment='Certifications: ["gas_certified", "electrical_license"]',
    )

    # Location (for proximity routing)
    home_plz: Mapped[str | None] = mapped_column(
        String(10),
        nullable=True,
        comment="Home postal code for route optimization",
    )
    home_latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    home_longitude: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Availability
    working_hours: Mapped[dict[str, str] | None] = mapped_column(
        JSON,
        nullable=True,
        comment='{"monday": "08:00-17:00", ...}',
    )
    vacation_dates: Mapped[list[str] | None] = mapped_column(
        JSON,
        nullable=True,
        comment='["2025-01-20", "2025-01-21"]',
    )
    max_tasks_per_day: Mapped[int] = mapped_column(
        Integer,
        default=10,
        nullable=False,
    )

    # Status
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )

    # Analytics
    total_tasks_completed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    avg_completion_time_minutes: Mapped[float | None] = mapped_column(Float, nullable=True)
    customer_rating: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
        comment="Average rating 1.0-5.0",
    )

    # External system reference
    external_id: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        comment="ID in external HR/ERP system",
    )

    # Relationships
    tenant: Mapped["TenantModel"] = relationship(back_populates="workers")
    department: Mapped["DepartmentModel"] = relationship(back_populates="workers")
    assigned_tasks: Mapped[list["TaskModel"]] = relationship(
        back_populates="assigned_worker",
        lazy="dynamic",
        foreign_keys="TaskModel.assigned_worker_id",
    )

    # Indexes
    __table_args__ = (
        Index("ix_workers_tenant_active", "tenant_id", "is_active"),
        Index("ix_workers_tenant_department", "tenant_id", "department_id"),
    )

    @property
    def full_name(self) -> str:
        """Get full name."""
        return f"{self.first_name} {self.last_name}"

    def to_dict(self) -> dict[str, Any]:
        """Convert model to dictionary for API responses."""
        return {
            "id": str(self.id),
            "tenant_id": str(self.tenant_id),
            "department_id": str(self.department_id) if self.department_id else None,
            "first_name": self.first_name,
            "last_name": self.last_name,
            "full_name": self.full_name,
            "email": self.email,
            "phone": self.phone,
            "role": self.role,
            "trade_categories": self.trade_categories or [],
            "certifications": self.certifications or [],
            "home_plz": self.home_plz,
            "working_hours": self.working_hours or {},
            "max_tasks_per_day": self.max_tasks_per_day,
            "is_active": self.is_active,
            "stats": {
                "total_tasks_completed": self.total_tasks_completed,
                "avg_completion_time_minutes": self.avg_completion_time_minutes,
                "customer_rating": self.customer_rating,
            },
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class TaskModel(Base, UUIDMixin, TimestampMixin):
    """Unified Task ORM model.

    Represents tasks created from any source (phone, email, form).
    This is the central work item that gets routed to departments/workers.

    A task has a lifecycle: new → assigned → in_progress → completed
    """

    __tablename__ = "tasks"

    # Tenant reference
    tenant_id: Mapped[UUID] = mapped_column(
        UUIDType(),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Source information
    source_type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        index=True,
        comment="phone, email, form, whatsapp, manual",
    )
    source_id: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        comment="Reference to original call_id, email_id, etc.",
    )

    # Classification (from AI)
    task_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
        comment="repairs, quotes, complaints, billing, appointment, general",
    )
    urgency: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        index=True,
        comment="notfall, dringend, normal, routine",
    )
    trade_category: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        comment="shk, elektro, sanitaer, etc.",
    )

    # Customer information
    customer_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    customer_phone: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    customer_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    customer_address: Mapped[str | None] = mapped_column(Text, nullable=True)
    customer_plz: Mapped[str | None] = mapped_column(String(10), nullable=True, index=True)

    # Content
    title: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="Short summary of the task",
    )
    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Full description from customer",
    )
    ai_summary: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="AI-generated summary",
    )
    attachments_json: Mapped[list[dict] | None] = mapped_column(
        JSON,
        nullable=True,
        comment='[{"filename": "...", "url": "...", "type": "image/jpeg"}]',
    )

    # Location (for geographic routing)
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    distance_from_hq_km: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
        comment="Pre-calculated distance from tenant HQ",
    )

    # Routing
    routing_priority: Mapped[int] = mapped_column(
        Integer,
        default=100,
        nullable=False,
        comment="Lower = higher priority (0=notfall, 50=dringend, 100=normal)",
    )
    routing_reason: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Why was this routed here",
    )
    assigned_department_id: Mapped[UUID | None] = mapped_column(
        UUIDType(),
        ForeignKey("departments.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    assigned_worker_id: Mapped[UUID | None] = mapped_column(
        UUIDType(),
        ForeignKey("workers.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    assigned_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    assigned_by: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        comment="auto_routing, manual:worker_id",
    )

    # Status tracking
    status: Mapped[str] = mapped_column(
        String(50),
        default="new",
        nullable=False,
        index=True,
        comment="new, assigned, in_progress, completed, cancelled",
    )
    due_date: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # Notes & metadata
    internal_notes: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Internal notes from workers",
    )
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(
        JSON,
        nullable=True,
    )

    # Relationships
    tenant: Mapped["TenantModel"] = relationship(back_populates="tasks")
    assigned_department: Mapped["DepartmentModel"] = relationship(
        back_populates="tasks",
        foreign_keys=[assigned_department_id],
    )
    assigned_worker: Mapped["WorkerModel"] = relationship(
        back_populates="assigned_tasks",
        foreign_keys=[assigned_worker_id],
    )

    # Indexes
    __table_args__ = (
        Index("ix_tasks_tenant_status", "tenant_id", "status"),
        Index("ix_tasks_tenant_urgency", "tenant_id", "urgency"),
        Index("ix_tasks_tenant_type_status", "tenant_id", "task_type", "status"),
        Index("ix_tasks_tenant_routing", "tenant_id", "routing_priority", "created_at"),
        Index("ix_tasks_assigned", "tenant_id", "assigned_worker_id", "status"),
    )

    def to_dict(self) -> dict[str, Any]:
        """Convert model to dictionary for API responses."""
        return {
            "id": str(self.id),
            "tenant_id": str(self.tenant_id),
            "source": {
                "type": self.source_type,
                "id": self.source_id,
            },
            "classification": {
                "task_type": self.task_type,
                "urgency": self.urgency,
                "trade_category": self.trade_category,
            },
            "customer": {
                "name": self.customer_name,
                "phone": self.customer_phone,
                "email": self.customer_email,
                "address": self.customer_address,
                "plz": self.customer_plz,
            },
            "content": {
                "title": self.title,
                "description": self.description,
                "ai_summary": self.ai_summary,
                "attachments": self.attachments_json or [],
            },
            "location": {
                "latitude": self.latitude,
                "longitude": self.longitude,
                "distance_from_hq_km": self.distance_from_hq_km,
            },
            "routing": {
                "priority": self.routing_priority,
                "reason": self.routing_reason,
                "assigned_department_id": str(self.assigned_department_id) if self.assigned_department_id else None,
                "assigned_worker_id": str(self.assigned_worker_id) if self.assigned_worker_id else None,
                "assigned_at": self.assigned_at.isoformat() if self.assigned_at else None,
                "assigned_by": self.assigned_by,
            },
            "status": self.status,
            "due_date": self.due_date.isoformat() if self.due_date else None,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "internal_notes": self.internal_notes,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class RoutingRuleModel(Base, UUIDMixin, TimestampMixin):
    """Routing Rule ORM model.

    Custom routing rules defined by each tenant.
    Rules are evaluated in priority order to determine
    where to route incoming tasks.

    Example: "If task_type=repairs AND urgency=notfall, route to Notdienst department"
    """

    __tablename__ = "routing_rules"

    # Tenant reference
    tenant_id: Mapped[UUID] = mapped_column(
        UUIDType(),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Rule identification
    name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="Human-readable rule name",
    )
    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    # Priority (lower = evaluate first)
    priority: Mapped[int] = mapped_column(
        Integer,
        default=100,
        nullable=False,
        comment="Lower numbers are evaluated first",
    )

    # Conditions (all must match)
    conditions: Mapped[dict[str, Any]] = mapped_column(
        JSON,
        nullable=False,
        comment='{"task_type": "repairs", "urgency": ["notfall", "dringend"]}',
    )

    # Actions (what to do when conditions match)
    route_to_department_id: Mapped[UUID | None] = mapped_column(
        UUIDType(),
        ForeignKey("departments.id", ondelete="SET NULL"),
        nullable=True,
    )
    route_to_worker_id: Mapped[UUID | None] = mapped_column(
        UUIDType(),
        ForeignKey("workers.id", ondelete="SET NULL"),
        nullable=True,
    )
    set_priority: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        comment="Override routing_priority",
    )
    send_notification: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )
    notification_channels: Mapped[list[str] | None] = mapped_column(
        JSON,
        nullable=True,
        comment='["sms", "email", "push"]',
    )
    escalate_after_minutes: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        comment="Escalate if not handled within X minutes",
    )

    # Status
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )

    # Relationships
    tenant: Mapped["TenantModel"] = relationship(back_populates="routing_rules")

    # Indexes
    __table_args__ = (
        Index("ix_routing_rules_tenant_priority", "tenant_id", "priority"),
        Index("ix_routing_rules_tenant_active", "tenant_id", "is_active"),
    )

    def to_dict(self) -> dict[str, Any]:
        """Convert model to dictionary for API responses."""
        return {
            "id": str(self.id),
            "tenant_id": str(self.tenant_id),
            "name": self.name,
            "description": self.description,
            "priority": self.priority,
            "conditions": self.conditions,
            "actions": {
                "route_to_department_id": str(self.route_to_department_id) if self.route_to_department_id else None,
                "route_to_worker_id": str(self.route_to_worker_id) if self.route_to_worker_id else None,
                "set_priority": self.set_priority,
                "send_notification": self.send_notification,
                "notification_channels": self.notification_channels or [],
                "escalate_after_minutes": self.escalate_after_minutes,
            },
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

    def matches(self, task: TaskModel) -> bool:
        """Check if this rule's conditions match the given task.

        All conditions must match for the rule to apply.
        Supports equality and list membership checks.
        """
        for field, expected in self.conditions.items():
            actual = getattr(task, field, None)

            if isinstance(expected, list):
                # List membership check
                if actual not in expected:
                    return False
            else:
                # Equality check
                if actual != expected:
                    return False

        return True
