"""Multi-Tenant API endpoints.

REST API for tenant-scoped operations:
- Departments: CRUD for department management
- Workers: CRUD for worker management
- Tasks: Task management with routing
- Routing Rules: Routing configuration
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from itf_shared import get_logger

from phone_agent.db import get_db
from phone_agent.db.repositories import (
    TenantRepository,
    DepartmentRepository,
    WorkerRepository,
    TaskRepository,
    RoutingRuleRepository,
)
from phone_agent.db.models.tenant import (
    TenantModel,
    DepartmentModel,
    WorkerModel,
    TaskModel,
    RoutingRuleModel,
)
from phone_agent.api.auth import (
    TenantContext,
    get_tenant_context,
    require_tenant_admin,
    require_tenant_worker,
)
from phone_agent.services import RoutingEngine, RoutingDecision

log = get_logger(__name__)

router = APIRouter(prefix="/tenant", tags=["Multi-Tenant"])


# ============================================================================
# Request/Response Models
# ============================================================================


class DepartmentCreate(BaseModel):
    """Create department request."""

    name: str = Field(..., min_length=1, max_length=100)
    description: str | None = None
    handles_task_types: list[str] | None = None
    handles_urgency_levels: list[str] | None = None
    phone: str | None = None
    email: str | None = None
    working_hours: dict[str, str] | None = None


class DepartmentUpdate(BaseModel):
    """Update department request."""

    name: str | None = None
    description: str | None = None
    handles_task_types: list[str] | None = None
    handles_urgency_levels: list[str] | None = None
    phone: str | None = None
    email: str | None = None
    working_hours: dict[str, str] | None = None
    is_active: bool | None = None


class DepartmentResponse(BaseModel):
    """Department response model."""

    id: str
    name: str
    description: str | None
    handles_task_types: list[str] | None
    handles_urgency_levels: list[str] | None
    phone: str | None
    email: str | None
    working_hours: dict[str, str] | None
    is_active: bool
    created_at: datetime


class WorkerCreate(BaseModel):
    """Create worker request."""

    first_name: str = Field(..., min_length=1, max_length=100)
    last_name: str = Field(..., min_length=1, max_length=100)
    department_id: str | None = None
    role: str = Field(default="worker", description="Role: admin, worker, viewer")
    phone: str | None = None
    email: str | None = None
    trade_categories: list[str] | None = None
    certifications: list[str] | None = None
    working_hours: dict[str, str] | None = None
    max_tasks_per_day: int = Field(default=10, ge=1, le=50)
    home_plz: str | None = Field(None, max_length=10)


class WorkerUpdate(BaseModel):
    """Update worker request."""

    first_name: str | None = None
    last_name: str | None = None
    department_id: str | None = None
    role: str | None = None
    phone: str | None = None
    email: str | None = None
    trade_categories: list[str] | None = None
    certifications: list[str] | None = None
    working_hours: dict[str, str] | None = None
    max_tasks_per_day: int | None = None
    home_plz: str | None = None
    is_active: bool | None = None
    is_available: bool | None = None


class WorkerResponse(BaseModel):
    """Worker response model."""

    id: str
    first_name: str
    last_name: str
    department_id: str | None
    role: str
    phone: str | None
    email: str | None
    trade_categories: list[str] | None
    is_active: bool
    is_available: bool
    current_task_count: int
    created_at: datetime


class TaskCreate(BaseModel):
    """Create task request."""

    source_type: str = Field(default="manual", description="phone, email, form, whatsapp, manual")
    source_id: str | None = None
    task_type: str = Field(..., description="repairs, quotes, complaints, billing, appointment, general")
    urgency: str = Field(default="normal", description="notfall, dringend, normal, routine")
    trade_category: str | None = None
    customer_name: str | None = None
    customer_phone: str | None = None
    customer_email: str | None = None
    customer_address: str | None = None
    customer_plz: str | None = None
    title: str = Field(..., min_length=1, max_length=255)
    description: str | None = None


class TaskUpdate(BaseModel):
    """Update task request."""

    task_type: str | None = None
    urgency: str | None = None
    trade_category: str | None = None
    title: str | None = None
    description: str | None = None
    status: str | None = None
    internal_notes: str | None = None


class TaskAssign(BaseModel):
    """Assign task request."""

    worker_id: str | None = None
    department_id: str | None = None
    reason: str | None = None


class TaskResponse(BaseModel):
    """Task response model."""

    id: str
    source_type: str
    task_type: str
    urgency: str
    trade_category: str | None
    customer_name: str | None
    customer_phone: str | None
    title: str
    description: str | None
    status: str
    routing_priority: int
    routing_reason: str | None
    assigned_department_id: str | None
    assigned_worker_id: str | None
    assigned_at: datetime | None
    created_at: datetime


class RoutingRuleCreate(BaseModel):
    """Create routing rule request."""

    name: str = Field(..., min_length=1, max_length=100)
    description: str | None = None
    priority: int = Field(default=100, ge=0, le=1000)
    conditions: dict[str, Any] = Field(..., description="Rule conditions JSON")
    route_to_department_id: str | None = None
    route_to_worker_id: str | None = None
    set_priority: int | None = None
    send_notification: bool = False
    notification_channels: list[str] | None = None
    escalate_after_minutes: int | None = None


class RoutingRuleUpdate(BaseModel):
    """Update routing rule request."""

    name: str | None = None
    description: str | None = None
    priority: int | None = None
    conditions: dict[str, Any] | None = None
    route_to_department_id: str | None = None
    route_to_worker_id: str | None = None
    set_priority: int | None = None
    send_notification: bool | None = None
    notification_channels: list[str] | None = None
    escalate_after_minutes: int | None = None
    is_active: bool | None = None


class RoutingRuleResponse(BaseModel):
    """Routing rule response model."""

    id: str
    name: str
    description: str | None
    priority: int
    conditions: dict[str, Any]
    route_to_department_id: str | None
    route_to_worker_id: str | None
    is_active: bool
    created_at: datetime


# ============================================================================
# Helper Functions
# ============================================================================


def _department_to_response(dept: DepartmentModel) -> DepartmentResponse:
    """Convert department model to response."""
    return DepartmentResponse(
        id=str(dept.id),
        name=dept.name,
        description=dept.description,
        handles_task_types=dept.handles_task_types,
        handles_urgency_levels=dept.handles_urgency_levels,
        phone=dept.phone,
        email=dept.email,
        working_hours=dept.working_hours,
        is_active=dept.is_active,
        created_at=dept.created_at,
    )


def _worker_to_response(worker: WorkerModel) -> WorkerResponse:
    """Convert worker model to response."""
    return WorkerResponse(
        id=str(worker.id),
        first_name=worker.first_name,
        last_name=worker.last_name,
        department_id=str(worker.department_id) if worker.department_id else None,
        role=worker.role,
        phone=worker.phone,
        email=worker.email,
        trade_categories=worker.trade_categories,
        is_active=worker.is_active,
        is_available=worker.is_available,
        current_task_count=worker.current_task_count or 0,
        created_at=worker.created_at,
    )


def _task_to_response(task: TaskModel) -> TaskResponse:
    """Convert task model to response."""
    return TaskResponse(
        id=str(task.id),
        source_type=task.source_type,
        task_type=task.task_type,
        urgency=task.urgency,
        trade_category=task.trade_category,
        customer_name=task.customer_name,
        customer_phone=task.customer_phone,
        title=task.title,
        description=task.description,
        status=task.status,
        routing_priority=task.routing_priority or 100,
        routing_reason=task.routing_reason,
        assigned_department_id=str(task.assigned_department_id) if task.assigned_department_id else None,
        assigned_worker_id=str(task.assigned_worker_id) if task.assigned_worker_id else None,
        assigned_at=task.assigned_at,
        created_at=task.created_at,
    )


def _rule_to_response(rule: RoutingRuleModel) -> RoutingRuleResponse:
    """Convert routing rule model to response."""
    return RoutingRuleResponse(
        id=str(rule.id),
        name=rule.name,
        description=rule.description,
        priority=rule.priority,
        conditions=rule.conditions or {},
        route_to_department_id=str(rule.route_to_department_id) if rule.route_to_department_id else None,
        route_to_worker_id=str(rule.route_to_worker_id) if rule.route_to_worker_id else None,
        is_active=rule.is_active,
        created_at=rule.created_at,
    )


# ============================================================================
# Department Endpoints
# ============================================================================


@router.get("/departments", response_model=list[DepartmentResponse])
async def list_departments(
    include_inactive: bool = Query(False, description="Include inactive departments"),
    tenant: TenantContext = Depends(get_tenant_context),
    db: AsyncSession = Depends(get_db),
):
    """List all departments for the current tenant."""
    dept_repo = DepartmentRepository(db)
    departments = await dept_repo.get_by_tenant(
        tenant_id=tenant.tenant_id,
        include_inactive=include_inactive,
    )
    return [_department_to_response(d) for d in departments]


@router.post("/departments", response_model=DepartmentResponse, status_code=status.HTTP_201_CREATED)
async def create_department(
    data: DepartmentCreate,
    tenant: TenantContext = Depends(require_tenant_admin),
    db: AsyncSession = Depends(get_db),
):
    """Create a new department (admin only)."""
    dept_repo = DepartmentRepository(db)

    dept = DepartmentModel(
        tenant_id=tenant.tenant_id,
        name=data.name,
        description=data.description,
        handles_task_types=data.handles_task_types,
        handles_urgency_levels=data.handles_urgency_levels,
        phone=data.phone,
        email=data.email,
        working_hours=data.working_hours,
    )

    created = await dept_repo.create(dept)
    await db.commit()

    log.info(f"Created department {created.id} for tenant {tenant.tenant_id}")
    return _department_to_response(created)


@router.get("/departments/{department_id}", response_model=DepartmentResponse)
async def get_department(
    department_id: str,
    tenant: TenantContext = Depends(get_tenant_context),
    db: AsyncSession = Depends(get_db),
):
    """Get department by ID."""
    dept_repo = DepartmentRepository(db)

    dept = await dept_repo.get(UUID(department_id))
    if not dept or dept.tenant_id != tenant.tenant_id:
        raise HTTPException(status_code=404, detail="Department not found")

    return _department_to_response(dept)


@router.patch("/departments/{department_id}", response_model=DepartmentResponse)
async def update_department(
    department_id: str,
    data: DepartmentUpdate,
    tenant: TenantContext = Depends(require_tenant_admin),
    db: AsyncSession = Depends(get_db),
):
    """Update department (admin only)."""
    dept_repo = DepartmentRepository(db)

    dept = await dept_repo.get(UUID(department_id))
    if not dept or dept.tenant_id != tenant.tenant_id:
        raise HTTPException(status_code=404, detail="Department not found")

    # Update fields
    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(dept, field, value)

    await db.flush()
    await db.commit()
    await db.refresh(dept)

    log.info(f"Updated department {department_id}")
    return _department_to_response(dept)


@router.delete("/departments/{department_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_department(
    department_id: str,
    tenant: TenantContext = Depends(require_tenant_admin),
    db: AsyncSession = Depends(get_db),
):
    """Soft-delete department (admin only)."""
    dept_repo = DepartmentRepository(db)

    dept = await dept_repo.get(UUID(department_id))
    if not dept or dept.tenant_id != tenant.tenant_id:
        raise HTTPException(status_code=404, detail="Department not found")

    dept.is_active = False
    dept.deleted_at = datetime.now(timezone.utc)
    await db.commit()

    log.info(f"Deleted department {department_id}")


# ============================================================================
# Worker Endpoints
# ============================================================================


@router.get("/workers", response_model=list[WorkerResponse])
async def list_workers(
    department_id: str | None = Query(None, description="Filter by department"),
    include_inactive: bool = Query(False, description="Include inactive workers"),
    tenant: TenantContext = Depends(get_tenant_context),
    db: AsyncSession = Depends(get_db),
):
    """List all workers for the current tenant."""
    worker_repo = WorkerRepository(db)
    workers = await worker_repo.get_by_tenant(
        tenant_id=tenant.tenant_id,
        department_id=UUID(department_id) if department_id else None,
        include_inactive=include_inactive,
    )
    return [_worker_to_response(w) for w in workers]


@router.post("/workers", response_model=WorkerResponse, status_code=status.HTTP_201_CREATED)
async def create_worker(
    data: WorkerCreate,
    tenant: TenantContext = Depends(require_tenant_admin),
    db: AsyncSession = Depends(get_db),
):
    """Create a new worker (admin only)."""
    worker_repo = WorkerRepository(db)

    worker = WorkerModel(
        tenant_id=tenant.tenant_id,
        department_id=UUID(data.department_id) if data.department_id else None,
        first_name=data.first_name,
        last_name=data.last_name,
        role=data.role,
        phone=data.phone,
        email=data.email,
        trade_categories=data.trade_categories,
        certifications=data.certifications,
        working_hours=data.working_hours,
        max_tasks_per_day=data.max_tasks_per_day,
        home_plz=data.home_plz,
    )

    created = await worker_repo.create(worker)
    await db.commit()

    log.info(f"Created worker {created.id} for tenant {tenant.tenant_id}")
    return _worker_to_response(created)


@router.get("/workers/{worker_id}", response_model=WorkerResponse)
async def get_worker(
    worker_id: str,
    tenant: TenantContext = Depends(get_tenant_context),
    db: AsyncSession = Depends(get_db),
):
    """Get worker by ID."""
    worker_repo = WorkerRepository(db)

    worker = await worker_repo.get(UUID(worker_id))
    if not worker or worker.tenant_id != tenant.tenant_id:
        raise HTTPException(status_code=404, detail="Worker not found")

    return _worker_to_response(worker)


@router.patch("/workers/{worker_id}", response_model=WorkerResponse)
async def update_worker(
    worker_id: str,
    data: WorkerUpdate,
    tenant: TenantContext = Depends(require_tenant_admin),
    db: AsyncSession = Depends(get_db),
):
    """Update worker (admin only)."""
    worker_repo = WorkerRepository(db)

    worker = await worker_repo.get(UUID(worker_id))
    if not worker or worker.tenant_id != tenant.tenant_id:
        raise HTTPException(status_code=404, detail="Worker not found")

    # Update fields
    update_data = data.model_dump(exclude_unset=True)
    if "department_id" in update_data and update_data["department_id"]:
        update_data["department_id"] = UUID(update_data["department_id"])

    for field, value in update_data.items():
        setattr(worker, field, value)

    await db.flush()
    await db.commit()
    await db.refresh(worker)

    log.info(f"Updated worker {worker_id}")
    return _worker_to_response(worker)


# ============================================================================
# Task Endpoints
# ============================================================================


@router.get("/tasks", response_model=list[TaskResponse])
async def list_tasks(
    status_filter: str | None = Query(None, alias="status", description="Filter by status"),
    task_type: str | None = Query(None, description="Filter by task type"),
    urgency: str | None = Query(None, description="Filter by urgency"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    tenant: TenantContext = Depends(get_tenant_context),
    db: AsyncSession = Depends(get_db),
):
    """List tasks for the current tenant."""
    task_repo = TaskRepository(db)
    tasks = await task_repo.get_by_tenant(
        tenant_id=tenant.tenant_id,
        status=status_filter,
        task_type=task_type,
        urgency=urgency,
        skip=(page - 1) * page_size,
        limit=page_size,
    )
    return [_task_to_response(t) for t in tasks]


@router.post("/tasks", response_model=TaskResponse, status_code=status.HTTP_201_CREATED)
async def create_task(
    data: TaskCreate,
    auto_route: bool = Query(True, description="Auto-route task after creation"),
    tenant: TenantContext = Depends(require_tenant_worker),
    db: AsyncSession = Depends(get_db),
):
    """Create a new task with optional auto-routing."""
    task_repo = TaskRepository(db)

    task = TaskModel(
        tenant_id=tenant.tenant_id,
        source_type=data.source_type,
        source_id=data.source_id,
        task_type=data.task_type,
        urgency=data.urgency,
        trade_category=data.trade_category,
        customer_name=data.customer_name,
        customer_phone=data.customer_phone,
        customer_email=data.customer_email,
        customer_address=data.customer_address,
        customer_plz=data.customer_plz,
        title=data.title,
        description=data.description,
        status="new",
        routing_priority=100,
    )

    created = await task_repo.create(task)

    # Auto-route if requested
    if auto_route:
        tenant_repo = TenantRepository(db)
        dept_repo = DepartmentRepository(db)
        worker_repo = WorkerRepository(db)
        rule_repo = RoutingRuleRepository(db)

        engine = RoutingEngine(
            tenant_repo=tenant_repo,
            department_repo=dept_repo,
            worker_repo=worker_repo,
            task_repo=task_repo,
            rule_repo=rule_repo,
        )

        decision = await engine.route_task(tenant.tenant_id, created)
        created = await engine.apply_routing(created, decision)

    await db.commit()
    await db.refresh(created)

    log.info(f"Created task {created.id} for tenant {tenant.tenant_id}")
    return _task_to_response(created)


@router.get("/tasks/{task_id}", response_model=TaskResponse)
async def get_task(
    task_id: str,
    tenant: TenantContext = Depends(get_tenant_context),
    db: AsyncSession = Depends(get_db),
):
    """Get task by ID."""
    task_repo = TaskRepository(db)

    task = await task_repo.get(UUID(task_id))
    if not task or task.tenant_id != tenant.tenant_id:
        raise HTTPException(status_code=404, detail="Task not found")

    return _task_to_response(task)


@router.patch("/tasks/{task_id}", response_model=TaskResponse)
async def update_task(
    task_id: str,
    data: TaskUpdate,
    tenant: TenantContext = Depends(require_tenant_worker),
    db: AsyncSession = Depends(get_db),
):
    """Update task details."""
    task_repo = TaskRepository(db)

    task = await task_repo.get(UUID(task_id))
    if not task or task.tenant_id != tenant.tenant_id:
        raise HTTPException(status_code=404, detail="Task not found")

    # Update fields
    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(task, field, value)

    await db.flush()
    await db.commit()
    await db.refresh(task)

    log.info(f"Updated task {task_id}")
    return _task_to_response(task)


@router.post("/tasks/{task_id}/assign", response_model=TaskResponse)
async def assign_task(
    task_id: str,
    data: TaskAssign,
    tenant: TenantContext = Depends(require_tenant_worker),
    db: AsyncSession = Depends(get_db),
):
    """Assign task to a worker or department."""
    task_repo = TaskRepository(db)
    worker_repo = WorkerRepository(db)

    task = await task_repo.get(UUID(task_id))
    if not task or task.tenant_id != tenant.tenant_id:
        raise HTTPException(status_code=404, detail="Task not found")

    # Decrement old worker's count
    if task.assigned_worker_id:
        await worker_repo.decrement_task_count(task.assigned_worker_id)

    # Update assignment
    if data.department_id:
        task.assigned_department_id = UUID(data.department_id)

    if data.worker_id:
        task.assigned_worker_id = UUID(data.worker_id)
        task.assigned_at = datetime.now(timezone.utc)
        task.assigned_by = f"manual:{tenant.user_id}"
        task.status = "assigned"
        await worker_repo.increment_task_count(UUID(data.worker_id))

    if data.reason:
        task.routing_reason = data.reason

    await db.flush()
    await db.commit()
    await db.refresh(task)

    log.info(f"Assigned task {task_id} to worker={data.worker_id}, dept={data.department_id}")
    return _task_to_response(task)


@router.get("/tasks/stats/summary")
async def get_task_stats(
    tenant: TenantContext = Depends(get_tenant_context),
    db: AsyncSession = Depends(get_db),
):
    """Get task statistics for the current tenant."""
    task_repo = TaskRepository(db)
    stats = await task_repo.get_stats(tenant.tenant_id)
    return stats


# ============================================================================
# Routing Rule Endpoints
# ============================================================================


@router.get("/routing-rules", response_model=list[RoutingRuleResponse])
async def list_routing_rules(
    include_inactive: bool = Query(False, description="Include inactive rules"),
    tenant: TenantContext = Depends(get_tenant_context),
    db: AsyncSession = Depends(get_db),
):
    """List routing rules for the current tenant."""
    rule_repo = RoutingRuleRepository(db)
    rules = await rule_repo.get_by_tenant(
        tenant_id=tenant.tenant_id,
        include_inactive=include_inactive,
    )
    return [_rule_to_response(r) for r in rules]


@router.post("/routing-rules", response_model=RoutingRuleResponse, status_code=status.HTTP_201_CREATED)
async def create_routing_rule(
    data: RoutingRuleCreate,
    tenant: TenantContext = Depends(require_tenant_admin),
    db: AsyncSession = Depends(get_db),
):
    """Create a new routing rule (admin only)."""
    rule_repo = RoutingRuleRepository(db)

    rule = RoutingRuleModel(
        tenant_id=tenant.tenant_id,
        name=data.name,
        description=data.description,
        priority=data.priority,
        conditions=data.conditions,
        route_to_department_id=UUID(data.route_to_department_id) if data.route_to_department_id else None,
        route_to_worker_id=UUID(data.route_to_worker_id) if data.route_to_worker_id else None,
        set_priority=data.set_priority,
        send_notification=data.send_notification,
        notification_channels=data.notification_channels,
        escalate_after_minutes=data.escalate_after_minutes,
    )

    created = await rule_repo.create(rule)
    await db.commit()

    log.info(f"Created routing rule {created.id} for tenant {tenant.tenant_id}")
    return _rule_to_response(created)


@router.patch("/routing-rules/{rule_id}", response_model=RoutingRuleResponse)
async def update_routing_rule(
    rule_id: str,
    data: RoutingRuleUpdate,
    tenant: TenantContext = Depends(require_tenant_admin),
    db: AsyncSession = Depends(get_db),
):
    """Update routing rule (admin only)."""
    rule_repo = RoutingRuleRepository(db)

    rule = await rule_repo.get(UUID(rule_id))
    if not rule or rule.tenant_id != tenant.tenant_id:
        raise HTTPException(status_code=404, detail="Routing rule not found")

    # Update fields
    update_data = data.model_dump(exclude_unset=True)
    if "route_to_department_id" in update_data and update_data["route_to_department_id"]:
        update_data["route_to_department_id"] = UUID(update_data["route_to_department_id"])
    if "route_to_worker_id" in update_data and update_data["route_to_worker_id"]:
        update_data["route_to_worker_id"] = UUID(update_data["route_to_worker_id"])

    for field, value in update_data.items():
        setattr(rule, field, value)

    await db.flush()
    await db.commit()
    await db.refresh(rule)

    log.info(f"Updated routing rule {rule_id}")
    return _rule_to_response(rule)


@router.delete("/routing-rules/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_routing_rule(
    rule_id: str,
    tenant: TenantContext = Depends(require_tenant_admin),
    db: AsyncSession = Depends(get_db),
):
    """Soft-delete routing rule (admin only)."""
    rule_repo = RoutingRuleRepository(db)

    rule = await rule_repo.get(UUID(rule_id))
    if not rule or rule.tenant_id != tenant.tenant_id:
        raise HTTPException(status_code=404, detail="Routing rule not found")

    rule.is_active = False
    await db.commit()

    log.info(f"Deleted routing rule {rule_id}")


# ============================================================================
# Routing Test Endpoint
# ============================================================================


@router.post("/routing/test")
async def test_routing(
    task_type: str = Query(..., description="Task type to test"),
    urgency: str = Query("normal", description="Urgency level"),
    trade_category: str | None = Query(None, description="Trade category"),
    customer_plz: str | None = Query(None, description="Customer PLZ"),
    tenant: TenantContext = Depends(get_tenant_context),
    db: AsyncSession = Depends(get_db),
):
    """Test routing rules without creating a task.

    Returns the routing decision that would be made for the given parameters.
    """
    # Create a mock task for testing
    mock_task = TaskModel(
        tenant_id=tenant.tenant_id,
        source_type="test",
        task_type=task_type,
        urgency=urgency,
        trade_category=trade_category,
        customer_plz=customer_plz,
        title="Test Task",
        status="new",
        routing_priority=100,
    )

    # Initialize routing engine
    tenant_repo = TenantRepository(db)
    dept_repo = DepartmentRepository(db)
    worker_repo = WorkerRepository(db)
    task_repo = TaskRepository(db)
    rule_repo = RoutingRuleRepository(db)

    engine = RoutingEngine(
        tenant_repo=tenant_repo,
        department_repo=dept_repo,
        worker_repo=worker_repo,
        task_repo=task_repo,
        rule_repo=rule_repo,
    )

    # Get routing decision
    decision = await engine.route_task(tenant.tenant_id, mock_task)

    return {
        "input": {
            "task_type": task_type,
            "urgency": urgency,
            "trade_category": trade_category,
            "customer_plz": customer_plz,
        },
        "decision": decision.to_dict(),
    }
