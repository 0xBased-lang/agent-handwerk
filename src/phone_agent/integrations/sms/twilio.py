"""Twilio SMS Gateway Implementation.

Twilio is a global cloud communications platform with excellent
SMS delivery status tracking via webhooks.

Features:
- Delivery status webhooks (queued, sent, delivered, failed, undelivered)
- Message segmentation and pricing
- International number support
- Excellent delivery rates
"""
from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any
from uuid import UUID

import httpx
from itf_shared import get_logger

from phone_agent.integrations.sms.base import (
    SMSGateway,
    SMSMessage,
    SMSResult,
    SMSStatus,
)

log = get_logger(__name__)


# Twilio status to our status mapping
TWILIO_STATUS_MAP: dict[str, SMSStatus] = {
    "queued": SMSStatus.PENDING,
    "sending": SMSStatus.PENDING,
    "sent": SMSStatus.SENT,
    "delivered": SMSStatus.DELIVERED,
    "failed": SMSStatus.FAILED,
    "undelivered": SMSStatus.FAILED,
    "canceled": SMSStatus.FAILED,
}


class TwilioSMSGateway(SMSGateway):
    """Twilio SMS gateway implementation.

    Uses the Twilio REST API to send SMS messages with delivery tracking.
    Requires a Twilio account with SMS capability.

    API Documentation: https://www.twilio.com/docs/sms/api

    Status Callback Flow:
    1. Message queued by Twilio
    2. Message sent to carrier
    3. Carrier delivers to device (or fails)
    4. Twilio receives delivery report
    5. Twilio calls our status webhook

    Attributes:
        account_sid: Twilio Account SID
        auth_token: Twilio Auth Token
        from_number: Default sender phone number
        status_callback_url: URL for delivery status webhooks
    """

    API_BASE = "https://api.twilio.com/2010-04-01"

    def __init__(
        self,
        account_sid: str,
        auth_token: str,
        from_number: str,
        status_callback_url: str | None = None,
        messaging_service_sid: str | None = None,
        timeout: float = 30.0,
    ):
        """Initialize Twilio SMS gateway.

        Args:
            account_sid: Twilio Account SID
            auth_token: Twilio Auth Token
            from_number: Default sender phone number (E.164 format)
            status_callback_url: URL for delivery status webhooks
            messaging_service_sid: Optional Messaging Service SID for advanced routing
            timeout: HTTP request timeout
        """
        self.account_sid = account_sid
        self.auth_token = auth_token
        self.from_number = from_number
        self.status_callback_url = status_callback_url
        self.messaging_service_sid = messaging_service_sid
        self.timeout = timeout

        # Create HTTP client with basic auth
        auth = httpx.BasicAuth(account_sid, auth_token)
        self._client = httpx.AsyncClient(
            base_url=f"{self.API_BASE}/Accounts/{account_sid}",
            auth=auth,
            timeout=timeout,
            headers={
                "Accept": "application/json",
            },
        )

    async def send(self, message: SMSMessage) -> SMSResult:
        """Send SMS via Twilio API.

        Args:
            message: SMS message to send

        Returns:
            Result with success status and Twilio message SID
        """
        normalized_to = self.normalize_phone(message.to)
        from_number = message.from_number or self.from_number

        # Build form data
        data = {
            "To": normalized_to,
            "Body": message.body,
        }

        # Use messaging service if configured, otherwise use From number
        if self.messaging_service_sid:
            data["MessagingServiceSid"] = self.messaging_service_sid
        else:
            data["From"] = from_number

        # Add status callback if configured
        if self.status_callback_url:
            data["StatusCallback"] = self.status_callback_url

        try:
            response = await self._client.post(
                "/Messages.json",
                data=data,
            )

            if response.status_code in (200, 201):
                result_data = response.json()
                message_sid = result_data.get("sid", "")
                status = result_data.get("status", "queued")
                price = result_data.get("price")
                num_segments = result_data.get("num_segments", 1)

                log.info(
                    "SMS sent via Twilio",
                    message_sid=message_sid,
                    to=normalized_to,
                    status=status,
                    segments=num_segments,
                )

                return SMSResult(
                    success=True,
                    message_id=message_sid,
                    status=TWILIO_STATUS_MAP.get(status, SMSStatus.PENDING),
                    provider="twilio",
                    sent_at=datetime.now(),
                    segments=int(num_segments) if num_segments else 1,
                    cost=abs(float(price)) if price else None,
                )

            else:
                # Error response - safely parse JSON
                try:
                    error_data = response.json() if response.content else {}
                except (ValueError, TypeError):
                    error_data = {}
                error_code = str(error_data.get("code", response.status_code))
                error_message = error_data.get("message", f"HTTP {response.status_code}")

                log.error(
                    "Twilio SMS failed",
                    status_code=response.status_code,
                    error_code=error_code,
                    error=error_message,
                    to=normalized_to,
                )

                return SMSResult(
                    success=False,
                    status=SMSStatus.FAILED,
                    provider="twilio",
                    error_message=f"[{error_code}] {error_message}",
                )

        except httpx.TimeoutException:
            log.error("Twilio SMS timeout", to=normalized_to)
            return SMSResult(
                success=False,
                status=SMSStatus.FAILED,
                provider="twilio",
                error_message="Request timeout",
            )

        except httpx.HTTPError as e:
            log.error("Twilio SMS HTTP error", error=str(e), to=normalized_to)
            return SMSResult(
                success=False,
                status=SMSStatus.FAILED,
                provider="twilio",
                error_message=str(e),
            )

        except Exception as e:
            log.error("Twilio SMS error", error=str(e), to=normalized_to)
            return SMSResult(
                success=False,
                status=SMSStatus.FAILED,
                provider="twilio",
                error_message=str(e),
            )

    async def send_bulk(self, messages: list[SMSMessage]) -> list[SMSResult]:
        """Send multiple SMS messages.

        Uses asyncio.gather for parallel sending with concurrency limit.

        Args:
            messages: List of messages to send

        Returns:
            List of results for each message
        """
        # Limit concurrency to avoid rate limiting
        semaphore = asyncio.Semaphore(10)

        async def send_with_limit(msg: SMSMessage) -> SMSResult:
            async with semaphore:
                return await self.send(msg)

        results = await asyncio.gather(
            *[send_with_limit(msg) for msg in messages],
            return_exceptions=True,
        )

        # Handle any exceptions
        final_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                log.error(
                    "Bulk SMS send failed",
                    index=i,
                    error=str(result),
                )
                final_results.append(SMSResult(
                    success=False,
                    status=SMSStatus.FAILED,
                    provider="twilio",
                    error_message=str(result),
                ))
            else:
                final_results.append(result)

        return final_results

    async def get_status(self, message_id: str) -> SMSStatus:
        """Get message status from Twilio.

        Args:
            message_id: Twilio Message SID

        Returns:
            Current delivery status
        """
        try:
            response = await self._client.get(f"/Messages/{message_id}.json")

            if response.status_code == 200:
                data = response.json()
                status = data.get("status", "unknown")
                return TWILIO_STATUS_MAP.get(status, SMSStatus.UNKNOWN)

            log.warning(
                "Failed to get Twilio message status",
                message_id=message_id,
                status_code=response.status_code,
            )
            return SMSStatus.UNKNOWN

        except Exception as e:
            log.error(
                "Twilio status check error",
                message_id=message_id,
                error=str(e),
            )
            return SMSStatus.UNKNOWN

    async def get_message(self, message_id: str) -> dict[str, Any] | None:
        """Get full message details from Twilio.

        Args:
            message_id: Twilio Message SID

        Returns:
            Message details dict or None on error
        """
        try:
            response = await self._client.get(f"/Messages/{message_id}.json")

            if response.status_code == 200:
                return response.json()

            log.warning(
                "Failed to get Twilio message",
                message_id=message_id,
                status_code=response.status_code,
            )
            return None

        except Exception as e:
            log.error(
                "Twilio get message error",
                message_id=message_id,
                error=str(e),
            )
            return None

    async def get_account_balance(self) -> dict[str, Any] | None:
        """Get Twilio account balance.

        Returns:
            Balance info dict or None on error
        """
        try:
            response = await self._client.get("/Balance.json")

            if response.status_code == 200:
                return response.json()

            log.warning(
                "Failed to get Twilio balance",
                status_code=response.status_code,
            )
            return None

        except Exception as e:
            log.error("Twilio balance check error", error=str(e))
            return None

    async def close(self) -> None:
        """Close the HTTP client."""
        await self._client.aclose()

    async def __aenter__(self) -> "TwilioSMSGateway":
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Async context manager exit."""
        await self.close()


class TwilioWebhookHandler:
    """Handler for Twilio status callback webhooks.

    Twilio sends status updates to our webhook URL as the message
    progresses through the delivery pipeline.

    Status progression:
    queued -> sending -> sent -> delivered
                     -> failed
                     -> undelivered

    Webhook parameters:
    - MessageSid: Unique message identifier
    - MessageStatus: Current status
    - To: Recipient number
    - From: Sender number
    - ErrorCode: Error code if failed
    - ErrorMessage: Error description if failed
    """

    # Error codes that should trigger retry
    RETRYABLE_ERROR_CODES = {
        "30001",  # Queue overflow
        "30002",  # Account suspended (temporary)
        "30003",  # Unreachable destination
        "30005",  # Unknown destination
        "30006",  # Landline or unreachable carrier
        "30007",  # Carrier violation
        "30008",  # Unknown error
        "30009",  # Missing segment
        "30010",  # Message price exceeds max
    }

    # Error codes that should not retry
    NON_RETRYABLE_ERROR_CODES = {
        "21211",  # Invalid phone number
        "21612",  # Number not provisioned
        "21614",  # Invalid To number
        "30004",  # Message blocked
        "30011",  # Invalid message body
    }

    @staticmethod
    def parse_webhook(data: dict[str, Any]) -> dict[str, Any]:
        """Parse Twilio webhook data into normalized format.

        Args:
            data: Raw webhook form data

        Returns:
            Normalized webhook data
        """
        message_sid = data.get("MessageSid", "")
        message_status = data.get("MessageStatus", "unknown")
        error_code = data.get("ErrorCode")
        error_message = data.get("ErrorMessage")

        # Map Twilio status to our status
        status = TWILIO_STATUS_MAP.get(message_status, SMSStatus.UNKNOWN)

        return {
            "provider_message_id": message_sid,
            "status": status.value,
            "twilio_status": message_status,
            "to_number": data.get("To", ""),
            "from_number": data.get("From", ""),
            "error_code": error_code,
            "error_message": error_message,
            "api_version": data.get("ApiVersion", ""),
            "account_sid": data.get("AccountSid", ""),
            "sms_sid": data.get("SmsSid", ""),
            "sms_status": data.get("SmsStatus", ""),
            "num_segments": data.get("NumSegments"),
            "price": data.get("Price"),
            "price_unit": data.get("PriceUnit"),
        }

    @staticmethod
    def should_retry(error_code: str | None) -> bool:
        """Check if an error should trigger a retry.

        Args:
            error_code: Twilio error code

        Returns:
            True if message should be retried
        """
        if error_code is None:
            return False

        return error_code in TwilioWebhookHandler.RETRYABLE_ERROR_CODES

    @staticmethod
    def get_error_category(error_code: str | None) -> str:
        """Categorize error for reporting.

        Args:
            error_code: Twilio error code

        Returns:
            Error category string
        """
        if error_code is None:
            return "unknown"

        code = int(error_code) if error_code.isdigit() else 0

        if code >= 21000 and code < 22000:
            return "invalid_request"
        elif code >= 30000 and code < 31000:
            return "delivery_failure"
        elif code >= 32000 and code < 33000:
            return "channel_error"
        else:
            return "other"
