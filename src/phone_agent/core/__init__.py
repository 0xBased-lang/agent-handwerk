"""Core business logic for phone agent."""

from phone_agent.core.audio import AudioPipeline
from phone_agent.core.conversation import ConversationEngine
from phone_agent.core.call_handler import CallHandler, CallState
from phone_agent.core.exceptions import (
    PhoneAgentError,
    DatabaseError,
    DatabaseConnectionError,
    DatabaseQueryError,
    RecordNotFoundError,
    TelephonyError,
    SIPConnectionError,
    CallError,
    CallNotFoundError,
    AIError,
    ModelNotLoadedError,
    IntegrationError,
    CalendarIntegrationError,
    SMSGatewayError,
    BusinessError,
    ValidationError,
    AppointmentConflictError,
    AuthError,
    InvalidSignatureError,
)

__all__ = [
    # Core components
    "AudioPipeline",
    "ConversationEngine",
    "CallHandler",
    "CallState",
    # Exceptions
    "PhoneAgentError",
    "DatabaseError",
    "DatabaseConnectionError",
    "DatabaseQueryError",
    "RecordNotFoundError",
    "TelephonyError",
    "SIPConnectionError",
    "CallError",
    "CallNotFoundError",
    "AIError",
    "ModelNotLoadedError",
    "IntegrationError",
    "CalendarIntegrationError",
    "SMSGatewayError",
    "BusinessError",
    "ValidationError",
    "AppointmentConflictError",
    "AuthError",
    "InvalidSignatureError",
]
