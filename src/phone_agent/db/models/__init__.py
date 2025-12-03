"""Database Models for Phone Agent.

Exports all ORM models for import convenience:

Core Models:
- CallModel: Phone call records
- AppointmentModel: Healthcare/service appointments

CRM Models:
- ContactModel: Patients/customers
- CompanyModel: Business entities
- ContactCompanyLinkModel: M2M relationship

Compliance Models:
- AuditLogModel: Immutable audit trail
- ConsentModel: DSGVO consent records
- DataRetentionPolicyModel: Retention configuration

Analytics Models:
- CallMetricsModel: Daily/hourly aggregates
- CampaignMetricsModel: Campaign performance
- RecallCampaignModel: Campaign definitions
- CampaignContactModel: Contacts within campaigns
- DashboardSnapshotModel: KPI snapshots

SMS Models:
- SMSMessageModel: SMS delivery tracking
"""

# Core models
from phone_agent.db.models.core import (
    CallModel,
    AppointmentModel,
)

# SMS models
from phone_agent.db.models.sms import (
    SMSMessageModel,
)

# Email models
from phone_agent.db.models.email import (
    EmailMessageModel,
)

# CRM models
from phone_agent.db.models.crm import (
    ContactModel,
    CompanyModel,
    ContactCompanyLinkModel,
)

# Compliance models
from phone_agent.db.models.compliance import (
    AuditLogModel,
    ConsentModel,
    DataRetentionPolicyModel,
)

# Analytics models
from phone_agent.db.models.analytics import (
    CallMetricsModel,
    CampaignMetricsModel,
    RecallCampaignModel,
    CampaignContactModel,
    DashboardSnapshotModel,
)

__all__ = [
    # Core
    "CallModel",
    "AppointmentModel",
    # SMS
    "SMSMessageModel",
    # Email
    "EmailMessageModel",
    # CRM
    "ContactModel",
    "CompanyModel",
    "ContactCompanyLinkModel",
    # Compliance
    "AuditLogModel",
    "ConsentModel",
    "DataRetentionPolicyModel",
    # Analytics
    "CallMetricsModel",
    "CampaignMetricsModel",
    "RecallCampaignModel",
    "CampaignContactModel",
    "DashboardSnapshotModel",
]
