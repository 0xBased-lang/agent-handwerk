"""SMS Gateway Integration Module.

Provides SMS sending capabilities for:
- Appointment confirmations
- Reminders
- Notifications

Supported providers:
- twilio: Full delivery tracking via webhooks (recommended)
- sipgate: German VoIP provider, limited status tracking
- mock: For development and testing

Delivery Tracking:
- Twilio provides webhook callbacks for delivery status
- Status progression: queued -> sent -> delivered
- Failed messages can be automatically retried
"""

from phone_agent.integrations.sms.base import (
    SMSGateway,
    SMSMessage,
    SMSResult,
    SMSStatus,
    MockSMSGateway,
)
from phone_agent.integrations.sms.factory import get_sms_gateway, reset_sms_gateway

# Lazy imports for provider-specific gateways
def __getattr__(name: str):
    """Lazy load provider-specific gateways."""
    if name == "SipgateSMSGateway":
        from phone_agent.integrations.sms.sipgate import SipgateSMSGateway
        return SipgateSMSGateway
    elif name == "TwilioSMSGateway":
        from phone_agent.integrations.sms.twilio import TwilioSMSGateway
        return TwilioSMSGateway
    elif name == "TwilioWebhookHandler":
        from phone_agent.integrations.sms.twilio import TwilioWebhookHandler
        return TwilioWebhookHandler
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

__all__ = [
    # Base classes
    "SMSGateway",
    "SMSMessage",
    "SMSResult",
    "SMSStatus",
    "MockSMSGateway",
    # Provider gateways (lazy loaded)
    "SipgateSMSGateway",
    "TwilioSMSGateway",
    "TwilioWebhookHandler",
    # Factory
    "get_sms_gateway",
    "reset_sms_gateway",
]
