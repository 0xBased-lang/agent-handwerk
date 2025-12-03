"""Handwerk (Trades) industry configuration.

Implements comprehensive automation for German trades businesses:
- Job intake and urgency assessment
- Technician scheduling and dispatch
- Follow-up campaigns (maintenance, quotes)
- DSGVO/GDPR compliance
"""

# Prompts
from phone_agent.industry.handwerk.prompts import (
    SYSTEM_PROMPT,
    GREETING_PROMPT,
    JOB_INTAKE_PROMPT,
    SCHEDULING_PROMPT,
    QUOTE_PROMPT,
    FAREWELL_PROMPT,
    EMERGENCY_PROMPT,
    MAINTENANCE_REMINDER_PROMPT,
    QUOTE_FOLLOWUP_PROMPT,
    SMS_APPOINTMENT_CONFIRMATION,
    SMS_APPOINTMENT_REMINDER,
    SMS_TECHNICIAN_ETA,
)

# Basic workflows
from phone_agent.industry.handwerk.workflows import (
    UrgencyLevel,
    TradeCategory,
    TriageResult as BasicTriageResult,
    perform_triage,
    is_emergency,
    detect_trade_category,
)

# Advanced triage engine
from phone_agent.industry.handwerk.triage import (
    TriageEngine,
    TriageResult,
    JobIssue,
    CustomerContext,
    get_triage_engine,
)

# Technician matching
from phone_agent.industry.handwerk.technician import (
    Technician,
    TechnicianQualification,
    TechnicianMatcher,
    TechnicianMatch,
    get_technician_matcher,
)

# Scheduling
from phone_agent.industry.handwerk.scheduling import (
    SchedulingService,
    SchedulingPreferences,
    Customer,
    ServiceCall,
    TimeSlot,
    JobType,
    get_scheduling_service,
)

# Follow-up campaigns
from phone_agent.industry.handwerk.followup import (
    FollowUpService,
    FollowUpCampaign,
    FollowUpCustomer,
    FollowUpType,
    FollowUpStatus,
    get_followup_service,
)

# Compliance
from phone_agent.industry.handwerk.compliance import (
    ConsentManager,
    ConsentType,
    ConsentStatus,
    AuditLogger,
    AuditAction,
    DataProtectionService,
    get_consent_manager,
    get_audit_logger,
    get_data_protection_service,
)

# Conversation manager
from phone_agent.industry.handwerk.conversation import (
    HandwerkConversationManager,
    ConversationContext,
    ConversationResponse,
    ConversationState,
    CustomerIntent,
    get_conversation_manager,
)

__all__ = [
    # Prompts
    "SYSTEM_PROMPT",
    "GREETING_PROMPT",
    "JOB_INTAKE_PROMPT",
    "SCHEDULING_PROMPT",
    "QUOTE_PROMPT",
    "FAREWELL_PROMPT",
    "EMERGENCY_PROMPT",
    "MAINTENANCE_REMINDER_PROMPT",
    "QUOTE_FOLLOWUP_PROMPT",
    "SMS_APPOINTMENT_CONFIRMATION",
    "SMS_APPOINTMENT_REMINDER",
    "SMS_TECHNICIAN_ETA",
    # Basic triage (from workflows.py)
    "UrgencyLevel",
    "TradeCategory",
    "BasicTriageResult",
    "perform_triage",
    "is_emergency",
    "detect_trade_category",
    # Advanced triage
    "TriageEngine",
    "TriageResult",
    "JobIssue",
    "CustomerContext",
    "get_triage_engine",
    # Technician
    "Technician",
    "TechnicianQualification",
    "TechnicianMatcher",
    "TechnicianMatch",
    "get_technician_matcher",
    # Scheduling
    "SchedulingService",
    "SchedulingPreferences",
    "Customer",
    "ServiceCall",
    "TimeSlot",
    "JobType",
    "get_scheduling_service",
    # Follow-up
    "FollowUpService",
    "FollowUpCampaign",
    "FollowUpCustomer",
    "FollowUpType",
    "FollowUpStatus",
    "get_followup_service",
    # Compliance
    "ConsentManager",
    "ConsentType",
    "ConsentStatus",
    "AuditLogger",
    "AuditAction",
    "DataProtectionService",
    "get_consent_manager",
    "get_audit_logger",
    "get_data_protection_service",
    # Conversation
    "HandwerkConversationManager",
    "ConversationContext",
    "ConversationResponse",
    "ConversationState",
    "CustomerIntent",
    "get_conversation_manager",
]
