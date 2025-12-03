"""Email Webhook API Endpoints.

Handles inbound webhook events from email providers (SendGrid).
Processes delivery status updates, opens, clicks, bounces, and spam reports.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
from datetime import datetime, date
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request, Header, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select, func

from phone_agent.config import get_settings
from phone_agent.db.session import get_db_context


logger = logging.getLogger(__name__)
router = APIRouter(prefix="/webhooks/email", tags=["email-webhooks"])


class SendGridEvent(BaseModel):
    """SendGrid webhook event payload."""

    email: str
    event: str
    timestamp: int
    sg_message_id: Optional[str] = None
    sg_event_id: Optional[str] = None
    reason: Optional[str] = None
    status: Optional[str] = None
    url: Optional[str] = None  # For click events
    ip: Optional[str] = None
    useragent: Optional[str] = None
    # Custom args we pass in send
    message_id: Optional[str] = None
    appointment_id: Optional[str] = None


class EmailStatsResponse(BaseModel):
    """Email statistics response."""

    date: str
    total_sent: int = 0
    delivered: int = 0
    opened: int = 0
    clicked: int = 0
    bounced: int = 0
    spam_reports: int = 0
    delivery_rate: float = 0.0
    open_rate: float = 0.0
    click_rate: float = 0.0


def verify_sendgrid_signature(
    payload: bytes,
    signature: str,
    timestamp: str,
    public_key: str,
) -> bool:
    """Verify SendGrid webhook signature.

    SendGrid uses ECDSA signatures for webhook verification.
    For simplicity, this implementation validates timestamp freshness.
    """
    try:
        # Check timestamp is recent (within 5 minutes)
        ts = int(timestamp)
        now = int(datetime.now().timestamp())
        if abs(now - ts) > 300:
            logger.warning("SendGrid webhook timestamp too old")
            return False
        return True
    except (ValueError, TypeError):
        return False


@router.post("/sendgrid/events")
async def handle_sendgrid_events(
    request: Request,
    x_twilio_email_event_webhook_signature: Optional[str] = Header(None),
    x_twilio_email_event_webhook_timestamp: Optional[str] = Header(None),
) -> dict:
    """Handle SendGrid webhook events.

    SendGrid sends events for:
    - processed: Email accepted by SendGrid
    - dropped: Email dropped (invalid, bounce list, etc.)
    - delivered: Email delivered to recipient
    - deferred: Email temporarily deferred
    - bounce: Hard bounce
    - open: Email opened
    - click: Link clicked
    - spamreport: Marked as spam
    - unsubscribe: User unsubscribed
    """
    settings = get_settings()

    try:
        body = await request.body()
        events = await request.json()

        if not isinstance(events, list):
            events = [events]

        processed = 0
        errors = 0

        for event_data in events:
            try:
                event = SendGridEvent(**event_data)
                await _process_sendgrid_event(event)
                processed += 1
            except Exception as e:
                logger.error(f"Error processing SendGrid event: {e}")
                errors += 1

        return {
            "status": "ok",
            "processed": processed,
            "errors": errors,
        }

    except Exception as e:
        logger.exception(f"Error handling SendGrid webhook: {e}")
        raise HTTPException(status_code=500, detail="Webhook processing error")


async def _process_sendgrid_event(event: SendGridEvent) -> None:
    """Process a single SendGrid event."""
    from phone_agent.db.models.email import EmailMessageModel

    logger.info(f"Processing SendGrid event: {event.event} for {event.email}")

    # Try to find the email message
    message_id = event.message_id or event.sg_message_id
    if not message_id:
        logger.warning("No message ID in SendGrid event")
        return

    async with get_db_context() as session:
        # Try to find by our message ID first
        email_msg = None
        if event.message_id:
            try:
                msg_uuid = UUID(event.message_id)
                result = await session.execute(
                    select(EmailMessageModel).where(EmailMessageModel.id == msg_uuid)
                )
                email_msg = result.scalar_one_or_none()
            except ValueError:
                pass

        # Fall back to provider message ID
        if not email_msg and event.sg_message_id:
            result = await session.execute(
                select(EmailMessageModel).where(
                    EmailMessageModel.provider_message_id == event.sg_message_id
                )
            )
            email_msg = result.scalar_one_or_none()

        if not email_msg:
            logger.warning(f"Email message not found for ID: {message_id}")
            return

        # Update based on event type
        event_time = datetime.fromtimestamp(event.timestamp)

        if event.event == "delivered":
            email_msg.mark_delivered(delivered_at=event_time)
            logger.info(f"Email {email_msg.id} marked as delivered")

        elif event.event == "open":
            email_msg.mark_opened(opened_at=event_time)
            logger.info(f"Email {email_msg.id} marked as opened")

        elif event.event == "click":
            email_msg.mark_clicked(url=event.url, clicked_at=event_time)
            logger.info(f"Email {email_msg.id} - link clicked: {event.url}")

        elif event.event == "bounce":
            email_msg.mark_bounced(
                bounce_type="hard",
                bounce_reason=event.reason or "Hard bounce",
            )
            logger.warning(f"Email {email_msg.id} bounced: {event.reason}")

        elif event.event == "dropped":
            email_msg.mark_failed(
                error_message=f"Dropped: {event.reason}",
                error_code=event.status,
            )
            logger.warning(f"Email {email_msg.id} dropped: {event.reason}")

        elif event.event == "spamreport":
            email_msg.status = "spam"
            email_msg.error_message = "Marked as spam by recipient"
            logger.warning(f"Email {email_msg.id} marked as spam")

        elif event.event == "deferred":
            # Don't change status, just log
            logger.info(f"Email {email_msg.id} deferred: {event.reason}")

        elif event.event == "processed":
            # Email accepted by SendGrid
            if email_msg.status == "pending":
                email_msg.status = "sent"
                email_msg.sent_at = event_time

        await session.commit()


@router.get("/stats/today", response_model=EmailStatsResponse)
async def get_today_email_stats() -> EmailStatsResponse:
    """Get today's email delivery statistics."""
    from phone_agent.db.models.email import EmailMessageModel

    today = date.today()

    async with get_db_context() as session:
        # Total sent today
        result = await session.execute(
            select(func.count()).select_from(EmailMessageModel).where(
                func.date(EmailMessageModel.created_at) == today
            )
        )
        total_sent = result.scalar() or 0

        # Delivered
        result = await session.execute(
            select(func.count()).select_from(EmailMessageModel).where(
                func.date(EmailMessageModel.created_at) == today,
                EmailMessageModel.status.in_(["delivered", "opened", "clicked"])
            )
        )
        delivered = result.scalar() or 0

        # Opened
        result = await session.execute(
            select(func.count()).select_from(EmailMessageModel).where(
                func.date(EmailMessageModel.created_at) == today,
                EmailMessageModel.status.in_(["opened", "clicked"])
            )
        )
        opened = result.scalar() or 0

        # Clicked
        result = await session.execute(
            select(func.count()).select_from(EmailMessageModel).where(
                func.date(EmailMessageModel.created_at) == today,
                EmailMessageModel.status == "clicked"
            )
        )
        clicked = result.scalar() or 0

        # Bounced
        result = await session.execute(
            select(func.count()).select_from(EmailMessageModel).where(
                func.date(EmailMessageModel.created_at) == today,
                EmailMessageModel.status == "bounced"
            )
        )
        bounced = result.scalar() or 0

        # Spam reports
        result = await session.execute(
            select(func.count()).select_from(EmailMessageModel).where(
                func.date(EmailMessageModel.created_at) == today,
                EmailMessageModel.status == "spam"
            )
        )
        spam_reports = result.scalar() or 0

        return EmailStatsResponse(
            date=today.isoformat(),
            total_sent=total_sent,
            delivered=delivered,
            opened=opened,
            clicked=clicked,
            bounced=bounced,
            spam_reports=spam_reports,
            delivery_rate=delivered / total_sent if total_sent > 0 else 0.0,
            open_rate=opened / delivered if delivered > 0 else 0.0,
            click_rate=clicked / opened if opened > 0 else 0.0,
        )


