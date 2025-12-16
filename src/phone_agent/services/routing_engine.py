"""Routing Engine for multi-tenant task distribution.

Implements intelligent task routing based on:
- Tenant-specific routing rules
- Task type and urgency
- Department capabilities
- Worker availability and workload
- Geographic proximity (via GeoService)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Sequence
from uuid import UUID

from phone_agent.db.models.tenant import (
    TenantModel,
    DepartmentModel,
    WorkerModel,
    TaskModel,
    RoutingRuleModel,
)
from phone_agent.db.repositories.tenant_repos import (
    TenantRepository,
    DepartmentRepository,
    WorkerRepository,
    TaskRepository,
    RoutingRuleRepository,
)

logger = logging.getLogger(__name__)


# Priority mapping for urgency levels
URGENCY_PRIORITY = {
    "notfall": 0,      # Emergency - highest priority
    "dringend": 50,    # Urgent
    "normal": 100,     # Normal
    "routine": 150,    # Routine - lowest priority
}


@dataclass
class RoutingDecision:
    """Result of routing engine decision."""

    department_id: UUID | None = None
    worker_id: UUID | None = None
    priority: int = 100
    reason: str = ""
    escalate_after_minutes: int | None = None
    send_notification: bool = False
    notification_channels: list[str] | None = None
    matched_rule_id: UUID | None = None
    matched_rule_name: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "department_id": str(self.department_id) if self.department_id else None,
            "worker_id": str(self.worker_id) if self.worker_id else None,
            "priority": self.priority,
            "reason": self.reason,
            "escalate_after_minutes": self.escalate_after_minutes,
            "send_notification": self.send_notification,
            "notification_channels": self.notification_channels,
            "matched_rule_id": str(self.matched_rule_id) if self.matched_rule_id else None,
            "matched_rule_name": self.matched_rule_name,
        }


class RoutingEngine:
    """Intelligent task routing engine.

    Applies tenant-specific routing rules to determine the best
    department and/or worker for each incoming task.

    Rule Evaluation Order:
    1. Explicit routing rules (ordered by priority)
    2. Default routing by task_type → department
    3. Worker assignment within department (if configured)

    Usage:
        engine = RoutingEngine(
            tenant_repo=tenant_repo,
            department_repo=department_repo,
            worker_repo=worker_repo,
            task_repo=task_repo,
            rule_repo=rule_repo,
        )

        decision = await engine.route_task(tenant_id, task)
        await engine.apply_routing(task, decision)
    """

    def __init__(
        self,
        tenant_repo: TenantRepository,
        department_repo: DepartmentRepository,
        worker_repo: WorkerRepository,
        task_repo: TaskRepository,
        rule_repo: RoutingRuleRepository,
        geo_service: Any | None = None,  # Optional GeoService for proximity routing
    ):
        """Initialize routing engine.

        Args:
            tenant_repo: Tenant repository
            department_repo: Department repository
            worker_repo: Worker repository
            task_repo: Task repository
            rule_repo: Routing rule repository
            geo_service: Optional geo service for proximity routing
        """
        self.tenant_repo = tenant_repo
        self.department_repo = department_repo
        self.worker_repo = worker_repo
        self.task_repo = task_repo
        self.rule_repo = rule_repo
        self.geo_service = geo_service

    async def route_task(
        self,
        tenant_id: UUID,
        task: TaskModel,
    ) -> RoutingDecision:
        """Determine best routing for a task.

        Args:
            tenant_id: Tenant UUID
            task: Task to route

        Returns:
            RoutingDecision with department/worker assignment
        """
        logger.info(
            f"Routing task {task.id} for tenant {tenant_id}: "
            f"type={task.task_type}, urgency={task.urgency}"
        )

        # 1. Get tenant's routing rules (ordered by priority)
        rules = await self.rule_repo.get_active_rules(tenant_id)

        # 2. Evaluate each rule in priority order
        for rule in rules:
            if self._matches_conditions(task, rule.conditions):
                logger.info(f"Task matched rule: {rule.name} (priority={rule.priority})")

                decision = RoutingDecision(
                    department_id=rule.route_to_department_id,
                    worker_id=rule.route_to_worker_id,
                    priority=rule.set_priority or self._calculate_priority(task),
                    reason=f"Matched rule: {rule.name}",
                    escalate_after_minutes=rule.escalate_after_minutes,
                    send_notification=rule.send_notification,
                    notification_channels=rule.notification_channels,
                    matched_rule_id=rule.id,
                    matched_rule_name=rule.name,
                )

                # If rule routes to department but not worker, try to find worker
                if decision.department_id and not decision.worker_id:
                    worker = await self._find_best_worker(
                        tenant_id, decision.department_id, task
                    )
                    if worker:
                        decision.worker_id = worker.id
                        decision.reason += f" → Assigned to {worker.first_name} {worker.last_name}"

                return decision

        # 3. No rules matched - fall back to default routing
        logger.info(f"No rules matched, using default routing for task_type={task.task_type}")
        return await self._default_routing(tenant_id, task)

    def _matches_conditions(
        self,
        task: TaskModel,
        conditions: dict[str, Any] | None,
    ) -> bool:
        """Check if task matches rule conditions.

        Conditions format:
        {
            "task_type": "repairs",           # Exact match
            "task_type": ["repairs", "quotes"], # Any of
            "urgency": ["notfall", "dringend"], # Any of
            "trade_category": "shk",          # Exact match
            "customer_plz_starts": "72",      # PLZ prefix
        }

        Args:
            task: Task to evaluate
            conditions: Rule conditions dict

        Returns:
            True if all conditions match
        """
        if not conditions:
            return False

        for field, expected in conditions.items():
            # Handle special conditions
            if field == "customer_plz_starts":
                if not task.customer_plz or not task.customer_plz.startswith(expected):
                    return False
                continue

            if field == "distance_km_max":
                if task.distance_from_hq_km is None or task.distance_from_hq_km > expected:
                    return False
                continue

            # Standard field matching
            actual = getattr(task, field, None)
            if actual is None:
                return False

            if isinstance(expected, list):
                if actual not in expected:
                    return False
            elif actual != expected:
                return False

        return True

    def _calculate_priority(self, task: TaskModel) -> int:
        """Calculate routing priority from task urgency.

        Lower number = higher priority.

        Args:
            task: Task to calculate priority for

        Returns:
            Priority value (0-150)
        """
        return URGENCY_PRIORITY.get(task.urgency, 100)

    async def _default_routing(
        self,
        tenant_id: UUID,
        task: TaskModel,
    ) -> RoutingDecision:
        """Apply default routing when no rules match.

        Default routing:
        1. Find department that handles this task_type
        2. Assign to least-loaded available worker

        Args:
            tenant_id: Tenant UUID
            task: Task to route

        Returns:
            RoutingDecision
        """
        decision = RoutingDecision(
            priority=self._calculate_priority(task),
            reason="Default routing",
        )

        # Find department by task_type
        departments = await self.department_repo.get_by_task_type(
            tenant_id, task.task_type
        )

        if departments:
            department = departments[0]  # Take first matching
            decision.department_id = department.id
            decision.reason = f"Default routing: {department.name} handles {task.task_type}"

            # Find available worker in department
            worker = await self._find_best_worker(tenant_id, department.id, task)
            if worker:
                decision.worker_id = worker.id
                decision.reason += f" → {worker.first_name} {worker.last_name}"
        else:
            # No department found - route to generic "Kundendienst" if exists
            all_depts = await self.department_repo.get_by_tenant(tenant_id)
            kundendienst = next(
                (d for d in all_depts if "kundendienst" in d.name.lower()),
                None
            )
            if kundendienst:
                decision.department_id = kundendienst.id
                decision.reason = f"Default fallback: {kundendienst.name}"
            else:
                decision.reason = "No matching department found"

        # Set notification for high urgency
        if task.urgency in ("notfall", "dringend"):
            decision.send_notification = True
            decision.notification_channels = ["sms", "email"]
            if task.urgency == "notfall":
                decision.escalate_after_minutes = 15
            else:
                decision.escalate_after_minutes = 60

        return decision

    async def _find_best_worker(
        self,
        tenant_id: UUID,
        department_id: UUID,
        task: TaskModel,
    ) -> WorkerModel | None:
        """Find best available worker for a task.

        Selection criteria (in order):
        1. Available and active
        2. In the specified department
        3. Has matching trade_category (if applicable)
        4. Lowest current workload
        5. Closest proximity (if geo_service available)

        Args:
            tenant_id: Tenant UUID
            department_id: Department UUID
            task: Task being assigned

        Returns:
            Best matching worker or None
        """
        # Get available workers in department
        workers = await self.worker_repo.get_available_workers(
            tenant_id=tenant_id,
            department_id=department_id,
            trade_categories=[task.trade_category] if task.trade_category else None,
        )

        if not workers:
            return None

        # If only one worker, return them
        if len(workers) == 1:
            return workers[0]

        # Score workers and pick best
        best_worker = None
        best_score = float("inf")

        for worker in workers:
            score = self._score_worker(worker, task)
            if score < best_score:
                best_score = score
                best_worker = worker

        return best_worker

    def _score_worker(self, worker: WorkerModel, task: TaskModel) -> float:
        """Score a worker for task assignment.

        Lower score = better match.

        Scoring factors:
        - Current workload (task count)
        - Trade category match
        - Geographic proximity (if available)

        Args:
            worker: Worker to score
            task: Task being assigned

        Returns:
            Score value (lower is better)
        """
        score = 0.0

        # Workload factor (0-100 points)
        workload = worker.current_task_count or 0
        max_tasks = worker.max_tasks_per_day or 10
        score += (workload / max_tasks) * 100

        # Trade category bonus (-20 if match)
        if task.trade_category and worker.trade_categories:
            if task.trade_category in worker.trade_categories:
                score -= 20

        # TODO: Add proximity scoring when geo_service available
        # if self.geo_service and task.latitude and task.longitude:
        #     distance = await self.geo_service.calculate_distance(...)
        #     score += distance * 0.5  # 0.5 points per km

        return score

    async def apply_routing(
        self,
        task: TaskModel,
        decision: RoutingDecision,
    ) -> TaskModel:
        """Apply routing decision to a task.

        Updates task with:
        - assigned_department_id
        - assigned_worker_id
        - assigned_at
        - assigned_by
        - routing_priority
        - routing_reason
        - status

        Args:
            task: Task to update
            decision: Routing decision

        Returns:
            Updated task
        """
        # Update task
        if decision.department_id:
            task.assigned_department_id = decision.department_id

        if decision.worker_id:
            task.assigned_worker_id = decision.worker_id
            task.assigned_at = datetime.now(timezone.utc)
            task.assigned_by = "auto_routing"
            task.status = "assigned"

            # Increment worker's task count
            await self.worker_repo.increment_task_count(decision.worker_id)
        else:
            task.status = "new"  # No worker assigned yet

        task.routing_priority = decision.priority
        task.routing_reason = decision.reason

        # Save task
        await self.task_repo._session.flush()
        await self.task_repo._session.refresh(task)

        logger.info(
            f"Applied routing for task {task.id}: "
            f"dept={decision.department_id}, worker={decision.worker_id}, "
            f"reason='{decision.reason}'"
        )

        return task

    async def reassign_task(
        self,
        task_id: UUID,
        new_worker_id: UUID,
        reason: str = "manual_reassignment",
    ) -> TaskModel | None:
        """Reassign a task to a different worker.

        Args:
            task_id: Task UUID
            new_worker_id: New worker UUID
            reason: Reason for reassignment

        Returns:
            Updated task or None
        """
        task = await self.task_repo.get(task_id)
        if not task:
            return None

        # Decrement old worker's count
        if task.assigned_worker_id:
            await self.worker_repo.decrement_task_count(task.assigned_worker_id)

        # Update task
        task.assigned_worker_id = new_worker_id
        task.assigned_at = datetime.now(timezone.utc)
        task.assigned_by = reason
        task.routing_reason = f"Reassigned: {reason}"

        # Increment new worker's count
        await self.worker_repo.increment_task_count(new_worker_id)

        await self.task_repo._session.flush()
        await self.task_repo._session.refresh(task)

        return task

    async def escalate_task(
        self,
        task_id: UUID,
        reason: str = "timeout",
    ) -> TaskModel | None:
        """Escalate a task (increase priority, notify management).

        Args:
            task_id: Task UUID
            reason: Escalation reason

        Returns:
            Updated task or None
        """
        task = await self.task_repo.get(task_id)
        if not task:
            return None

        # Increase priority (lower number = higher)
        current_priority = task.routing_priority or 100
        task.routing_priority = max(0, current_priority - 50)

        # Add escalation note
        task.routing_reason = f"ESCALATED ({reason}): {task.routing_reason or 'No previous reason'}"

        # TODO: Notify management department

        await self.task_repo._session.flush()
        await self.task_repo._session.refresh(task)

        logger.warning(f"Task {task_id} escalated: {reason}")
        return task
