"""Email Gateway Factory.

Creates the appropriate email gateway based on configuration.

Supported providers:
- smtp: Standard SMTP email
- sendgrid: SendGrid API with tracking
- mock: For development and testing
"""

from __future__ import annotations

from itf_shared import get_logger

from phone_agent.config import get_settings
from phone_agent.integrations.email.base import EmailGateway, MockEmailGateway

log = get_logger(__name__)


# Singleton instance
_email_gateway: EmailGateway | None = None


def get_email_gateway() -> EmailGateway:
    """Get the configured email gateway.

    Returns:
        Email gateway instance based on config.
    """
    global _email_gateway

    if _email_gateway is not None:
        return _email_gateway

    settings = get_settings()
    email_config = settings.integrations.email

    if not email_config.enabled:
        log.info("Email gateway disabled, using mock")
        _email_gateway = MockEmailGateway()
        return _email_gateway

    provider = email_config.provider.lower()
    log.info("Initializing email gateway", provider=provider)

    if provider == "smtp":
        smtp_config = email_config.smtp

        if not smtp_config.host:
            log.warning("SMTP host not configured, using mock email")
            _email_gateway = MockEmailGateway()
        else:
            from phone_agent.integrations.email.smtp import SMTPEmailGateway

            _email_gateway = SMTPEmailGateway(
                host=smtp_config.host,
                port=smtp_config.port,
                username=smtp_config.username or None,
                password=smtp_config.password or None,
                use_tls=smtp_config.use_tls,
                use_ssl=smtp_config.use_ssl,
                from_email=email_config.from_email or None,
                from_name=email_config.from_name or None,
            )
            log.info(
                "SMTP email gateway initialized",
                host=smtp_config.host,
                port=smtp_config.port,
                from_email=email_config.from_email,
            )

    elif provider == "sendgrid":
        sendgrid_config = email_config.sendgrid

        if not sendgrid_config.api_key:
            log.warning("SendGrid API key not configured, using mock email")
            _email_gateway = MockEmailGateway()
        else:
            from phone_agent.integrations.email.sendgrid import SendGridEmailGateway

            _email_gateway = SendGridEmailGateway(
                api_key=sendgrid_config.api_key,
                from_email=email_config.from_email or None,
                from_name=email_config.from_name or None,
                webhook_url=sendgrid_config.webhook_url or None,
            )
            log.info(
                "SendGrid email gateway initialized",
                from_email=email_config.from_email,
                webhook_enabled=bool(sendgrid_config.webhook_url),
            )

    elif provider == "mock":
        _email_gateway = MockEmailGateway()
        log.info("Mock email gateway initialized")

    else:
        log.warning(f"Unknown email provider '{provider}', using mock")
        _email_gateway = MockEmailGateway()

    return _email_gateway


def reset_email_gateway() -> None:
    """Reset the email gateway (for testing)."""
    global _email_gateway
    _email_gateway = None


# =============================================================================
# Convenience Functions for Sending Emails
# =============================================================================


async def send_appointment_confirmation(
    email: str,
    patient_name: str,
    appointment_date,
    appointment_time,
    provider_name: str,
    appointment_type: str,
    practice_name: str,
    practice_address: str = "",
    practice_phone: str = "",
    practice_email: str = "",
    notes: str = "",
) -> bool:
    """Send appointment confirmation email.

    Convenience function for sending appointment confirmations.

    Args:
        email: Patient email address
        patient_name: Patient name
        appointment_date: Appointment date
        appointment_time: Appointment time
        provider_name: Doctor/provider name
        appointment_type: Type of appointment
        practice_name: Practice name
        practice_address: Practice address
        practice_phone: Practice phone
        practice_email: Practice email
        notes: Additional notes

    Returns:
        True if email sent successfully
    """
    from phone_agent.integrations.email.templates import (
        TemplateContext,
        create_appointment_confirmation_email,
    )

    gateway = get_email_gateway()
    ctx = TemplateContext(
        practice_name=practice_name,
        practice_address=practice_address,
        practice_phone=practice_phone,
        practice_email=practice_email,
    )

    message = create_appointment_confirmation_email(
        to_email=email,
        patient_name=patient_name,
        appointment_date=appointment_date,
        appointment_time=appointment_time,
        provider_name=provider_name,
        appointment_type=appointment_type,
        ctx=ctx,
        notes=notes,
    )

    result = await gateway.send(message)
    return result.success


async def send_appointment_reminder(
    email: str,
    patient_name: str,
    appointment_date,
    appointment_time,
    provider_name: str,
    practice_name: str,
    practice_address: str = "",
    practice_phone: str = "",
    hours_before: int = 24,
) -> bool:
    """Send appointment reminder email.

    Args:
        email: Patient email address
        patient_name: Patient name
        appointment_date: Appointment date
        appointment_time: Appointment time
        provider_name: Doctor/provider name
        practice_name: Practice name
        practice_address: Practice address
        practice_phone: Practice phone
        hours_before: Hours before appointment

    Returns:
        True if email sent successfully
    """
    from phone_agent.integrations.email.templates import (
        TemplateContext,
        create_appointment_reminder_email,
    )

    gateway = get_email_gateway()
    ctx = TemplateContext(
        practice_name=practice_name,
        practice_address=practice_address,
        practice_phone=practice_phone,
    )

    message = create_appointment_reminder_email(
        to_email=email,
        patient_name=patient_name,
        appointment_date=appointment_date,
        appointment_time=appointment_time,
        provider_name=provider_name,
        ctx=ctx,
        hours_before=hours_before,
    )

    result = await gateway.send(message)
    return result.success


async def send_appointment_cancellation(
    email: str,
    patient_name: str,
    appointment_date,
    appointment_time,
    practice_name: str,
    practice_phone: str = "",
    practice_email: str = "",
    reason: str = "",
) -> bool:
    """Send appointment cancellation email.

    Args:
        email: Patient email address
        patient_name: Patient name
        appointment_date: Appointment date
        appointment_time: Appointment time
        practice_name: Practice name
        practice_phone: Practice phone
        practice_email: Practice email
        reason: Cancellation reason

    Returns:
        True if email sent successfully
    """
    from phone_agent.integrations.email.templates import (
        TemplateContext,
        create_appointment_cancellation_email,
    )

    gateway = get_email_gateway()
    ctx = TemplateContext(
        practice_name=practice_name,
        practice_phone=practice_phone,
        practice_email=practice_email,
    )

    message = create_appointment_cancellation_email(
        to_email=email,
        patient_name=patient_name,
        appointment_date=appointment_date,
        appointment_time=appointment_time,
        ctx=ctx,
        reason=reason,
    )

    result = await gateway.send(message)
    return result.success
