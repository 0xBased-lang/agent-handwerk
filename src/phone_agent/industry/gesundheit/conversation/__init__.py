"""Healthcare conversation management package.

Provides modular conversation handling for healthcare phone calls.

Modules:
- state: Conversation states, intents, and context
- intents: Intent detection from user input
- responses: German response templates
- actions: Core action implementations
- handlers: Flow control and routing
- manager: Main orchestrator

Usage:
    from phone_agent.industry.gesundheit.conversation import (
        HealthcareConversationManager,
        ConversationContext,
        ConversationResponse,
        ConversationState,
        PatientIntent,
    )

    manager = HealthcareConversationManager("Dr. Mustermann")
    context, response = manager.start_conversation("call-123")
"""

from phone_agent.industry.gesundheit.conversation.state import (
    ConversationState,
    PatientIntent,
    ConversationContext,
    ConversationResponse,
)
from phone_agent.industry.gesundheit.conversation.intents import (
    IntentDetector,
    get_intent_detector,
    INTENT_KEYWORDS,
)
from phone_agent.industry.gesundheit.conversation.actions import ConversationActions
from phone_agent.industry.gesundheit.conversation.handlers import ConversationHandlers
from phone_agent.industry.gesundheit.conversation.manager import HealthcareConversationManager

__all__ = [
    # State and context
    "ConversationState",
    "PatientIntent",
    "ConversationContext",
    "ConversationResponse",
    # Intent detection
    "IntentDetector",
    "get_intent_detector",
    "INTENT_KEYWORDS",
    # Actions and handlers
    "ConversationActions",
    "ConversationHandlers",
    # Main manager
    "HealthcareConversationManager",
]