@router.get("/stats/range")
async def get_email_stats_range(
    start_date: str,
    end_date: str,
) -> dict:
    """Get email statistics for a date range."""
    from phone_agent.db.models.email import EmailMessageModel

    try:
        start = datetime.fromisoformat(start_date).date()
        end = datetime.fromisoformat(end_date).date()
    except ValueError:
        raise HTTPException(400, "Invalid date format. Use YYYY-MM-DD")

    async with get_db_context() as session:
        # Total
        result = await session.execute(
            select(func.count()).select_from(EmailMessageModel).where(
                func.date(EmailMessageModel.created_at) >= start,
                func.date(EmailMessageModel.created_at) <= end,
            )
        )
        total = result.scalar() or 0

        # Delivered
        result = await session.execute(
            select(func.count()).select_from(EmailMessageModel).where(
                func.date(EmailMessageModel.created_at) >= start,
                func.date(EmailMessageModel.created_at) <= end,
                EmailMessageModel.status.in_(["delivered", "opened", "clicked"])
            )
        )
        delivered = result.scalar() or 0

        # Opened
        result = await session.execute(
            select(func.count()).select_from(EmailMessageModel).where(
                func.date(EmailMessageModel.created_at) >= start,
                func.date(EmailMessageModel.created_at) <= end,
                EmailMessageModel.status.in_(["opened", "clicked"])
            )
        )
        opened = result.scalar() or 0

        # Clicked
        result = await session.execute(
            select(func.count()).select_from(EmailMessageModel).where(
                func.date(EmailMessageModel.created_at) >= start,
                func.date(EmailMessageModel.created_at) <= end,
                EmailMessageModel.status == "clicked"
            )
        )
        clicked = result.scalar() or 0

        # Bounced
        result = await session.execute(
            select(func.count()).select_from(EmailMessageModel).where(
                func.date(EmailMessageModel.created_at) >= start,
                func.date(EmailMessageModel.created_at) <= end,
                EmailMessageModel.status == "bounced"
            )
        )
        bounced = result.scalar() or 0

        # Failed
        result = await session.execute(
            select(func.count()).select_from(EmailMessageModel).where(
                func.date(EmailMessageModel.created_at) >= start,
                func.date(EmailMessageModel.created_at) <= end,
                EmailMessageModel.status == "failed"
            )
        )
        failed = result.scalar() or 0

        # Group by date - simplified approach
        result = await session.execute(
            select(
                func.date(EmailMessageModel.created_at).label("date"),
                func.count().label("total"),
            ).where(
                func.date(EmailMessageModel.created_at) >= start,
                func.date(EmailMessageModel.created_at) <= end,
            ).group_by(
                func.date(EmailMessageModel.created_at)
            )
        )
        daily_stats = result.all()

        return {
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
            "summary": {
                "total": total,
                "delivered": delivered,
                "opened": opened,
                "clicked": clicked,
                "bounced": bounced,
                "failed": failed,
                "delivery_rate": delivered / total if total > 0 else 0.0,
                "open_rate": opened / delivered if delivered > 0 else 0.0,
            },
            "daily": [
                {"date": str(row.date), "total": row.total}
                for row in daily_stats
            ],
        }


