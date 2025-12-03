"""Freie Berufe conversation management.

Manages the state machine for professional services phone conversations.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class ConversationState(str, Enum):
    """States in the conversation flow."""

    GREETING = "greeting"
    INTENT_DETECTION = "intent_detection"
    LEAD_INTAKE = "lead_intake"
    QUALIFICATION = "qualification"
    APPOINTMENT_BOOKING = "appointment_booking"
    CALLBACK_SCHEDULING = "callback_scheduling"
    EXISTING_CLIENT = "existing_client"
    INFORMATION = "information"
    REJECTION = "rejection"
    ESCALATION = "escalation"
    FAREWELL = "farewell"


class ClientIntent(str, Enum):
    """Detected client intents."""

    NEW_INQUIRY = "new_inquiry"
    EXISTING_CLIENT = "existing_client"
    CALLBACK_REQUEST = "callback_request"
    INFORMATION_REQUEST = "information_request"
    COMPLAINT = "complaint"
    REFERRAL = "referral"
    UNKNOWN = "unknown"


@dataclass
class LeadData:
    """Data collected during lead intake."""

    # Contact info
    name: str | None = None
    phone: str | None = None
    email: str | None = None
    company: str | None = None
    position: str | None = None

    # Inquiry details
    service_area: str | None = None
    topic: str | None = None
    description: str | None = None

    # Qualification
    has_deadline: bool = False
    deadline_date: str | None = None
    is_decision_maker: bool = False
    budget_indicated: bool = False

    # Lead source
    referral_source: str | None = None
    referred_by: str | None = None

    # Appointment
    preferred_date: str | None = None
    preferred_time: str | None = None
    preferred_format: str | None = None  # phone, video, in-person

    # Scoring
    lead_score: int = 0
    qualification_status: str = "pending"

    def get_missing_fields(self) -> list[str]:
        """Get list of required fields that are missing."""
        missing = []
        if not self.name:
            missing.append("Name")
        if not self.phone:
            missing.append("Telefonnummer")
        if not self.topic and not self.service_area:
            missing.append("Anliegen")
        return missing

    def is_complete_for_booking(self) -> bool:
        """Check if enough info for appointment booking."""
        return bool(self.name and self.phone and (self.topic or self.service_area))


@dataclass
class ConversationContext:
    """Context for the current conversation."""

    call_id: str
    state: ConversationState = ConversationState.GREETING
    intent: ClientIntent = ClientIntent.UNKNOWN
    lead_data: LeadData = field(default_factory=LeadData)

    # Conversation history
    turn_count: int = 0
    messages: list[dict[str, str]] = field(default_factory=list)
    started_at: datetime = field(default_factory=datetime.now)

    # Practice context
    practice_name: str = "Kanzlei"
    specialty: str = "Rechts- und Steuerberatung"

    # Flags
    needs_escalation: bool = False
    escalation_reason: str | None = None
    is_existing_client: bool = False


@dataclass
class ConversationResponse:
    """Response from conversation processing."""

    message: str
    next_state: ConversationState
    intent: ClientIntent
    appointment_booked: bool = False
    callback_scheduled: bool = False
    lead_data: LeadData | None = None
    needs_escalation: bool = False
    escalation_reason: str | None = None
    suggested_slots: list[dict[str, Any]] = field(default_factory=list)
    actions: list[str] = field(default_factory=list)


class FreieBerufeConversationManager:
    """Manages conversation flow for professional services calls."""

    def __init__(
        self,
        practice_name: str = "Kanzlei",
        specialty: str = "Rechts- und Steuerberatung",
    ):
        """Initialize conversation manager."""
        self._practice_name = practice_name
        self._specialty = specialty
        self._contexts: dict[str, ConversationContext] = {}

    def start_conversation(self, call_id: str) -> ConversationContext:
        """Start a new conversation."""
        context = ConversationContext(
            call_id=call_id,
            practice_name=self._practice_name,
            specialty=self._specialty,
        )
        self._contexts[call_id] = context
        return context

    def get_context(self, call_id: str) -> ConversationContext | None:
        """Get existing conversation context."""
        return self._contexts.get(call_id)

    def process_turn(
        self,
        call_id: str,
        client_message: str,
    ) -> ConversationResponse:
        """
        Process a conversation turn.

        Args:
            call_id: Unique call identifier
            client_message: What the client said

        Returns:
            ConversationResponse with next message and state
        """
        context = self._contexts.get(call_id)
        if not context:
            context = self.start_conversation(call_id)

        context.turn_count += 1
        context.messages.append({"role": "client", "content": client_message})

        # Process based on current state
        response = self._process_state(context, client_message)

        # Update context state
        context.state = response.next_state
        context.intent = response.intent
        context.messages.append({"role": "assistant", "content": response.message})

        return response

    def _process_state(
        self,
        context: ConversationContext,
        message: str,
    ) -> ConversationResponse:
        """Process message based on current state."""
        handlers = {
            ConversationState.GREETING: self._handle_greeting,
            ConversationState.INTENT_DETECTION: self._handle_intent_detection,
            ConversationState.LEAD_INTAKE: self._handle_lead_intake,
            ConversationState.QUALIFICATION: self._handle_qualification,
            ConversationState.APPOINTMENT_BOOKING: self._handle_appointment_booking,
            ConversationState.CALLBACK_SCHEDULING: self._handle_callback_scheduling,
            ConversationState.EXISTING_CLIENT: self._handle_existing_client,
            ConversationState.INFORMATION: self._handle_information,
            ConversationState.REJECTION: self._handle_rejection,
            ConversationState.ESCALATION: self._handle_escalation,
            ConversationState.FAREWELL: self._handle_farewell,
        }

        handler = handlers.get(context.state, self._handle_intent_detection)
        return handler(context, message)

    def _handle_greeting(
        self,
        context: ConversationContext,
        message: str,
    ) -> ConversationResponse:
        """Handle initial greeting."""
        response_message = (
            f"Guten Tag, {context.practice_name}, Sie sprechen mit dem Telefonassistenten. "
            "Wie kann ich Ihnen behilflich sein?"
        )

        return ConversationResponse(
            message=response_message,
            next_state=ConversationState.INTENT_DETECTION,
            intent=ClientIntent.UNKNOWN,
        )

    def _handle_intent_detection(
        self,
        context: ConversationContext,
        message: str,
    ) -> ConversationResponse:
        """Detect client intent from message."""
        message_lower = message.lower()

        # Check for existing client
        if any(w in message_lower for w in ["mandant", "bestehend", "schon bei ihnen", "mein berater"]):
            context.is_existing_client = True
            return ConversationResponse(
                message="Willkommen zurück! Darf ich fragen, mit welchem Berater Sie normalerweise sprechen?",
                next_state=ConversationState.EXISTING_CLIENT,
                intent=ClientIntent.EXISTING_CLIENT,
            )

        # Check for callback request
        if any(w in message_lower for w in ["rückruf", "zurückrufen", "erreichbar"]):
            return ConversationResponse(
                message="Gerne organisiere ich einen Rückruf. Wann sind Sie am besten erreichbar?",
                next_state=ConversationState.CALLBACK_SCHEDULING,
                intent=ClientIntent.CALLBACK_REQUEST,
            )

        # Check for complaint
        if any(w in message_lower for w in ["beschwerde", "unzufrieden", "problem"]):
            return ConversationResponse(
                message="Das tut mir leid zu hören. Ich verbinde Sie mit einem verantwortlichen Mitarbeiter.",
                next_state=ConversationState.ESCALATION,
                intent=ClientIntent.COMPLAINT,
                needs_escalation=True,
                escalation_reason="Beschwerde",
            )

        # Check for information request only
        if any(w in message_lower for w in ["öffnungszeiten", "adresse", "wo", "erreichbar"]):
            return ConversationResponse(
                message=self._get_information_response(message),
                next_state=ConversationState.FAREWELL,
                intent=ClientIntent.INFORMATION_REQUEST,
            )

        # Check for referral
        if any(w in message_lower for w in ["empfohlen", "empfehlung"]):
            context.lead_data.referral_source = "Empfehlung"
            self._extract_lead_data(context, message)
            return ConversationResponse(
                message="Vielen Dank für Ihr Vertrauen! Darf ich fragen, wer uns empfohlen hat?",
                next_state=ConversationState.LEAD_INTAKE,
                intent=ClientIntent.REFERRAL,
            )

        # Default to new inquiry
        self._extract_lead_data(context, message)
        return ConversationResponse(
            message=(
                "Vielen Dank für Ihre Anfrage. Um Sie bestmöglich beraten zu können, "
                "hätte ich ein paar Fragen. Worum geht es bei Ihrem Anliegen?"
            ),
            next_state=ConversationState.LEAD_INTAKE,
            intent=ClientIntent.NEW_INQUIRY,
        )

    def _handle_lead_intake(
        self,
        context: ConversationContext,
        message: str,
    ) -> ConversationResponse:
        """Handle lead data collection."""
        self._extract_lead_data(context, message)

        missing = context.lead_data.get_missing_fields()

        if not missing:
            # All basic data collected, move to qualification
            return ConversationResponse(
                message="Vielen Dank. Gibt es eine Frist, die wir beachten müssen?",
                next_state=ConversationState.QUALIFICATION,
                intent=ClientIntent.NEW_INQUIRY,
                lead_data=context.lead_data,
            )

        # Ask for next missing field
        first_missing = missing[0]
        response_message = self._get_question_for_field(first_missing)

        return ConversationResponse(
            message=response_message,
            next_state=ConversationState.LEAD_INTAKE,
            intent=ClientIntent.NEW_INQUIRY,
        )

    def _handle_qualification(
        self,
        context: ConversationContext,
        message: str,
    ) -> ConversationResponse:
        """Handle lead qualification."""
        message_lower = message.lower()

        # Check for deadline
        if any(w in message_lower for w in ["ja", "frist", "termin", "bis", "spätestens"]):
            context.lead_data.has_deadline = True

            # Extract deadline details
            deadline_info = self._extract_deadline(message)
            if deadline_info.get("deadline_date"):
                context.lead_data.deadline_date = deadline_info["deadline_date"]

        # Check for urgency indicators
        if any(w in message_lower for w in ["dringend", "eilig", "sofort", "heute", "morgen"]):
            context.lead_data.has_deadline = True

        # Move to appointment booking
        return ConversationResponse(
            message=(
                "Verstanden. Ich kann Ihnen gerne einen Erstberatungstermin anbieten. "
                "Wann passt es Ihnen am besten? Wir haben Termine vor Ort, telefonisch oder per Video."
            ),
            next_state=ConversationState.APPOINTMENT_BOOKING,
            intent=ClientIntent.NEW_INQUIRY,
            lead_data=context.lead_data,
        )

    def _handle_appointment_booking(
        self,
        context: ConversationContext,
        message: str,
    ) -> ConversationResponse:
        """Handle appointment booking."""
        message_lower = message.lower()

        # Extract preferences
        if "telefon" in message_lower:
            context.lead_data.preferred_format = "phone"
        elif "video" in message_lower:
            context.lead_data.preferred_format = "video"
        else:
            context.lead_data.preferred_format = "in-person"

        # Extract date/time if mentioned
        date_info = self._extract_date_time(message)
        if date_info.get("date"):
            context.lead_data.preferred_date = date_info["date"]
        if date_info.get("time"):
            context.lead_data.preferred_time = date_info["time"]

        # Simulate booking confirmation
        return ConversationResponse(
            message=self._generate_booking_confirmation(context),
            next_state=ConversationState.FAREWELL,
            intent=ClientIntent.NEW_INQUIRY,
            appointment_booked=True,
            lead_data=context.lead_data,
            actions=["create_appointment", "send_email_confirmation"],
        )

    def _handle_callback_scheduling(
        self,
        context: ConversationContext,
        message: str,
    ) -> ConversationResponse:
        """Handle callback scheduling."""
        self._extract_lead_data(context, message)

        return ConversationResponse(
            message=(
                "Vielen Dank. Ein Berater wird Sie schnellstmöglich zurückrufen. "
                "Bei dringenden Anliegen bemühen wir uns um einen Rückruf innerhalb von 2 Stunden, "
                "ansonsten innerhalb des nächsten Werktages."
            ),
            next_state=ConversationState.FAREWELL,
            intent=ClientIntent.CALLBACK_REQUEST,
            callback_scheduled=True,
            lead_data=context.lead_data,
            actions=["schedule_callback"],
        )

    def _handle_existing_client(
        self,
        context: ConversationContext,
        message: str,
    ) -> ConversationResponse:
        """Handle existing client routing."""
        return ConversationResponse(
            message=(
                "Ich versuche, Sie mit dem zuständigen Berater zu verbinden. "
                "Einen Moment bitte."
            ),
            next_state=ConversationState.FAREWELL,
            intent=ClientIntent.EXISTING_CLIENT,
            actions=["transfer_to_advisor"],
        )

    def _handle_information(
        self,
        context: ConversationContext,
        message: str,
    ) -> ConversationResponse:
        """Handle information requests."""
        return ConversationResponse(
            message=self._get_information_response(message),
            next_state=ConversationState.FAREWELL,
            intent=ClientIntent.INFORMATION_REQUEST,
        )

    def _handle_rejection(
        self,
        context: ConversationContext,
        message: str,
    ) -> ConversationResponse:
        """Handle polite rejection for non-matching inquiries."""
        return ConversationResponse(
            message=(
                "Vielen Dank für Ihre Anfrage. Leider liegt Ihr Anliegen außerhalb unseres "
                "Tätigkeitsbereichs. Ich empfehle Ihnen, sich an einen spezialisierten "
                "Kollegen zu wenden. Bei zukünftigen Fragen zu unserem Fachgebiet "
                "sind wir gerne für Sie da."
            ),
            next_state=ConversationState.FAREWELL,
            intent=context.intent,
        )

    def _handle_escalation(
        self,
        context: ConversationContext,
        message: str,
    ) -> ConversationResponse:
        """Handle escalation to human."""
        return ConversationResponse(
            message="Einen Moment bitte, ich verbinde Sie.",
            next_state=ConversationState.FAREWELL,
            intent=context.intent,
            needs_escalation=True,
            escalation_reason=context.escalation_reason,
            actions=["transfer_to_human"],
        )

    def _handle_farewell(
        self,
        context: ConversationContext,
        message: str,
    ) -> ConversationResponse:
        """Handle farewell."""
        return ConversationResponse(
            message="Vielen Dank für Ihren Anruf! Bei weiteren Fragen sind wir gerne für Sie da. Auf Wiederhören!",
            next_state=ConversationState.FAREWELL,
            intent=context.intent,
            actions=["end_call"],
        )

    def _extract_lead_data(self, context: ConversationContext, message: str) -> None:
        """Extract lead data from message."""
        from phone_agent.industry.freie_berufe.workflows import (
            extract_contact_info,
            classify_inquiry,
        )

        data = context.lead_data
        contact_info = extract_contact_info(message)

        # Update contact info
        if not data.name and contact_info.get("name"):
            data.name = contact_info["name"]
        if not data.phone and contact_info.get("phone"):
            data.phone = contact_info["phone"]
        if not data.email and contact_info.get("email"):
            data.email = contact_info["email"]
        if not data.company and contact_info.get("company"):
            data.company = contact_info["company"]

        # Classify inquiry
        inquiry_result = classify_inquiry(message)
        if not data.service_area:
            data.service_area = inquiry_result.service_area.value
        if not data.topic and inquiry_result.inquiry_type.value != "information":
            data.topic = inquiry_result.reason

    def _get_question_for_field(self, field: str) -> str:
        """Get appropriate question for a missing field."""
        questions = {
            "Name": "Auf welchen Namen darf ich die Anfrage aufnehmen?",
            "Telefonnummer": "Unter welcher Nummer erreichen wir Sie am besten?",
            "Anliegen": "Worum geht es bei Ihrem Anliegen?",
        }
        return questions.get(field, f"Ich benötige noch: {field}")

    def _get_information_response(self, message: str) -> str:
        """Generate response for information requests."""
        message_lower = message.lower()

        if "öffnungszeit" in message_lower:
            return (
                "Wir sind Montag bis Donnerstag von 9 bis 18 Uhr "
                "und Freitag von 9 bis 16 Uhr für Sie da."
            )

        if "adresse" in message_lower or "wo" in message_lower:
            return (
                "Sie finden uns in der Musterstraße 1, 12345 Musterstadt. "
                "Parkplätze sind im Hof verfügbar."
            )

        return "Wie kann ich Ihnen weiterhelfen?"

    def _extract_deadline(self, message: str) -> dict[str, Any]:
        """Extract deadline information from message."""
        from phone_agent.industry.freie_berufe.workflows import detect_deadline
        return detect_deadline(message)

    def _extract_date_time(self, message: str) -> dict[str, Any]:
        """Extract date and time from message."""
        import re
        from datetime import datetime, timedelta

        result: dict[str, Any] = {}
        message_lower = message.lower()
        today = datetime.now()

        # Time patterns
        time_match = re.search(r'(\d{1,2})\s*(?:uhr|:)', message_lower)
        if time_match:
            hour = int(time_match.group(1))
            if 8 <= hour <= 18:
                result["time"] = f"{hour:02d}:00"

        # Relative dates
        if "heute" in message_lower:
            result["date"] = today.strftime("%Y-%m-%d")
        elif "morgen" in message_lower:
            result["date"] = (today + timedelta(days=1)).strftime("%Y-%m-%d")
        elif "nächste woche" in message_lower:
            result["date"] = (today + timedelta(days=7)).strftime("%Y-%m-%d")

        return result

    def _generate_booking_confirmation(self, context: ConversationContext) -> str:
        """Generate booking confirmation message."""
        data = context.lead_data

        format_text = {
            "phone": "telefonischen",
            "video": "Video-",
            "in-person": "persönlichen",
        }.get(data.preferred_format, "")

        message = (
            f"Perfekt! Ich habe einen {format_text}Erstberatungstermin für Sie vorgemerkt. "
            "Sie erhalten in Kürze eine Bestätigung per E-Mail mit allen Details "
            "und einer Liste der Unterlagen, die Sie bitte mitbringen."
        )

        if data.has_deadline:
            message += " Aufgrund der Frist werden wir uns bemühen, Sie prioritär zu beraten."

        message += (
            " Bitte sagen Sie rechtzeitig ab, falls Sie den Termin nicht wahrnehmen können."
        )

        return message

    def end_conversation(self, call_id: str) -> None:
        """End and clean up a conversation."""
        if call_id in self._contexts:
            del self._contexts[call_id]


# Singleton instance with thread-safe initialization
_conversation_manager: FreieBerufeConversationManager | None = None
_conversation_manager_lock = __import__("threading").Lock()


def get_conversation_manager(
    practice_name: str = "Kanzlei",
    specialty: str = "Rechts- und Steuerberatung",
) -> FreieBerufeConversationManager:
    """Get or create conversation manager singleton.

    Thread-safe via double-checked locking pattern.
    """
    global _conversation_manager
    if _conversation_manager is None:
        with _conversation_manager_lock:
            # Double-check after acquiring lock
            if _conversation_manager is None:
                _conversation_manager = FreieBerufeConversationManager(practice_name, specialty)
    return _conversation_manager
