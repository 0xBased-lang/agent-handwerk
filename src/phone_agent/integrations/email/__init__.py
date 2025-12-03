"""Email Gateway Integration Module.

Provides email sending capabilities for:
- Appointment confirmations
- Reminders
- Notifications
- Custom messages

Supported providers:
- smtp: Standard SMTP email (works with Gmail, Office 365, etc.)
- sendgrid: SendGrid API with delivery tracking
- mock: For development and testing

Delivery Tracking:
- SendGrid provides webhook callbacks for delivery status
- Status progression: queued -> processed -> delivered/bounced
- Open and click tracking available with SendGrid
"""

from phone_agent.integrations.email.base import (
    EmailGateway,
    EmailMessage,
    EmailResult,
    EmailStatus,
    EmailPriority,
    EmailAttachment,
    MockEmailGateway,
)
from phone_agent.integrations.email.factory import (
    get_email_gateway,
    reset_email_gateway,
    send_appointment_confirmation,
    send_appointment_reminder,
    send_appointment_cancellation,
)


# Lazy imports for provider-specific gateways
def __getattr__(name: str):
    """Lazy load provider-specific gateways."""
    if name == "SMTPEmailGateway":
        from phone_agent.integrations.email.smtp import SMTPEmailGateway

        return SMTPEmailGateway
    elif name == "SendGridEmailGateway":
        from phone_agent.integrations.email.sendgrid import SendGridEmailGateway

        return SendGridEmailGateway
    elif name == "SendGridWebhookHandler":
        from phone_agent.integrations.email.sendgrid import SendGridWebhookHandler

        return SendGridWebhookHandler
    elif name == "TemplateContext":
        from phone_agent.integrations.email.templates import TemplateContext

        return TemplateContext
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    # Base classes
    "EmailGateway",
    "EmailMessage",
    "EmailResult",
    "EmailStatus",
    "EmailPriority",
    "EmailAttachment",
    "MockEmailGateway",
    # Provider gateways (lazy loaded)
    "SMTPEmailGateway",
    "SendGridEmailGateway",
    "SendGridWebhookHandler",
    # Templates
    "TemplateContext",
    # Factory
    "get_email_gateway",
    "reset_email_gateway",
    # Convenience functions
    "send_appointment_confirmation",
    "send_appointment_reminder",
    "send_appointment_cancellation",
]
