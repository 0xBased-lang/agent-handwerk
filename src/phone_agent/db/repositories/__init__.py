"""Repository Layer for Phone Agent.

Exports all repositories for data access:

Base:
- BaseRepository: Generic CRUD operations

Specialized:
- CallRepository: Call records
- ContactRepository: CRM contacts
- CompanyRepository: CRM companies
- CallMetricsRepository: Call analytics
- CampaignMetricsRepository: Campaign analytics
- RecallCampaignRepository: Campaign management
- DashboardSnapshotRepository: Dashboard snapshots
- SMSMessageRepository: SMS delivery tracking

Multi-Tenant:
- TenantRepository: Company/tenant management
- DepartmentRepository: Department CRUD with tenant isolation
- WorkerRepository: Worker management
- TaskRepository: Task management with routing
- RoutingRuleRepository: Routing rules

Services:
- AnalyticsService: High-level analytics aggregation
"""

from phone_agent.db.repositories.base import BaseRepository
from phone_agent.db.repositories.calls import CallRepository
from phone_agent.db.repositories.appointments import AppointmentRepository
from phone_agent.db.repositories.contacts import (
    ContactRepository,
    CompanyRepository,
)
from phone_agent.db.repositories.analytics import (
    CallMetricsRepository,
    CampaignMetricsRepository,
    RecallCampaignRepository,
    DashboardSnapshotRepository,
    AnalyticsService,
)
from phone_agent.db.repositories.compliance import (
    ConsentRepository,
    AuditLogRepository,
)
from phone_agent.db.repositories.sms import SMSMessageRepository
from phone_agent.db.repositories.jobs import JobRepository
from phone_agent.db.repositories.tenant_repos import (
    TenantRepository,
    DepartmentRepository,
    WorkerRepository,
    TaskRepository,
    RoutingRuleRepository,
)

__all__ = [
    # Base
    "BaseRepository",
    # Calls
    "CallRepository",
    # Appointments
    "AppointmentRepository",
    # CRM
    "ContactRepository",
    "CompanyRepository",
    # Analytics
    "CallMetricsRepository",
    "CampaignMetricsRepository",
    "RecallCampaignRepository",
    "DashboardSnapshotRepository",
    "AnalyticsService",
    # Compliance
    "ConsentRepository",
    "AuditLogRepository",
    # SMS
    "SMSMessageRepository",
    # Handwerk
    "JobRepository",
    # Multi-Tenant
    "TenantRepository",
    "DepartmentRepository",
    "WorkerRepository",
    "TaskRepository",
    "RoutingRuleRepository",
]
