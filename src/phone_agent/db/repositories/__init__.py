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
]
