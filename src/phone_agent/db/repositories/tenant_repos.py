"""Repositories for multi-tenant models.

Provides data access for:
- TenantRepository: Company/tenant management
- DepartmentRepository: Department CRUD with tenant isolation
- WorkerRepository: Worker management with skills and availability
- TaskRepository: Task management with routing and filtering
- RoutingRuleRepository: Routing rules with priority ordering
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Sequence
from uuid import UUID

from sqlalchemy import select, func, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from phone_agent.db.repositories.base import BaseRepository
from phone_agent.db.models.tenant import (
    TenantModel,
    DepartmentModel,
    WorkerModel,
    TaskModel,
    RoutingRuleModel,
)


class TenantRepository(BaseRepository[TenantModel]):
    """Repository for tenant (company) management."""

    def __init__(self, session: AsyncSession):
        """Initialize repository."""
        super().__init__(TenantModel, session)

    async def get_by_subdomain(self, subdomain: str) -> TenantModel | None:
        """Get tenant by subdomain.

        Args:
            subdomain: Tenant subdomain (e.g., "mueller-shk")

        Returns:
            TenantModel or None
        """
        stmt = select(self._model).where(self._model.subdomain == subdomain)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_phone(self, phone: str) -> TenantModel | None:
        """Get tenant by phone number.

        Args:
            phone: Phone number to match

        Returns:
            TenantModel or None
        """
        stmt = select(self._model).where(self._model.phone == phone)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_active_tenants(
        self,
        industry: str | None = None,
        skip: int = 0,
        limit: int = 100,
    ) -> Sequence[TenantModel]:
        """Get all active tenants, optionally filtered by industry.

        Args:
            industry: Optional industry filter
            skip: Pagination offset
            limit: Max results

        Returns:
            List of active tenants
        """
        stmt = select(self._model).where(self._model.status == "active")

        if industry:
            stmt = stmt.where(self._model.industry == industry)

        stmt = stmt.offset(skip).limit(limit).order_by(self._model.name)
        result = await self._session.execute(stmt)
        return result.scalars().all()

    async def get_with_departments(self, tenant_id: UUID) -> TenantModel | None:
        """Get tenant with departments eagerly loaded.

        Args:
            tenant_id: Tenant UUID

        Returns:
            TenantModel with departments or None
        """
        stmt = (
            select(self._model)
            .where(self._model.id == tenant_id)
            .options(selectinload(self._model.departments))
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()


class DepartmentRepository(BaseRepository[DepartmentModel]):
    """Repository for department management with tenant isolation."""

    def __init__(self, session: AsyncSession):
        """Initialize repository."""
        super().__init__(DepartmentModel, session)

    async def get_by_tenant(
        self,
        tenant_id: UUID,
        include_inactive: bool = False,
    ) -> Sequence[DepartmentModel]:
        """Get all departments for a tenant.

        Args:
            tenant_id: Tenant UUID
            include_inactive: Include inactive departments

        Returns:
            List of departments
        """
        stmt = select(self._model).where(self._model.tenant_id == tenant_id)

        if not include_inactive:
            stmt = stmt.where(self._model.is_active == True)

        stmt = stmt.order_by(self._model.name)
        result = await self._session.execute(stmt)
        return result.scalars().all()

    async def get_by_task_type(
        self,
        tenant_id: UUID,
        task_type: str,
    ) -> Sequence[DepartmentModel]:
        """Get departments that handle a specific task type.

        Args:
            tenant_id: Tenant UUID
            task_type: Task type (e.g., "repairs", "quotes")

        Returns:
            List of matching departments
        """
        # Query departments where handles_task_types contains the task_type
        stmt = (
            select(self._model)
            .where(
                and_(
                    self._model.tenant_id == tenant_id,
                    self._model.is_active == True,
                    # JSON contains check - SQLite compatible
                    self._model.handles_task_types.contains(f'"{task_type}"'),
                )
            )
            .order_by(self._model.name)
        )
        result = await self._session.execute(stmt)
        return result.scalars().all()

    async def get_with_workers(
        self,
        department_id: UUID,
        tenant_id: UUID,
    ) -> DepartmentModel | None:
        """Get department with workers eagerly loaded.

        Args:
            department_id: Department UUID
            tenant_id: Tenant UUID (for isolation)

        Returns:
            DepartmentModel with workers or None
        """
        stmt = (
            select(self._model)
            .where(
                and_(
                    self._model.id == department_id,
                    self._model.tenant_id == tenant_id,
                )
            )
            .options(selectinload(self._model.workers))
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()


class WorkerRepository(BaseRepository[WorkerModel]):
    """Repository for worker management."""

    def __init__(self, session: AsyncSession):
        """Initialize repository."""
        super().__init__(WorkerModel, session)

    async def get_by_tenant(
        self,
        tenant_id: UUID,
        department_id: UUID | None = None,
        include_inactive: bool = False,
    ) -> Sequence[WorkerModel]:
        """Get workers for a tenant, optionally filtered by department.

        Args:
            tenant_id: Tenant UUID
            department_id: Optional department filter
            include_inactive: Include inactive workers

        Returns:
            List of workers
        """
        stmt = select(self._model).where(self._model.tenant_id == tenant_id)

        if department_id:
            stmt = stmt.where(self._model.department_id == department_id)

        if not include_inactive:
            stmt = stmt.where(self._model.is_active == True)

        stmt = stmt.order_by(self._model.last_name, self._model.first_name)
        result = await self._session.execute(stmt)
        return result.scalars().all()

    async def get_available_workers(
        self,
        tenant_id: UUID,
        department_id: UUID | None = None,
        trade_categories: list[str] | None = None,
    ) -> Sequence[WorkerModel]:
        """Get available workers for assignment.

        Args:
            tenant_id: Tenant UUID
            department_id: Optional department filter
            trade_categories: Optional trade category filter

        Returns:
            List of available workers
        """
        stmt = select(self._model).where(
            and_(
                self._model.tenant_id == tenant_id,
                self._model.is_active == True,
                self._model.is_available == True,
            )
        )

        if department_id:
            stmt = stmt.where(self._model.department_id == department_id)

        # TODO: Add trade_categories filter with JSON contains

        # Order by workload (least loaded first)
        stmt = stmt.order_by(self._model.current_task_count)
        result = await self._session.execute(stmt)
        return result.scalars().all()

    async def get_by_email(
        self,
        tenant_id: UUID,
        email: str,
    ) -> WorkerModel | None:
        """Get worker by email.

        Args:
            tenant_id: Tenant UUID
            email: Worker email

        Returns:
            WorkerModel or None
        """
        stmt = select(self._model).where(
            and_(
                self._model.tenant_id == tenant_id,
                self._model.email == email,
            )
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def increment_task_count(self, worker_id: UUID) -> None:
        """Increment worker's current task count.

        Args:
            worker_id: Worker UUID
        """
        worker = await self.get(worker_id)
        if worker:
            worker.current_task_count = (worker.current_task_count or 0) + 1
            await self._session.flush()

    async def decrement_task_count(self, worker_id: UUID) -> None:
        """Decrement worker's current task count.

        Args:
            worker_id: Worker UUID
        """
        worker = await self.get(worker_id)
        if worker and worker.current_task_count and worker.current_task_count > 0:
            worker.current_task_count -= 1
            await self._session.flush()


class TaskRepository(BaseRepository[TaskModel]):
    """Repository for task management with routing support."""

    def __init__(self, session: AsyncSession):
        """Initialize repository."""
        super().__init__(TaskModel, session)

    async def get_by_tenant(
        self,
        tenant_id: UUID,
        status: str | list[str] | None = None,
        task_type: str | None = None,
        urgency: str | None = None,
        skip: int = 0,
        limit: int = 100,
    ) -> Sequence[TaskModel]:
        """Get tasks for a tenant with filtering.

        Args:
            tenant_id: Tenant UUID
            status: Optional status filter (single or list)
            task_type: Optional task type filter
            urgency: Optional urgency filter
            skip: Pagination offset
            limit: Max results

        Returns:
            List of tasks
        """
        stmt = select(self._model).where(self._model.tenant_id == tenant_id)

        if status:
            if isinstance(status, list):
                stmt = stmt.where(self._model.status.in_(status))
            else:
                stmt = stmt.where(self._model.status == status)

        if task_type:
            stmt = stmt.where(self._model.task_type == task_type)

        if urgency:
            stmt = stmt.where(self._model.urgency == urgency)

        # Order by priority (lower = higher priority) then created_at
        stmt = (
            stmt.order_by(self._model.routing_priority, self._model.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return result.scalars().all()

    async def get_unassigned(
        self,
        tenant_id: UUID,
        limit: int = 100,
    ) -> Sequence[TaskModel]:
        """Get unassigned tasks for a tenant.

        Args:
            tenant_id: Tenant UUID
            limit: Max results

        Returns:
            List of unassigned tasks
        """
        stmt = (
            select(self._model)
            .where(
                and_(
                    self._model.tenant_id == tenant_id,
                    self._model.status == "new",
                    self._model.assigned_worker_id == None,
                )
            )
            .order_by(self._model.routing_priority, self._model.created_at)
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return result.scalars().all()

    async def get_by_worker(
        self,
        tenant_id: UUID,
        worker_id: UUID,
        status: str | list[str] | None = None,
    ) -> Sequence[TaskModel]:
        """Get tasks assigned to a worker.

        Args:
            tenant_id: Tenant UUID
            worker_id: Worker UUID
            status: Optional status filter

        Returns:
            List of assigned tasks
        """
        stmt = select(self._model).where(
            and_(
                self._model.tenant_id == tenant_id,
                self._model.assigned_worker_id == worker_id,
            )
        )

        if status:
            if isinstance(status, list):
                stmt = stmt.where(self._model.status.in_(status))
            else:
                stmt = stmt.where(self._model.status == status)

        stmt = stmt.order_by(self._model.routing_priority, self._model.created_at)
        result = await self._session.execute(stmt)
        return result.scalars().all()

    async def get_by_source(
        self,
        tenant_id: UUID,
        source_type: str,
        source_id: str,
    ) -> TaskModel | None:
        """Get task by source reference.

        Args:
            tenant_id: Tenant UUID
            source_type: Source type (phone, email, form)
            source_id: Source ID (call_id, email_id, etc.)

        Returns:
            TaskModel or None
        """
        stmt = select(self._model).where(
            and_(
                self._model.tenant_id == tenant_id,
                self._model.source_type == source_type,
                self._model.source_id == source_id,
            )
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def assign_to_worker(
        self,
        task_id: UUID,
        worker_id: UUID,
        assigned_by: str = "auto_routing",
    ) -> TaskModel | None:
        """Assign task to a worker.

        Args:
            task_id: Task UUID
            worker_id: Worker UUID
            assigned_by: Who/what assigned the task

        Returns:
            Updated TaskModel or None
        """
        task = await self.get(task_id)
        if not task:
            return None

        task.assigned_worker_id = worker_id
        task.assigned_at = datetime.now(timezone.utc)
        task.assigned_by = assigned_by
        task.status = "assigned"

        await self._session.flush()
        await self._session.refresh(task)
        return task

    async def assign_to_department(
        self,
        task_id: UUID,
        department_id: UUID,
        reason: str | None = None,
    ) -> TaskModel | None:
        """Assign task to a department.

        Args:
            task_id: Task UUID
            department_id: Department UUID
            reason: Routing reason

        Returns:
            Updated TaskModel or None
        """
        task = await self.get(task_id)
        if not task:
            return None

        task.assigned_department_id = department_id
        if reason:
            task.routing_reason = reason

        await self._session.flush()
        await self._session.refresh(task)
        return task

    async def get_stats(self, tenant_id: UUID) -> dict[str, Any]:
        """Get task statistics for a tenant.

        Args:
            tenant_id: Tenant UUID

        Returns:
            Dict with task statistics
        """
        # Total count
        total_stmt = (
            select(func.count())
            .select_from(self._model)
            .where(self._model.tenant_id == tenant_id)
        )
        total = (await self._session.execute(total_stmt)).scalar() or 0

        # Count by status
        status_stmt = (
            select(self._model.status, func.count())
            .where(self._model.tenant_id == tenant_id)
            .group_by(self._model.status)
        )
        status_result = await self._session.execute(status_stmt)
        by_status = dict(status_result.all())

        # Count by urgency
        urgency_stmt = (
            select(self._model.urgency, func.count())
            .where(self._model.tenant_id == tenant_id)
            .group_by(self._model.urgency)
        )
        urgency_result = await self._session.execute(urgency_stmt)
        by_urgency = dict(urgency_result.all())

        return {
            "total": total,
            "by_status": by_status,
            "by_urgency": by_urgency,
        }


class RoutingRuleRepository(BaseRepository[RoutingRuleModel]):
    """Repository for routing rules."""

    def __init__(self, session: AsyncSession):
        """Initialize repository."""
        super().__init__(RoutingRuleModel, session)

    async def get_by_tenant(
        self,
        tenant_id: UUID,
        include_inactive: bool = False,
    ) -> Sequence[RoutingRuleModel]:
        """Get routing rules for a tenant, ordered by priority.

        Args:
            tenant_id: Tenant UUID
            include_inactive: Include inactive rules

        Returns:
            List of routing rules ordered by priority (lower first)
        """
        stmt = select(self._model).where(self._model.tenant_id == tenant_id)

        if not include_inactive:
            stmt = stmt.where(self._model.is_active == True)

        # Lower priority number = evaluated first
        stmt = stmt.order_by(self._model.priority)
        result = await self._session.execute(stmt)
        return result.scalars().all()

    async def get_active_rules(
        self,
        tenant_id: UUID,
    ) -> Sequence[RoutingRuleModel]:
        """Get active routing rules for a tenant.

        Args:
            tenant_id: Tenant UUID

        Returns:
            List of active routing rules ordered by priority
        """
        return await self.get_by_tenant(tenant_id, include_inactive=False)

    async def update_priority(
        self,
        rule_id: UUID,
        new_priority: int,
    ) -> RoutingRuleModel | None:
        """Update rule priority.

        Args:
            rule_id: Rule UUID
            new_priority: New priority value

        Returns:
            Updated RoutingRuleModel or None
        """
        rule = await self.get(rule_id)
        if not rule:
            return None

        rule.priority = new_priority
        await self._session.flush()
        await self._session.refresh(rule)
        return rule
