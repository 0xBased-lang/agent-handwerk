"""sipgate SMS Gateway Implementation.

sipgate is a German VoIP provider with SMS API capabilities.
Popular choice for German businesses due to:
- German data residency
- GDPR compliance
- Good pricing for German numbers
- Reliable delivery
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any

import httpx
from itf_shared import get_logger

from phone_agent.integrations.sms.base import (
    SMSGateway,
    SMSMessage,
    SMSResult,
    SMSStatus,
)

log = get_logger(__name__)


class SipgateSMSGateway(SMSGateway):
    """sipgate SMS gateway implementation.

    Uses the sipgate REST API to send SMS messages.
    Requires a sipgate team account with SMS capability.

    API Documentation: https://api.sipgate.com/v2/doc
    """

    API_BASE = "https://api.sipgate.com/v2"

    def __init__(
        self,
        token_id: str,
        token: str,
        sms_id: str = "s0",  # Default SMS extension
        timeout: float = 30.0,
    ):
        """Initialize sipgate SMS gateway.

        Args:
            token_id: sipgate API token ID
            token: sipgate API token
            sms_id: SMS extension ID (default: s0)
            timeout: HTTP request timeout
        """
        self.token_id = token_id
        self.token = token
        self.sms_id = sms_id
        self.timeout = timeout

        # Create HTTP client with basic auth
        auth = httpx.BasicAuth(token_id, token)
        self._client = httpx.AsyncClient(
            base_url=self.API_BASE,
            auth=auth,
            timeout=timeout,
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
        )

    async def send(self, message: SMSMessage) -> SMSResult:
        """Send SMS via sipgate API.

        Args:
            message: SMS message to send

        Returns:
            Result with success status
        """
        normalized_to = self.normalize_phone(message.to)

        payload = {
            "smsId": self.sms_id,
            "recipient": normalized_to,
            "message": message.body,
        }

        try:
            response = await self._client.post("/sessions/sms", json=payload)

            if response.status_code == 204:
                # Success - sipgate returns 204 No Content on success
                # Unfortunately sipgate doesn't return a message ID
                message_id = f"sipgate_{datetime.now().timestamp()}"

                log.info(
                    "SMS sent via sipgate",
                    to=normalized_to,
                    segments=self.calculate_segments(message.body),
                )

                return SMSResult(
                    success=True,
                    message_id=message_id,
                    status=SMSStatus.SENT,
                    provider="sipgate",
                    sent_at=datetime.now(),
                    segments=self.calculate_segments(message.body),
                )

            else:
                # Error response
                error_data = response.json() if response.content else {}
                error_message = error_data.get("message", f"HTTP {response.status_code}")

                log.error(
                    "sipgate SMS failed",
                    status_code=response.status_code,
                    error=error_message,
                    to=normalized_to,
                )

                return SMSResult(
                    success=False,
                    status=SMSStatus.FAILED,
                    provider="sipgate",
                    error_message=error_message,
                )

        except httpx.TimeoutException:
            log.error("sipgate SMS timeout", to=normalized_to)
            return SMSResult(
                success=False,
                status=SMSStatus.FAILED,
                provider="sipgate",
                error_message="Request timeout",
            )

        except httpx.HTTPError as e:
            log.error("sipgate SMS HTTP error", error=str(e), to=normalized_to)
            return SMSResult(
                success=False,
                status=SMSStatus.FAILED,
                provider="sipgate",
                error_message=str(e),
            )

        except Exception as e:
            log.error("sipgate SMS error", error=str(e), to=normalized_to)
            return SMSResult(
                success=False,
                status=SMSStatus.FAILED,
                provider="sipgate",
                error_message=str(e),
            )

    async def get_status(self, message_id: str) -> SMSStatus:
        """Get message status.

        Note: sipgate doesn't provide a status API for individual messages.
        Status tracking would require implementing webhooks.

        Args:
            message_id: Message ID

        Returns:
            UNKNOWN (sipgate doesn't support status queries)
        """
        # sipgate doesn't support status queries via API
        return SMSStatus.UNKNOWN

    async def get_account_info(self) -> dict[str, Any] | None:
        """Get sipgate account information.

        Useful for verifying credentials and checking balance.

        Returns:
            Account info dict or None on error
        """
        try:
            response = await self._client.get("/account")

            if response.status_code == 200:
                return response.json()
            else:
                log.error("Failed to get sipgate account info", status=response.status_code)
                return None

        except Exception as e:
            log.error("sipgate account info error", error=str(e))
            return None

    async def list_sms_extensions(self) -> list[dict[str, Any]]:
        """List available SMS extensions.

        Returns:
            List of SMS extension IDs and labels
        """
        try:
            response = await self._client.get("/sms")

            if response.status_code == 200:
                data = response.json()
                return data.get("items", [])
            else:
                log.error("Failed to list sipgate SMS extensions", status=response.status_code)
                return []

        except Exception as e:
            log.error("sipgate list SMS error", error=str(e))
            return []

    async def close(self) -> None:
        """Close the HTTP client."""
        await self._client.aclose()

    async def __aenter__(self) -> "SipgateSMSGateway":
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Async context manager exit."""
        await self.close()
