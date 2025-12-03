"""Base conversation management classes.

Provides abstract base classes for industry-specific conversation managers.
Reduces ~1000 LOC of duplication across gesundheit, handwerk, freie_berufe, and gastro.

Usage:
    from phone_agent.industry.base import (
        BaseConversationState,
        BaseConversationContext,
        BaseConversationResponse,
        BaseConversationManager,
    )

    class MyState(BaseConversationState):
        GREETING = "greeting"
        FAREWELL = "farewell"
        ...

    class MyManager(BaseConversationManager[MyState, MyContext, MyResponse]):
        def _get_state_handlers(self) -> dict[MyState, StateHandler]:
            ...
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Generic, TypeVar


# Type for message history entries
MessageDict = dict[str, Any]

# Generic type variables for industry-specific types
StateT = TypeVar("StateT", bound="BaseConversationState")
ContextT = TypeVar("ContextT", bound="BaseConversationContext")
ResponseT = TypeVar("ResponseT", bound="BaseConversationResponse")

# State handler function signature
StateHandler = Callable[["BaseConversationContext", str], "BaseConversationResponse"]


class BaseConversationState(str, Enum):
    """Base conversation state enum.

    Industry modules should extend this with their specific states.
    Common states are provided as a starting point.
    """

    GREETING = "greeting"
    INTENT_DETECTION = "intent_detection"
    ESCALATION = "escalation"
    FAREWELL = "farewell"
    COMPLETED = "completed"


class BaseIntent(str, Enum):
    """Base intent enum.

    Industry modules should extend this with their specific intents.
    """

    UNKNOWN = "unknown"
    SPEAK_TO_HUMAN = "speak_to_human"
    COMPLAINT = "complaint"
    INFORMATION_REQUEST = "information_request"
    CANCEL = "cancel"


@dataclass
class BaseConversationContext:
    """Base conversation context with common fields.

    Industry modules should extend this with their specific data fields.
    All common fields are defined here to avoid duplication.

    Attributes:
        call_id: Unique identifier for the call
        state: Current conversation state
        intent: Detected user intent
        turn_count: Number of conversation turns
        messages: Conversation history
        started_at: When the conversation started
        business_name: Name of the business
        needs_escalation: Whether to escalate to human
        escalation_reason: Reason for escalation
    """

    call_id: str
    started_at: datetime = field(default_factory=datetime.now)

    # Conversation tracking
    turn_count: int = 0
    messages: list[MessageDict] = field(default_factory=list)

    # Business context
    business_name: str = "Business"

    # Escalation flags
    needs_escalation: bool = False
    escalation_reason: str | None = None

    def add_message(
        self,
        role: str,
        content: str,
        **metadata: Any,
    ) -> None:
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

    def get_last_user_message(self) -> str | None:
        """Get the most recent user message."""
        for msg in reversed(self.messages):
            if msg.get("role") == "user":
                return msg.get("content")
        return None

    def get_conversation_duration(self) -> float:
        """Get conversation duration in seconds."""
        return (datetime.now() - self.started_at).total_seconds()


@dataclass
class BaseConversationResponse:
    """Base conversation response with common fields.

    Industry modules should extend this with their specific action fields.

    Attributes:
        message: Response message to speak
        next_state: State to transition to
        requires_input: Whether we need user input
        needs_escalation: Whether to escalate to human
        escalation_reason: Reason for escalation
        actions: List of actions to perform
        metadata: Additional response metadata
        end_call: Whether to end the call
    """

    message: str
    next_state: BaseConversationState
    requires_input: bool = True
    needs_escalation: bool = False
    escalation_reason: str | None = None
    actions: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    end_call: bool = False


class BaseConversationManager(ABC, Generic[StateT, ContextT, ResponseT]):
    """Abstract base class for conversation managers.

    Provides common functionality for all industry-specific managers:
    - Context lifecycle management
    - State machine routing
    - Greeting generation
    - Intent detection framework
    - Escalation handling

    Subclasses must implement:
    - _get_state_handlers(): Return state-to-handler mapping
    - _create_context(): Create industry-specific context
    - _detect_intent(): Detect intent from message
    - Industry-specific handler methods

    Type Parameters:
        StateT: Industry-specific state enum
        ContextT: Industry-specific context class
        ResponseT: Industry-specific response class
    """

    def __init__(self, business_name: str = "Business") -> None:
        """Initialize conversation manager.

        Args:
            business_name: Name of the business for greetings
        """
        self.business_name = business_name
        self._contexts: dict[str, ContextT] = {}

    # =========================================================================
    # Abstract Methods (must be implemented by subclasses)
    # =========================================================================

    @abstractmethod
    def _get_state_handlers(self) -> dict[StateT, Callable[[ContextT, str], ResponseT]]:
        """Get mapping of states to handler methods.

        Returns:
            Dictionary mapping state enum values to handler methods
        """
        ...

    @abstractmethod
    def _create_context(self, call_id: str) -> ContextT:
        """Create a new industry-specific context.

        Args:
            call_id: Unique call identifier

        Returns:
            New context instance
        """
        ...

    @abstractmethod
    def _detect_intent(self, message: str) -> Any:
        """Detect intent from user message.

        Args:
            message: User's message (lowercased)

        Returns:
            Detected intent enum value
        """
        ...

    # =========================================================================
    # Common Lifecycle Methods
    # =========================================================================

    def start_conversation(self, call_id: str) -> ContextT:
        """Start a new conversation.

        Args:
            call_id: Unique call identifier

        Returns:
            New conversation context
        """
        context = self._create_context(call_id)
        self._contexts[call_id] = context
        return context

    def get_context(self, call_id: str) -> ContextT | None:
        """Get existing conversation context.

        Args:
            call_id: Call identifier

        Returns:
            Context if exists, None otherwise
        """
        return self._contexts.get(call_id)

    def end_conversation(self, call_id: str) -> None:
        """End and clean up a conversation.

        Args:
            call_id: Call identifier
        """
        if call_id in self._contexts:
            del self._contexts[call_id]

    # =========================================================================
    # Common Processing Methods
    # =========================================================================

    def process_turn(
        self,
        call_id: str,
        user_message: str,
    ) -> ResponseT:
        """Process a conversation turn.

        Args:
            call_id: Unique call identifier
            user_message: What the user said

        Returns:
            Response with next message and state
        """
        context = self._contexts.get(call_id)
        if not context:
            context = self.start_conversation(call_id)

        # Track the turn
        context.turn_count += 1
        context.add_message("user", user_message)

        # Get current state and route to handler
        current_state = self._get_current_state(context)
        handlers = self._get_state_handlers()
        handler = handlers.get(current_state, self._handle_unknown)

        # Process and get response
        response = handler(context, user_message)

        # Record assistant message
        context.add_message("assistant", response.message)

        return response

    def _get_current_state(self, context: ContextT) -> StateT:
        """Get current conversation state.

        Override in subclasses for complex state logic.

        Args:
            context: Conversation context

        Returns:
            Current state
        """
        return getattr(context, "state", BaseConversationState.GREETING)

    # =========================================================================
    # Common Handler Methods
    # =========================================================================

    def _handle_greeting(self, context: ContextT, message: str) -> ResponseT:
        """Handle initial greeting.

        Override for industry-specific greeting logic.
        """
        greeting = self._generate_greeting()
        return self._create_response(
            message=greeting,
            next_state=self._get_state_after_greeting(),
        )

    def _handle_farewell(self, context: ContextT, message: str) -> ResponseT:
        """Handle farewell.

        Override for industry-specific farewell logic.
        """
        farewell = self._generate_farewell()
        return self._create_response(
            message=farewell,
            next_state=self._get_completed_state(),
            requires_input=False,
            end_call=True,
            actions=["end_call"],
        )

    def _handle_escalation(self, context: ContextT, message: str) -> ResponseT:
        """Handle escalation to human."""
        return self._create_response(
            message="Einen Moment bitte, ich verbinde Sie mit einem Mitarbeiter.",
            next_state=self._get_farewell_state(),
            needs_escalation=True,
            escalation_reason=context.escalation_reason,
            actions=["transfer_to_human"],
        )

    def _handle_unknown(self, context: ContextT, message: str) -> ResponseT:
        """Handle unrecognized input."""
        return self._create_response(
            message=(
                "Entschuldigung, das habe ich nicht verstanden. "
                "Können Sie das bitte wiederholen?"
            ),
            next_state=self._get_current_state(context),
        )

    # =========================================================================
    # Common Utility Methods
    # =========================================================================

    def _generate_greeting(self) -> str:
        """Generate time-appropriate greeting.

        Returns:
            Greeting message
        """
        hour = datetime.now().hour

        if hour < 12:
            time_greeting = "Guten Morgen"
        elif hour < 18:
            time_greeting = "Guten Tag"
        else:
            time_greeting = "Guten Abend"

        return (
            f"{time_greeting}, {self.business_name}, "
            f"hier spricht der Telefonassistent. "
            f"Wie kann ich Ihnen helfen?"
        )

    def _generate_farewell(self) -> str:
        """Generate farewell message.

        Returns:
            Farewell message
        """
        return (
            f"Vielen Dank für Ihren Anruf bei {self.business_name}. "
            f"Auf Wiederhören!"
        )

    def _check_keywords(
        self,
        message: str,
        keywords: list[str],
    ) -> bool:
        """Check if message contains any of the keywords.

        Args:
            message: Message to check (should be lowercased)
            keywords: List of keywords to look for

        Returns:
            True if any keyword found
        """
        return any(kw in message for kw in keywords)

    def _get_question_for_field(self, field: str) -> str:
        """Get appropriate question for a missing field.

        Override for industry-specific field questions.

        Args:
            field: Name of the missing field

        Returns:
            Question to ask
        """
        common_questions = {
            "Name": "Darf ich Ihren Namen erfahren?",
            "Telefonnummer": "Unter welcher Nummer erreiche ich Sie?",
            "E-Mail": "Haben Sie eine E-Mail-Adresse?",
        }
        return common_questions.get(field, f"Ich benötige noch: {field}")

    def _get_information_response(self, message: str) -> str:
        """Generate response for common information requests.

        Override for industry-specific information.

        Args:
            message: User's message

        Returns:
            Information response
        """
        message_lower = message.lower()

        if "öffnungszeit" in message_lower:
            return "Bitte rufen Sie während unserer Geschäftszeiten an."

        if "adresse" in message_lower or "wo" in message_lower:
            return "Unsere Adresse finden Sie auf unserer Website."

        return "Wie kann ich Ihnen weiterhelfen?"

    # =========================================================================
    # State Helpers (override in subclasses if states differ)
    # =========================================================================

    def _get_state_after_greeting(self) -> StateT:
        """Get state to transition to after greeting."""
        return BaseConversationState.INTENT_DETECTION  # type: ignore

    def _get_farewell_state(self) -> StateT:
        """Get farewell state."""
        return BaseConversationState.FAREWELL  # type: ignore

    def _get_completed_state(self) -> StateT:
        """Get completed state."""
        return BaseConversationState.COMPLETED  # type: ignore

    # =========================================================================
    # Response Factory (subclasses should override with their ResponseT)
    # =========================================================================

    def _create_response(
        self,
        message: str,
        next_state: StateT,
        requires_input: bool = True,
        needs_escalation: bool = False,
        escalation_reason: str | None = None,
        actions: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        end_call: bool = False,
        **kwargs: Any,
    ) -> ResponseT:
        """Create a response object.

        Override in subclasses to return industry-specific response type.

        Args:
            message: Response message
            next_state: Next conversation state
            requires_input: Whether user input needed
            needs_escalation: Whether to escalate
            escalation_reason: Reason for escalation
            actions: Actions to perform
            metadata: Additional metadata
            end_call: Whether to end call
            **kwargs: Additional industry-specific fields

        Returns:
            Response object
        """
        return BaseConversationResponse(  # type: ignore
            message=message,
            next_state=next_state,
            requires_input=requires_input,
            needs_escalation=needs_escalation,
            escalation_reason=escalation_reason,
            actions=actions or [],
            metadata=metadata or {},
            end_call=end_call,
        )
