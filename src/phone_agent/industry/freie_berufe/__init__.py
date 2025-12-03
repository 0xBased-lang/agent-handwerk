"""Freie Berufe (Professional Services) industry configuration.

Implements comprehensive automation for German professional services:
- Lead intake and qualification
- Appointment scheduling with advisors
- Follow-up campaigns
- DSGVO/GDPR compliance

Target professions:
- Rechtsanwälte (Lawyers)
- Steuerberater (Tax Consultants)
- Wirtschaftsprüfer (Auditors)
- Unternehmensberater (Consultants)
- Architekten (Architects)
"""

# Prompts
from phone_agent.industry.freie_berufe.prompts import (
    SYSTEM_PROMPT,
    GREETING_PROMPT,
    LEAD_INTAKE_PROMPT,
    QUALIFICATION_PROMPT,
    APPOINTMENT_PROMPT,
    CALLBACK_PROMPT,
    REJECTION_PROMPT,
    FAREWELL_PROMPT,
    FOLLOWUP_PROMPT,
    REFERRAL_PROMPT,
    SMS_APPOINTMENT_CONFIRMATION,
    SMS_CALLBACK_CONFIRMATION,
    EMAIL_APPOINTMENT_CONFIRMATION,
)

# Basic workflows
from phone_agent.industry.freie_berufe.workflows import (
    InquiryType,
    ServiceArea,
    UrgencyLevel,
    InquiryResult,
    classify_inquiry,
    get_time_of_day,
    extract_contact_info,
    detect_deadline,
    format_available_slots,
    calculate_lead_score,
)

# Advanced triage engine
from phone_agent.industry.freie_berufe.triage import (
    TriageEngine,
    TriageResult,
    ContactContext,
    InquiryContext,
    LeadPriority,
    QualificationStatus,
    ClientType,
    get_triage_engine,
)

# Scheduling
from phone_agent.industry.freie_berufe.scheduling import (
    SchedulingService,
    Advisor,
    AdvisorRole,
    Appointment,
    AppointmentType,
    AppointmentStatus,
    AvailableSlot,
    get_scheduling_service,
)

# Conversation manager
from phone_agent.industry.freie_berufe.conversation import (
    FreieBerufeConversationManager,
    ConversationContext,
    ConversationResponse,
    ConversationState,
    ClientIntent,
    LeadData,
    get_conversation_manager,
)

__all__ = [
    # Prompts
    "SYSTEM_PROMPT",
    "GREETING_PROMPT",
    "LEAD_INTAKE_PROMPT",
    "QUALIFICATION_PROMPT",
    "APPOINTMENT_PROMPT",
    "CALLBACK_PROMPT",
    "REJECTION_PROMPT",
    "FAREWELL_PROMPT",
    "FOLLOWUP_PROMPT",
    "REFERRAL_PROMPT",
    "SMS_APPOINTMENT_CONFIRMATION",
    "SMS_CALLBACK_CONFIRMATION",
    "EMAIL_APPOINTMENT_CONFIRMATION",
    # Basic workflows
    "InquiryType",
    "ServiceArea",
    "UrgencyLevel",
    "InquiryResult",
    "classify_inquiry",
    "get_time_of_day",
    "extract_contact_info",
    "detect_deadline",
    "format_available_slots",
    "calculate_lead_score",
    # Advanced triage
    "TriageEngine",
    "TriageResult",
    "ContactContext",
    "InquiryContext",
    "LeadPriority",
    "QualificationStatus",
    "ClientType",
    "get_triage_engine",
    # Scheduling
    "SchedulingService",
    "Advisor",
    "AdvisorRole",
    "Appointment",
    "AppointmentType",
    "AppointmentStatus",
    "AvailableSlot",
    "get_scheduling_service",
    # Conversation
    "FreieBerufeConversationManager",
    "ConversationContext",
    "ConversationResponse",
    "ConversationState",
    "ClientIntent",
    "LeadData",
    "get_conversation_manager",
]
