"""Gastro (Restaurant/Hospitality) industry configuration.

Implements comprehensive automation for German restaurants:
- Reservation intake and management
- Party size and special request handling
- No-show prevention and reminders
- DSGVO/GDPR compliance
"""

# Prompts
from phone_agent.industry.gastro.prompts import (
    SYSTEM_PROMPT,
    GREETING_PROMPT,
    RESERVATION_INTAKE_PROMPT,
    AVAILABILITY_PROMPT,
    SPECIAL_REQUESTS_PROMPT,
    CONFIRMATION_PROMPT,
    CANCELLATION_PROMPT,
    FAREWELL_PROMPT,
    REMINDER_CALL_PROMPT,
    SMS_RESERVATION_CONFIRMATION,
    SMS_RESERVATION_REMINDER,
    SMS_NO_SHOW_WARNING,
)

# Basic workflows
from phone_agent.industry.gastro.workflows import (
    RequestType,
    ServicePeriod,
    RequestResult,
    classify_request,
    get_service_period,
    get_time_of_day,
    extract_party_size,
    extract_date_time,
    format_available_slots,
)

# Advanced triage engine
from phone_agent.industry.gastro.triage import (
    TriageEngine,
    TriageResult,
    GuestContext,
    GuestPriority,
    RequestUrgency,
    SpecialRequest,
    SpecialRequestType,
    ReservationSlot,
    get_triage_engine,
)

# Scheduling
from phone_agent.industry.gastro.scheduling import (
    SchedulingService,
    Table,
    TableStatus,
    TimeSlot,
    Reservation,
    ReservationStatus,
    AvailabilitySlot,
    get_scheduling_service,
)

# Conversation manager
from phone_agent.industry.gastro.conversation import (
    GastroConversationManager,
    ConversationContext,
    ConversationResponse,
    ConversationState,
    GuestIntent,
    ReservationData,
    get_conversation_manager,
)

__all__ = [
    # Prompts
    "SYSTEM_PROMPT",
    "GREETING_PROMPT",
    "RESERVATION_INTAKE_PROMPT",
    "AVAILABILITY_PROMPT",
    "SPECIAL_REQUESTS_PROMPT",
    "CONFIRMATION_PROMPT",
    "CANCELLATION_PROMPT",
    "FAREWELL_PROMPT",
    "REMINDER_CALL_PROMPT",
    "SMS_RESERVATION_CONFIRMATION",
    "SMS_RESERVATION_REMINDER",
    "SMS_NO_SHOW_WARNING",
    # Basic workflows
    "RequestType",
    "ServicePeriod",
    "RequestResult",
    "classify_request",
    "get_service_period",
    "get_time_of_day",
    "extract_party_size",
    "extract_date_time",
    "format_available_slots",
    # Advanced triage
    "TriageEngine",
    "TriageResult",
    "GuestContext",
    "GuestPriority",
    "RequestUrgency",
    "SpecialRequest",
    "SpecialRequestType",
    "ReservationSlot",
    "get_triage_engine",
    # Scheduling
    "SchedulingService",
    "Table",
    "TableStatus",
    "TimeSlot",
    "Reservation",
    "ReservationStatus",
    "AvailabilitySlot",
    "get_scheduling_service",
    # Conversation
    "GastroConversationManager",
    "ConversationContext",
    "ConversationResponse",
    "ConversationState",
    "GuestIntent",
    "ReservationData",
    "get_conversation_manager",
]
