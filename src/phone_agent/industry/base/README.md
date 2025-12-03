# Base Conversation Module

Foundation classes for industry-specific conversation managers.

## Purpose

This module provides abstract base classes and common functionality for building
new industry-specific conversation managers. It establishes consistent patterns
for state management, intent detection, and conversation flow control.

## Components

### BaseConversationState
Abstract enum base for conversation states. Each industry defines its own states
(e.g., `GREETING`, `RESERVATION_INTAKE` for gastro, `PROBLEM_INQUIRY` for handwerk).

### BaseIntent
Abstract enum base for customer/client intents. Industries define domain-specific
intents (e.g., `NEW_RESERVATION` for gastro, `REQUEST_SERVICE` for handwerk).

### BaseConversationContext
Dataclass providing common conversation context fields:
- `call_id`: Unique call identifier
- `state`: Current conversation state
- `intent`: Detected intent
- `turn_count`: Number of conversation turns
- `messages`: Conversation history
- `started_at`: Conversation start timestamp
- `needs_escalation`: Escalation flag
- `escalation_reason`: Reason for escalation

### BaseConversationResponse
Dataclass for conversation processing responses:
- `message`: Response text to speak
- `next_state`: State to transition to
- `intent`: Detected/confirmed intent
- `needs_escalation`: Whether to escalate
- `actions`: List of actions to perform

### BaseConversationManager
Abstract base class providing:
- `start_conversation(call_id)`: Initialize new conversation
- `get_context(call_id)`: Retrieve existing context
- `end_conversation(call_id)`: Clean up conversation
- `process_turn(call_id, message)`: Abstract - implement in subclass
- `_detect_intent(message, context)`: Abstract - implement in subclass
- `_generate_response(context)`: Abstract - implement in subclass

## Usage

```python
from phone_agent.industry.base import (
    BaseConversationState,
    BaseIntent,
    BaseConversationContext,
    BaseConversationResponse,
    BaseConversationManager,
)

class MyIndustryState(BaseConversationState):
    GREETING = "greeting"
    INTAKE = "intake"
    CONFIRMATION = "confirmation"
    FAREWELL = "farewell"

class MyIndustryIntent(BaseIntent):
    NEW_REQUEST = "new_request"
    CANCEL = "cancel"
    UNKNOWN = "unknown"

class MyIndustryManager(BaseConversationManager):
    def process_turn(self, call_id: str, message: str) -> BaseConversationResponse:
        # Implement industry-specific logic
        ...

    def _detect_intent(self, message: str, context) -> MyIndustryIntent:
        # Implement intent detection
        ...

    def _generate_response(self, context) -> str:
        # Implement response generation
        ...
```

## Existing Industry Modules

The following industry modules were built before this base class and have their
own implementations that work well:

| Module | Lines | Status | Notes |
|--------|-------|--------|-------|
| gesundheit | 2,062 | Package structure | Already well-refactored into 7 files |
| handwerk | 986 | Monolithic | Complex domain integrations (triage, technician) |
| freie_berufe | 612 | Monolithic | Lead qualification workflow |
| gastro | 613 | Monolithic | Restaurant reservation workflow |

### Why Existing Modules Weren't Refactored

1. **Domain-specific logic**: Each industry has unique states, intents, and data
   classes that don't share common implementations

2. **Working code**: 503 tests pass - refactoring carries regression risk

3. **Minimal benefit**: ~15% deduplication vs 4+ hours of risky refactoring

4. **Different abstractions**:
   - Gastro uses `ReservationData`
   - Freie Berufe uses `LeadData`
   - Handwerk uses `TriageResult`, `TechnicianMatch`
   - These are fundamentally different domain models

### When to Use Base Classes

Use these base classes when:
- Creating a **new** industry vertical
- Building a prototype conversation flow
- Need consistent interface for multi-industry systems

Don't refactor existing modules unless:
- Adding significant new shared functionality
- Consolidating multiple industries into unified system
- Technical debt becomes blocking issue

## File Structure

```
src/phone_agent/industry/base/
├── __init__.py          # Public exports
├── conversation.py      # Base classes implementation
└── README.md           # This file
```

## Version History

- **v1.0.0** (2024): Initial extraction from common patterns across 4 industries
