"""Healthcare-specific conversation manager.

This module is a backwards-compatible re-export from the refactored
conversation package. All functionality has been moved to:

- phone_agent.industry.gesundheit.conversation.state
- phone_agent.industry.gesundheit.conversation.intents
- phone_agent.industry.gesundheit.conversation.responses
- phone_agent.industry.gesundheit.conversation.actions
- phone_agent.industry.gesundheit.conversation.handlers
- phone_agent.industry.gesundheit.conversation.manager

Import directly from the package for new code:
    from phone_agent.industry.gesundheit.conversation import (
        HealthcareConversationManager,
        ConversationContext,
        ConversationResponse,
    )
"""

# Re-export everything for backwards compatibility
from phone_agent.industry.gesundheit.conversation import (
    # State and context
    ConversationState,
    PatientIntent,
    ConversationContext,
    ConversationResponse,
    # Intent detection
    IntentDetector,
    get_intent_detector,
    INTENT_KEYWORDS,
    # Actions and handlers
    ConversationActions,
    ConversationHandlers,
    # Main manager
    HealthcareConversationManager,
)

__all__ = [
    "ConversationState",
    "PatientIntent",
    "ConversationContext",
    "ConversationResponse",
    "IntentDetector",
    "get_intent_detector",
    "INTENT_KEYWORDS",
    "ConversationActions",
    "ConversationHandlers",
    "HealthcareConversationManager",
]
