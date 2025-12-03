"""Healthcare conversation manager.

Main orchestrator for healthcare phone call workflows.
Coordinates between handlers, actions, and state management.
"""

from __future__ import annotations

from datetime import datetime

from phone_agent.industry.gesundheit.triage import (
    TriageEngine,
    get_triage_engine,
)
from phone_agent.industry.gesundheit.scheduling import (
    SchedulingService,
    get_scheduling_service,
)
from phone_agent.industry.gesundheit.compliance import (
    ConsentManager,
    AuditLogger,
    AuditAction,
    get_consent_manager,
    get_audit_logger,
)
from phone_agent.industry.gesundheit.conversation.state import (
    ConversationContext,
    ConversationResponse,
    ConversationState,
    PatientIntent,
)
from phone_agent.industry.gesundheit.conversation.intents import IntentDetector
from phone_agent.industry.gesundheit.conversation.actions import ConversationActions
from phone_agent.industry.gesundheit.conversation.handlers import ConversationHandlers
from phone_agent.industry.gesundheit.conversation import responses


class HealthcareConversationManager:
    """
    Orchestrates healthcare phone conversations.

    Manages the complete flow from greeting to appointment booking,
    including triage assessment and consent management.

    Usage:
        manager = HealthcareConversationManager("Dr. Mustermann")
        context, response = manager.start_conversation("call-123")

        while response.requires_input:
            user_input = get_user_speech()  # From STT
            response = manager.process_input(context, user_input)
            play_message(response.message)  # To TTS
    """

    def __init__(
        self,
        practice_name: str = "Dr. Mustermann",
        triage_engine: TriageEngine | None = None,
        scheduling_service: SchedulingService | None = None,
        consent_manager: ConsentManager | None = None,
        audit_logger: AuditLogger | None = None,
    ):
        """Initialize conversation manager.

        Args:
            practice_name: Name of the medical practice
            triage_engine: Optional custom triage engine
            scheduling_service: Optional custom scheduling service
            consent_manager: Optional custom consent manager
            audit_logger: Optional custom audit logger
        """
        self.practice_name = practice_name
        self._triage = triage_engine or get_triage_engine()
        self._scheduling = scheduling_service or get_scheduling_service()
        self._consent = consent_manager or get_consent_manager()
        self._audit = audit_logger or get_audit_logger()

        # Initialize components
        self._intent_detector = IntentDetector(self._triage)
        self._actions = ConversationActions(
            practice_name=practice_name,
            triage_engine=self._triage,
            scheduling_service=self._scheduling,
            audit_logger=self._audit,
        )
        self._handlers = ConversationHandlers(
            actions=self._actions,
            intent_detector=self._intent_detector,
        )

    def start_conversation(self, call_id: str) -> tuple[ConversationContext, ConversationResponse]:
        """
        Start a new conversation.

        Args:
            call_id: Unique identifier for the call

        Returns:
            Tuple of conversation context and initial response
        """
        context = ConversationContext(call_id=call_id)

        # Log call start
        self._audit.log_call_event(
            call_id=call_id,
            action=AuditAction.CALL_STARTED,
        )

        # Generate greeting
        greeting = responses.greeting(self.practice_name)
        context.add_message("assistant", greeting)

        return context, ConversationResponse(
            state=ConversationState.GREETING,
            message=greeting,
            requires_input=True,
        )

    def process_input(
        self,
        context: ConversationContext,
        user_input: str,
    ) -> ConversationResponse:
        """
        Process user input and advance conversation.

        Args:
            context: Current conversation context
            user_input: What the user said

        Returns:
            Response with next message and state
        """
        context.add_message("user", user_input)
        input_lower = user_input.lower()

        # Detect intent from input
        detected_intent = self._intent_detector.detect(input_lower)
        if detected_intent != PatientIntent.UNKNOWN:
            context.detected_intent = detected_intent

        # Handle emergency keywords immediately
        if detected_intent == PatientIntent.EMERGENCY or self._intent_detector.is_emergency(input_lower):
            return self._actions.handle_emergency(context)

        # Route based on current state and intent
        current_state = self._handlers.get_current_state(context)

        return self._route_by_state(context, user_input, current_state)

    def _route_by_state(
        self,
        context: ConversationContext,
        user_input: str,
        current_state: ConversationState,
    ) -> ConversationResponse:
        """Route to appropriate handler based on state.

        Args:
            context: Conversation context
            user_input: User input
            current_state: Current conversation state

        Returns:
            Handler response
        """
        if current_state == ConversationState.GREETING:
            return self._handlers.handle_initial_request(context, user_input)

        elif current_state == ConversationState.PATIENT_IDENTIFICATION:
            # Log data access
            self._audit.log(
                action=AuditAction.DATA_SEARCH,
                actor_id="phone_agent",
                actor_type="ai_agent",
                resource_type="patient",
                details={"search_query": "name lookup"},
            )
            return self._handlers.handle_patient_identification(context, user_input)

        elif current_state == ConversationState.REASON_INQUIRY:
            response = self._handlers.handle_reason(context, user_input)
            if response is None:
                # Need to search for appointments
                import asyncio
                return asyncio.get_event_loop().run_until_complete(
                    self._actions.search_appointments(context)
                )
            return response

        elif current_state == ConversationState.TRIAGE_ASSESSMENT:
            return self._handlers.handle_triage(context, user_input)

        elif current_state == ConversationState.APPOINTMENT_OFFER:
            return self._handlers.handle_appointment_selection(context, user_input)

        elif current_state == ConversationState.APPOINTMENT_CONFIRMATION:
            import asyncio
            return asyncio.get_event_loop().run_until_complete(
                self._handlers.handle_confirmation(context, user_input)
            )

        elif current_state == ConversationState.FAREWELL:
            return self._handle_farewell(context)

        # Inbound flow states
        elif current_state == ConversationState.PRESCRIPTION_REQUEST:
            return self._handlers.handle_prescription_request(context, user_input)

        elif current_state == ConversationState.PRESCRIPTION_DETAILS:
            return self._handlers.handle_prescription_details(context, user_input)

        elif current_state == ConversationState.LAB_RESULTS_INQUIRY:
            response = self._handlers.handle_lab_results_inquiry(context, user_input)
            if response is None:
                import asyncio
                return asyncio.get_event_loop().run_until_complete(
                    self._actions.search_appointments(context)
                )
            return response

        elif current_state == ConversationState.LAB_IDENTITY_VERIFICATION:
            return self._handlers.handle_lab_identity_verification(context, user_input)

        elif current_state == ConversationState.APPOINTMENT_RESCHEDULE:
            response = self._handlers.handle_appointment_reschedule(context, user_input)
            if response is None:
                import asyncio
                return asyncio.get_event_loop().run_until_complete(
                    self._actions.search_appointments(context)
                )
            return response

        elif current_state == ConversationState.RESCHEDULE_CONFIRM:
            import asyncio
            return asyncio.get_event_loop().run_until_complete(
                self._handlers.handle_reschedule_confirm(context, user_input)
            )

        # Default: try to understand what they want
        return self._handlers.handle_unknown(context, user_input)

    def _handle_farewell(self, context: ConversationContext) -> ConversationResponse:
        """Handle conversation conclusion.

        Args:
            context: Conversation context

        Returns:
            Farewell response
        """
        message = responses.farewell(self.practice_name)
        context.add_message("assistant", message)

        # Log call end
        self._audit.log_call_event(
            call_id=context.call_id,
            action=AuditAction.CALL_ENDED,
            patient_id=context.patient_id,
            details={
                "duration_seconds": int((datetime.now() - context.started_at).total_seconds()),
                "appointment_booked": context.booked_appointment is not None,
            },
        )

        return ConversationResponse(
            state=ConversationState.COMPLETED,
            message=message,
            requires_input=False,
            end_call=True,
        )

    async def process_input_async(
        self,
        context: ConversationContext,
        user_input: str,
    ) -> ConversationResponse:
        """
        Async version of process_input.

        Args:
            context: Current conversation context
            user_input: What the user said

        Returns:
            Response with next message and state
        """
        context.add_message("user", user_input)
        input_lower = user_input.lower()

        # Detect intent from input
        detected_intent = self._intent_detector.detect(input_lower)
        if detected_intent != PatientIntent.UNKNOWN:
            context.detected_intent = detected_intent

        # Handle emergency keywords immediately
        if detected_intent == PatientIntent.EMERGENCY or self._intent_detector.is_emergency(input_lower):
            return self._actions.handle_emergency(context)

        # Route based on current state and intent
        current_state = self._handlers.get_current_state(context)

        return await self._route_by_state_async(context, user_input, current_state)

    async def _route_by_state_async(
        self,
        context: ConversationContext,
        user_input: str,
        current_state: ConversationState,
    ) -> ConversationResponse:
        """Async version of state routing.

        Args:
            context: Conversation context
            user_input: User input
            current_state: Current conversation state

        Returns:
            Handler response
        """
        if current_state == ConversationState.GREETING:
            return self._handlers.handle_initial_request(context, user_input)

        elif current_state == ConversationState.PATIENT_IDENTIFICATION:
            self._audit.log(
                action=AuditAction.DATA_SEARCH,
                actor_id="phone_agent",
                actor_type="ai_agent",
                resource_type="patient",
                details={"search_query": "name lookup"},
            )
            return self._handlers.handle_patient_identification(context, user_input)

        elif current_state == ConversationState.REASON_INQUIRY:
            response = self._handlers.handle_reason(context, user_input)
            if response is None:
                return await self._actions.search_appointments(context)
            return response

        elif current_state == ConversationState.TRIAGE_ASSESSMENT:
            return self._handlers.handle_triage(context, user_input)

        elif current_state == ConversationState.APPOINTMENT_OFFER:
            return self._handlers.handle_appointment_selection(context, user_input)

        elif current_state == ConversationState.APPOINTMENT_CONFIRMATION:
            return await self._handlers.handle_confirmation(context, user_input)

        elif current_state == ConversationState.FAREWELL:
            return self._handle_farewell(context)

        elif current_state == ConversationState.PRESCRIPTION_REQUEST:
            return self._handlers.handle_prescription_request(context, user_input)

        elif current_state == ConversationState.PRESCRIPTION_DETAILS:
            return self._handlers.handle_prescription_details(context, user_input)

        elif current_state == ConversationState.LAB_RESULTS_INQUIRY:
            response = self._handlers.handle_lab_results_inquiry(context, user_input)
            if response is None:
                return await self._actions.search_appointments(context)
            return response

        elif current_state == ConversationState.LAB_IDENTITY_VERIFICATION:
            return self._handlers.handle_lab_identity_verification(context, user_input)

        elif current_state == ConversationState.APPOINTMENT_RESCHEDULE:
            response = self._handlers.handle_appointment_reschedule(context, user_input)
            if response is None:
                return await self._actions.search_appointments(context)
            return response

        elif current_state == ConversationState.RESCHEDULE_CONFIRM:
            return await self._handlers.handle_reschedule_confirm(context, user_input)

        return self._handlers.handle_unknown(context, user_input)
