"""Handwerk (Trades) specific conversation manager.

Orchestrates the full trades phone call workflow:
1. Greeting and customer identification
2. Address verification
3. Problem assessment
4. Urgency determination
5. Technician matching and scheduling
6. Consent management
7. Call conclusion and documentation
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, date
from enum import Enum
from typing import Any
from uuid import UUID, uuid4

from phone_agent.industry.handwerk.triage import (
    TriageEngine,
    TriageResult,
    UrgencyLevel,
    TradeCategory,
    JobIssue,
    get_triage_engine,
)
from phone_agent.industry.handwerk.technician import (
    TechnicianMatcher,
    Technician,
    TechnicianMatch,
    get_technician_matcher,
)
from phone_agent.industry.handwerk.scheduling import (
    SchedulingService,
    SchedulingPreferences,
    Customer,
    ServiceCall,
    JobType,
    TimeSlot,
    get_scheduling_service,
)
from phone_agent.industry.handwerk.compliance import (
    ConsentManager,
    ConsentType,
    AuditLogger,
    AuditAction,
    get_consent_manager,
    get_audit_logger,
)


class ConversationState(str, Enum):
    """States in the trades conversation flow."""

    GREETING = "greeting"
    CUSTOMER_IDENTIFICATION = "customer_identification"
    ADDRESS_VERIFICATION = "address_verification"
    PROBLEM_INQUIRY = "problem_inquiry"
    PROBLEM_DETAILS = "problem_details"
    URGENCY_ASSESSMENT = "urgency_assessment"
    TECHNICIAN_SEARCH = "technician_search"
    SLOT_OFFER = "slot_offer"
    SLOT_CONFIRMATION = "slot_confirmation"
    CONSENT_CHECK = "consent_check"
    ADDITIONAL_INFO = "additional_info"
    FAREWELL = "farewell"
    TRANSFER_TO_STAFF = "transfer_to_staff"
    EMERGENCY_REDIRECT = "emergency_redirect"
    QUOTE_REQUEST = "quote_request"
    COMPLETED = "completed"


class CustomerIntent(str, Enum):
    """Detected customer intents."""

    REQUEST_SERVICE = "request_service"
    EMERGENCY_SERVICE = "emergency_service"
    SCHEDULE_MAINTENANCE = "schedule_maintenance"
    GET_QUOTE = "get_quote"
    CANCEL_APPOINTMENT = "cancel_appointment"
    RESCHEDULE_APPOINTMENT = "reschedule_appointment"
    CHECK_STATUS = "check_status"
    SPEAK_TO_STAFF = "speak_to_staff"
    COMPLAINT = "complaint"
    GENERAL_INQUIRY = "general_inquiry"
    UNKNOWN = "unknown"


@dataclass
class ConversationContext:
    """Context maintained throughout the conversation."""

    call_id: str
    started_at: datetime = field(default_factory=datetime.now)

    # Customer identification
    customer_identified: bool = False
    customer_id: UUID | None = None
    customer_name: str | None = None
    customer_company: str | None = None
    customer_phone: str | None = None
    customer_email: str | None = None

    # Address
    address_verified: bool = False
    street: str | None = None
    zip_code: str | None = None
    city: str | None = None
    access_info: str | None = None  # "Schlüssel beim Nachbarn"

    # Intent and problem
    detected_intent: CustomerIntent = CustomerIntent.UNKNOWN
    stated_problem: str | None = None
    detected_trade: TradeCategory | None = None
    detected_issues: list[JobIssue] = field(default_factory=list)

    # Triage
    triage_performed: bool = False
    triage_result: TriageResult | None = None
    is_emergency: bool = False
    emergency_type: str | None = None

    # Technician matching
    matched_technician: TechnicianMatch | None = None

    # Scheduling
    job_type: JobType = JobType.REPARATUR
    offered_slots: list[TimeSlot] = field(default_factory=list)
    selected_slot: TimeSlot | None = None
    booked_service_call: ServiceCall | None = None

    # Consent
    consents_checked: dict[ConsentType, bool] = field(default_factory=dict)

    # Quote request
    quote_requested: bool = False
    quote_notes: str | None = None

    # Conversation history
    messages: list[dict[str, Any]] = field(default_factory=list)

    # Transfer/escalation
    needs_transfer: bool = False
    transfer_reason: str | None = None

    def add_message(self, role: str, content: str, **metadata):
        """Add a message to conversation history."""
        self.messages.append({
            "role": role,
            "content": content,
            "timestamp": datetime.now().isoformat(),
            **metadata,
        })


@dataclass
class ConversationResponse:
    """Response from conversation manager."""

    state: ConversationState
    message: str
    requires_input: bool = True
    options: list[str] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    # Actions to take
    schedule_callback: bool = False
    send_sms: bool = False
    sms_content: str | None = None
    dispatch_technician: bool = False
    transfer_call: bool = False
    end_call: bool = False
    is_emergency: bool = False


# Emergency keywords that require immediate action
EMERGENCY_PATTERNS = {
    "gas_leak": [
        "gasgeruch", "gasleck", "riecht nach gas", "gas ausgetreten",
        "gasherd an", "gas strömt", "gasleitung",
    ],
    "water_main": [
        "wasserrohrbruch", "rohr geplatzt", "wasser spritzt",
        "überschwemmung", "wasserschaden", "wasserleitung gebrochen",
    ],
    "electrical": [
        "kabel brennt", "steckdose raucht", "kurzschluss", "stromschlag",
        "sicherung fliegt", "elektrischer brand", "funken sprühen",
    ],
    "flooding": [
        "wasser läuft", "keller überflutet", "übergelaufen",
        "wasserhahn defekt", "wasser abstellen",
    ],
    "locked_danger": [
        "kind eingesperrt", "baby allein", "herd an", "ofen an",
        "ausgesperrt notfall", "schlüssel vergessen kind",
    ],
    "heating_emergency": [
        "heizung ausgefallen", "keine heizung", "friert", "eiskalt",
        "heizung defekt winter",
    ],
}


class HandwerkConversationManager:
    """
    Orchestrates trades phone conversations.

    Manages the complete flow from greeting to service call booking,
    including problem assessment and technician dispatch.
    """

    def __init__(
        self,
        company_name: str = "Mustermann GmbH",
        triage_engine: TriageEngine | None = None,
        technician_matcher: TechnicianMatcher | None = None,
        scheduling_service: SchedulingService | None = None,
        consent_manager: ConsentManager | None = None,
        audit_logger: AuditLogger | None = None,
    ):
        """Initialize conversation manager."""
        self.company_name = company_name
        self._triage = triage_engine or get_triage_engine()
        self._technician = technician_matcher or get_technician_matcher()
        self._scheduling = scheduling_service or get_scheduling_service()
        self._consent = consent_manager or get_consent_manager()
        self._audit = audit_logger or get_audit_logger()

        # Intent keywords (German)
        self._intent_keywords = {
            CustomerIntent.REQUEST_SERVICE: [
                "reparatur", "defekt", "kaputt", "funktioniert nicht",
                "problem mit", "geht nicht", "läuft nicht",
            ],
            CustomerIntent.EMERGENCY_SERVICE: [
                "notfall", "dringend", "sofort", "notdienst",
                "gasgeruch", "wasserrohrbruch", "ausgesperrt",
            ],
            CustomerIntent.SCHEDULE_MAINTENANCE: [
                "wartung", "inspektion", "check", "prüfung",
                "jährlich", "regelmäßig",
            ],
            CustomerIntent.GET_QUOTE: [
                "angebot", "kostenvoranschlag", "kosten", "preis",
                "was kostet", "schätzung",
            ],
            CustomerIntent.CANCEL_APPOINTMENT: [
                "absagen", "stornieren", "nicht kommen",
            ],
            CustomerIntent.RESCHEDULE_APPOINTMENT: [
                "verschieben", "umbuchen", "anderen termin",
            ],
            CustomerIntent.CHECK_STATUS: [
                "status", "wann kommt", "monteur", "techniker",
            ],
            CustomerIntent.SPEAK_TO_STAFF: [
                "mitarbeiter", "chef", "rückruf", "mensch sprechen",
            ],
            CustomerIntent.COMPLAINT: [
                "beschwerde", "reklamation", "unzufrieden", "mangel",
            ],
        }

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

        # Get time-appropriate greeting
        hour = datetime.now().hour
        if hour < 12:
            time_greeting = "Guten Morgen"
        elif hour < 18:
            time_greeting = "Guten Tag"
        else:
            time_greeting = "Guten Abend"

        greeting = (
            f"{time_greeting}, {self.company_name}, "
            f"hier spricht der Telefonassistent. "
            f"Wie kann ich Ihnen helfen?"
        )

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
        detected_intent = self._detect_intent(input_lower)
        if detected_intent != CustomerIntent.UNKNOWN:
            context.detected_intent = detected_intent

        # Check for emergency keywords immediately
        emergency_type = self._detect_emergency(input_lower)
        if emergency_type:
            context.is_emergency = True
            context.emergency_type = emergency_type
            return self._handle_emergency(context, user_input, emergency_type)

        # Route based on current state and intent
        current_state = self._get_current_state(context)

        if current_state == ConversationState.GREETING:
            return self._handle_initial_request(context, user_input)

        elif current_state == ConversationState.CUSTOMER_IDENTIFICATION:
            return self._handle_customer_identification(context, user_input)

        elif current_state == ConversationState.ADDRESS_VERIFICATION:
            return self._handle_address_verification(context, user_input)

        elif current_state == ConversationState.PROBLEM_INQUIRY:
            return self._handle_problem_inquiry(context, user_input)

        elif current_state == ConversationState.PROBLEM_DETAILS:
            return self._handle_problem_details(context, user_input)

        elif current_state == ConversationState.SLOT_OFFER:
            return self._handle_slot_selection(context, user_input)

        elif current_state == ConversationState.SLOT_CONFIRMATION:
            return self._handle_confirmation(context, user_input)

        elif current_state == ConversationState.QUOTE_REQUEST:
            return self._handle_quote_request(context, user_input)

        elif current_state == ConversationState.FAREWELL:
            return self._handle_farewell(context)

        # Default: try to understand what they want
        return self._handle_unknown(context, user_input)

    def _detect_intent(self, text: str) -> CustomerIntent:
        """Detect intent from user text."""
        for intent, keywords in self._intent_keywords.items():
            for keyword in keywords:
                if keyword in text:
                    return intent
        return CustomerIntent.UNKNOWN

    def _detect_emergency(self, text: str) -> str | None:
        """Detect emergency type from text."""
        for emergency_type, keywords in EMERGENCY_PATTERNS.items():
            for keyword in keywords:
                if keyword in text:
                    return emergency_type
        return None

    def _get_current_state(self, context: ConversationContext) -> ConversationState:
        """Determine current conversation state."""
        if context.booked_service_call:
            return ConversationState.FAREWELL

        if context.selected_slot:
            return ConversationState.SLOT_CONFIRMATION

        if context.offered_slots:
            return ConversationState.SLOT_OFFER

        if context.quote_requested:
            return ConversationState.QUOTE_REQUEST

        if context.triage_performed and context.triage_result:
            if context.triage_result.urgency == UrgencyLevel.SICHERHEIT:
                return ConversationState.EMERGENCY_REDIRECT
            return ConversationState.TECHNICIAN_SEARCH

        if context.stated_problem and context.address_verified:
            return ConversationState.URGENCY_ASSESSMENT

        if context.stated_problem and not context.address_verified:
            return ConversationState.ADDRESS_VERIFICATION

        if context.customer_identified:
            return ConversationState.PROBLEM_INQUIRY

        if context.detected_intent != CustomerIntent.UNKNOWN:
            return ConversationState.CUSTOMER_IDENTIFICATION

        return ConversationState.GREETING

    def _handle_emergency(
        self,
        context: ConversationContext,
        user_input: str,
        emergency_type: str,
    ) -> ConversationResponse:
        """Handle emergency situation."""
        context.detected_intent = CustomerIntent.EMERGENCY_SERVICE

        emergency_messages = {
            "gas_leak": (
                "WICHTIG: Wenn Sie Gasgeruch bemerken, verlassen Sie sofort das Gebäude, "
                "öffnen Sie keine Schalter oder Lichtschalter, und rufen Sie die 112 oder "
                "den Gas-Notdienst an. "
                "Soll ich Sie mit unserem Notdienst verbinden?"
            ),
            "water_main": (
                "Bei einem Wasserrohrbruch schließen Sie bitte sofort den Hauptwasserhahn. "
                "Ich kann Ihnen einen Notfall-Monteur schicken. "
                "Soll ich das sofort veranlassen?"
            ),
            "electrical": (
                "WICHTIG: Bei elektrischen Problemen mit Rauch oder Funken schalten Sie "
                "sofort die Sicherung aus oder den Hauptschalter. Bei Gefahr rufen Sie die 112. "
                "Soll ich Sie mit unserem Elektro-Notdienst verbinden?"
            ),
            "flooding": (
                "Bei einer Überschwemmung schalten Sie bitte den Strom ab, falls Wasser "
                "elektrische Anlagen erreicht hat. "
                "Ich kann sofort einen Monteur schicken. Soll ich das veranlassen?"
            ),
            "locked_danger": (
                "Ich verstehe, dass Sie dringend Hilfe brauchen. "
                "Bei Gefahr für Personen rufen Sie bitte die 112. "
                "Ansonsten kann ich sofort unseren Schlüsseldienst schicken. "
                "Wie soll ich vorgehen?"
            ),
            "heating_emergency": (
                "Bei ausgefallener Heizung im Winter verstehe ich die Dringlichkeit. "
                "Ich suche sofort einen verfügbaren Techniker für Sie. "
                "Darf ich Ihre Adresse haben?"
            ),
        }

        message = emergency_messages.get(emergency_type, (
            "Ich verstehe, dass Sie dringende Hilfe brauchen. "
            "Soll ich Sie mit unserem Notdienst verbinden oder "
            "sofort einen Techniker schicken?"
        ))

        context.add_message("assistant", message)

        return ConversationResponse(
            state=ConversationState.EMERGENCY_REDIRECT,
            message=message,
            requires_input=True,
            options=["Sofort Techniker schicken", "Mit Notdienst verbinden", "112 rufen"],
            metadata={"emergency_type": emergency_type},
            is_emergency=True,
        )

    def _handle_initial_request(
        self,
        context: ConversationContext,
        user_input: str,
    ) -> ConversationResponse:
        """Handle initial request after greeting."""
        context.stated_problem = user_input

        # Detect trade category from problem description
        issues = self._triage.extract_issues_from_text(user_input)
        if issues:
            context.detected_issues = issues
            context.detected_trade = issues[0].category

        # Determine next step based on intent
        if context.detected_intent == CustomerIntent.SPEAK_TO_STAFF:
            return self._initiate_transfer(context, "Verbindung zum Personal gewünscht")

        if context.detected_intent == CustomerIntent.GET_QUOTE:
            context.quote_requested = True
            message = (
                "Gerne erstelle ich Ihnen ein Angebot. "
                "Darf ich Ihren Namen und Ihre Adresse haben?"
            )
        elif context.detected_intent == CustomerIntent.COMPLAINT:
            return self._initiate_transfer(context, "Beschwerde/Reklamation")
        else:
            message = (
                "Verstanden, da helfe ich Ihnen gerne. "
                "Darf ich Ihren Namen und Ihre Telefonnummer für Rückfragen haben?"
            )

        context.add_message("assistant", message)

        return ConversationResponse(
            state=ConversationState.CUSTOMER_IDENTIFICATION,
            message=message,
            requires_input=True,
        )

    def _handle_customer_identification(
        self,
        context: ConversationContext,
        user_input: str,
    ) -> ConversationResponse:
        """Handle customer identification."""
        # Simple extraction (would use NLU in production)
        context.customer_name = user_input.strip()
        context.customer_identified = True

        # Log data access
        self._audit.log(
            action=AuditAction.DATA_SEARCH,
            actor_id="phone_agent",
            actor_type="ai_agent",
            resource_type="customer",
            details={"search_query": "name lookup"},
        )

        # Get first name for personal address
        first_name = context.customer_name.split()[0] if context.customer_name else "Kunde"

        message = (
            f"Vielen Dank, {first_name}. "
            f"An welcher Adresse sollen wir vorbeikommen?"
        )

        context.add_message("assistant", message)

        return ConversationResponse(
            state=ConversationState.ADDRESS_VERIFICATION,
            message=message,
            requires_input=True,
        )

    def _handle_address_verification(
        self,
        context: ConversationContext,
        user_input: str,
    ) -> ConversationResponse:
        """Handle address verification."""
        # Simple address storage (would parse in production)
        context.street = user_input.strip()
        context.address_verified = True

        # If problem was mentioned earlier, proceed to triage
        if context.stated_problem:
            return self._perform_triage(context)

        message = "Können Sie mir bitte das Problem genauer beschreiben?"

        context.add_message("assistant", message)

        return ConversationResponse(
            state=ConversationState.PROBLEM_INQUIRY,
            message=message,
            requires_input=True,
        )

    def _handle_problem_inquiry(
        self,
        context: ConversationContext,
        user_input: str,
    ) -> ConversationResponse:
        """Handle problem description."""
        context.stated_problem = user_input

        # Check for emergency in problem description
        emergency_type = self._detect_emergency(user_input.lower())
        if emergency_type:
            context.is_emergency = True
            context.emergency_type = emergency_type
            return self._handle_emergency(context, user_input, emergency_type)

        # Extract issues
        issues = self._triage.extract_issues_from_text(user_input)
        if issues:
            context.detected_issues = issues
            context.detected_trade = issues[0].category

        return self._perform_triage(context)

    def _handle_problem_details(
        self,
        context: ConversationContext,
        user_input: str,
    ) -> ConversationResponse:
        """Handle additional problem details."""
        # Append to problem description and re-triage
        context.stated_problem = f"{context.stated_problem or ''} {user_input}"
        return self._perform_triage(context)

    def _perform_triage(self, context: ConversationContext) -> ConversationResponse:
        """Perform triage assessment."""
        result = self._triage.assess(
            issues=context.detected_issues,
            free_text=context.stated_problem,
        )

        context.triage_performed = True
        context.triage_result = result

        # Handle based on urgency
        if result.urgency == UrgencyLevel.SICHERHEIT:
            return self._handle_emergency(
                context,
                context.stated_problem or "",
                context.emergency_type or "general_emergency"
            )

        if result.urgency == UrgencyLevel.DRINGEND:
            context.job_type = JobType.NOTFALL

            message = (
                f"Ich verstehe, dass das dringend ist. {result.recommended_action} "
                f"Ich suche sofort einen verfügbaren Techniker für heute."
            )

            context.add_message("assistant", message, triage=result.to_dict())

            return self._search_slots(context, urgent=True)

        # Standard or routine
        if result.urgency == UrgencyLevel.ROUTINE:
            context.job_type = JobType.WARTUNG
        else:
            context.job_type = JobType.REPARATUR

        message = (
            f"Vielen Dank für die Beschreibung. {result.recommended_action} "
            f"Ich schaue nach verfügbaren Terminen."
        )

        context.add_message("assistant", message, triage=result.to_dict())

        return self._search_slots(context)

    def _search_slots(
        self,
        context: ConversationContext,
        urgent: bool = False,
    ) -> ConversationResponse:
        """Search for available time slots."""
        prefs = SchedulingPreferences(
            job_type=context.job_type,
            trade_category=context.detected_trade,
            urgency_max_wait_hours=4 if urgent else None,
        )

        slots = self._scheduling.find_slots(prefs, limit=3)
        context.offered_slots = slots

        if not slots:
            message = (
                "Leider habe ich aktuell keine passenden Termine gefunden. "
                "Soll ich Sie für einen Rückruf vormerken, sobald ein Termin frei wird?"
            )
            context.add_message("assistant", message)
            return ConversationResponse(
                state=ConversationState.SLOT_OFFER,
                message=message,
                requires_input=True,
                options=["Ja, bitte Rückruf", "Nein, danke"],
            )

        # Format slots for speech
        slots_text = self._format_slots_for_speech(slots)

        if urgent:
            message = (
                f"Ich habe folgende Termine für Sie gefunden:\n\n{slots_text}\n\n"
                f"Unser Monteur ruft Sie etwa 30 Minuten vor Ankunft an. "
                f"Welcher Termin passt Ihnen?"
            )
        else:
            message = f"{slots_text}\n\nWelcher Termin passt Ihnen am besten?"

        context.add_message("assistant", message)

        return ConversationResponse(
            state=ConversationState.SLOT_OFFER,
            message=message,
            requires_input=True,
            options=[f"Termin {i+1}" for i in range(len(slots))],
        )

    def _format_slots_for_speech(self, slots: list[TimeSlot]) -> str:
        """Format time slots for speech output."""
        lines = []
        for i, slot in enumerate(slots, 1):
            day_names = {
                0: "Montag", 1: "Dienstag", 2: "Mittwoch",
                3: "Donnerstag", 4: "Freitag", 5: "Samstag", 6: "Sonntag"
            }
            day_name = day_names.get(slot.start_time.weekday(), "")
            date_str = slot.start_time.strftime("%d.%m.")
            start_str = slot.start_time.strftime("%H:%M")
            end_str = slot.end_time.strftime("%H:%M") if slot.end_time else ""

            if end_str:
                lines.append(f"Termin {i}: {day_name}, {date_str} zwischen {start_str} und {end_str} Uhr")
            else:
                lines.append(f"Termin {i}: {day_name}, {date_str} ab {start_str} Uhr")

        return "\n".join(lines)

    def _handle_slot_selection(
        self,
        context: ConversationContext,
        user_input: str,
    ) -> ConversationResponse:
        """Handle time slot selection."""
        input_lower = user_input.lower()

        # Check for callback request:
        # - "rückruf" (callback) always triggers callback scheduling
        # - "ja" (yes) without offered slots triggers callback (user confused)
        if "rückruf" in input_lower or ("ja" in input_lower and not context.offered_slots):
            message = (
                "Kein Problem, ich habe Sie für einen Rückruf vorgemerkt. "
                "Wir melden uns, sobald ein Termin frei wird. "
                "Kann ich sonst noch etwas für Sie tun?"
            )
            context.add_message("assistant", message)
            return ConversationResponse(
                state=ConversationState.FAREWELL,
                message=message,
                requires_input=True,
                schedule_callback=True,
            )

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

            slot_text = self._format_slot_for_confirmation(context.selected_slot)

            message = (
                f"Perfekt! Ich trage Sie ein für {slot_text}. "
                f"Unser Monteur ruft Sie etwa 30 Minuten vor Ankunft an. "
                f"Ist das so richtig?"
            )

            context.add_message("assistant", message)

            return ConversationResponse(
                state=ConversationState.SLOT_CONFIRMATION,
                message=message,
                requires_input=True,
                options=["Ja, richtig", "Nein, anders"],
            )

        # Didn't understand selection
        message = "Entschuldigung, welchen Termin möchten Sie? Bitte sagen Sie Termin 1, 2 oder 3."
        context.add_message("assistant", message)

        return ConversationResponse(
            state=ConversationState.SLOT_OFFER,
            message=message,
            requires_input=True,
        )

    def _format_slot_for_confirmation(self, slot: TimeSlot) -> str:
        """Format a single slot for confirmation."""
        day_names = {
            0: "Montag", 1: "Dienstag", 2: "Mittwoch",
            3: "Donnerstag", 4: "Freitag", 5: "Samstag", 6: "Sonntag"
        }
        day_name = day_names.get(slot.start_time.weekday(), "")
        date_str = slot.start_time.strftime("%d.%m.")
        start_str = slot.start_time.strftime("%H:%M")
        end_str = slot.end_time.strftime("%H:%M") if slot.end_time else ""

        if end_str:
            return f"{day_name}, den {date_str} zwischen {start_str} und {end_str} Uhr"
        return f"{day_name}, den {date_str} ab {start_str} Uhr"

    def _handle_confirmation(
        self,
        context: ConversationContext,
        user_input: str,
    ) -> ConversationResponse:
        """Handle appointment confirmation."""
        input_lower = user_input.lower()

        if "ja" in input_lower or "richtig" in input_lower or "stimmt" in input_lower:
            # Book the service call
            customer = Customer(
                id=context.customer_id or uuid4(),
                first_name=context.customer_name.split()[0] if context.customer_name else "Kunde",
                last_name=" ".join(context.customer_name.split()[1:]) if context.customer_name and len(context.customer_name.split()) > 1 else "",
                phone=context.customer_phone or "",
                company_name=context.customer_company,
                street=context.street or "",
                zip_code=context.zip_code or "",
                city=context.city or "",
            )

            service_call = self._scheduling.book_service_call(
                slot=context.selected_slot,
                customer=customer,
                problem_description=context.stated_problem or "Telefonische Anmeldung",
                job_type=context.job_type,
            )

            context.booked_service_call = service_call

            # Log service call creation
            self._audit.log(
                action=AuditAction.SERVICE_CALL_CREATED,
                actor_id="phone_agent",
                actor_type="ai_agent",
                resource_type="service_call",
                resource_id=str(service_call.id),
                customer_id=context.customer_id,
            )

            slot_text = self._format_slot_for_confirmation(context.selected_slot)

            message = (
                f"Wunderbar! Ihr Termin ist bestätigt für {slot_text}. "
                f"Unser Monteur ruft Sie etwa 30 Minuten vor Ankunft an. "
                f"Bitte stellen Sie sicher, dass jemand vor Ort ist. "
                f"Kann ich sonst noch etwas für Sie tun?"
            )

            context.add_message("assistant", message)

            return ConversationResponse(
                state=ConversationState.FAREWELL,
                message=message,
                requires_input=True,
                send_sms=True,
                sms_content=(
                    f"{self.company_name}: Termin bestätigt für {slot_text}. "
                    f"Monteur ruft 30 Min. vorher an."
                ),
                dispatch_technician=True,
            )

        # They said no - go back to selection
        context.selected_slot = None
        message = "Kein Problem. Welcher Termin passt Ihnen besser?"
        context.add_message("assistant", message)

        return ConversationResponse(
            state=ConversationState.SLOT_OFFER,
            message=message,
            requires_input=True,
        )

    def _handle_quote_request(
        self,
        context: ConversationContext,
        user_input: str,
    ) -> ConversationResponse:
        """Handle quote request flow."""
        context.quote_notes = user_input

        message = (
            "Vielen Dank für die Informationen. Wir erstellen Ihnen gerne ein Angebot. "
            "Unser Team wird sich innerhalb von 24 Stunden bei Ihnen melden. "
            "Kann ich sonst noch etwas für Sie tun?"
        )

        context.add_message("assistant", message)

        return ConversationResponse(
            state=ConversationState.FAREWELL,
            message=message,
            requires_input=True,
        )

    def _handle_farewell(self, context: ConversationContext) -> ConversationResponse:
        """Handle conversation conclusion."""
        message = (
            f"Vielen Dank für Ihren Anruf bei {self.company_name}. "
            f"Wir freuen uns, Ihnen helfen zu können. "
            f"Auf Wiederhören!"
        )

        context.add_message("assistant", message)

        # Log call end
        self._audit.log_call_event(
            call_id=context.call_id,
            action=AuditAction.CALL_ENDED,
            customer_id=context.customer_id,
            details={
                "duration_seconds": int((datetime.now() - context.started_at).total_seconds()),
                "service_call_booked": context.booked_service_call is not None,
                "was_emergency": context.is_emergency,
                "trade_category": context.detected_trade.value if context.detected_trade else None,
            },
        )

        return ConversationResponse(
            state=ConversationState.COMPLETED,
            message=message,
            requires_input=False,
            end_call=True,
        )

    def _initiate_transfer(
        self,
        context: ConversationContext,
        reason: str,
    ) -> ConversationResponse:
        """Initiate transfer to staff."""
        context.needs_transfer = True
        context.transfer_reason = reason

        message = (
            "Ich verbinde Sie mit einem Mitarbeiter. "
            "Bitte bleiben Sie einen Moment in der Leitung."
        )

        context.add_message("assistant", message)

        return ConversationResponse(
            state=ConversationState.TRANSFER_TO_STAFF,
            message=message,
            requires_input=False,
            transfer_call=True,
            metadata={"transfer_reason": reason},
        )

    def _handle_unknown(
        self,
        context: ConversationContext,
        user_input: str,
    ) -> ConversationResponse:
        """Handle unrecognized input."""
        message = (
            "Entschuldigung, das habe ich nicht verstanden. "
            "Brauchen Sie eine Reparatur, möchten Sie einen Wartungstermin, "
            "oder soll ich Sie mit einem Mitarbeiter verbinden?"
        )

        context.add_message("assistant", message)

        return ConversationResponse(
            state=ConversationState.PROBLEM_INQUIRY,
            message=message,
            requires_input=True,
            options=["Reparatur", "Wartungstermin", "Mit Mitarbeiter sprechen"],
        )


# Manager instances keyed by company name (thread-safe)
_conversation_managers: dict[str, HandwerkConversationManager] = {}
_conversation_manager_lock = __import__("threading").Lock()


def get_conversation_manager(
    company_name: str = "Mustermann GmbH",
) -> HandwerkConversationManager:
    """Get or create conversation manager for a specific company.

    Thread-safe via double-checked locking pattern.
    Each company gets its own manager instance.
    """
    if company_name not in _conversation_managers:
        with _conversation_manager_lock:
            # Double-check after acquiring lock
            if company_name not in _conversation_managers:
                _conversation_managers[company_name] = HandwerkConversationManager(
                    company_name=company_name
                )
    return _conversation_managers[company_name]
