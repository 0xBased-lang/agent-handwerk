"""Email Poller service.

Polls IMAP mailboxes for new emails and processes them.
Creates tasks from incoming emails using classification and routing.
"""

from __future__ import annotations

import asyncio
import imaplib
import os
import smtplib
import ssl
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any
from uuid import uuid4

from cryptography.fernet import Fernet
from itf_shared import get_logger

from phone_agent.services.email_parser import EmailParser, ParsedEmail
from phone_agent.services.email_classifier import EmailClassifier, EmailClassification
from phone_agent.industry.handwerk.email_prompts import EMAIL_AUTO_REPLY_TEMPLATES

log = get_logger(__name__)


@dataclass
class EmailConfig:
    """Email configuration for a tenant."""

    tenant_id: str
    enabled: bool = True

    # IMAP settings
    imap_host: str = ""
    imap_port: int = 993
    imap_user: str = ""
    imap_password: str = ""  # Encrypted
    imap_use_ssl: bool = True

    # SMTP settings (for auto-replies)
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""  # Encrypted
    smtp_use_tls: bool = True

    # Processing settings
    poll_interval_minutes: int = 2
    folder: str = "INBOX"
    mark_as_read: bool = True
    move_to_folder: str | None = "Processed"
    send_auto_reply: bool = True

    # Tenant info (for auto-reply)
    company_name: str = ""
    emergency_phone: str = ""


@dataclass
class ProcessedEmail:
    """Result of processing an email."""

    email_id: str
    parsed: ParsedEmail
    classification: EmailClassification
    task_id: str | None = None
    auto_reply_sent: bool = False
    error: str | None = None


class EmailEncryption:
    """Encrypt/decrypt email passwords."""

    def __init__(self, key: bytes | None = None):
        """Initialize encryption with key.

        Args:
            key: Fernet key (32 bytes, base64). If None, uses EMAIL_ENCRYPTION_KEY env.
        """
        if key is None:
            key_str = os.environ.get("EMAIL_ENCRYPTION_KEY")
            if key_str:
                key = key_str.encode()
            else:
                # Generate a new key (for development only)
                key = Fernet.generate_key()
                log.warning("No EMAIL_ENCRYPTION_KEY set, using generated key (not persistent!)")

        self._fernet = Fernet(key)

    def encrypt(self, plaintext: str) -> str:
        """Encrypt a password."""
        return self._fernet.encrypt(plaintext.encode()).decode()

    def decrypt(self, ciphertext: str) -> str:
        """Decrypt a password."""
        return self._fernet.decrypt(ciphertext.encode()).decode()


