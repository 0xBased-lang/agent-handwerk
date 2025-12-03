"""SMS Webhook endpoints for delivery tracking.

Handles status callbacks from SMS providers (Twilio, sipgate)
to update message delivery status in the database.

Security:
- All webhooks validate signatures from providers
- Twilio uses X-Twilio-Signature header
- sipgate uses Basic Auth or API token
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field

from itf_shared import get_logger

from phone_agent.api.webhook_security import (
    WebhookSecurityManager,
    WebhookSecurityError,
)
from phone_agent.dependencies import get_webhook_security
from phone_agent.db.session import get_db_context
from phone_agent.db.repositories.sms import SMSMessageRepository
from phone_agent.integrations.sms.twilio import TwilioWebhookHandler

log = get_logger(__name__)

router = APIRouter(prefix="/sms", tags=["sms-webhooks"])


# ============================================================================
# Helper Functions
# ============================================================================


def get_security_manager() -> WebhookSecurityManager:
    """Get webhook security manager via DI."""
    return get_webhook_security()


async def validate_twilio_sms(request: Request) -> None:
    """Validate Twilio SMS webhook signature.

    Raises HTTPException 403 if validation fails.
    """
    try:
        security = get_security_manager()
        await security.validate_twilio(request)
    except WebhookSecurityError as e:
        log.warning(
            "Invalid Twilio SMS webhook signature",
            path=str(request.url.path),
            error=str(e),
        )
        raise HTTPException(status_code=403, detail="Invalid signature")


# ============================================================================
# Response Models
# ============================================================================


class SMSWebhookResponse(BaseModel):
    """Standard SMS webhook response."""

    success: bool
    message_id: str | None = None
    status: str | None = None
    action: str | None = None
    message: str | None = None


class SMSStatusUpdate(BaseModel):
    """SMS status update from provider."""

    provider_message_id: str
    status: str
    error_code: str | None = None
    error_message: str | None = None
    cost: float | None = None
    segments: int | None = None


# ============================================================================
# Twilio SMS Webhooks
# ============================================================================


@router.post("/twilio/status", response_model=SMSWebhookResponse)
async def handle_twilio_sms_status(request: Request) -> SMSWebhookResponse:
    """Handle Twilio SMS status callback webhook.

    Twilio calls this endpoint when message status changes.
    Updates the database with delivery status.

    Status progression:
    - queued: Message is queued for sending
    - sending: Message is being sent to carrier
    - sent: Message was sent to carrier
    - delivered: Message was delivered to recipient
    - failed: Message delivery failed
    - undelivered: Message was sent but not delivered

    Expected form parameters:
    - MessageSid: Unique message identifier
    - MessageStatus: Current status
    - To: Recipient number
    - From: Sender number
    - ErrorCode: Error code (if failed)
    - ErrorMessage: Error description (if failed)
    """
    # Validate signature
    await validate_twilio_sms(request)

    # Parse form data
    form_data = await request.form()
    data = {key: value for key, value in form_data.items()}

    # Parse webhook data
    parsed = TwilioWebhookHandler.parse_webhook(data)

    provider_message_id = parsed["provider_message_id"]
    status = parsed["status"]
    error_code = parsed.get("error_code")
    error_message = parsed.get("error_message")

    log.info(
        "Twilio SMS status webhook",
        message_sid=provider_message_id,
        status=status,
        twilio_status=parsed.get("twilio_status"),
        error_code=error_code,
    )

    # Update database
    try:
        async with get_db_context() as session:
            repo = SMSMessageRepository(session)

            # Find and update the message
            sms = await repo.update_status_by_provider_id(
                provider_message_id=provider_message_id,
                status=status,
                error_code=error_code,
                error_message=error_message,
                cost=float(parsed["price"]) if parsed.get("price") else None,
            )

            if sms is None:
                log.warning(
                    "SMS not found for status update",
                    provider_message_id=provider_message_id,
                )
                return SMSWebhookResponse(
                    success=False,
                    message_id=provider_message_id,
                    status=status,
                    action="not_found",
                    message="SMS message not found in database",
                )

            # Check if we should retry failed messages
            if status in ("failed", "undelivered"):
                should_retry = TwilioWebhookHandler.should_retry(error_code)

                if should_retry and sms.can_retry():
                    # Calculate exponential backoff delay
                    delay = 60 * (2 ** sms.retry_count)  # 60s, 120s, 240s, etc.
                    await repo.mark_for_retry(sms.id, delay_seconds=delay)

                    log.info(
                        "SMS marked for retry",
                        message_id=str(sms.id),
                        retry_count=sms.retry_count,
                        next_retry_delay=delay,
                    )

            await session.commit()

            return SMSWebhookResponse(
                success=True,
                message_id=str(sms.id),
                status=status,
                action="status_updated",
            )

    except Exception as e:
        log.error(
            "Failed to update SMS status",
            provider_message_id=provider_message_id,
            error=str(e),
        )
        return SMSWebhookResponse(
            success=False,
            message_id=provider_message_id,
            status=status,
            action="error",
            message=str(e),
        )


@router.post("/twilio/inbound", response_model=SMSWebhookResponse)
async def handle_twilio_inbound_sms(request: Request) -> Response:
    """Handle inbound SMS from Twilio.

    Called when someone sends an SMS to our Twilio number.
    Could be used for:
    - Appointment confirmation replies
    - Cancellation requests
    - General inquiries

    Returns TwiML response.
    """
    # Validate signature
    await validate_twilio_sms(request)

    form_data = await request.form()

    message_sid = form_data.get("MessageSid", "")
    from_number = form_data.get("From", "")
    to_number = form_data.get("To", "")
    body = form_data.get("Body", "")
    num_media = form_data.get("NumMedia", "0")

    log.info(
        "Inbound SMS received",
        message_sid=message_sid,
        from_number=from_number,
        to_number=to_number,
        body_preview=body[:50] if body else "",
        num_media=num_media,
    )

    # Process the inbound message
    response_message = await _process_inbound_sms(
        from_number=from_number,
        to_number=to_number,
        body=body,
        message_sid=message_sid,
    )

    # Return TwiML response
    twiml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Message>{response_message}</Message>
</Response>"""

    return Response(content=twiml, media_type="application/xml")


