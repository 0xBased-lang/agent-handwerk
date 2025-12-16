"""Business services for phone-agent.

Contains domain-specific business logic services:
- RecallService: Patient recall campaign management
- CampaignScheduler: Background job scheduling for campaigns
- ComplianceService: DSGVO compliance and consent management
- RoutingEngine: Multi-tenant task routing
- GeoService: PLZ-based geographic calculations
- TenantResolver: Tenant identification from various sources
- EmailParser: Parse raw MIME emails
- EmailClassifier: LLM-based email classification
- EmailPoller: IMAP mailbox polling service
"""

from phone_agent.services.recall_service import RecallService
from phone_agent.services.campaign_scheduler import CampaignScheduler
from phone_agent.services.compliance_service import (
    ComplianceService,
    ComplianceServiceError,
    ConsentNotFoundError,
    ConsentDeniedError,
)
from phone_agent.services.routing_engine import RoutingEngine, RoutingDecision
from phone_agent.services.geo_service import GeoService, GeoLocation, ServiceAreaResult
from phone_agent.services.tenant_resolver import TenantResolver, TenantResolution
from phone_agent.services.email_parser import EmailParser, ParsedEmail, EmailAttachment
from phone_agent.services.email_classifier import EmailClassifier, EmailClassification
from phone_agent.services.email_poller import (
    EmailPoller,
    EmailConfig,
    ProcessedEmail,
    EmailEncryption,
    EmailIntakeService,
)

__all__ = [
    # Campaign & Recall
    "RecallService",
    "CampaignScheduler",
    # Compliance
    "ComplianceService",
    "ComplianceServiceError",
    "ConsentNotFoundError",
    "ConsentDeniedError",
    # Multi-Tenant Routing
    "RoutingEngine",
    "RoutingDecision",
    # Geographic
    "GeoService",
    "GeoLocation",
    "ServiceAreaResult",
    # Tenant Resolution
    "TenantResolver",
    "TenantResolution",
    # Email Processing
    "EmailParser",
    "ParsedEmail",
    "EmailAttachment",
    "EmailClassifier",
    "EmailClassification",
    "EmailPoller",
    "EmailConfig",
    "ProcessedEmail",
    "EmailEncryption",
    "EmailIntakeService",
]
