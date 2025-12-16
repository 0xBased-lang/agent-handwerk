"""Email Parser service.

Extracts structured data from raw MIME email messages.
Handles various encodings, attachments, and HTML/text content.
"""

from __future__ import annotations

import email
import re
from dataclasses import dataclass, field
from datetime import datetime
from email import policy
from email.header import decode_header
from email.message import EmailMessage
from email.utils import parsedate_to_datetime
from typing import Any
import html2text

from itf_shared import get_logger

log = get_logger(__name__)


@dataclass
class EmailAttachment:
    """Parsed email attachment."""

    filename: str
    content_type: str
    size: int
    content: bytes | None = None  # Only populated if small enough


@dataclass
class ParsedEmail:
    """Parsed email with extracted content."""

    message_id: str
    subject: str
    sender_email: str
    sender_name: str | None
    recipient_email: str
    recipient_name: str | None
    cc_emails: list[str] = field(default_factory=list)
    date: datetime | None = None

    # Content
    text_body: str = ""
    html_body: str = ""
    plain_text: str = ""  # Cleaned plain text (HTML converted)

    # Attachments
    attachments: list[EmailAttachment] = field(default_factory=list)
    has_attachments: bool = False

    # Metadata
    reply_to: str | None = None
    in_reply_to: str | None = None
    references: list[str] = field(default_factory=list)

    # Raw data
    raw_headers: dict[str, str] = field(default_factory=dict)