async def _process_inbound_sms(
    from_number: str,
    to_number: str,
    body: str,
    message_sid: str,
) -> str:
    """Process inbound SMS and determine response.

    Handles common patterns:
    - "JA" / "YES" / "OK" - Confirm appointment
    - "NEIN" / "NO" / "CANCEL" - Cancel appointment
    - "HILFE" / "HELP" - Show help message

    Args:
        from_number: Sender phone number
        to_number: Recipient phone number (our number)
        body: Message body
        message_sid: Twilio message SID

    Returns:
        Response message to send back
    """
    body_upper = body.strip().upper()

    # Confirmation keywords (German and English)
    confirmation_keywords = {"JA", "YES", "OK", "BESTÄTIGEN", "CONFIRM", "1"}
    if body_upper in confirmation_keywords:
        # TODO: Look up pending appointment for this number and confirm it
        log.info("Appointment confirmation via SMS", from_number=from_number)
        return "Vielen Dank! Ihr Termin wurde bestätigt. / Thank you! Your appointment has been confirmed."

    # Cancellation keywords
    cancellation_keywords = {"NEIN", "NO", "ABSAGEN", "CANCEL", "STORNIEREN", "2"}
    if body_upper in cancellation_keywords:
        # TODO: Look up pending appointment for this number and cancel it
        log.info("Appointment cancellation via SMS", from_number=from_number)
        return "Ihr Termin wurde storniert. Bitte rufen Sie uns an für einen neuen Termin. / Your appointment has been cancelled. Please call us for a new appointment."

    # Help keywords
    help_keywords = {"HILFE", "HELP", "INFO", "?"}
    if body_upper in help_keywords:
        return (
            "Antworten Sie mit:\n"
            "JA - Termin bestätigen\n"
            "NEIN - Termin absagen\n"
            "\n"
            "Reply with:\n"
            "YES - Confirm appointment\n"
            "NO - Cancel appointment"
        )

    # Default response for unknown messages
    return (
        "Vielen Dank für Ihre Nachricht. "
        "Für Terminänderungen rufen Sie uns bitte an. "
        "/ Thank you for your message. "
        "Please call us for appointment changes."
    )


