"""Healthcare (Gesundheit) industry configuration.

Implements comprehensive healthcare automation for German ambulatory practices:
- Telephone triage with symptom assessment
- Intelligent appointment scheduling
- Patient recall campaigns
- DSGVO/GDPR compliance
"""

# Prompts
from phone_agent.industry.gesundheit.prompts import (
    SYSTEM_PROMPT,
    GREETING_PROMPT,
    TRIAGE_PROMPT,
    APPOINTMENT_PROMPT,
    FAREWELL_PROMPT,
)

# Basic workflows
from phone_agent.industry.gesundheit.workflows import (
    TriageLevel,
    TriageResult as BasicTriageResult,
    perform_triage,
)

# Advanced triage
from phone_agent.industry.gesundheit.triage import (
    TriageEngine,
    TriageResult,
    Symptom,
    SymptomCategory,
    UrgencyLevel,
    PatientContext,
    get_triage_engine,
)

# Scheduling
from phone_agent.industry.gesundheit.scheduling import (
    SchedulingService,
    SchedulingPreferences,
    TimeSlot,
    Appointment,
    AppointmentType,
    Patient,
    get_scheduling_service,
)

# Recall campaigns
from phone_agent.industry.gesundheit.recall import (
    RecallService,
    RecallCampaign,
    RecallPatient,
    RecallType,
    RecallStatus,
    ContactMethod,
    get_recall_service,
)

# Compliance
from phone_agent.industry.gesundheit.compliance import (
    ConsentManager,
    ConsentType,
    ConsentStatus,
    Consent,
    AuditLogger,
    AuditAction,
    DataProtectionService,
    get_consent_manager,
    get_audit_logger,
    get_data_protection_service,
)

__all__ = [
    # Prompts
    "SYSTEM_PROMPT",
    "GREETING_PROMPT",
    "TRIAGE_PROMPT",
    "APPOINTMENT_PROMPT",
    "FAREWELL_PROMPT",
    # Basic triage
    "TriageLevel",
    "BasicTriageResult",
    "perform_triage",
    # Advanced triage
    "TriageEngine",
    "TriageResult",
    "Symptom",
    "SymptomCategory",
    "UrgencyLevel",
    "PatientContext",
    "get_triage_engine",
    # Scheduling
    "SchedulingService",
    "SchedulingPreferences",
    "TimeSlot",
    "Appointment",
    "AppointmentType",
    "Patient",
    "get_scheduling_service",
    # Recall
    "RecallService",
    "RecallCampaign",
    "RecallPatient",
    "RecallType",
    "RecallStatus",
    "ContactMethod",
    "get_recall_service",
    # Compliance
    "ConsentManager",
    "ConsentType",
    "ConsentStatus",
    "Consent",
    "AuditLogger",
    "AuditAction",
    "DataProtectionService",
    "get_consent_manager",
    "get_audit_logger",
    "get_data_protection_service",
]