@router.post("/track/{message_id}/status")
async def track_email_status(message_id: UUID) -> dict:
    """Manually check and update email delivery status.

    For providers that support delivery status API queries.
    """
    from phone_agent.db.models.email import EmailMessageModel

    async with get_db_context() as session:
        result = await session.execute(
            select(EmailMessageModel).where(EmailMessageModel.id == message_id)
        )
        email_msg = result.scalar_one_or_none()

        if not email_msg:
            raise HTTPException(404, "Email message not found")

        return {
            "id": str(email_msg.id),
            "status": email_msg.status,
            "sent_at": email_msg.sent_at.isoformat() if email_msg.sent_at else None,
            "delivered_at": email_msg.delivered_at.isoformat() if email_msg.delivered_at else None,
            "opened_at": email_msg.opened_at.isoformat() if email_msg.opened_at else None,
            "clicked_at": email_msg.clicked_at.isoformat() if email_msg.clicked_at else None,
            "error_message": email_msg.error_message,
            "retry_count": email_msg.retry_count,
        }


@router.get("/message/{message_id}")
async def get_email_message(message_id: UUID) -> dict:
    """Get email message details."""
    from phone_agent.db.models.email import EmailMessageModel

    async with get_db_context() as session:
        result = await session.execute(
            select(EmailMessageModel).where(EmailMessageModel.id == message_id)
        )
        email_msg = result.scalar_one_or_none()

        if not email_msg:
            raise HTTPException(404, "Email message not found")

        return {
            "id": str(email_msg.id),
            "to_email": email_msg.to_email,
            "subject": email_msg.subject,
            "template_type": email_msg.template_type,
            "status": email_msg.status,
            "provider": email_msg.provider,
            "created_at": email_msg.created_at.isoformat(),
            "sent_at": email_msg.sent_at.isoformat() if email_msg.sent_at else None,
            "delivered_at": email_msg.delivered_at.isoformat() if email_msg.delivered_at else None,
            "opened_at": email_msg.opened_at.isoformat() if email_msg.opened_at else None,
            "clicked_at": email_msg.clicked_at.isoformat() if email_msg.clicked_at else None,
            "open_count": email_msg.open_count,
            "click_count": email_msg.click_count,
            "error_message": email_msg.error_message,
            "retry_count": email_msg.retry_count,
            "appointment_id": str(email_msg.appointment_id) if email_msg.appointment_id else None,
            "contact_id": str(email_msg.contact_id) if email_msg.contact_id else None,
        }