# ============================================================================
# sipgate SMS Webhooks (Placeholder)
# ============================================================================


@router.post("/sipgate/status")
async def handle_sipgate_sms_status(request: Request) -> dict[str, Any]:
    """Handle sipgate SMS status callback webhook.

    Note: sipgate has limited status callback support compared to Twilio.
    This endpoint handles whatever status updates sipgate provides.
    """
    # Validate sipgate signature
    try:
        security = get_security_manager()
        await security.validate_sipgate(request)
    except WebhookSecurityError as e:
        log.warning("Invalid sipgate SMS webhook signature", error=str(e))
        raise HTTPException(status_code=403, detail="Invalid signature")

    data = await request.json()

    log.info(
        "sipgate SMS status webhook",
        data=data,
    )

    # sipgate doesn't have detailed status callbacks like Twilio
    # Log the data for debugging
    return {"status": "ok", "received": True}


# ============================================================================
# Internal Tracking Endpoints
# ============================================================================


@router.post("/track/{message_id}")
async def track_sms_status(message_id: str) -> SMSWebhookResponse:
    """Manually trigger status check for a message.

    Polls the provider API to get current status.
    Useful for debugging or when webhooks are delayed.

    Args:
        message_id: Internal SMS message UUID

    Returns:
        Current status information
    """
    from uuid import UUID
    from phone_agent.integrations.sms.factory import get_sms_gateway

    try:
        async with get_db_context() as session:
            repo = SMSMessageRepository(session)
            sms = await repo.get(UUID(message_id))

            if sms is None:
                return SMSWebhookResponse(
                    success=False,
                    message_id=message_id,
                    action="not_found",
                    message="SMS message not found",
                )

            if not sms.provider_message_id:
                return SMSWebhookResponse(
                    success=False,
                    message_id=message_id,
                    status=sms.status,
                    action="no_provider_id",
                    message="Message has no provider message ID",
                )

            # Get current status from provider
            gateway = get_sms_gateway()
            current_status = await gateway.get_status(sms.provider_message_id)

            # Update if status changed
            if current_status.value != sms.status:
                await repo.update_status(sms.id, current_status.value)
                await session.commit()

                log.info(
                    "SMS status updated via tracking",
                    message_id=message_id,
                    old_status=sms.status,
                    new_status=current_status.value,
                )

            return SMSWebhookResponse(
                success=True,
                message_id=message_id,
                status=current_status.value,
                action="status_checked",
            )

    except Exception as e:
        log.error("SMS tracking failed", message_id=message_id, error=str(e))
        return SMSWebhookResponse(
            success=False,
            message_id=message_id,
            action="error",
            message=str(e),
        )


@router.get("/stats/today")
async def get_sms_stats_today() -> dict[str, Any]:
    """Get SMS statistics for today.

    Returns aggregate counts by status, provider, and type.
    Useful for monitoring dashboards.
    """
    from datetime import date

    try:
        async with get_db_context() as session:
            repo = SMSMessageRepository(session)
            stats = await repo.get_daily_stats(date.today())
            return stats

    except Exception as e:
        log.error("Failed to get SMS stats", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/stats/{target_date}")
async def get_sms_stats_for_date(target_date: str) -> dict[str, Any]:
    """Get SMS statistics for a specific date.

    Args:
        target_date: Date in ISO format (YYYY-MM-DD)

    Returns:
        Aggregate counts for the specified date
    """
    from datetime import date

    try:
        parsed_date = date.fromisoformat(target_date)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail="Invalid date format. Use YYYY-MM-DD.",
        )

    try:
        async with get_db_context() as session:
            repo = SMSMessageRepository(session)
            stats = await repo.get_daily_stats(parsed_date)
            return stats

    except Exception as e:
        log.error("Failed to get SMS stats", date=target_date, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))
