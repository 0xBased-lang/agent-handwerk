"""Base industry conversation module.

Provides abstract base classes and common functionality for all industry-specific
conversation managers, reducing code duplication across verticals.
"""

from phone_agent.industry.base.conversation import (
    # Base classes
    BaseConversationState,
    BaseIntent,
    BaseConversationContext,
    BaseConversationResponse,
    BaseConversationManager,
    # Type aliases
    StateHandler,
    MessageDict,
)

__all__ = [
    "BaseConversationState",
    "BaseIntent",
    "BaseConversationContext",
    "BaseConversationResponse",
    "BaseConversationManager",
    "StateHandler",
    "MessageDict",
]