class EmailPoller:
    """Poll IMAP mailboxes for new emails.

    Polls multiple company mailboxes on a schedule, classifies
    incoming emails, and creates tasks via the routing engine.
    """

    def __init__(
        self,
        encryption: EmailEncryption | None = None,
        groq_api_key: str | None = None,
    ):
        """Initialize email poller.

        Args:
            encryption: Encryption handler for passwords
            groq_api_key: API key for LLM classification
        """
        self.encryption = encryption or EmailEncryption()
        self.groq_api_key = groq_api_key or os.environ.get("GROQ_API_KEY", "")

        self._parser = EmailParser()
        self._classifier = EmailClassifier(api_key=self.groq_api_key)

        # Active polling tasks
        self._tasks: dict[str, asyncio.Task] = {}
        self._running = False

        # Callbacks for task creation and auto-reply
        self._on_email_processed: list[callable] = []

    def register_callback(self, callback: callable) -> None:
        """Register callback for processed emails.

        Callback signature: async def callback(result: ProcessedEmail, config: EmailConfig)
        """
        self._on_email_processed.append(callback)

    async def start(self, configs: list[EmailConfig]) -> None:
        """Start polling all configured mailboxes.

        Args:
            configs: List of email configurations
        """
        if self._running:
            log.warning("Email poller already running")
            return

        self._running = True
        log.info("Starting email poller", num_configs=len(configs))

        for config in configs:
            if config.enabled:
                self._start_polling_task(config)

    async def stop(self) -> None:
        """Stop all polling tasks."""
        self._running = False

        for tenant_id, task in self._tasks.items():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        self._tasks.clear()
        log.info("Email poller stopped")

    def _start_polling_task(self, config: EmailConfig) -> None:
        """Start polling task for a single mailbox."""
        if config.tenant_id in self._tasks:
            return

        task = asyncio.create_task(self._poll_loop(config))
        self._tasks[config.tenant_id] = task
        log.info(
            "Started polling task",
            tenant_id=config.tenant_id,
            imap_host=config.imap_host,
            interval_minutes=config.poll_interval_minutes,
        )

    async def _poll_loop(self, config: EmailConfig) -> None:
        """Main polling loop for a mailbox."""
        while self._running:
            try:
                await self._poll_mailbox(config)
            except Exception as e:
                log.error(
                    "Polling failed",
                    tenant_id=config.tenant_id,
                    error=str(e),
                )

            # Wait for next poll
            await asyncio.sleep(config.poll_interval_minutes * 60)

    async def _poll_mailbox(self, config: EmailConfig) -> list[ProcessedEmail]:
        """Poll a single mailbox for new emails.

        Args:
            config: Email configuration

        Returns:
            List of processed emails
        """
        results: list[ProcessedEmail] = []

        try:
            # Connect to IMAP
            if config.imap_use_ssl:
                mail = imaplib.IMAP4_SSL(config.imap_host, config.imap_port)
            else:
                mail = imaplib.IMAP4(config.imap_host, config.imap_port)

            # Decrypt password and login
            password = self.encryption.decrypt(config.imap_password)
            mail.login(config.imap_user, password)

            # Select folder
            mail.select(config.folder)

            # Search for unread emails
            status, messages = mail.search(None, "UNSEEN")
            if status != "OK":
                log.warning("IMAP search failed", tenant_id=config.tenant_id)
                return results

            email_ids = messages[0].split()
            log.debug(
                "Found unread emails",
                tenant_id=config.tenant_id,
                count=len(email_ids),
            )

            # Process each email
            for email_id in email_ids:
                try:
                    result = await self._process_email(mail, email_id, config)
                    results.append(result)

                    # Notify callbacks
                    for callback in self._on_email_processed:
                        try:
                            await callback(result, config)
                        except Exception as e:
                            log.error("Callback failed", error=str(e))

                except Exception as e:
                    log.error(
                        "Email processing failed",
                        tenant_id=config.tenant_id,
                        email_id=email_id,
                        error=str(e),
                    )

            # Cleanup
            mail.expunge()
            mail.logout()

        except imaplib.IMAP4.error as e:
            log.error("IMAP error", tenant_id=config.tenant_id, error=str(e))
        except Exception as e:
            log.error("Mailbox polling failed", tenant_id=config.tenant_id, error=str(e))

        return results

    async def _process_email(
        self,
        mail: imaplib.IMAP4_SSL,
        email_id: bytes,
        config: EmailConfig,
    ) -> ProcessedEmail:
        """Process a single email.

        Args:
            mail: IMAP connection
            email_id: Email ID to process
            config: Email configuration

        Returns:
            ProcessedEmail result
        """
        # Fetch email
        status, msg_data = mail.fetch(email_id, "(RFC822)")
        if status != "OK":
            raise RuntimeError(f"Failed to fetch email {email_id}")

        raw_email = msg_data[0][1]

        # Parse email
        parsed = self._parser.parse(raw_email)

        # Classify email
        classification = await self._classifier.classify(parsed)

        # Create result
        result = ProcessedEmail(
            email_id=email_id.decode() if isinstance(email_id, bytes) else str(email_id),
            parsed=parsed,
            classification=classification,
        )

        # Mark as read if configured
        if config.mark_as_read:
            mail.store(email_id, "+FLAGS", "\\Seen")

        # Move to folder if configured
        if config.move_to_folder:
            try:
                mail.copy(email_id, config.move_to_folder)
                mail.store(email_id, "+FLAGS", "\\Deleted")
            except Exception as e:
                log.warning(
                    "Failed to move email to folder",
                    folder=config.move_to_folder,
                    error=str(e),
                )

        # Send auto-reply if configured (not for spam)
        if (
            config.send_auto_reply
            and classification.task_type != "spam"
            and classification.urgency
        ):
            try:
                await self._send_auto_reply(parsed, classification, config)
                result.auto_reply_sent = True
            except Exception as e:
                log.warning("Auto-reply failed", error=str(e))

        log.info(
            "Email processed",
            tenant_id=config.tenant_id,
            subject=parsed.subject[:50] if parsed.subject else None,
            task_type=classification.task_type,
            urgency=classification.urgency,
            confidence=classification.confidence,
        )

        return result

    async def _send_auto_reply(
        self,
        parsed: ParsedEmail,
        classification: EmailClassification,
        config: EmailConfig,
    ) -> None:
        """Send auto-reply email.

        Args:
            parsed: Original parsed email
            classification: Email classification
            config: Email configuration
        """
        # Get template for urgency level
        template = EMAIL_AUTO_REPLY_TEMPLATES.get(classification.urgency)
        if not template:
            return

        # Generate ticket number
        ticket_number = f"TKT-{datetime.now().strftime('%Y%m%d')}-{uuid4().hex[:6].upper()}"

        # Format reply
        customer_name = classification.customer_name or parsed.sender_name or "Kunde"
        reply_body = template.format(
            customer_name=customer_name,
            ticket_number=ticket_number,
            company_name=config.company_name or "IT-Friends Handwerk",
            emergency_phone=config.emergency_phone or "",
        )

        # Create reply email
        msg = MIMEMultipart()
        msg["From"] = config.smtp_user
        msg["To"] = parsed.sender_email
        msg["Subject"] = f"Re: {parsed.subject}" if parsed.subject else "Ihre Anfrage"
        msg["In-Reply-To"] = parsed.message_id
        msg["References"] = parsed.message_id

        msg.attach(MIMEText(reply_body, "plain", "utf-8"))

        # Send via SMTP
        await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: self._send_smtp(msg, config),
        )

        log.info(
            "Auto-reply sent",
            to=parsed.sender_email,
            ticket_number=ticket_number,
            urgency=classification.urgency,
        )

    def _send_smtp(self, msg: MIMEMultipart, config: EmailConfig) -> None:
        """Send email via SMTP (sync)."""
        if config.smtp_use_tls:
            context = ssl.create_default_context()
            with smtplib.SMTP(config.smtp_host, config.smtp_port) as server:
                server.starttls(context=context)
                password = self.encryption.decrypt(config.smtp_password)
                server.login(config.smtp_user, password)
                server.send_message(msg)
        else:
            with smtplib.SMTP_SSL(config.smtp_host, config.smtp_port) as server:
                password = self.encryption.decrypt(config.smtp_password)
                server.login(config.smtp_user, password)
                server.send_message(msg)

    async def poll_once(self, config: EmailConfig) -> list[ProcessedEmail]:
        """Poll a mailbox once (manual trigger).

        Args:
            config: Email configuration

        Returns:
            List of processed emails
        """
        return await self._poll_mailbox(config)

    def add_config(self, config: EmailConfig) -> None:
        """Add a new mailbox configuration and start polling.

        Args:
            config: Email configuration
        """
        if config.enabled and self._running:
            self._start_polling_task(config)

    def remove_config(self, tenant_id: str) -> None:
        """Remove a mailbox configuration and stop polling.

        Args:
            tenant_id: Tenant ID to remove
        """
        if tenant_id in self._tasks:
            self._tasks[tenant_id].cancel()
            del self._tasks[tenant_id]


