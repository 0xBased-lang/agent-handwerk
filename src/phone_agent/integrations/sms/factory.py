"""SMS Gateway Factory.

Creates the appropriate SMS gateway based on configuration.

Supported providers:
- twilio: Full delivery tracking via webhooks
- sipgate: German VoIP provider, limited status tracking
- mock: For development and testing
"""

from __future__ import annotations

from itf_shared import get_logger

from phone_agent.config import get_settings
from phone_agent.integrations.sms.base import SMSGateway, MockSMSGateway

log = get_logger(__name__)


# Singleton instance
_sms_gateway: SMSGateway | None = None


def get_sms_gateway() -> SMSGateway:
    """Get the configured SMS gateway.

    Returns:
        SMS gateway instance based on config.
    """
    global _sms_gateway

    if _sms_gateway is not None:
        return _sms_gateway

    settings = get_settings()
    sms_config = settings.integrations.sms

    if not sms_config.enabled:
        log.info("SMS gateway disabled, using mock")
        _sms_gateway = MockSMSGateway()
        return _sms_gateway

    provider = sms_config.provider.lower()
    log.info("Initializing SMS gateway", provider=provider)

    if provider == "twilio":
        # Check for Twilio credentials
        twilio_config = settings.telephony.twilio

        if not twilio_config.account_sid or not twilio_config.auth_token:
            log.warning("Twilio credentials not configured, using mock SMS")
            _sms_gateway = MockSMSGateway()
        else:
            from phone_agent.integrations.sms.twilio import TwilioSMSGateway

            # Build status callback URL
            status_callback_url = None
            if twilio_config.webhook_url:
                status_callback_url = f"{twilio_config.webhook_url}/api/v1/webhooks/sms/twilio/status"

            _sms_gateway = TwilioSMSGateway(
                account_sid=twilio_config.account_sid,
                auth_token=twilio_config.auth_token,
                from_number=twilio_config.from_number or "",
                status_callback_url=status_callback_url,
                messaging_service_sid=getattr(twilio_config, "messaging_service_sid", None),
            )
            log.info(
                "Twilio SMS gateway initialized",
                from_number=twilio_config.from_number,
                status_callback=bool(status_callback_url),
            )

    elif provider == "sipgate":
        # Check for sipgate credentials
        sipgate_config = settings.telephony.sipgate

        if not sipgate_config.api_token or not sipgate_config.username:
            log.warning("sipgate credentials not configured, using mock SMS")
            _sms_gateway = MockSMSGateway()
        else:
            from phone_agent.integrations.sms.sipgate import SipgateSMSGateway

            _sms_gateway = SipgateSMSGateway(
                token_id=sipgate_config.username,
                token=sipgate_config.api_token,
            )
            log.info("sipgate SMS gateway initialized")

    elif provider == "mock":
        _sms_gateway = MockSMSGateway()
        log.info("Mock SMS gateway initialized")

    else:
        log.warning(f"Unknown SMS provider '{provider}', using mock")
        _sms_gateway = MockSMSGateway()

    return _sms_gateway


def reset_sms_gateway() -> None:
    """Reset the SMS gateway (for testing)."""
    global _sms_gateway
    _sms_gateway = None


async def send_appointment_confirmation(
    phone: str,
    patient_name: str,
    appointment_date: str,
    appointment_time: str,
    provider_name: str,
    practice_name: str = "Praxis",
) -> bool:
    """Send appointment confirmation SMS.

    Convenience function for sending appointment confirmations.

    Args:
        phone: Patient phone number
        patient_name: Patient name
        appointment_date: Date string (e.g., "15.01.2025")
        appointment_time: Time string (e.g., "10:30")
        provider_name: Doctor/provider name
        practice_name: Practice name

    Returns:
        True if SMS sent successfully
    """
    from phone_agent.integrations.sms.base import SMSMessage

    gateway = get_sms_gateway()

    message = SMSMessage(
        to=phone,
        body=(
            f"Terminbestätigung {practice_name}\n\n"
            f"Guten Tag {patient_name},\n"
            f"Ihr Termin am {appointment_date} um {appointment_time} Uhr "
            f"bei {provider_name} wurde bestätigt.\n\n"
            f"Bei Verhinderung bitte absagen.\n"
            f"Ihre {practice_name}"
        ),
        reference=f"confirmation_{appointment_date}_{appointment_time}",
    )

    result = await gateway.send(message)
    return result.success


async def send_appointment_reminder(
    phone: str,
    patient_name: str,
    appointment_date: str,
    appointment_time: str,
    provider_name: str,
    practice_name: str = "Praxis",
    hours_before: int = 24,
) -> bool:
    """Send appointment reminder SMS.

    Convenience function for sending appointment reminders.

    Args:
        phone: Patient phone number
        patient_name: Patient name
        appointment_date: Date string
        appointment_time: Time string
        provider_name: Doctor/provider name
        practice_name: Practice name
        hours_before: Hours before appointment

    Returns:
        True if SMS sent successfully
    """
    from phone_agent.integrations.sms.base import SMSMessage

    gateway = get_sms_gateway()

    if hours_before <= 24:
        time_text = "morgen"
    else:
        time_text = f"am {appointment_date}"

    message = SMSMessage(
        to=phone,
        body=(
            f"Terminerinnerung {practice_name}\n\n"
            f"Guten Tag {patient_name},\n"
            f"wir erinnern Sie an Ihren Termin {time_text} "
            f"um {appointment_time} Uhr bei {provider_name}.\n\n"
            f"Ihre {practice_name}"
        ),
        reference=f"reminder_{appointment_date}_{appointment_time}",
    )

    result = await gateway.send(message)
    return result.success


async def send_cancellation_notification(
    phone: str,
    patient_name: str,
    appointment_date: str,
    appointment_time: str,
    practice_name: str = "Praxis",
) -> bool:
    """Send appointment cancellation notification SMS.

    Args:
        phone: Patient phone number
        patient_name: Patient name
        appointment_date: Date string
        appointment_time: Time string
        practice_name: Practice name

    Returns:
        True if SMS sent successfully
    """
    from phone_agent.integrations.sms.base import SMSMessage

    gateway = get_sms_gateway()

    message = SMSMessage(
        to=phone,
        body=(
            f"Terminabsage {practice_name}\n\n"
            f"Guten Tag {patient_name},\n"
            f"Ihr Termin am {appointment_date} um {appointment_time} Uhr "
            f"wurde storniert.\n\n"
            f"Zur Neubuchung rufen Sie uns an.\n"
            f"Ihre {practice_name}"
        ),
        reference=f"cancellation_{appointment_date}_{appointment_time}",
    )

    result = await gateway.send(message)
    return result.success
