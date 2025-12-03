"""Gastro conversation management.

Manages the state machine for restaurant phone conversations.
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
    RESERVATION_INTAKE = "reservation_intake"
    AVAILABILITY_CHECK = "availability_check"
    SPECIAL_REQUESTS = "special_requests"
    CONFIRMATION = "confirmation"
    MODIFICATION = "modification"
    CANCELLATION = "cancellation"
    INFORMATION = "information"
    ESCALATION = "escalation"
    FAREWELL = "farewell"


class GuestIntent(str, Enum):
    """Detected guest intents."""

    NEW_RESERVATION = "new_reservation"
    MODIFY_RESERVATION = "modify_reservation"
    CANCEL_RESERVATION = "cancel_reservation"
    GET_INFORMATION = "get_information"
    MAKE_COMPLAINT = "make_complaint"
    GROUP_BOOKING = "group_booking"
    UNKNOWN = "unknown"


@dataclass
class ReservationData:
    """Data collected during reservation flow."""

    guest_name: str | None = None
    phone: str | None = None
    email: str | None = None
    party_size: int | None = None
    preferred_date: str | None = None
    preferred_time: str | None = None
    confirmed_date: str | None = None
    confirmed_time: str | None = None
    special_requests: list[str] = field(default_factory=list)
    allergies: list[str] = field(default_factory=list)
    occasion: str | None = None
    seating_preference: str | None = None
    reservation_id: str | None = None

    def get_missing_fields(self) -> list[str]:
        """Get list of required fields that are missing."""
        missing = []
        if not self.guest_name:
            missing.append("Name")
        if not self.phone:
            missing.append("Telefonnummer")
        if not self.party_size:
            missing.append("Personenzahl")
        if not self.preferred_date:
            missing.append("Datum")
        if not self.preferred_time:
            missing.append("Uhrzeit")
        return missing

    def is_complete(self) -> bool:
        """Check if all required fields are collected."""
        return len(self.get_missing_fields()) == 0


@dataclass
class ConversationContext:
    """Context for the current conversation."""

    call_id: str
    state: ConversationState = ConversationState.GREETING
    intent: GuestIntent = GuestIntent.UNKNOWN
    reservation_data: ReservationData = field(default_factory=ReservationData)

    # Conversation history
    turn_count: int = 0
    messages: list[dict[str, str]] = field(default_factory=list)
    started_at: datetime = field(default_factory=datetime.now)

    # Restaurant context
    restaurant_name: str = "Restaurant"

    # Existing reservation (for modifications)
    existing_reservation: dict[str, Any] | None = None

    # Flags
    needs_escalation: bool = False
    escalation_reason: str | None = None
    is_vip: bool = False


@dataclass
class ConversationResponse:
    """Response from conversation processing."""

    message: str
    next_state: ConversationState
    intent: GuestIntent
    reservation_complete: bool = False
    reservation_data: ReservationData | None = None
    needs_escalation: bool = False
    escalation_reason: str | None = None
    suggested_slots: list[dict[str, Any]] = field(default_factory=list)
    actions: list[str] = field(default_factory=list)  # Actions to perform


class GastroConversationManager:
    """Manages conversation flow for restaurant calls."""

    def __init__(self, restaurant_name: str = "Restaurant"):
        """Initialize conversation manager."""
        self._restaurant_name = restaurant_name
        self._contexts: dict[str, ConversationContext] = {}

    def start_conversation(self, call_id: str) -> ConversationContext:
        """Start a new conversation."""
        context = ConversationContext(
            call_id=call_id,
            restaurant_name=self._restaurant_name,
        )
        self._contexts[call_id] = context
        return context

    def get_context(self, call_id: str) -> ConversationContext | None:
        """Get existing conversation context."""
        return self._contexts.get(call_id)

    def process_turn(
        self,
        call_id: str,
        guest_message: str,
    ) -> ConversationResponse:
        """
        Process a conversation turn.

        Args:
            call_id: Unique call identifier
            guest_message: What the guest said

        Returns:
            ConversationResponse with next message and state
        """
        context = self._contexts.get(call_id)
        if not context:
            context = self.start_conversation(call_id)

        context.turn_count += 1
        context.messages.append({"role": "guest", "content": guest_message})

        # Process based on current state
        response = self._process_state(context, guest_message)

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
            ConversationState.RESERVATION_INTAKE: self._handle_reservation_intake,
            ConversationState.AVAILABILITY_CHECK: self._handle_availability_check,
            ConversationState.SPECIAL_REQUESTS: self._handle_special_requests,
            ConversationState.CONFIRMATION: self._handle_confirmation,
            ConversationState.MODIFICATION: self._handle_modification,
            ConversationState.CANCELLATION: self._handle_cancellation,
            ConversationState.INFORMATION: self._handle_information,
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
        # For first turn, we're responding to the guest
        response_message = (
            f"Guten Tag, {context.restaurant_name}, hier spricht der Reservierungsassistent. "
            "Wie kann ich Ihnen behilflich sein?"
        )

        return ConversationResponse(
            message=response_message,
            next_state=ConversationState.INTENT_DETECTION,
            intent=GuestIntent.UNKNOWN,
        )

    def _handle_intent_detection(
        self,
        context: ConversationContext,
        message: str,
    ) -> ConversationResponse:
        """Detect guest intent from message."""
        message_lower = message.lower()

        # Check for specific intents
        if any(w in message_lower for w in ["reservieren", "tisch", "buchen", "platz"]):
            context.intent = GuestIntent.NEW_RESERVATION
            # Try to extract initial data
            self._extract_reservation_data(context, message)

            missing = context.reservation_data.get_missing_fields()
            if missing:
                first_missing = missing[0]
                response_message = self._get_question_for_field(first_missing)
            else:
                response_message = "Ich prüfe kurz die Verfügbarkeit..."

            return ConversationResponse(
                message=response_message,
                next_state=ConversationState.RESERVATION_INTAKE,
                intent=GuestIntent.NEW_RESERVATION,
            )

        if any(w in message_lower for w in ["ändern", "verschieben", "umbuchen"]):
            return ConversationResponse(
                message="Gerne ändere ich Ihre Reservierung. Unter welchem Namen war gebucht?",
                next_state=ConversationState.MODIFICATION,
                intent=GuestIntent.MODIFY_RESERVATION,
            )

        if any(w in message_lower for w in ["absagen", "stornieren"]):
            return ConversationResponse(
                message="Ich kann Ihre Reservierung stornieren. Unter welchem Namen war gebucht?",
                next_state=ConversationState.CANCELLATION,
                intent=GuestIntent.CANCEL_RESERVATION,
            )

        if any(w in message_lower for w in ["öffnungszeiten", "speisekarte", "adresse"]):
            return ConversationResponse(
                message=self._get_information_response(message),
                next_state=ConversationState.FAREWELL,
                intent=GuestIntent.GET_INFORMATION,
            )

        if any(w in message_lower for w in ["beschwerde", "problem", "unzufrieden"]):
            return ConversationResponse(
                message="Das tut mir leid zu hören. Ich verbinde Sie mit unserem Restaurantleiter.",
                next_state=ConversationState.ESCALATION,
                intent=GuestIntent.MAKE_COMPLAINT,
                needs_escalation=True,
                escalation_reason="Beschwerde",
            )

        # Default to reservation
        return ConversationResponse(
            message="Möchten Sie einen Tisch reservieren? Für wie viele Personen und wann?",
            next_state=ConversationState.RESERVATION_INTAKE,
            intent=GuestIntent.NEW_RESERVATION,
        )

    def _handle_reservation_intake(
        self,
        context: ConversationContext,
        message: str,
    ) -> ConversationResponse:
        """Handle reservation data collection."""
        self._extract_reservation_data(context, message)

        missing = context.reservation_data.get_missing_fields()

        if not missing:
            # All data collected, check availability
            return ConversationResponse(
                message="Perfekt, ich prüfe kurz die Verfügbarkeit...",
                next_state=ConversationState.AVAILABILITY_CHECK,
                intent=GuestIntent.NEW_RESERVATION,
                reservation_data=context.reservation_data,
            )

        # Ask for next missing field
        first_missing = missing[0]
        response_message = self._get_question_for_field(first_missing)

        return ConversationResponse(
            message=response_message,
            next_state=ConversationState.RESERVATION_INTAKE,
            intent=GuestIntent.NEW_RESERVATION,
        )

    def _handle_availability_check(
        self,
        context: ConversationContext,
        message: str,
    ) -> ConversationResponse:
        """Handle availability check and slot confirmation."""
        data = context.reservation_data

        # Simulate availability check
        data.confirmed_date = data.preferred_date
        data.confirmed_time = data.preferred_time

        response_message = (
            f"Sehr gerne! Für {data.party_size} Personen am {data.preferred_date} "
            f"um {data.preferred_time} Uhr habe ich noch einen schönen Tisch frei. "
            "Gibt es besondere Wünsche oder Allergien, die wir beachten sollen?"
        )

        return ConversationResponse(
            message=response_message,
            next_state=ConversationState.SPECIAL_REQUESTS,
            intent=GuestIntent.NEW_RESERVATION,
            reservation_data=context.reservation_data,
        )

    def _handle_special_requests(
        self,
        context: ConversationContext,
        message: str,
    ) -> ConversationResponse:
        """Handle special requests and allergies."""
        message_lower = message.lower()

        # Extract allergies
        if any(w in message_lower for w in ["glutenfrei", "gluten", "zöliakie"]):
            context.reservation_data.allergies.append("Glutenfrei")
        if any(w in message_lower for w in ["laktose", "milch"]):
            context.reservation_data.allergies.append("Laktosefrei")
        if any(w in message_lower for w in ["vegan"]):
            context.reservation_data.allergies.append("Vegan")
        if any(w in message_lower for w in ["vegetarisch"]):
            context.reservation_data.allergies.append("Vegetarisch")
        if any(w in message_lower for w in ["nuss", "erdnuss"]):
            context.reservation_data.allergies.append("Nussfrei")

        # Extract occasions
        if any(w in message_lower for w in ["geburtstag"]):
            context.reservation_data.occasion = "Geburtstag"
        if any(w in message_lower for w in ["jubiläum", "jahrestag"]):
            context.reservation_data.occasion = "Jubiläum"

        # Extract seating
        if "terrasse" in message_lower:
            context.reservation_data.seating_preference = "Terrasse"
        if "fenster" in message_lower:
            context.reservation_data.seating_preference = "Fensterplatz"

        # Store any other requests
        if message_lower not in ["nein", "nein danke", "keine", "nichts"]:
            if not context.reservation_data.allergies and not context.reservation_data.occasion:
                context.reservation_data.special_requests.append(message)

        # Move to confirmation
        return ConversationResponse(
            message=self._generate_confirmation_message(context),
            next_state=ConversationState.CONFIRMATION,
            intent=GuestIntent.NEW_RESERVATION,
            reservation_data=context.reservation_data,
        )

    def _handle_confirmation(
        self,
        context: ConversationContext,
        message: str,
    ) -> ConversationResponse:
        """Handle reservation confirmation."""
        message_lower = message.lower()

        if any(w in message_lower for w in ["ja", "richtig", "stimmt", "passt", "okay", "perfekt"]):
            return ConversationResponse(
                message=(
                    "Wunderbar, Ihre Reservierung ist bestätigt! "
                    "Sie erhalten in Kürze eine SMS-Bestätigung. "
                    "Falls Sie den Termin nicht wahrnehmen können, bitten wir um Absage "
                    "mindestens 2 Stunden vorher. Wir freuen uns auf Ihren Besuch!"
                ),
                next_state=ConversationState.FAREWELL,
                intent=GuestIntent.NEW_RESERVATION,
                reservation_complete=True,
                reservation_data=context.reservation_data,
                actions=["create_reservation", "send_sms_confirmation"],
            )

        if any(w in message_lower for w in ["nein", "falsch", "anders"]):
            return ConversationResponse(
                message="Was möchten Sie ändern?",
                next_state=ConversationState.RESERVATION_INTAKE,
                intent=GuestIntent.NEW_RESERVATION,
            )

        # Unclear response
        return ConversationResponse(
            message="Entschuldigung, ich habe Sie nicht verstanden. Ist die Reservierung so korrekt?",
            next_state=ConversationState.CONFIRMATION,
            intent=GuestIntent.NEW_RESERVATION,
        )

    def _handle_modification(
        self,
        context: ConversationContext,
        message: str,
    ) -> ConversationResponse:
        """Handle reservation modification."""
        # Simple modification flow
        return ConversationResponse(
            message=(
                "Ich habe Ihre Reservierung gefunden und angepasst. "
                "Sie erhalten eine neue Bestätigung per SMS."
            ),
            next_state=ConversationState.FAREWELL,
            intent=GuestIntent.MODIFY_RESERVATION,
            actions=["modify_reservation", "send_sms_confirmation"],
        )

    def _handle_cancellation(
        self,
        context: ConversationContext,
        message: str,
    ) -> ConversationResponse:
        """Handle reservation cancellation."""
        return ConversationResponse(
            message=(
                "Ich habe Ihre Reservierung storniert. "
                "Wir würden uns freuen, Sie ein anderes Mal bei uns begrüßen zu dürfen."
            ),
            next_state=ConversationState.FAREWELL,
            intent=GuestIntent.CANCEL_RESERVATION,
            actions=["cancel_reservation"],
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
            intent=GuestIntent.GET_INFORMATION,
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
            intent=GuestIntent.MAKE_COMPLAINT,
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
            message="Vielen Dank für Ihren Anruf! Auf Wiederhören!",
            next_state=ConversationState.FAREWELL,
            intent=context.intent,
            actions=["end_call"],
        )

    def _extract_reservation_data(
        self,
        context: ConversationContext,
        message: str,
    ) -> None:
        """Extract reservation data from message."""
        from phone_agent.industry.gastro.workflows import (
            extract_party_size,
            extract_date_time,
        )

        data = context.reservation_data
        message_lower = message.lower()

        # Extract party size
        if not data.party_size:
            size = extract_party_size(message)
            if size:
                data.party_size = size

        # Extract date/time
        dt_info = extract_date_time(message)
        if not data.preferred_date and "date" in dt_info:
            data.preferred_date = dt_info["date"]
        if not data.preferred_time and "time" in dt_info:
            data.preferred_time = dt_info["time"]

        # Extract name (simple heuristic)
        if not data.guest_name:
            name_indicators = ["name ist", "heiße", "ich bin", "auf den namen"]
            for indicator in name_indicators:
                if indicator in message_lower:
                    # Get word after indicator
                    idx = message_lower.find(indicator) + len(indicator)
                    rest = message[idx:].strip()
                    if rest:
                        name = rest.split()[0].strip(".,!?")
                        if len(name) >= 2:
                            data.guest_name = name.capitalize()
                            break

        # Extract phone (simple pattern)
        if not data.phone:
            import re
            phone_match = re.search(r'(\d[\d\s/-]{8,}\d)', message)
            if phone_match:
                data.phone = phone_match.group(1).replace(" ", "").replace("-", "")

    def _get_question_for_field(self, field: str) -> str:
        """Get appropriate question for a missing field."""
        questions = {
            "Name": "Auf welchen Namen darf ich reservieren?",
            "Telefonnummer": "Und unter welcher Telefonnummer erreiche ich Sie?",
            "Personenzahl": "Für wie viele Personen darf ich reservieren?",
            "Datum": "An welchem Tag hätten Sie gerne einen Tisch?",
            "Uhrzeit": "Und um welche Uhrzeit?",
        }
        return questions.get(field, f"Ich benötige noch: {field}")

    def _generate_confirmation_message(self, context: ConversationContext) -> str:
        """Generate confirmation message with all details."""
        data = context.reservation_data

        message = (
            f"Ich fasse zusammen: Ein Tisch für {data.party_size} Personen "
            f"am {data.preferred_date} um {data.preferred_time} Uhr, "
            f"auf den Namen {data.guest_name}."
        )

        if data.allergies:
            message += f" Notiert: {', '.join(data.allergies)}."

        if data.occasion:
            message += f" Anlass: {data.occasion}."

        if data.seating_preference:
            message += f" Wunsch: {data.seating_preference}."

        message += " Ist das so korrekt?"

        return message

    def _get_information_response(self, message: str) -> str:
        """Generate response for information requests."""
        message_lower = message.lower()

        if "öffnungszeit" in message_lower:
            return (
                "Wir haben Dienstag bis Samstag von 11:30 bis 14:30 Uhr "
                "und 17:30 bis 22:00 Uhr geöffnet. "
                "Sonntags durchgehend von 11:30 bis 21:00 Uhr. "
                "Montag ist Ruhetag."
            )

        if "speisekarte" in message_lower or "menü" in message_lower:
            return (
                "Unsere aktuelle Speisekarte finden Sie auf unserer Website. "
                "Wir bieten auch vegetarische und vegane Gerichte an."
            )

        if "adresse" in message_lower or "wo" in message_lower:
            return (
                "Sie finden uns in der Musterstraße 1, 12345 Musterstadt. "
                "Parkplätze sind direkt vor dem Restaurant verfügbar."
            )

        return "Wie kann ich Ihnen weiterhelfen?"

    def end_conversation(self, call_id: str) -> None:
        """End and clean up a conversation."""
        if call_id in self._contexts:
            del self._contexts[call_id]


# Singleton instance with thread-safe initialization
_conversation_manager: GastroConversationManager | None = None
_conversation_manager_lock = __import__("threading").Lock()


def get_conversation_manager(
    restaurant_name: str = "Restaurant",
) -> GastroConversationManager:
    """Get or create conversation manager singleton.

    Thread-safe via double-checked locking pattern.
    """
    global _conversation_manager
    if _conversation_manager is None:
        with _conversation_manager_lock:
            # Double-check after acquiring lock
            if _conversation_manager is None:
                _conversation_manager = GastroConversationManager(restaurant_name)
    return _conversation_manager
