"""Conversation state and context definitions.

Contains enums for conversation states and patient intents,
plus dataclasses for maintaining conversation context.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, date
from enum import Enum
from typing import Any
from uuid import UUID

from phone_agent.industry.gesundheit.triage import TriageResult
from phone_agent.industry.gesundheit.scheduling import (
    Appointment,
    AppointmentType,
    TimeSlot,
)
from phone_agent.industry.gesundheit.compliance import ConsentType


class ConversationState(str, Enum):
    """States in the healthcare conversation flow."""

    GREETING = "greeting"
    PATIENT_IDENTIFICATION = "patient_identification"
    REASON_INQUIRY = "reason_inquiry"
    TRIAGE_ASSESSMENT = "triage_assessment"
    URGENCY_HANDLING = "urgency_handling"
    APPOINTMENT_SEARCH = "appointment_search"
    APPOINTMENT_OFFER = "appointment_offer"
    APPOINTMENT_CONFIRMATION = "appointment_confirmation"
    CONSENT_CHECK = "consent_check"
    ADDITIONAL_INFO = "additional_info"
    FAREWELL = "farewell"
    TRANSFER_TO_STAFF = "transfer_to_staff"
    EMERGENCY_REDIRECT = "emergency_redirect"
    COMPLETED = "completed"
    # Inbound flow states
    PRESCRIPTION_REQUEST = "prescription_request"
    PRESCRIPTION_DETAILS = "prescription_details"
    LAB_RESULTS_INQUIRY = "lab_results_inquiry"
    LAB_IDENTITY_VERIFICATION = "lab_identity_verification"
    APPOINTMENT_RESCHEDULE = "appointment_reschedule"
    RESCHEDULE_CONFIRM = "reschedule_confirm"


class PatientIntent(str, Enum):
    """Detected patient intents."""

    BOOK_APPOINTMENT = "book_appointment"
    CANCEL_APPOINTMENT = "cancel_appointment"
    RESCHEDULE_APPOINTMENT = "reschedule_appointment"
    REQUEST_PRESCRIPTION = "request_prescription"
    REQUEST_PRESCRIPTION_REFILL = "request_prescription_refill"
    LAB_RESULTS = "lab_results"
    LAB_RESULTS_INQUIRY = "lab_results_inquiry"
    SPEAK_TO_STAFF = "speak_to_staff"
    GENERAL_INQUIRY = "general_inquiry"
    EMERGENCY = "emergency"
    UNKNOWN = "unknown"


@dataclass
class ConversationContext:
    """Context maintained throughout the conversation.

    Tracks all information gathered during the call including
    patient identification, triage results, and booking state.
    """

    call_id: str
    started_at: datetime = field(default_factory=datetime.now)

    # Patient identification
    patient_identified: bool = False
    patient_id: UUID | None = None
    patient_name: str | None = None
    patient_dob: date | None = None
    patient_phone: str | None = None

    # Intent and reason
    detected_intent: PatientIntent = PatientIntent.UNKNOWN
    stated_reason: str | None = None

    # Triage
    triage_performed: bool = False
    triage_result: TriageResult | None = None
    symptoms_mentioned: list[str] = field(default_factory=list)

    # Scheduling
    appointment_type: AppointmentType = AppointmentType.REGULAR
    offered_slots: list[TimeSlot] = field(default_factory=list)
    selected_slot: TimeSlot | None = None
    booked_appointment: Appointment | None = None

    # Consent
    consents_checked: dict[ConsentType, bool] = field(default_factory=dict)

    # Conversation history
    messages: list[dict[str, Any]] = field(default_factory=list)

    # Transfer/escalation
    needs_transfer: bool = False
    transfer_reason: str | None = None

    # Prescription refill
    prescription_medication: str | None = None
    prescription_last_date: date | None = None
    prescription_pharmacy: str | None = None
    prescription_queued: bool = False

    # Lab results
    lab_results_ready: bool = False
    lab_results_discussed: bool = False
    lab_dob_verified: bool = False

    # Rescheduling
    existing_appointment_id: UUID | None = None
    old_appointment_slot: TimeSlot | None = None
    reschedule_reason: str | None = None

    def add_message(self, role: str, content: str, **metadata: Any) -> None:
        """Add a message to conversation history.

        Args:
            role: Message role (user, assistant, system)
            content: Message content
            **metadata: Additional metadata to store
        """
        self.messages.append({
            "role": role,
            "content": content,
            "timestamp": datetime.now().isoformat(),
            **metadata,
        })

    def get_first_name(self) -> str:
        """Get patient's first name for personalization."""
        if self.patient_name:
            return self.patient_name.split()[0]
        return "Patient"


@dataclass
class ConversationResponse:
    """Response from conversation manager.

    Contains the message to speak, state information,
    and any actions to perform.
    """

    state: ConversationState
    message: str
    requires_input: bool = True
    options: list[str] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    # Actions to take
    schedule_callback: bool = False
    send_sms: bool = False
    sms_content: str | None = None
    transfer_call: bool = False
    end_call: bool = False

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for API responses."""
        return {
            "state": self.state.value,
            "message": self.message,
            "requires_input": self.requires_input,
            "options": self.options,
            "metadata": self.metadata,
            "actions": {
                "schedule_callback": self.schedule_callback,
                "send_sms": self.send_sms,
                "sms_content": self.sms_content,
                "transfer_call": self.transfer_call,
                "end_call": self.end_call,
            },
        }