class EmailParser:
    """Parse raw MIME emails into structured data."""

    def __init__(
        self,
        max_attachment_size: int = 10 * 1024 * 1024,  # 10MB
        include_attachment_content: bool = False,
    ):
        """Initialize email parser.

        Args:
            max_attachment_size: Maximum attachment size to process
            include_attachment_content: Whether to include attachment bytes
        """
        self.max_attachment_size = max_attachment_size
        self.include_attachment_content = include_attachment_content
        self._html2text = html2text.HTML2Text()
        self._html2text.ignore_links = False
        self._html2text.ignore_images = True
        self._html2text.body_width = 0

    def parse(self, raw_email: bytes | str) -> ParsedEmail:
        """Parse raw email into structured data.

        Args:
            raw_email: Raw MIME email content

        Returns:
            ParsedEmail with extracted content
        """
        # Parse the raw email
        if isinstance(raw_email, str):
            raw_email = raw_email.encode("utf-8")

        msg = email.message_from_bytes(raw_email, policy=policy.default)

        # Extract headers
        message_id = msg.get("Message-ID", "")
        subject = self._decode_header(msg.get("Subject", ""))

        # Parse sender
        sender = msg.get("From", "")
        sender_email, sender_name = self._parse_address(sender)

        # Parse recipient
        recipient = msg.get("To", "")
        recipient_email, recipient_name = self._parse_address(recipient)

        # Parse CC
        cc = msg.get("Cc", "")
        cc_emails = self._parse_address_list(cc)

        # Parse date
        date_str = msg.get("Date")
        date = None
        if date_str:
            try:
                date = parsedate_to_datetime(date_str)
            except Exception:
                log.warning("Failed to parse email date", date=date_str)

        # Extract body
        text_body, html_body = self._extract_body(msg)

        # Convert HTML to plain text if needed
        plain_text = text_body
        if not plain_text and html_body:
            plain_text = self._html_to_text(html_body)

        # Clean up the plain text
        plain_text = self._clean_text(plain_text)

        # Extract attachments
        attachments = self._extract_attachments(msg)

        # Build parsed email
        parsed = ParsedEmail(
            message_id=message_id,
            subject=subject,
            sender_email=sender_email,
            sender_name=sender_name,
            recipient_email=recipient_email,
            recipient_name=recipient_name,
            cc_emails=cc_emails,
            date=date,
            text_body=text_body,
            html_body=html_body,
            plain_text=plain_text,
            attachments=attachments,
            has_attachments=len(attachments) > 0,
            reply_to=msg.get("Reply-To"),
            in_reply_to=msg.get("In-Reply-To"),
            references=self._parse_references(msg.get("References", "")),
            raw_headers={k: str(v) for k, v in msg.items()},
        )

        log.debug(
            "Email parsed",
            message_id=message_id[:50] if message_id else None,
            subject=subject[:50] if subject else None,
            sender=sender_email,
            body_length=len(plain_text),
            attachments=len(attachments),
        )

        return parsed

    def _decode_header(self, header: str) -> str:
        """Decode email header handling various encodings."""
        if not header:
            return ""

        parts = decode_header(header)
        decoded_parts = []

        for content, charset in parts:
            if isinstance(content, bytes):
                charset = charset or "utf-8"
                try:
                    decoded_parts.append(content.decode(charset))
                except Exception:
                    decoded_parts.append(content.decode("utf-8", errors="replace"))
            else:
                decoded_parts.append(content)

        return "".join(decoded_parts)

    def _parse_address(self, address: str) -> tuple[str, str | None]:
        """Parse email address into email and name.

        Args:
            address: Email address string (e.g., "Max Müller <max@example.de>")

        Returns:
            Tuple of (email, name or None)
        """
        if not address:
            return "", None

        address = self._decode_header(address)

        # Pattern: "Name <email>" or just "email"
        match = re.match(r'^"?([^"<]+)"?\s*<([^>]+)>$', address.strip())
        if match:
            name = match.group(1).strip()
            email_addr = match.group(2).strip()
            return email_addr, name

        # Just email
        email_match = re.search(r'[\w\.-]+@[\w\.-]+\.\w+', address)
        if email_match:
            return email_match.group(0), None

        return address.strip(), None

    def _parse_address_list(self, addresses: str) -> list[str]:
        """Parse comma-separated email addresses."""
        if not addresses:
            return []

        addresses = self._decode_header(addresses)
        result = []

        for addr in addresses.split(","):
            email_addr, _ = self._parse_address(addr.strip())
            if email_addr:
                result.append(email_addr)

        return result

    def _extract_body(self, msg: EmailMessage) -> tuple[str, str]:
        """Extract text and HTML body from message.

        Returns:
            Tuple of (text_body, html_body)
        """
        text_body = ""
        html_body = ""

        if msg.is_multipart():
            for part in msg.walk():
                content_type = part.get_content_type()
                content_disposition = str(part.get("Content-Disposition", ""))

                # Skip attachments
                if "attachment" in content_disposition:
                    continue

                if content_type == "text/plain":
                    try:
                        text_body = part.get_content()
                    except Exception:
                        text_body = self._decode_payload(part)
                elif content_type == "text/html":
                    try:
                        html_body = part.get_content()
                    except Exception:
                        html_body = self._decode_payload(part)
        else:
            content_type = msg.get_content_type()
            if content_type == "text/plain":
                try:
                    text_body = msg.get_content()
                except Exception:
                    text_body = self._decode_payload(msg)
            elif content_type == "text/html":
                try:
                    html_body = msg.get_content()
                except Exception:
                    html_body = self._decode_payload(msg)

        return text_body, html_body

    def _decode_payload(self, part) -> str:
        """Decode email part payload with fallback encoding."""
        payload = part.get_payload(decode=True)
        if not payload:
            return ""

        # Try various encodings
        charset = part.get_content_charset() or "utf-8"
        for encoding in [charset, "utf-8", "iso-8859-1", "windows-1252"]:
            try:
                return payload.decode(encoding)
            except Exception:
                continue

        return payload.decode("utf-8", errors="replace")

    def _html_to_text(self, html: str) -> str:
        """Convert HTML to plain text."""
        try:
            return self._html2text.handle(html)
        except Exception as e:
            log.warning("HTML to text conversion failed", error=str(e))
            # Fallback: strip tags
            return re.sub(r'<[^>]+>', ' ', html)

    def _clean_text(self, text: str) -> str:
        """Clean up extracted text."""
        if not text:
            return ""

        # Remove excessive whitespace
        text = re.sub(r'\s+', ' ', text)

        # Remove common email signatures
        # German email signatures often start with these
        signature_patterns = [
            r'--\s*\n.*$',  # Standard signature delimiter
            r'Mit freundlichen Grüßen.*$',
            r'Beste Grüße.*$',
            r'Viele Grüße.*$',
            r'Herzliche Grüße.*$',
            r'MfG.*$',
            r'Regards.*$',
            r'Best regards.*$',
        ]

        for pattern in signature_patterns:
            text = re.sub(pattern, '', text, flags=re.IGNORECASE | re.DOTALL)

        # Remove quoted replies (lines starting with >)
        text = re.sub(r'^>.*$', '', text, flags=re.MULTILINE)

        # Remove forwarded message headers
        text = re.sub(r'-----Original Message-----.*$', '', text, flags=re.IGNORECASE | re.DOTALL)
        text = re.sub(r'-----Ursprüngliche Nachricht-----.*$', '', text, flags=re.IGNORECASE | re.DOTALL)

        # Final cleanup
        text = re.sub(r'\s+', ' ', text).strip()

        return text

    def _extract_attachments(self, msg: EmailMessage) -> list[EmailAttachment]:
        """Extract attachment metadata (and optionally content)."""
        attachments = []

        if not msg.is_multipart():
            return attachments

        for part in msg.walk():
            content_disposition = str(part.get("Content-Disposition", ""))

            if "attachment" not in content_disposition:
                continue

            filename = part.get_filename()
            if filename:
                filename = self._decode_header(filename)
            else:
                filename = "unknown"

            content_type = part.get_content_type()
            payload = part.get_payload(decode=True)
            size = len(payload) if payload else 0

            attachment = EmailAttachment(
                filename=filename,
                content_type=content_type,
                size=size,
                content=payload if self.include_attachment_content and size <= self.max_attachment_size else None,
            )

            attachments.append(attachment)

            log.debug(
                "Attachment extracted",
                filename=filename,
                content_type=content_type,
                size=size,
            )

        return attachments

    def _parse_references(self, references: str) -> list[str]:
        """Parse References header into list of message IDs."""
        if not references:
            return []

        # Message IDs are in angle brackets
        return re.findall(r'<([^>]+)>', references)

    def extract_customer_info(self, parsed: ParsedEmail) -> dict[str, Any]:
        """Extract customer information from parsed email.

        Uses pattern matching to find:
        - Phone numbers (German format)
        - Addresses (PLZ + City)
        - Names

        Args:
            parsed: ParsedEmail to extract from

        Returns:
            Dict with extracted customer info
        """
        text = f"{parsed.subject} {parsed.plain_text}"

        info: dict[str, Any] = {
            "name": parsed.sender_name,
            "email": parsed.sender_email,
            "phone": None,
            "address": None,
            "plz": None,
            "city": None,
        }

        # Extract German phone numbers
        # Formats: +49..., 0049..., 0xxx/..., 0xxx-..., 0xxx ...
        phone_patterns = [
            r'\+49\s*[\d\s/-]+',
            r'0049\s*[\d\s/-]+',
            r'0\d{2,4}\s*[-/]\s*[\d\s/-]+',
            r'0\d{3,4}\s+[\d\s]+',
            r'Tel\.?:?\s*([\d\s+/-]+)',
            r'Telefon:?\s*([\d\s+/-]+)',
            r'Mobil:?\s*([\d\s+/-]+)',
        ]

        for pattern in phone_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                phone = re.sub(r'\s+', '', match.group(0))
                phone = re.sub(r'Tel\.?:?|Telefon:?|Mobil:?', '', phone, flags=re.IGNORECASE)
                if len(phone) >= 6:  # Minimum valid length
                    info["phone"] = phone.strip()
                    break

        # Extract German PLZ (5 digits)
        plz_match = re.search(r'\b(\d{5})\s+([A-Za-zäöüÄÖÜß][A-Za-zäöüÄÖÜß\s-]{2,30})\b', text)
        if plz_match:
            info["plz"] = plz_match.group(1)
            info["city"] = plz_match.group(2).strip()

        # Extract street address (German format: Straße Nr., PLZ Stadt)
        street_patterns = [
            r'([A-Za-zäöüÄÖÜß][A-Za-zäöüÄÖÜß\s-]+(?:straße|str\.|weg|platz|allee|gasse))\s*(\d+[a-z]?)',
            r'([A-Za-zäöüÄÖÜß][A-Za-zäöüÄÖÜß\s-]+)\s+(\d+[a-z]?)\s*,?\s*\d{5}',
        ]

        for pattern in street_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                street = match.group(1).strip()
                number = match.group(2).strip()
                info["address"] = f"{street} {number}"
                break

        return info
