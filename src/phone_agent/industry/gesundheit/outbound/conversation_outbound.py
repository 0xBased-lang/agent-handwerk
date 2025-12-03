"""Outbound Conversation Manager for Healthcare.

Handles outbound call conversations with:
- Goal-directed dialogue flow
- Identity verification
- Appointment scheduling integration
- Clear success/failure outcomes

State machine:
INTRODUCTION → IDENTITY_VERIFICATION → PURPOSE_STATEMENT →
MAIN_DIALOG → APPOINTMENT_OFFER → CONFIRMATION → FAREWELL
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, date, time
from enum import Enum
from typing import Any
from uuid import UUID, uuid4

from itf_shared import get_logger

log = get_logger(__name__)


class OutboundState(str, Enum):
    """Outbound conversation states."""

    INTRODUCTION = "introduction"
    IDENTITY_VERIFICATION = "identity_verification"
    PURPOSE_STATEMENT = "purpose_statement"
    MAIN_DIALOG = "main_dialog"
    APPOINTMENT_OFFER = "appointment_offer"
    CONFIRMATION = "confirmation"
    FAREWELL = "farewell"
    COMPLETED = "completed"
    FAILED = "failed"


class OutboundOutcome(str, Enum):
    """Outcome of an outbound conversation."""

    # Success outcomes
    APPOINTMENT_CONFIRMED = "appointment_confirmed"
    APPOINTMENT_RESCHEDULED = "appointment_rescheduled"
    INFORMATION_DELIVERED = "information_delivered"
    CALLBACK_SCHEDULED = "callback_scheduled"

    # Neutral outcomes
    PATIENT_DECLINED = "patient_declined"
    PATIENT_UNAVAILABLE = "patient_unavailable"
    CALLBACK_REQUESTED = "callback_requested"
    VOICEMAIL_LEFT = "voicemail_left"

    # Negative outcomes
    WRONG_PERSON = "wrong_person"
    WRONG_NUMBER = "wrong_number"
    IDENTITY_NOT_VERIFIED = "identity_not_verified"
    CONVERSATION_FAILED = "conversation_failed"
    PATIENT_HUNG_UP = "patient_hung_up"


class CampaignType(str, Enum):
    """Type of outbound campaign."""

    REMINDER = "reminder"           # Appointment reminder
    RECALL = "recall"               # Preventive care recall
    NO_SHOW = "no_show"             # No-show follow-up
    LAB_RESULTS = "lab_results"     # Lab results notification
    PRESCRIPTION = "prescription"   # Prescription ready


class OutboundCallType(str, Enum):
    """Type of outbound call for tracking/analytics."""

    APPOINTMENT_REMINDER = "appointment_reminder"
    RECALL_CAMPAIGN = "recall_campaign"
    NO_SHOW_FOLLOWUP = "no_show_followup"
    LAB_RESULTS = "lab_results"
    PRESCRIPTION_READY = "prescription_ready"
    GENERAL_FOLLOWUP = "general_followup"


@dataclass
class OutboundContext:
    """Context for outbound conversation."""

    # Call identification
    call_id: UUID = field(default_factory=uuid4)
    campaign_type: CampaignType = CampaignType.REMINDER

    # Patient information
    patient_id: str = ""
    patient_name: str = ""
    patient_first_name: str = ""
    patient_phone: str = ""
    patient_dob: date | None = None

    # Campaign-specific data
    campaign_id: UUID | None = None
    appointment_id: UUID | None = None
    appointment_date: date | None = None
    appointment_time: time | None = None
    provider_name: str = ""

    # State tracking
    state: OutboundState = OutboundState.INTRODUCTION
    identity_verified: bool = False
    purpose_stated: bool = False

    # Conversation history
    turns: list[dict[str, str]] = field(default_factory=list)

    # Outcome
    outcome: OutboundOutcome | None = None
    outcome_notes: str = ""

    # Scheduling result
    new_appointment_date: date | None = None
    new_appointment_time: time | None = None

    # Timestamps
    started_at: datetime = field(default_factory=datetime.now)
    ended_at: datetime | None = None

    def add_turn(self, role: str, message: str) -> None:
        """Add a conversation turn."""
        self.turns.append({
            "role": role,
            "message": message,
            "timestamp": datetime.now().isoformat(),
        })

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "call_id": str(self.call_id),
            "campaign_type": self.campaign_type.value,
            "patient_id": self.patient_id,
            "patient_name": self.patient_name,
            "state": self.state.value,
            "identity_verified": self.identity_verified,
            "outcome": self.outcome.value if self.outcome else None,
            "outcome_notes": self.outcome_notes,
            "turns_count": len(self.turns),
            "started_at": self.started_at.isoformat(),
            "ended_at": self.ended_at.isoformat() if self.ended_at else None,
        }


@dataclass
class OutboundResponse:
    """Response from conversation manager."""

    state: OutboundState
    message: str
    should_end_call: bool = False
    should_transfer: bool = False
    transfer_target: str | None = None
    wait_for_response: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)


class OutboundConversationManager:
    """Manages outbound call conversations.

    Implements a goal-directed dialogue system for:
    - Appointment reminders
    - Recall campaigns
    - No-show follow-up
    - Lab results notification
    - Prescription ready notification

    Usage:
        manager = OutboundConversationManager(scheduling_service)
        context = OutboundContext(
            campaign_type=CampaignType.REMINDER,
            patient_name="Max Mustermann",
            patient_first_name="Max",
            appointment_date=date.today() + timedelta(days=1),
            appointment_time=time(14, 30),
        )

        # Get initial greeting
        response = await manager.start_conversation(context)

        # Process patient responses
        while not response.should_end_call:
            patient_input = await get_patient_speech()
            response = await manager.process_input(context, patient_input)
    """

    def __init__(
        self,
        scheduling_service: Any | None = None,
        recall_service: Any | None = None,
    ) -> None:
        """Initialize conversation manager.

        Args:
            scheduling_service: For scheduling/rescheduling appointments
            recall_service: For updating recall campaign status
        """
        self._scheduling_service = scheduling_service
        self._recall_service = recall_service

        # German response keywords
        self._positive_keywords = [
            "ja", "okay", "ok", "gut", "richtig", "genau", "passt",
            "stimmt", "korrekt", "gerne", "einverstanden", "bestätigt",
        ]
        self._negative_keywords = [
            "nein", "nicht", "falsch", "absagen", "stornieren",
            "geht nicht", "kann nicht", "leider nicht",
        ]
        self._reschedule_keywords = [
            "verschieben", "anderen termin", "umbuchen", "ändern",
            "später", "früher", "anderer tag", "andere zeit",
        ]
        self._callback_keywords = [
            "zurückrufen", "später anrufen", "gerade schlecht",
            "kann nicht sprechen", "im meeting", "beschäftigt",
        ]

    async def start_conversation(
        self,
        context: OutboundContext,
    ) -> OutboundResponse:
        """Start an outbound conversation.

        Args:
            context: Conversation context with patient info

        Returns:
            Initial response (greeting)
        """
        log.info(
            "Starting outbound conversation",
            call_id=str(context.call_id),
            campaign_type=context.campaign_type.value,
            patient_name=context.patient_name,
        )

        context.state = OutboundState.INTRODUCTION
        greeting = self._get_introduction(context)
        context.add_turn("assistant", greeting)

        return OutboundResponse(
            state=OutboundState.INTRODUCTION,
            message=greeting,
            wait_for_response=True,
        )

    async def process_input(
        self,
        context: OutboundContext,
        user_input: str,
    ) -> OutboundResponse:
        """Process patient input and return next response.

        Args:
            context: Current conversation context
            user_input: Patient's speech (transcribed)

        Returns:
            Next response
        """
        context.add_turn("user", user_input)
        user_lower = user_input.lower()

        log.debug(
            "Processing input",
            call_id=str(context.call_id),
            state=context.state.value,
            input_preview=user_input[:50],
        )

        # Check for callback request (any state)
        if self._is_callback_request(user_lower):
            return await self._handle_callback_request(context)

        # Check for hangup/goodbye (any state)
        if self._is_goodbye(user_lower):
            return await self._handle_goodbye(context)

        # State-specific handling
        match context.state:
            case OutboundState.INTRODUCTION:
                return await self._handle_introduction_response(context, user_lower)
            case OutboundState.IDENTITY_VERIFICATION:
                return await self._handle_identity_response(context, user_lower)
            case OutboundState.PURPOSE_STATEMENT:
                return await self._handle_purpose_response(context, user_lower)
            case OutboundState.MAIN_DIALOG:
                return await self._handle_main_dialog(context, user_lower)
            case OutboundState.APPOINTMENT_OFFER:
                return await self._handle_appointment_response(context, user_lower)
            case OutboundState.CONFIRMATION:
                return await self._handle_confirmation(context, user_lower)
            case OutboundState.FAREWELL:
                return await self._end_conversation(context, OutboundOutcome.INFORMATION_DELIVERED)
            case _:
                return await self._end_conversation(context, OutboundOutcome.CONVERSATION_FAILED)

    # ========== State Handlers ==========

    async def _handle_introduction_response(
        self,
        context: OutboundContext,
        user_input: str,
    ) -> OutboundResponse:
        """Handle response to introduction."""
        # Check if they confirm identity
        if self._is_positive(user_input):
            context.identity_verified = True
            context.state = OutboundState.PURPOSE_STATEMENT
            message = self._get_purpose_statement(context)
            context.add_turn("assistant", message)
            return OutboundResponse(
                state=OutboundState.PURPOSE_STATEMENT,
                message=message,
            )

        # Check if wrong person
        if self._is_negative(user_input) or "falsche nummer" in user_input:
            return await self._end_conversation(context, OutboundOutcome.WRONG_PERSON)

        # Ask for verification
        context.state = OutboundState.IDENTITY_VERIFICATION
        message = self._get_identity_verification_prompt(context)
        context.add_turn("assistant", message)
        return OutboundResponse(
            state=OutboundState.IDENTITY_VERIFICATION,
            message=message,
        )

    async def _handle_identity_response(
        self,
        context: OutboundContext,
        user_input: str,
    ) -> OutboundResponse:
        """Handle identity verification response."""
        # Check if they confirm identity
        if self._is_positive(user_input) or context.patient_first_name.lower() in user_input:
            context.identity_verified = True
            context.state = OutboundState.PURPOSE_STATEMENT
            message = self._get_purpose_statement(context)
            context.add_turn("assistant", message)
            return OutboundResponse(
                state=OutboundState.PURPOSE_STATEMENT,
                message=message,
            )

        # Wrong person
        if self._is_negative(user_input):
            return await self._end_conversation(context, OutboundOutcome.WRONG_PERSON)

        # Still unclear - one more try
        message = (
            f"Entschuldigung, ich möchte sichergehen. "
            f"Spreche ich mit {context.patient_name}?"
        )
        context.add_turn("assistant", message)
        return OutboundResponse(
            state=OutboundState.IDENTITY_VERIFICATION,
            message=message,
        )

    async def _handle_purpose_response(
        self,
        context: OutboundContext,
        user_input: str,
    ) -> OutboundResponse:
        """Handle response to purpose statement."""
        context.purpose_stated = True

        # For reminders - check if they confirm
        if context.campaign_type == CampaignType.REMINDER:
            if self._is_positive(user_input):
                return await self._confirm_appointment(context)
            elif self._is_reschedule(user_input):
                return await self._offer_reschedule(context)
            elif self._is_negative(user_input):
                return await self._handle_cancellation(context)

        # For recalls - ask about scheduling
        if context.campaign_type == CampaignType.RECALL:
            context.state = OutboundState.APPOINTMENT_OFFER
            message = self._get_appointment_offer(context)
            context.add_turn("assistant", message)
            return OutboundResponse(
                state=OutboundState.APPOINTMENT_OFFER,
                message=message,
            )

        # For notifications - check understanding
        context.state = OutboundState.MAIN_DIALOG
        message = "Haben Sie dazu noch Fragen?"
        context.add_turn("assistant", message)
        return OutboundResponse(
            state=OutboundState.MAIN_DIALOG,
            message=message,
        )

    async def _handle_main_dialog(
        self,
        context: OutboundContext,
        user_input: str,
    ) -> OutboundResponse:
        """Handle main dialog phase."""
        # No more questions - end call
        if self._is_negative(user_input) or "keine fragen" in user_input:
            return await self._end_conversation(
                context,
                OutboundOutcome.INFORMATION_DELIVERED,
            )

        # Has questions - could transfer to staff
        if "?" in user_input or "frage" in user_input:
            message = (
                "Für detaillierte Fragen verbinde ich Sie gerne "
                "mit einer Mitarbeiterin. Einen Moment bitte."
            )
            context.add_turn("assistant", message)
            return OutboundResponse(
                state=OutboundState.MAIN_DIALOG,
                message=message,
                should_transfer=True,
                transfer_target="reception",
            )

        # Default - end politely
        return await self._end_conversation(
            context,
            OutboundOutcome.INFORMATION_DELIVERED,
        )

    async def _handle_appointment_response(
        self,
        context: OutboundContext,
        user_input: str,
    ) -> OutboundResponse:
        """Handle response to appointment offer."""
        if self._is_positive(user_input):
            # Accept offered appointment
            context.state = OutboundState.CONFIRMATION
            message = self._get_confirmation_message(context)
            context.add_turn("assistant", message)
            return OutboundResponse(
                state=OutboundState.CONFIRMATION,
                message=message,
            )

        if self._is_reschedule(user_input) or self._is_negative(user_input):
            # Offer alternatives
            message = self._get_alternative_slots_message(context)
            context.add_turn("assistant", message)
            return OutboundResponse(
                state=OutboundState.APPOINTMENT_OFFER,
                message=message,
            )

        # Unclear - ask again
        message = (
            "Möchten Sie den vorgeschlagenen Termin annehmen, "
            "oder soll ich Ihnen andere Termine anbieten?"
        )
        context.add_turn("assistant", message)
        return OutboundResponse(
            state=OutboundState.APPOINTMENT_OFFER,
            message=message,
        )

    async def _handle_confirmation(
        self,
        context: OutboundContext,
        user_input: str,
    ) -> OutboundResponse:
        """Handle confirmation response."""
        if self._is_positive(user_input):
            # Confirmed - end successfully
            outcome = OutboundOutcome.APPOINTMENT_CONFIRMED
            if context.new_appointment_date:
                outcome = OutboundOutcome.APPOINTMENT_RESCHEDULED
            return await self._end_conversation(context, outcome)

        # Not confirmed - go back
        context.state = OutboundState.APPOINTMENT_OFFER
        message = "Kein Problem. Möchten Sie einen anderen Termin?"
        context.add_turn("assistant", message)
        return OutboundResponse(
            state=OutboundState.APPOINTMENT_OFFER,
            message=message,
        )

    # ========== Action Handlers ==========

    async def _confirm_appointment(
        self,
        context: OutboundContext,
    ) -> OutboundResponse:
        """Confirm the existing appointment."""
        context.state = OutboundState.FAREWELL
        context.outcome = OutboundOutcome.APPOINTMENT_CONFIRMED

        message = (
            f"Wunderbar, Ihr Termin am {self._format_date(context.appointment_date)} "
            f"um {self._format_time(context.appointment_time)} Uhr "
            f"ist bestätigt. Wir freuen uns auf Sie! "
            f"Auf Wiederhören."
        )
        context.add_turn("assistant", message)

        return OutboundResponse(
            state=OutboundState.FAREWELL,
            message=message,
            should_end_call=True,
        )

    async def _offer_reschedule(
        self,
        context: OutboundContext,
    ) -> OutboundResponse:
        """Offer to reschedule appointment."""
        context.state = OutboundState.APPOINTMENT_OFFER

        message = (
            "Natürlich können wir den Termin verschieben. "
            "Wann würde es Ihnen besser passen? "
            "Vormittags oder nachmittags?"
        )
        context.add_turn("assistant", message)

        return OutboundResponse(
            state=OutboundState.APPOINTMENT_OFFER,
            message=message,
        )

    async def _handle_cancellation(
        self,
        context: OutboundContext,
    ) -> OutboundResponse:
        """Handle appointment cancellation."""
        context.state = OutboundState.CONFIRMATION

        message = (
            "Verstanden. Möchten Sie den Termin absagen, "
            "oder sollen wir einen neuen Termin finden?"
        )
        context.add_turn("assistant", message)

        return OutboundResponse(
            state=OutboundState.CONFIRMATION,
            message=message,
        )

    async def _handle_callback_request(
        self,
        context: OutboundContext,
    ) -> OutboundResponse:
        """Handle request for callback."""
        context.outcome = OutboundOutcome.CALLBACK_REQUESTED
        context.outcome_notes = "Patient requested callback"

        message = (
            "Natürlich, kein Problem. Wir rufen Sie später noch einmal an. "
            "Auf Wiederhören!"
        )
        context.add_turn("assistant", message)

        return await self._end_conversation(
            context,
            OutboundOutcome.CALLBACK_REQUESTED,
            message,
        )

    async def _handle_goodbye(
        self,
        context: OutboundContext,
    ) -> OutboundResponse:
        """Handle patient saying goodbye."""
        if context.state in (OutboundState.FAREWELL, OutboundState.CONFIRMATION):
            outcome = context.outcome or OutboundOutcome.INFORMATION_DELIVERED
        else:
            outcome = OutboundOutcome.PATIENT_HUNG_UP

        return await self._end_conversation(context, outcome)

    async def _end_conversation(
        self,
        context: OutboundContext,
        outcome: OutboundOutcome,
        final_message: str | None = None,
    ) -> OutboundResponse:
        """End the conversation."""
        context.state = OutboundState.COMPLETED
        context.outcome = outcome
        context.ended_at = datetime.now()

        if final_message is None:
            final_message = "Vielen Dank für das Gespräch. Auf Wiederhören!"

        context.add_turn("assistant", final_message)

        log.info(
            "Conversation ended",
            call_id=str(context.call_id),
            outcome=outcome.value,
            duration=(context.ended_at - context.started_at).total_seconds(),
        )

        return OutboundResponse(
            state=OutboundState.COMPLETED,
            message=final_message,
            should_end_call=True,
            metadata={"outcome": outcome.value},
        )

    # ========== Message Generators ==========

    def _get_introduction(self, context: OutboundContext) -> str:
        """Generate introduction message."""
        time_greeting = self._get_time_greeting()

        if context.campaign_type == CampaignType.REMINDER:
            return (
                f"{time_greeting}, hier ist der automatische Terminservice "
                f"der Praxis. Spreche ich mit {context.patient_name}?"
            )
        elif context.campaign_type == CampaignType.RECALL:
            return (
                f"{time_greeting}, hier ist der Vorsorge-Erinnerungsservice "
                f"der Praxis. Spreche ich mit {context.patient_name}?"
            )
        elif context.campaign_type == CampaignType.NO_SHOW:
            return (
                f"{time_greeting}, hier ist die Praxis. "
                f"Ich rufe an wegen Ihres heutigen Termins. "
                f"Spreche ich mit {context.patient_name}?"
            )
        else:
            return (
                f"{time_greeting}, hier ist die Praxis. "
                f"Spreche ich mit {context.patient_name}?"
            )

    def _get_identity_verification_prompt(self, context: OutboundContext) -> str:
        """Generate identity verification prompt."""
        return (
            f"Können Sie mir bitte Ihren Vornamen nennen, "
            f"damit ich sichergehen kann, dass ich richtig verbunden bin?"
        )

    def _get_purpose_statement(self, context: OutboundContext) -> str:
        """Generate purpose statement based on campaign type."""
        if context.campaign_type == CampaignType.REMINDER:
            return (
                f"Ich rufe an, um Sie an Ihren Termin "
                f"am {self._format_date(context.appointment_date)} "
                f"um {self._format_time(context.appointment_time)} Uhr "
                f"bei {context.provider_name or 'uns'} zu erinnern. "
                f"Können Sie diesen Termin wahrnehmen?"
            )
        elif context.campaign_type == CampaignType.RECALL:
            return (
                "Wir möchten Sie darauf aufmerksam machen, "
                "dass es Zeit für Ihre nächste Vorsorgeuntersuchung ist. "
                "Dürfen wir einen Termin für Sie vereinbaren?"
            )
        elif context.campaign_type == CampaignType.NO_SHOW:
            return (
                f"Wir haben Sie heute zum Termin um "
                f"{self._format_time(context.appointment_time)} Uhr erwartet. "
                f"Ist alles in Ordnung? Können wir einen neuen Termin vereinbaren?"
            )
        elif context.campaign_type == CampaignType.LAB_RESULTS:
            return (
                "Ihre Laborergebnisse liegen vor. "
                "Bitte vereinbaren Sie einen Termin zur Besprechung."
            )
        elif context.campaign_type == CampaignType.PRESCRIPTION:
            return (
                "Ihr Rezept liegt zur Abholung bereit. "
                "Sie können es während der Sprechzeiten abholen."
            )
        else:
            return "Ich habe eine wichtige Mitteilung für Sie."

    def _get_appointment_offer(self, context: OutboundContext) -> str:
        """Generate appointment offer message."""
        # In real implementation, query SchedulingService for slots
        return (
            "Ich kann Ihnen folgende Termine anbieten: "
            "Morgen um 10 Uhr, oder übermorgen um 14 Uhr. "
            "Welcher Termin passt Ihnen besser?"
        )

    def _get_alternative_slots_message(self, context: OutboundContext) -> str:
        """Generate alternative slots message."""
        return (
            "Ich schaue nach anderen Terminen. "
            "Wie wäre es mit nächster Woche? "
            "Ich hätte Montag um 9 Uhr oder Mittwoch um 15 Uhr."
        )

    def _get_confirmation_message(self, context: OutboundContext) -> str:
        """Generate confirmation message."""
        if context.new_appointment_date:
            return (
                f"Ich habe den Termin für Sie gebucht: "
                f"{self._format_date(context.new_appointment_date)} "
                f"um {self._format_time(context.new_appointment_time)} Uhr. "
                f"Sie erhalten eine SMS-Bestätigung. Ist das korrekt?"
            )
        else:
            return (
                f"Ihr Termin am {self._format_date(context.appointment_date)} "
                f"um {self._format_time(context.appointment_time)} Uhr ist bestätigt. "
                f"Ist das korrekt?"
            )

    # ========== Helper Methods ==========

    def _is_positive(self, text: str) -> bool:
        """Check if text contains positive response."""
        return any(kw in text for kw in self._positive_keywords)

    def _is_negative(self, text: str) -> bool:
        """Check if text contains negative response."""
        return any(kw in text for kw in self._negative_keywords)

    def _is_reschedule(self, text: str) -> bool:
        """Check if text requests rescheduling."""
        return any(kw in text for kw in self._reschedule_keywords)

    def _is_callback_request(self, text: str) -> bool:
        """Check if text requests callback."""
        return any(kw in text for kw in self._callback_keywords)

    def _is_goodbye(self, text: str) -> bool:
        """Check if text is a goodbye."""
        goodbye_keywords = [
            "tschüss", "auf wiedersehen", "wiederhören",
            "bye", "ciao", "servus",
        ]
        return any(kw in text for kw in goodbye_keywords)

    def _get_time_greeting(self) -> str:
        """Get time-appropriate greeting."""
        hour = datetime.now().hour
        if hour < 12:
            return "Guten Morgen"
        elif hour < 18:
            return "Guten Tag"
        else:
            return "Guten Abend"

    def _format_date(self, d: date | None) -> str:
        """Format date in German style."""
        if d is None:
            return "dem vereinbarten Tag"

        weekdays = [
            "Montag", "Dienstag", "Mittwoch", "Donnerstag",
            "Freitag", "Samstag", "Sonntag",
        ]
        weekday = weekdays[d.weekday()]
        return f"{weekday}, den {d.day}.{d.month}."

    def _format_time(self, t: time | None) -> str:
        """Format time in German style."""
        if t is None:
            return "der vereinbarten Zeit"
        return f"{t.hour}:{t.minute:02d}"


# Global singleton
_conversation_manager: OutboundConversationManager | None = None


def get_outbound_conversation_manager(
    scheduling_service: Any | None = None,
    recall_service: Any | None = None,
) -> OutboundConversationManager:
    """Get or create the global OutboundConversationManager singleton."""
    global _conversation_manager

    if _conversation_manager is None:
        _conversation_manager = OutboundConversationManager(
            scheduling_service=scheduling_service,
            recall_service=recall_service,
        )

    return _conversation_manager
