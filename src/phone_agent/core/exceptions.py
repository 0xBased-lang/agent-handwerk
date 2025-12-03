"""Phone Agent Exception Hierarchy.

Provides structured error handling with context preservation
and proper HTTP status code mapping.
"""

from __future__ import annotations

from typing import Any


class PhoneAgentError(Exception):
    """Base exception for all Phone Agent errors.

    All custom exceptions should inherit from this class.
    Provides:
    - Structured error context
    - HTTP status code mapping
    - Logging-friendly representation
    """

    status_code: int = 500
    error_code: str = "PHONE_AGENT_ERROR"

    def __init__(
        self,
        message: str,
        *,
        details: dict[str, Any] | None = None,
        cause: Exception | None = None,
    ) -> None:
        """Initialize the exception.

        Args:
            message: Human-readable error message
            details: Additional context for debugging
            cause: Original exception if wrapping
        """
        super().__init__(message)
        self.message = message
        self.details = details or {}
        self.cause = cause

    def to_dict(self) -> dict[str, Any]:
        """Convert to API-friendly dictionary."""
        result = {
            "error": self.error_code,
            "message": self.message,
        }
        if self.details:
            result["details"] = self.details
        if self.cause:
            result["cause"] = str(self.cause)
        return result

    def __str__(self) -> str:
        """String representation for logging."""
        parts = [f"{self.error_code}: {self.message}"]
        if self.details:
            parts.append(f"details={self.details}")
        if self.cause:
            parts.append(f"cause={self.cause}")
        return " | ".join(parts)


# =============================================================================
# Database Errors
# =============================================================================


class DatabaseError(PhoneAgentError):
    """Base class for database-related errors."""

    status_code = 503
    error_code = "DATABASE_ERROR"


class DatabaseConnectionError(DatabaseError):
    """Failed to connect to database."""

    error_code = "DATABASE_CONNECTION_ERROR"


class DatabaseQueryError(DatabaseError):
    """Database query execution failed."""

    error_code = "DATABASE_QUERY_ERROR"


class RecordNotFoundError(DatabaseError):
    """Requested record not found."""

    status_code = 404
    error_code = "RECORD_NOT_FOUND"


class RecordAlreadyExistsError(DatabaseError):
    """Record with given identifier already exists."""

    status_code = 409
    error_code = "RECORD_ALREADY_EXISTS"


# =============================================================================
# Telephony Errors
# =============================================================================


class TelephonyError(PhoneAgentError):
    """Base class for telephony-related errors."""

    status_code = 503
    error_code = "TELEPHONY_ERROR"


class SIPConnectionError(TelephonyError):
    """Failed to connect to SIP server."""

    error_code = "SIP_CONNECTION_ERROR"


class SIPRegistrationError(TelephonyError):
    """SIP registration failed."""

    error_code = "SIP_REGISTRATION_ERROR"


class CallError(TelephonyError):
    """Error during call handling."""

    error_code = "CALL_ERROR"


class CallNotFoundError(CallError):
    """Call with given ID not found."""

    status_code = 404
    error_code = "CALL_NOT_FOUND"


class CallTransferError(CallError):
    """Failed to transfer call."""

    error_code = "CALL_TRANSFER_ERROR"


class FreeSwitchError(TelephonyError):
    """FreeSWITCH-specific error."""

    error_code = "FREESWITCH_ERROR"


class AudioBridgeError(TelephonyError):
    """Audio bridge error."""

    error_code = "AUDIO_BRIDGE_ERROR"


# =============================================================================
# AI/Model Errors
# =============================================================================


class AIError(PhoneAgentError):
    """Base class for AI-related errors."""

    status_code = 503
    error_code = "AI_ERROR"


class ModelNotLoadedError(AIError):
    """AI model not loaded."""

    error_code = "MODEL_NOT_LOADED"


class ModelLoadError(AIError):
    """Failed to load AI model."""

    error_code = "MODEL_LOAD_ERROR"


class TranscriptionError(AIError):
    """Speech-to-text transcription failed."""

    error_code = "TRANSCRIPTION_ERROR"


class GenerationError(AIError):
    """LLM generation failed."""

    error_code = "GENERATION_ERROR"


class SynthesisError(AIError):
    """Text-to-speech synthesis failed."""

    error_code = "SYNTHESIS_ERROR"


# =============================================================================
# Integration Errors
# =============================================================================


class IntegrationError(PhoneAgentError):
    """Base class for external integration errors."""

    status_code = 502
    error_code = "INTEGRATION_ERROR"


class CalendarIntegrationError(IntegrationError):
    """Calendar integration failed."""

    error_code = "CALENDAR_INTEGRATION_ERROR"


class SMSGatewayError(IntegrationError):
    """SMS gateway error."""

    error_code = "SMS_GATEWAY_ERROR"


class PVSIntegrationError(IntegrationError):
    """Practice management system integration error."""

    error_code = "PVS_INTEGRATION_ERROR"


class WebhookError(IntegrationError):
    """Webhook delivery or processing error."""

    error_code = "WEBHOOK_ERROR"


# =============================================================================
# Business Logic Errors
# =============================================================================


class BusinessError(PhoneAgentError):
    """Base class for business logic errors."""

    status_code = 400
    error_code = "BUSINESS_ERROR"


class ValidationError(BusinessError):
    """Input validation failed."""

    error_code = "VALIDATION_ERROR"


class AppointmentConflictError(BusinessError):
    """Appointment time slot conflict."""

    status_code = 409
    error_code = "APPOINTMENT_CONFLICT"


class SchedulingError(BusinessError):
    """Scheduling operation failed."""

    error_code = "SCHEDULING_ERROR"


class TriageError(BusinessError):
    """Triage processing error."""

    error_code = "TRIAGE_ERROR"


class CampaignError(BusinessError):
    """Campaign-related error."""

    error_code = "CAMPAIGN_ERROR"


# =============================================================================
# Authentication/Authorization Errors
# =============================================================================


class AuthError(PhoneAgentError):
    """Base class for authentication/authorization errors."""

    status_code = 401
    error_code = "AUTH_ERROR"


class InvalidSignatureError(AuthError):
    """Webhook signature validation failed."""

    error_code = "INVALID_SIGNATURE"


class UnauthorizedError(AuthError):
    """Request not authorized."""

    error_code = "UNAUTHORIZED"


class ForbiddenError(AuthError):
    """Access forbidden."""

    status_code = 403
    error_code = "FORBIDDEN"


# =============================================================================
# Resource Errors
# =============================================================================


class ResourceError(PhoneAgentError):
    """Base class for resource-related errors."""

    status_code = 503
    error_code = "RESOURCE_ERROR"


class ResourceExhaustedError(ResourceError):
    """Resource limit exceeded."""

    error_code = "RESOURCE_EXHAUSTED"


class TimeoutError(ResourceError):
    """Operation timed out."""

    status_code = 504
    error_code = "TIMEOUT"


# =============================================================================
# Utility Functions
# =============================================================================


def wrap_exception(
    exc: Exception,
    wrapper_class: type[PhoneAgentError] = PhoneAgentError,
    message: str | None = None,
    **details: Any,
) -> PhoneAgentError:
    """Wrap a generic exception in a PhoneAgentError.

    Args:
        exc: Original exception to wrap
        wrapper_class: PhoneAgentError subclass to use
        message: Override message (defaults to str(exc))
        **details: Additional context details

    Returns:
        Wrapped PhoneAgentError instance
    """
    return wrapper_class(
        message=message or str(exc),
        details=details or None,
        cause=exc,
    )
