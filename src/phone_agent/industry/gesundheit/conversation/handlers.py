"""Flow control handlers for healthcare conversations.

Routes user input to appropriate actions based on conversation state.
"""

from __future__ import annotations

from phone_agent.industry.gesundheit.conversation.state import (
    ConversationContext,
    ConversationResponse,
    ConversationState,
    PatientIntent,
)
from phone_agent.industry.gesundheit.conversation.intents import IntentDetector
from phone_agent.industry.gesundheit.conversation.actions import ConversationActions
from phone_agent.industry.gesundheit.conversation import responses
from phone_agent.industry.gesundheit.scheduling import AppointmentType


class ConversationHandlers:
    """Handles conversation flow based on state and intent."""

    def __init__(
        self,
        actions: ConversationActions,
        intent_detector: IntentDetector,
    ):
        """Initialize handlers.

        Args:
            actions: Conversation actions instance
            intent_detector: Intent detection instance
        """
        self._actions = actions
        self._intents = intent_detector

    def get_current_state(self, context: ConversationContext) -> ConversationState:
        """Determine current conversation state.

        Args:
            context: Conversation context

        Returns:
            Current state based on context
        """
        if context.booked_appointment:
            return ConversationState.FAREWELL

        if context.selected_slot:
            return ConversationState.APPOINTMENT_CONFIRMATION

        if context.offered_slots:
            return ConversationState.APPOINTMENT_OFFER

        if context.triage_performed and context.triage_result:
            from phone_agent.industry.gesundheit.triage import UrgencyLevel
            if context.triage_result.urgency in [UrgencyLevel.URGENT, UrgencyLevel.VERY_URGENT]:
                return ConversationState.URGENCY_HANDLING
            return ConversationState.APPOINTMENT_SEARCH

        if context.stated_reason and self._intents.has_symptoms(context.stated_reason):
            return ConversationState.TRIAGE_ASSESSMENT

        if context.patient_identified:
            return ConversationState.REASON_INQUIRY

        if context.detected_intent != PatientIntent.UNKNOWN:
            return ConversationState.PATIENT_IDENTIFICATION

        return ConversationState.GREETING

    def handle_initial_request(
        self,
        context: ConversationContext,
        user_input: str,
    ) -> ConversationResponse:
        """Handle initial request after greeting.

        Args:
            context: Conversation context
            user_input: User's initial request

        Returns:
            Response with next step
        """
        context.stated_reason = user_input

        # Check if symptoms mentioned
        if self._intents.has_symptoms(user_input):
            context.symptoms_mentioned = self._intents.extract_symptoms(user_input)

        # Determine next step based on intent
        if context.detected_intent == PatientIntent.SPEAK_TO_STAFF:
            return self._actions.initiate_transfer(context, "Verbindung zum Personal gewünscht")

        # Prescription refill flow
        if context.detected_intent in [PatientIntent.REQUEST_PRESCRIPTION, PatientIntent.REQUEST_PRESCRIPTION_REFILL]:
            message = responses.request_identification("prescription")
            context.add_message("assistant", message)
            return ConversationResponse(
                state=ConversationState.PATIENT_IDENTIFICATION,
                message=message,
                requires_input=True,
                metadata={"next_flow": "prescription"},
            )

        # Lab results inquiry flow
        if context.detected_intent in [PatientIntent.LAB_RESULTS, PatientIntent.LAB_RESULTS_INQUIRY]:
            message = responses.request_identification("lab")
            context.add_message("assistant", message)
            return ConversationResponse(
                state=ConversationState.PATIENT_IDENTIFICATION,
                message=message,
                requires_input=True,
                metadata={"next_flow": "lab_results"},
            )

        # Reschedule appointment flow
        if context.detected_intent == PatientIntent.RESCHEDULE_APPOINTMENT:
            message = responses.request_identification("reschedule")
            context.add_message("assistant", message)
            return ConversationResponse(
                state=ConversationState.PATIENT_IDENTIFICATION,
                message=message,
                requires_input=True,
                metadata={"next_flow": "reschedule"},
            )

        # Cancel appointment flow
        if context.detected_intent == PatientIntent.CANCEL_APPOINTMENT:
            message = responses.request_identification("cancel")
            context.add_message("assistant", message)
            return ConversationResponse(
                state=ConversationState.PATIENT_IDENTIFICATION,
                message=message,
                requires_input=True,
                metadata={"next_flow": "cancel"},
            )

        # Default booking flow
        message = responses.request_identification("booking")
        context.add_message("assistant", message)

        return ConversationResponse(
            state=ConversationState.PATIENT_IDENTIFICATION,
            message=message,
            requires_input=True,
        )

    def handle_patient_identification(
        self,
        context: ConversationContext,
        user_input: str,
    ) -> ConversationResponse:
        """Handle patient identification.

        Args:
            context: Conversation context
            user_input: User's name/DOB

        Returns:
            Response for next step based on intent
        """
        # Simple extraction (would use NLU in production)
        context.patient_name = user_input.strip()
        context.patient_identified = True

        first_name = context.get_first_name()

        # Route based on detected intent
        if context.detected_intent in [PatientIntent.REQUEST_PRESCRIPTION, PatientIntent.REQUEST_PRESCRIPTION_REFILL]:
            return self._actions.request_prescription_details(context)

        if context.detected_intent in [PatientIntent.LAB_RESULTS, PatientIntent.LAB_RESULTS_INQUIRY]:
            return self._actions.request_lab_verification(context)

        if context.detected_intent == PatientIntent.RESCHEDULE_APPOINTMENT:
            return self._actions.start_reschedule_flow(context)

        if context.detected_intent == PatientIntent.CANCEL_APPOINTMENT:
            return self._actions.start_cancel_flow(context)

        # If symptoms were mentioned earlier, do triage
        if context.symptoms_mentioned:
            return self._actions.perform_triage(context)

        # Otherwise ask for reason
        message = responses.ask_reason(first_name)
        context.add_message("assistant", message)

        return ConversationResponse(
            state=ConversationState.REASON_INQUIRY,
            message=message,
            requires_input=True,
        )

    def handle_reason(
        self,
        context: ConversationContext,
        user_input: str,
    ) -> ConversationResponse | None:
        """Handle reason for call.

        Args:
            context: Conversation context
            user_input: User's stated reason

        Returns:
            Response or None if appointment search needed
        """
        context.stated_reason = user_input

        # Check for symptoms
        if self._intents.has_symptoms(user_input):
            context.symptoms_mentioned = self._intents.extract_symptoms(user_input)
            return self._actions.perform_triage(context)

        # No symptoms - signal to search for appointments
        return None

    def handle_triage(
        self,
        context: ConversationContext,
        user_input: str,
    ) -> ConversationResponse:
        """Handle additional triage questions.

        Args:
            context: Conversation context
            user_input: Additional symptom info

        Returns:
            Updated triage response
        """
        # Add to stated reason and re-assess
        context.stated_reason = f"{context.stated_reason or ''} {user_input}"
        return self._actions.perform_triage(context)

    def handle_appointment_selection(
        self,
        context: ConversationContext,
        user_input: str,
    ) -> ConversationResponse:
        """Handle appointment slot selection.

        Args:
            context: Conversation context
            user_input: User's selection

        Returns:
            Confirmation or retry response
        """
        return self._actions.select_appointment(context, user_input)

    async def handle_confirmation(
        self,
        context: ConversationContext,
        user_input: str,
    ) -> ConversationResponse:
        """Handle appointment confirmation.

        Args:
            context: Conversation context
            user_input: User's confirmation

        Returns:
            Booking result or back to selection
        """
        input_lower = user_input.lower()
        confirmed = "ja" in input_lower or "richtig" in input_lower or "stimmt" in input_lower
        return await self._actions.confirm_appointment(context, confirmed)

    def handle_prescription_request(
        self,
        context: ConversationContext,
        user_input: str,
    ) -> ConversationResponse:
        """Handle prescription refill request.

        Args:
            context: Conversation context
            user_input: Medication name

        Returns:
            Pharmacy request response
        """
        return self._actions.handle_prescription_medication(context, user_input)

    def handle_prescription_details(
        self,
        context: ConversationContext,
        user_input: str,
    ) -> ConversationResponse:
        """Handle prescription pharmacy/pickup details.

        Args:
            context: Conversation context
            user_input: Pharmacy preference

        Returns:
            Confirmation response
        """
        return self._actions.handle_prescription_pharmacy(context, user_input)

    def handle_lab_identity_verification(
        self,
        context: ConversationContext,
        user_input: str,
    ) -> ConversationResponse:
        """Handle lab results identity verification with DOB.

        Args:
            context: Conversation context
            user_input: Date of birth

        Returns:
            Lab results status response
        """
        return self._actions.verify_lab_identity(context, user_input)

    def handle_lab_results_inquiry(
        self,
        context: ConversationContext,
        user_input: str,
    ) -> ConversationResponse | None:
        """Handle lab results discussion booking.

        Args:
            context: Conversation context
            user_input: User's appointment preference

        Returns:
            Response or None if appointment search needed
        """
        input_lower = user_input.lower()
        wants_appointment = "ja" in input_lower or "termin" in input_lower
        return self._actions.handle_lab_discussion_request(context, wants_appointment)

    def handle_appointment_reschedule(
        self,
        context: ConversationContext,
        user_input: str,
    ) -> ConversationResponse | None:
        """Handle appointment rescheduling - find existing appointment.

        Args:
            context: Conversation context
            user_input: Current appointment info

        Returns:
            Response or None if slot search needed
        """
        context.reschedule_reason = context.reschedule_reason or "reschedule"

        if context.reschedule_reason == "cancel":
            return self._actions.start_cancel_flow(context)

        # For reschedule, signal to search for new slots
        message = (
            f"Ich habe Ihren Termin gefunden, {context.get_first_name()}. "
            f"Ich suche Ihnen alternative Termine. Einen Moment bitte."
        )
        context.add_message("assistant", message)

        return None  # Signal to search for appointments

    async def handle_reschedule_confirm(
        self,
        context: ConversationContext,
        user_input: str,
    ) -> ConversationResponse:
        """Handle reschedule/cancel confirmation.

        Args:
            context: Conversation context
            user_input: Confirmation or reason

        Returns:
            Confirmation response
        """
        if context.reschedule_reason == "cancel":
            return await self._actions.confirm_cancellation(context, user_input)

        # Regular reschedule - they selected a new slot
        if context.selected_slot:
            return await self._actions.confirm_reschedule(context)

        # No slot selected yet - should not reach here normally
        return self.handle_unknown(context, user_input)

    def handle_unknown(
        self,
        context: ConversationContext,
        user_input: str,
    ) -> ConversationResponse:
        """Handle unrecognized input.

        Args:
            context: Conversation context
            user_input: Unrecognized input

        Returns:
            Clarification request
        """
        message = responses.not_understood()
        context.add_message("assistant", message)

        return ConversationResponse(
            state=ConversationState.REASON_INQUIRY,
            message=message,
            requires_input=True,
            options=["Termin vereinbaren", "Termin ändern", "Mit Personal sprechen"],
        )
