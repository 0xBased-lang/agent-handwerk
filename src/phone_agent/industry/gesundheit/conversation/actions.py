"""Conversation actions for healthcare workflows.

Implements the core actions: triage, booking, prescription,
lab results, and rescheduling flows.
"""

from __future__ import annotations

from datetime import date
from uuid import uuid4

from phone_agent.industry.gesundheit.triage import (
    TriageEngine,
    TriageResult,
    UrgencyLevel,
    get_triage_engine,
)
from phone_agent.industry.gesundheit.scheduling import (
    SchedulingService,
    SchedulingPreferences,
    Patient,
    Appointment,
    AppointmentType,
    TimeSlot,
    get_scheduling_service,
)
from phone_agent.industry.gesundheit.compliance import (
    AuditLogger,
    AuditAction,
    get_audit_logger,
)
from phone_agent.industry.gesundheit.conversation.state import (
    ConversationContext,
    ConversationResponse,
    ConversationState,
    PatientIntent,
)
from phone_agent.industry.gesundheit.conversation import responses


class ConversationActions:
    """Encapsulates conversation action implementations."""

    def __init__(
        self,
        practice_name: str,
        triage_engine: TriageEngine | None = None,
        scheduling_service: SchedulingService | None = None,
        audit_logger: AuditLogger | None = None,
    ):
        """Initialize conversation actions.

        Args:
            practice_name: Name of the practice
            triage_engine: Optional triage engine
            scheduling_service: Optional scheduling service
            audit_logger: Optional audit logger
        """
        self.practice_name = practice_name
        self._triage = triage_engine or get_triage_engine()
        self._scheduling = scheduling_service or get_scheduling_service()
        self._audit = audit_logger or get_audit_logger()

    # ==================== TRIAGE ====================

    def perform_triage(self, context: ConversationContext) -> ConversationResponse:
        """Perform triage assessment.

        Args:
            context: Conversation context with symptoms

        Returns:
            Response with triage result and next steps
        """
        result = self._triage.assess(
            symptoms=[],
            free_text=context.stated_reason,
        )

        context.triage_performed = True
        context.triage_result = result

        # Handle based on urgency
        if result.urgency == UrgencyLevel.EMERGENCY:
            return self.handle_emergency(context)

        if result.urgency in [UrgencyLevel.VERY_URGENT, UrgencyLevel.URGENT]:
            context.appointment_type = AppointmentType.ACUTE
            message = responses.triage_urgent(result.recommended_action)
            context.add_message("assistant", message, triage=result.to_dict())
            # Will search for urgent appointments
            return ConversationResponse(
                state=ConversationState.APPOINTMENT_SEARCH,
                message=message,
                requires_input=False,
                metadata={"urgent": True, "triage_result": result.to_dict()},
            )

        # Standard urgency
        message = responses.triage_normal(result.recommended_action)
        context.add_message("assistant", message, triage=result.to_dict())

        return ConversationResponse(
            state=ConversationState.APPOINTMENT_SEARCH,
            message=message,
            requires_input=False,
            metadata={"triage_result": result.to_dict()},
        )

    def handle_emergency(self, context: ConversationContext) -> ConversationResponse:
        """Handle emergency situation.

        Args:
            context: Conversation context

        Returns:
            Emergency response with 112 guidance
        """
        context.detected_intent = PatientIntent.EMERGENCY
        message = responses.emergency_warning()
        context.add_message("assistant", message)

        return ConversationResponse(
            state=ConversationState.EMERGENCY_REDIRECT,
            message=message,
            requires_input=True,
            options=["Ja, bitte verbinden", "Nein, ich rufe 112"],
            metadata={"emergency": True},
        )

    # ==================== SCHEDULING ====================

    async def search_appointments(
        self,
        context: ConversationContext,
        urgent: bool = False,
    ) -> ConversationResponse:
        """Search for available appointments.

        Args:
            context: Conversation context
            urgent: Whether to search for urgent slots

        Returns:
            Response with available slots or callback offer
        """
        prefs = SchedulingPreferences(
            appointment_type=context.appointment_type,
            urgency_max_wait_hours=4 if urgent else None,
        )

        slots = await self._scheduling.find_slots(prefs, limit=3)
        context.offered_slots = slots

        if not slots:
            message = responses.no_slots_available()
            context.add_message("assistant", message)
            return ConversationResponse(
                state=ConversationState.APPOINTMENT_OFFER,
                message=message,
                requires_input=True,
                options=["Ja, bitte Rückruf", "Nein, danke"],
            )

        # Format slots for speech
        slots_text = self._scheduling.format_slots_for_speech(slots, "de", 3)
        message = f"{slots_text}\n\n{responses.appointment_selection_prompt()}"
        context.add_message("assistant", message)

        return ConversationResponse(
            state=ConversationState.APPOINTMENT_OFFER,
            message=message,
            requires_input=True,
            options=[f"Option {i+1}" for i in range(len(slots))],
        )

    def select_appointment(
        self,
        context: ConversationContext,
        user_input: str,
    ) -> ConversationResponse:
        """Handle appointment slot selection.

        Args:
            context: Conversation context
            user_input: User's selection

        Returns:
            Confirmation request or retry message
        """
        input_lower = user_input.lower()

        # Try to match selection
        selected_idx = None
        if "1" in input_lower or "erst" in input_lower:
            selected_idx = 0
        elif "2" in input_lower or "zweit" in input_lower:
            selected_idx = 1
        elif "3" in input_lower or "dritt" in input_lower:
            selected_idx = 2

        if selected_idx is not None and selected_idx < len(context.offered_slots):
            context.selected_slot = context.offered_slots[selected_idx]

            slot_text = self._scheduling.format_slot_for_speech(
                context.selected_slot, "de"
            )

            message = responses.appointment_confirm_prompt(slot_text)
            context.add_message("assistant", message)

            return ConversationResponse(
                state=ConversationState.APPOINTMENT_CONFIRMATION,
                message=message,
                requires_input=True,
                options=["Ja, richtig", "Nein, anders"],
            )

        # Didn't understand selection
        message = responses.appointment_selection_unclear()
        context.add_message("assistant", message)

        return ConversationResponse(
            state=ConversationState.APPOINTMENT_OFFER,
            message=message,
            requires_input=True,
        )

    async def confirm_appointment(
        self,
        context: ConversationContext,
        confirmed: bool,
    ) -> ConversationResponse:
        """Confirm and book appointment.

        Args:
            context: Conversation context
            confirmed: Whether user confirmed

        Returns:
            Booking confirmation or back to selection
        """
        if not confirmed:
            context.selected_slot = None
            message = "Kein Problem. Welcher Termin passt Ihnen besser?"
            context.add_message("assistant", message)
            return ConversationResponse(
                state=ConversationState.APPOINTMENT_OFFER,
                message=message,
                requires_input=True,
            )

        # Book the appointment
        patient = Patient(
            id=context.patient_id or uuid4(),
            first_name=context.get_first_name(),
            last_name=" ".join(context.patient_name.split()[1:]) if context.patient_name and len(context.patient_name.split()) > 1 else "",
            date_of_birth=context.patient_dob or date(1900, 1, 1),
            phone=context.patient_phone or "",
        )

        appointment = await self._scheduling.book_appointment(
            slot_id=context.selected_slot.id,
            patient=patient,
            reason=context.stated_reason or "Telefonische Anmeldung",
            appointment_type=context.appointment_type,
        )

        context.booked_appointment = appointment

        # Log appointment creation
        self._audit.log(
            action=AuditAction.APPOINTMENT_CREATED,
            actor_id="phone_agent",
            actor_type="ai_agent",
            resource_type="appointment",
            resource_id=str(appointment.id),
            patient_id=context.patient_id,
        )

        slot_text = self._scheduling.format_slot_for_speech(
            context.selected_slot, "de"
        )

        message = responses.appointment_booked(slot_text)
        context.add_message("assistant", message)

        return ConversationResponse(
            state=ConversationState.FAREWELL,
            message=message,
            requires_input=True,
            send_sms=True,
            sms_content=responses.sms_confirmation(self.practice_name, slot_text),
        )

    # ==================== PRESCRIPTION ====================

    def request_prescription_details(
        self,
        context: ConversationContext,
    ) -> ConversationResponse:
        """Start prescription refill flow.

        Args:
            context: Conversation context

        Returns:
            Request for medication details
        """
        message = responses.prescription_medication_request(context.get_first_name())
        context.add_message("assistant", message)

        return ConversationResponse(
            state=ConversationState.PRESCRIPTION_REQUEST,
            message=message,
            requires_input=True,
        )

    def handle_prescription_medication(
        self,
        context: ConversationContext,
        medication: str,
    ) -> ConversationResponse:
        """Handle prescription medication input.

        Args:
            context: Conversation context
            medication: Medication name from user

        Returns:
            Request for pharmacy preference
        """
        context.prescription_medication = medication.strip()
        message = responses.prescription_pharmacy_request(context.prescription_medication)
        context.add_message("assistant", message)

        return ConversationResponse(
            state=ConversationState.PRESCRIPTION_DETAILS,
            message=message,
            requires_input=True,
            options=["In der Praxis abholen", "Apotheke"],
        )

    def handle_prescription_pharmacy(
        self,
        context: ConversationContext,
        pharmacy_input: str,
    ) -> ConversationResponse:
        """Handle prescription pharmacy selection.

        Args:
            context: Conversation context
            pharmacy_input: Pharmacy preference from user

        Returns:
            Confirmation of prescription request
        """
        input_lower = pharmacy_input.lower()

        if "praxis" in input_lower or "abholen" in input_lower:
            context.prescription_pharmacy = "Praxisabholung"
        else:
            context.prescription_pharmacy = pharmacy_input.strip()

        context.prescription_queued = True

        # Log prescription request
        self._audit.log(
            action=AuditAction.DATA_CREATE,
            actor_id="phone_agent",
            actor_type="ai_agent",
            resource_type="prescription_request",
            patient_id=context.patient_id,
            details={
                "medication": context.prescription_medication,
                "pharmacy": context.prescription_pharmacy,
            },
        )

        message = responses.prescription_confirmed(
            context.get_first_name(),
            context.prescription_medication,
            context.prescription_pharmacy,
        )
        context.add_message("assistant", message)

        return ConversationResponse(
            state=ConversationState.FAREWELL,
            message=message,
            requires_input=True,
            metadata={"prescription_queued": True},
        )

    # ==================== LAB RESULTS ====================

    def request_lab_verification(
        self,
        context: ConversationContext,
    ) -> ConversationResponse:
        """Request DOB verification for lab results.

        Args:
            context: Conversation context

        Returns:
            DOB verification request
        """
        message = responses.lab_dob_verification(context.get_first_name())
        context.add_message("assistant", message)

        return ConversationResponse(
            state=ConversationState.LAB_IDENTITY_VERIFICATION,
            message=message,
            requires_input=True,
        )

    def verify_lab_identity(
        self,
        context: ConversationContext,
        dob_input: str,
    ) -> ConversationResponse:
        """Verify identity for lab results.

        Args:
            context: Conversation context
            dob_input: Date of birth from user

        Returns:
            Lab results status or appointment offer
        """
        # In production, verify DOB against patient record
        context.lab_dob_verified = True

        # Simulate results being ready
        context.lab_results_ready = True

        if context.lab_results_ready:
            message = responses.lab_results_ready(context.get_first_name())
            context.add_message("assistant", message)

            return ConversationResponse(
                state=ConversationState.LAB_RESULTS_INQUIRY,
                message=message,
                requires_input=True,
                options=["Ja, Termin vereinbaren", "Nein, danke"],
            )
        else:
            message = responses.lab_results_not_ready(context.get_first_name())
            context.add_message("assistant", message)

            return ConversationResponse(
                state=ConversationState.FAREWELL,
                message=message,
                requires_input=True,
            )

    def handle_lab_discussion_request(
        self,
        context: ConversationContext,
        wants_appointment: bool,
    ) -> ConversationResponse | None:
        """Handle lab results discussion appointment request.

        Args:
            context: Conversation context
            wants_appointment: Whether user wants discussion appointment

        Returns:
            Search response or decline message, None if search needed
        """
        if wants_appointment:
            context.appointment_type = AppointmentType.LAB
            context.stated_reason = "Besprechung Laborergebnisse"
            return None  # Signal to search for appointments

        message = (
            "Verstanden. Falls Sie später Fragen haben, können Sie jederzeit einen "
            "Besprechungstermin vereinbaren. Kann ich sonst noch etwas für Sie tun?"
        )
        context.add_message("assistant", message)

        return ConversationResponse(
            state=ConversationState.FAREWELL,
            message=message,
            requires_input=True,
        )

    # ==================== RESCHEDULE / CANCEL ====================

    def start_reschedule_flow(
        self,
        context: ConversationContext,
    ) -> ConversationResponse:
        """Start appointment reschedule flow.

        Args:
            context: Conversation context

        Returns:
            Request for current appointment info
        """
        message = responses.reschedule_lookup(context.get_first_name())
        context.add_message("assistant", message)

        return ConversationResponse(
            state=ConversationState.APPOINTMENT_RESCHEDULE,
            message=message,
            requires_input=True,
        )

    def start_cancel_flow(
        self,
        context: ConversationContext,
    ) -> ConversationResponse:
        """Start appointment cancellation flow.

        Args:
            context: Conversation context

        Returns:
            Request for cancellation reason
        """
        context.reschedule_reason = "cancel"
        message = responses.cancel_reason_request(context.get_first_name())
        context.add_message("assistant", message)

        return ConversationResponse(
            state=ConversationState.RESCHEDULE_CONFIRM,
            message=message,
            requires_input=True,
            metadata={"action": "cancel"},
        )

    async def confirm_cancellation(
        self,
        context: ConversationContext,
        reason: str,
    ) -> ConversationResponse:
        """Confirm appointment cancellation.

        Args:
            context: Conversation context
            reason: Cancellation reason

        Returns:
            Cancellation confirmation
        """
        context.reschedule_reason = reason

        # In production: call scheduling.cancel_appointment()

        # Log cancellation
        self._audit.log(
            action=AuditAction.APPOINTMENT_CANCELLED,
            actor_id="phone_agent",
            actor_type="ai_agent",
            resource_type="appointment",
            patient_id=context.patient_id,
            details={"reason": reason},
        )

        message = responses.cancel_confirmed(context.get_first_name())
        context.add_message("assistant", message)

        return ConversationResponse(
            state=ConversationState.FAREWELL,
            message=message,
            requires_input=True,
            options=["Ja, neuen Termin", "Nein, danke"],
            send_sms=True,
            sms_content=responses.sms_cancellation(self.practice_name),
        )

    async def confirm_reschedule(
        self,
        context: ConversationContext,
    ) -> ConversationResponse:
        """Confirm appointment reschedule.

        Args:
            context: Conversation context with new slot selected

        Returns:
            Reschedule confirmation
        """
        if not context.selected_slot:
            return ConversationResponse(
                state=ConversationState.APPOINTMENT_OFFER,
                message="Welcher Termin passt Ihnen?",
                requires_input=True,
            )

        slot_text = self._scheduling.format_slot_for_speech(context.selected_slot, "de")

        # Log reschedule
        self._audit.log(
            action=AuditAction.APPOINTMENT_MODIFIED,
            actor_id="phone_agent",
            actor_type="ai_agent",
            resource_type="appointment",
            patient_id=context.patient_id,
            details={"new_slot": slot_text},
        )

        message = responses.appointment_rescheduled(slot_text)
        context.add_message("assistant", message)

        return ConversationResponse(
            state=ConversationState.FAREWELL,
            message=message,
            requires_input=True,
            send_sms=True,
            sms_content=responses.sms_reschedule(self.practice_name, slot_text),
        )

    # ==================== TRANSFER ====================

    def initiate_transfer(
        self,
        context: ConversationContext,
        reason: str,
    ) -> ConversationResponse:
        """Initiate transfer to staff.

        Args:
            context: Conversation context
            reason: Transfer reason

        Returns:
            Transfer message
        """
        context.needs_transfer = True
        context.transfer_reason = reason

        message = responses.transfer_message()
        context.add_message("assistant", message)

        return ConversationResponse(
            state=ConversationState.TRANSFER_TO_STAFF,
            message=message,
            requires_input=False,
            transfer_call=True,
            metadata={"transfer_reason": reason},
        )