class EmailIntakeService:
    """High-level service for email intake with routing integration.

    Combines EmailPoller with RoutingEngine to create tasks from emails.
    """

    def __init__(
        self,
        poller: EmailPoller | None = None,
        db_session_factory: callable | None = None,
    ):
        """Initialize email intake service.

        Args:
            poller: EmailPoller instance (or creates new one)
            db_session_factory: Factory for database sessions
        """
        self.poller = poller or EmailPoller()
        self._db_session_factory = db_session_factory

        # Register callback for task creation
        self.poller.register_callback(self._on_email_processed)

    async def _on_email_processed(
        self,
        result: ProcessedEmail,
        config: EmailConfig,
    ) -> None:
        """Handle processed email - create task and route it.

        Args:
            result: Processed email result
            config: Email configuration
        """
        if not self._db_session_factory:
            log.warning("No database session factory - cannot create tasks")
            return

        if result.classification.task_type == "spam":
            log.debug("Skipping spam email")
            return

        async with self._db_session_factory() as db:
            from phone_agent.db.repositories.tenant_repos import TaskRepository
            from phone_agent.services.routing_engine import RoutingEngine

            task_repo = TaskRepository(db)
            routing_engine = RoutingEngine(db)

            # Create task from email
            task_data = {
                "tenant_id": config.tenant_id,
                "source_type": "email",
                "source_id": result.parsed.message_id,
                "task_type": result.classification.task_type,
                "urgency": result.classification.urgency,
                "trade_category": result.classification.trade_category,
                "customer_name": result.classification.customer_name,
                "customer_email": result.parsed.sender_email,
                "customer_phone": result.classification.customer_phone,
                "customer_plz": result.classification.customer_plz,
                "title": result.parsed.subject or "E-Mail-Anfrage",
                "description": result.parsed.plain_text[:2000],
                "ai_summary": result.classification.summary,
                "status": "new",
            }

            # Create task
            task = await task_repo.create(task_data)

            # Route task
            try:
                routing_decision = await routing_engine.route_task(
                    tenant_id=config.tenant_id,
                    task_type=task_data["task_type"],
                    urgency=task_data["urgency"],
                    trade_category=task_data["trade_category"],
                    customer_plz=task_data.get("customer_plz"),
                )

                if routing_decision.department_id:
                    await task_repo.update(
                        task.id,
                        {
                            "assigned_department_id": routing_decision.department_id,
                            "assigned_worker_id": routing_decision.worker_id,
                            "routing_reason": routing_decision.reason,
                        },
                    )

                    log.info(
                        "Email task routed",
                        task_id=str(task.id),
                        department_id=str(routing_decision.department_id) if routing_decision.department_id else None,
                        reason=routing_decision.reason,
                    )

            except Exception as e:
                log.error("Task routing failed", task_id=str(task.id), error=str(e))

            await db.commit()
            result.task_id = str(task.id)

    async def start(self, configs: list[EmailConfig]) -> None:
        """Start the email intake service."""
        await self.poller.start(configs)

    async def stop(self) -> None:
        """Stop the email intake service."""
        await self.poller.stop()
