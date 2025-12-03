"""SendGrid Email Gateway Implementation.

SendGrid is a cloud-based email delivery service with:
- High deliverability
- Email tracking (opens, clicks, bounces)
- Template support
- Webhook events for status updates
"""

from __future__ import annotations

import asyncio
import base64
from datetime import datetime
from typing import Any

import httpx
from itf_shared import get_logger

from phone_agent.integrations.email.base import (
    EmailAttachment,
    EmailGateway,
    EmailMessage,
    EmailPriority,
    EmailResult,
    EmailStatus,
)

log = get_logger(__name__)


# SendGrid event types to our status mapping
SENDGRID_EVENT_MAP: dict[str, EmailStatus] = {
    "processed": EmailStatus.QUEUED,
    "dropped": EmailStatus.FAILED,
    "deferred": EmailStatus.PENDING,
    "delivered": EmailStatus.DELIVERED,
    "bounce": EmailStatus.BOUNCED,
    "open": EmailStatus.OPENED,
    "click": EmailStatus.CLICKED,
    "spamreport": EmailStatus.SPAM,
    "unsubscribe": EmailStatus.UNSUBSCRIBED,
}


class SendGridEmailGateway(EmailGateway):
    """SendGrid email gateway implementation.

    Uses SendGrid Web API v3 for sending emails.

    Features:
    - High-volume sending
    - Email tracking and analytics
    - Template support
    - Webhook events

    API Documentation: https://docs.sendgrid.com/api-reference/mail-send

    Attributes:
        api_key: SendGrid API key
        from_email: Default sender email
        from_name: Default sender display name
        webhook_url: URL for event webhooks
    """

    API_BASE = "https://api.sendgrid.com/v3"

    def __init__(
        self,
        api_key: str,
        from_email: str | None = None,
        from_name: str | None = None,
        webhook_url: str | None = None,
        timeout: float = 30.0,
    ):
        """Initialize SendGrid email gateway.

        Args:
            api_key: SendGrid API key
            from_email: Default sender email
            from_name: Default sender display name
            webhook_url: URL for event webhooks
            timeout: HTTP request timeout
        """
        self.api_key = api_key
        self.from_email = from_email
        self.from_name = from_name
        self.webhook_url = webhook_url
        self.timeout = timeout

        # Create HTTP client
        self._client = httpx.AsyncClient(
            base_url=self.API_BASE,
            timeout=timeout,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
        )

    async def send(self, message: EmailMessage) -> EmailResult:
        """Send email via SendGrid API.

        Args:
            message: Email message to send

        Returns:
            Result with success status
        """
        # Validate message
        errors = self.validate_message(message)
        if errors:
            return EmailResult(
                success=False,
                status=EmailStatus.FAILED,
                provider="sendgrid",
                error_message="; ".join(errors),
            )

        # Determine sender
        from_email = message.from_email or self.from_email
        from_name = message.from_name or self.from_name

        if not from_email:
            return EmailResult(
                success=False,
                status=EmailStatus.FAILED,
                provider="sendgrid",
                error_message="No sender email configured",
            )

        try:
            # Build SendGrid payload
            payload = self._build_payload(message, from_email, from_name)

            # Send via API
            response = await self._client.post("/mail/send", json=payload)

            if response.status_code in (200, 202):
                # Success - extract message ID from headers
                message_id = response.headers.get("X-Message-Id", "")

                log.info(
                    "Email sent via SendGrid",
                    message_id=message_id,
                    to=message.to,
                    subject=message.subject,
                )

                return EmailResult(
                    success=True,
                    message_id=message_id,
                    status=EmailStatus.QUEUED,
                    provider="sendgrid",
                    sent_at=datetime.now(),
                    recipients_accepted=len(message.recipients),
                )

            else:
                # Error response - safely parse JSON
                try:
                    error_data = response.json() if response.content else {}
                except (ValueError, TypeError):
                    error_data = {}
                errors_list = error_data.get("errors", [])
                error_message = "; ".join(
                    e.get("message", "Unknown error") for e in errors_list
                ) if errors_list else f"HTTP {response.status_code}"

                log.error(
                    "SendGrid email failed",
                    status_code=response.status_code,
                    errors=errors_list,
                    to=message.to,
                )

                return EmailResult(
                    success=False,
                    status=EmailStatus.FAILED,
                    provider="sendgrid",
                    error_message=error_message,
                    error_code=str(response.status_code),
                )

        except httpx.TimeoutException:
            log.error("SendGrid timeout", to=message.to)
            return EmailResult(
                success=False,
                status=EmailStatus.FAILED,
                provider="sendgrid",
                error_message="Request timeout",
                error_code="TIMEOUT",
            )

        except httpx.HTTPError as e:
            log.error("SendGrid HTTP error", error=str(e), to=message.to)
            return EmailResult(
                success=False,
                status=EmailStatus.FAILED,
                provider="sendgrid",
                error_message=str(e),
            )

        except Exception as e:
            log.error("SendGrid unexpected error", error=str(e), to=message.to)
            return EmailResult(
                success=False,
                status=EmailStatus.FAILED,
                provider="sendgrid",
                error_message=str(e),
            )

    async def send_bulk(self, messages: list[EmailMessage]) -> list[EmailResult]:
        """Send multiple emails with rate limiting.

        Args:
            messages: List of messages to send

        Returns:
            List of results for each message
        """
        # SendGrid rate limit: 600 requests/minute for v3 API
        semaphore = asyncio.Semaphore(10)

        async def send_with_limit(msg: EmailMessage) -> EmailResult:
            async with semaphore:
                result = await self.send(msg)
                # Small delay to avoid rate limiting
                await asyncio.sleep(0.1)
                return result

        results = await asyncio.gather(
            *[send_with_limit(msg) for msg in messages],
            return_exceptions=True,
        )

        # Handle any exceptions
        final_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                log.error("Bulk email send failed", index=i, error=str(result))
                final_results.append(
                    EmailResult(
                        success=False,
                        status=EmailStatus.FAILED,
                        provider="sendgrid",
                        error_message=str(result),
                    )
                )
            else:
                final_results.append(result)

        return final_results

    def _build_payload(
        self,
        message: EmailMessage,
        from_email: str,
        from_name: str | None,
    ) -> dict[str, Any]:
        """Build SendGrid API payload.

        Args:
            message: Email message
            from_email: Sender email
            from_name: Sender display name

        Returns:
            SendGrid mail/send payload
        """
        # Build personalizations (recipients)
        personalizations = {
            "to": [{"email": email} for email in message.to],
        }

        if message.cc:
            personalizations["cc"] = [{"email": email} for email in message.cc]

        if message.bcc:
            personalizations["bcc"] = [{"email": email} for email in message.bcc]

        # Build base payload
        payload: dict[str, Any] = {
            "personalizations": [personalizations],
            "from": {"email": from_email},
            "subject": message.subject,
        }

        # Add sender name
        if from_name:
            payload["from"]["name"] = from_name

        # Add reply-to
        if message.reply_to:
            payload["reply_to"] = {"email": message.reply_to}

        # Add content
        content = []
        if message.body_text:
            content.append({"type": "text/plain", "value": message.body_text})
        if message.body_html:
            content.append({"type": "text/html", "value": message.body_html})

        payload["content"] = content

        # Add attachments
        if message.attachments:
            attachments = []
            for att in message.attachments:
                att_data = {
                    "content": base64.b64encode(att.content).decode("utf-8"),
                    "filename": att.filename,
                    "type": att.content_type,
                    "disposition": "inline" if att.content_id else "attachment",
                }
                if att.content_id:
                    att_data["content_id"] = att.content_id

                attachments.append(att_data)

            payload["attachments"] = attachments

        # Add categories/tags
        if message.tags:
            payload["categories"] = message.tags[:10]  # SendGrid max 10 categories

        # Add tracking settings
        payload["tracking_settings"] = {
            "click_tracking": {"enable": True},
            "open_tracking": {"enable": True},
        }

        # Add custom reference
        if message.reference:
            payload["custom_args"] = {"reference": message.reference}

        # Add scheduled send time
        if message.scheduled_at:
            # SendGrid accepts Unix timestamp
            payload["send_at"] = int(message.scheduled_at.timestamp())

        # Add priority headers
        if message.priority == EmailPriority.HIGH:
            payload["headers"] = {
                "X-Priority": "1",
                "Importance": "high",
            }
        elif message.priority == EmailPriority.LOW:
            payload["headers"] = {
                "X-Priority": "5",
                "Importance": "low",
            }

        # Add custom headers
        if message.headers:
            if "headers" not in payload:
                payload["headers"] = {}
            payload["headers"].update(message.headers)

        return payload

    async def get_message_stats(self, message_id: str) -> dict[str, Any] | None:
        """Get message statistics from SendGrid.

        Note: Requires additional API access.

        Args:
            message_id: SendGrid message ID

        Returns:
            Message statistics or None
        """
        try:
            response = await self._client.get(f"/messages/{message_id}")

            if response.status_code == 200:
                return response.json()

            log.warning(
                "Failed to get SendGrid message stats",
                message_id=message_id,
                status_code=response.status_code,
            )
            return None

        except Exception as e:
            log.error("SendGrid stats error", message_id=message_id, error=str(e))
            return None

    async def close(self) -> None:
        """Close the HTTP client."""
        await self._client.aclose()

    async def __aenter__(self) -> "SendGridEmailGateway":
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Async context manager exit."""
        await self.close()


class SendGridWebhookHandler:
    """Handler for SendGrid event webhooks.

    SendGrid sends event notifications for:
    - processed: Message accepted for delivery
    - dropped: Message dropped (spam, invalid, etc.)
    - deferred: Delivery temporarily deferred
    - delivered: Successfully delivered
    - bounce: Hard or soft bounce
    - open: Recipient opened email
    - click: Recipient clicked link
    - spamreport: Marked as spam
    - unsubscribe: Recipient unsubscribed

    Webhook documentation: https://docs.sendgrid.com/for-developers/tracking-events
    """

    @staticmethod
    def parse_webhook(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Parse SendGrid webhook events.

        Args:
            events: List of event objects from webhook

        Returns:
            List of normalized event data
        """
        parsed_events = []

        for event in events:
            event_type = event.get("event", "")
            status = SENDGRID_EVENT_MAP.get(event_type, EmailStatus.UNKNOWN)

            parsed = {
                "provider_message_id": event.get("sg_message_id", ""),
                "event_type": event_type,
                "status": status.value,
                "email": event.get("email", ""),
                "timestamp": event.get("timestamp"),
                "sg_event_id": event.get("sg_event_id", ""),
                "category": event.get("category", []),
                "reference": event.get("reference"),  # From custom_args
            }

            # Add event-specific data
            if event_type == "bounce":
                parsed["bounce_type"] = event.get("type", "")
                parsed["bounce_reason"] = event.get("reason", "")

            elif event_type == "click":
                parsed["url"] = event.get("url", "")

            elif event_type == "dropped":
                parsed["drop_reason"] = event.get("reason", "")

            parsed_events.append(parsed)

        return parsed_events

    @staticmethod
    def should_retry(event_type: str, bounce_type: str | None = None) -> bool:
        """Check if email should be retried based on event.

        Args:
            event_type: SendGrid event type
            bounce_type: Bounce classification (for bounce events)

        Returns:
            True if email should be retried
        """
        # Deferred = temporary issue, can retry
        if event_type == "deferred":
            return True

        # Soft bounces can be retried
        if event_type == "bounce" and bounce_type == "soft":
            return True

        return False

    @staticmethod
    def get_event_severity(event_type: str) -> str:
        """Get severity level for event type.

        Args:
            event_type: SendGrid event type

        Returns:
            Severity: info, warning, or error
        """
        if event_type in ("processed", "delivered", "open", "click"):
            return "info"
        elif event_type in ("deferred",):
            return "warning"
        else:
            return "error"
