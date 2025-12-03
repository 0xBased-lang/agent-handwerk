"""SMTP Email Gateway Implementation.

Standard SMTP email sending using aiosmtplib for async support.
Works with any SMTP server including:
- Gmail SMTP
- Office 365
- Amazon SES SMTP
- Self-hosted mail servers
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr, formatdate, make_msgid
from typing import Any

import aiosmtplib
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


class SMTPEmailGateway(EmailGateway):
    """SMTP email gateway implementation.

    Uses aiosmtplib for async SMTP operations.
    Supports TLS/SSL, authentication, and attachments.

    Attributes:
        host: SMTP server hostname
        port: SMTP server port (25, 465, 587)
        username: SMTP authentication username
        password: SMTP authentication password
        use_tls: Use STARTTLS encryption
        use_ssl: Use SSL/TLS connection
        from_email: Default sender email
        from_name: Default sender display name
    """

    def __init__(
        self,
        host: str,
        port: int = 587,
        username: str | None = None,
        password: str | None = None,
        use_tls: bool = True,
        use_ssl: bool = False,
        from_email: str | None = None,
        from_name: str | None = None,
        timeout: float = 30.0,
    ):
        """Initialize SMTP email gateway.

        Args:
            host: SMTP server hostname
            port: SMTP server port
            username: Authentication username (usually email)
            password: Authentication password
            use_tls: Use STARTTLS (port 587)
            use_ssl: Use SSL connection (port 465)
            from_email: Default sender email
            from_name: Default sender display name
            timeout: Connection timeout in seconds
        """
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.use_tls = use_tls
        self.use_ssl = use_ssl
        self.from_email = from_email
        self.from_name = from_name
        self.timeout = timeout

    async def send(self, message: EmailMessage) -> EmailResult:
        """Send email via SMTP.

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
                provider="smtp",
                error_message="; ".join(errors),
            )

        # Determine sender
        from_email = message.from_email or self.from_email
        from_name = message.from_name or self.from_name

        if not from_email:
            return EmailResult(
                success=False,
                status=EmailStatus.FAILED,
                provider="smtp",
                error_message="No sender email configured",
            )

        try:
            # Build MIME message
            mime_message = self._build_mime_message(message, from_email, from_name)

            # Send via SMTP
            async with aiosmtplib.SMTP(
                hostname=self.host,
                port=self.port,
                use_tls=self.use_ssl,
                timeout=self.timeout,
            ) as smtp:
                # STARTTLS if configured
                if self.use_tls and not self.use_ssl:
                    await smtp.starttls()

                # Authenticate if credentials provided
                if self.username and self.password:
                    await smtp.login(self.username, self.password)

                # Send email
                response = await smtp.send_message(mime_message)

                # Extract message ID
                message_id = mime_message["Message-ID"]

                log.info(
                    "Email sent via SMTP",
                    message_id=message_id,
                    to=message.to,
                    subject=message.subject,
                )

                return EmailResult(
                    success=True,
                    message_id=message_id,
                    status=EmailStatus.SENT,
                    provider="smtp",
                    sent_at=datetime.now(),
                    recipients_accepted=len(message.recipients),
                )

        except aiosmtplib.SMTPAuthenticationError as e:
            log.error("SMTP authentication failed", error=str(e))
            return EmailResult(
                success=False,
                status=EmailStatus.FAILED,
                provider="smtp",
                error_message="Authentication failed",
                error_code="AUTH_FAILED",
            )

        except aiosmtplib.SMTPRecipientsRefused as e:
            log.error("SMTP recipients refused", error=str(e))
            return EmailResult(
                success=False,
                status=EmailStatus.BOUNCED,
                provider="smtp",
                error_message=f"Recipients refused: {e.recipients}",
                error_code="RECIPIENTS_REFUSED",
            )

        except aiosmtplib.SMTPException as e:
            log.error("SMTP error", error=str(e))
            return EmailResult(
                success=False,
                status=EmailStatus.FAILED,
                provider="smtp",
                error_message=str(e),
            )

        except asyncio.TimeoutError:
            log.error("SMTP timeout", host=self.host)
            return EmailResult(
                success=False,
                status=EmailStatus.FAILED,
                provider="smtp",
                error_message="Connection timeout",
                error_code="TIMEOUT",
            )

        except Exception as e:
            log.error("SMTP unexpected error", error=str(e))
            return EmailResult(
                success=False,
                status=EmailStatus.FAILED,
                provider="smtp",
                error_message=str(e),
            )

    def _build_mime_message(
        self,
        message: EmailMessage,
        from_email: str,
        from_name: str | None,
    ) -> MIMEMultipart:
        """Build MIME message from EmailMessage.

        Args:
            message: Email message
            from_email: Sender email
            from_name: Sender display name

        Returns:
            MIMEMultipart message ready to send
        """
        # Create multipart message
        if message.attachments:
            mime_msg = MIMEMultipart("mixed")
            body_part = MIMEMultipart("alternative")
        else:
            mime_msg = MIMEMultipart("alternative")
            body_part = mime_msg

        # Set headers
        mime_msg["Subject"] = message.subject
        mime_msg["From"] = formataddr((from_name or "", from_email))
        mime_msg["To"] = ", ".join(message.to)
        mime_msg["Date"] = formatdate(localtime=True)
        mime_msg["Message-ID"] = make_msgid(domain=from_email.split("@")[-1])

        if message.cc:
            mime_msg["Cc"] = ", ".join(message.cc)

        if message.reply_to:
            mime_msg["Reply-To"] = message.reply_to

        # Set priority
        if message.priority == EmailPriority.HIGH:
            mime_msg["X-Priority"] = "1"
            mime_msg["Importance"] = "high"
        elif message.priority == EmailPriority.LOW:
            mime_msg["X-Priority"] = "5"
            mime_msg["Importance"] = "low"

        # Add custom headers
        if message.headers:
            for key, value in message.headers.items():
                mime_msg[key] = value

        # Add text body
        if message.body_text:
            text_part = MIMEText(message.body_text, "plain", "utf-8")
            body_part.attach(text_part)

        # Add HTML body
        if message.body_html:
            html_part = MIMEText(message.body_html, "html", "utf-8")
            body_part.attach(html_part)

        # Add body part if we have attachments
        if message.attachments:
            mime_msg.attach(body_part)

            # Add attachments
            for attachment in message.attachments:
                att_part = MIMEBase(*attachment.content_type.split("/", 1))
                att_part.set_payload(attachment.content)

                # Encode base64
                from email.encoders import encode_base64

                encode_base64(att_part)

                # Set filename
                att_part.add_header(
                    "Content-Disposition",
                    "attachment",
                    filename=attachment.filename,
                )

                # Set Content-ID for inline attachments
                if attachment.content_id:
                    att_part["Content-ID"] = f"<{attachment.content_id}>"

                mime_msg.attach(att_part)

        return mime_msg

    async def test_connection(self) -> bool:
        """Test SMTP connection.

        Returns:
            True if connection successful
        """
        try:
            async with aiosmtplib.SMTP(
                hostname=self.host,
                port=self.port,
                use_tls=self.use_ssl,
                timeout=self.timeout,
            ) as smtp:
                if self.use_tls and not self.use_ssl:
                    await smtp.starttls()

                if self.username and self.password:
                    await smtp.login(self.username, self.password)

                log.info("SMTP connection test successful", host=self.host)
                return True

        except Exception as e:
            log.error("SMTP connection test failed", host=self.host, error=str(e))
            return False
