"""Email Agent API endpoints.

REST API for email intake configuration and management:
- Configure IMAP/SMTP settings for tenants
- Test email connections
- Trigger manual email polls
- View processed emails
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Query
from pydantic import BaseModel, Field, EmailStr
from sqlalchemy.ext.asyncio import AsyncSession

from itf_shared import get_logger

from phone_agent.db import get_db
from phone_agent.db.models.tenant import TenantModel
from phone_agent.db.repositories.tenant_repos import TenantRepository, TaskRepository
from phone_agent.services.email_poller import (
    EmailPoller,
    EmailConfig,
    EmailEncryption,
    ProcessedEmail,
)
from phone_agent.services.email_classifier import EmailClassifier

log = get_logger(__name__)

router = APIRouter(prefix="/email", tags=["Email Agent"])


# ============================================================================
# Pydantic Schemas
# ============================================================================


class EmailConfigRequest(BaseModel):
    """Request to configure email intake."""

    enabled: bool = True

    # IMAP settings
    imap_host: str = Field(..., description="IMAP server hostname")
    imap_port: int = Field(993, description="IMAP port (default 993 for SSL)")
    imap_user: str = Field(..., description="IMAP username/email")
    imap_password: str = Field(..., description="IMAP password (will be encrypted)")
    imap_use_ssl: bool = Field(True, description="Use SSL for IMAP")

    # SMTP settings (for auto-replies)
    smtp_host: str | None = Field(None, description="SMTP server hostname")
    smtp_port: int = Field(587, description="SMTP port (default 587 for TLS)")
    smtp_user: str | None = Field(None, description="SMTP username")
    smtp_password: str | None = Field(None, description="SMTP password (will be encrypted)")
    smtp_use_tls: bool = Field(True, description="Use TLS for SMTP")

    # Processing settings
    poll_interval_minutes: int = Field(2, ge=1, le=60, description="Poll interval (1-60 minutes)")
    folder: str = Field("INBOX", description="IMAP folder to poll")
    mark_as_read: bool = Field(True, description="Mark processed emails as read")
    move_to_folder: str | None = Field("Processed", description="Move processed emails to folder")
    send_auto_reply: bool = Field(True, description="Send auto-reply to customers")

    class Config:
        json_schema_extra = {
            "example": {
                "enabled": True,
                "imap_host": "imap.gmail.com",
                "imap_port": 993,
                "imap_user": "info@firma-mueller.de",
                "imap_password": "your-app-password",
                "imap_use_ssl": True,
                "smtp_host": "smtp.gmail.com",
                "smtp_port": 587,
                "smtp_user": "info@firma-mueller.de",
                "smtp_password": "your-app-password",
                "smtp_use_tls": True,
                "poll_interval_minutes": 2,
                "folder": "INBOX",
                "mark_as_read": True,
                "move_to_folder": "Processed",
                "send_auto_reply": True,
            }
        }


class EmailConfigResponse(BaseModel):
    """Response with email configuration (passwords masked)."""

    enabled: bool
    imap_host: str
    imap_port: int
    imap_user: str
    imap_password: str = "********"  # Masked
    imap_use_ssl: bool
    smtp_host: str | None
    smtp_port: int
    smtp_user: str | None
    smtp_password: str = "********"  # Masked
    smtp_use_tls: bool
    poll_interval_minutes: int
    folder: str
    mark_as_read: bool
    move_to_folder: str | None
    send_auto_reply: bool


class EmailTestRequest(BaseModel):
    """Request to test email connection."""

    test_imap: bool = True
    test_smtp: bool = False


class EmailTestResponse(BaseModel):
    """Response from email connection test."""

    imap_success: bool = False
    imap_error: str | None = None
    imap_message_count: int = 0
    smtp_success: bool = False
    smtp_error: str | None = None


class ProcessedEmailResponse(BaseModel):
    """Response with processed email data."""

    id: str
    subject: str
    sender_email: str
    sender_name: str | None
    received_at: datetime | None
    task_type: str
    urgency: str
    trade_category: str
    confidence: float
    task_id: str | None
    auto_reply_sent: bool


class EmailStatsResponse(BaseModel):
    """Response with email processing statistics."""

    total_processed: int
    today_processed: int
    by_task_type: dict[str, int]
    by_urgency: dict[str, int]
    avg_confidence: float


class ManualClassifyRequest(BaseModel):
    """Request to manually classify email text."""

    subject: str = Field(..., description="Email subject")
    body: str = Field(..., description="Email body text")
    sender_email: EmailStr | None = Field(None, description="Sender email address")


class ClassificationResponse(BaseModel):
    """Response with email classification."""

    task_type: str
    urgency: str
    trade_category: str
    customer_name: str | None
    customer_phone: str | None
    customer_plz: str | None
    summary: str
    confidence: float
    needs_human_review: bool


# ============================================================================
# Global Email Poller (managed by application lifecycle)
# ============================================================================

_email_poller: EmailPoller | None = None
_encryption: EmailEncryption | None = None


def get_encryption() -> EmailEncryption:
    """Get or create encryption handler."""
    global _encryption
    if _encryption is None:
        _encryption = EmailEncryption()
    return _encryption


def get_email_poller() -> EmailPoller:
    """Get or create email poller."""
    global _email_poller
    if _email_poller is None:
        _email_poller = EmailPoller(encryption=get_encryption())
    return _email_poller


# ============================================================================
# Configuration Endpoints
# ============================================================================


@router.post("/config/{tenant_id}", response_model=EmailConfigResponse)
async def configure_email(
    tenant_id: UUID,
    config: EmailConfigRequest,
    db: AsyncSession = Depends(get_db),
) -> EmailConfigResponse:
    """Configure email intake for a tenant.

    Sets up IMAP polling and optional SMTP for auto-replies.
    Passwords are encrypted before storage.
    """
    # Get tenant
    tenant_repo = TenantRepository(db)
    tenant = await tenant_repo.get(tenant_id)
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    # Encrypt passwords
    encryption = get_encryption()
    encrypted_imap_password = encryption.encrypt(config.imap_password)
    encrypted_smtp_password = (
        encryption.encrypt(config.smtp_password) if config.smtp_password else None
    )

    # Build config JSON
    email_config = {
        "enabled": config.enabled,
        "imap_host": config.imap_host,
        "imap_port": config.imap_port,
        "imap_user": config.imap_user,
        "imap_password_encrypted": encrypted_imap_password,
        "imap_use_ssl": config.imap_use_ssl,
        "smtp_host": config.smtp_host,
        "smtp_port": config.smtp_port,
        "smtp_user": config.smtp_user,
        "smtp_password_encrypted": encrypted_smtp_password,
        "smtp_use_tls": config.smtp_use_tls,
        "poll_interval_minutes": config.poll_interval_minutes,
        "folder": config.folder,
        "mark_as_read": config.mark_as_read,
        "move_to_folder": config.move_to_folder,
        "send_auto_reply": config.send_auto_reply,
    }

    # Update tenant
    await tenant_repo.update(tenant_id, {"email_config_json": email_config})
    await db.commit()

    log.info(
        "Email config updated",
        tenant_id=str(tenant_id),
        imap_host=config.imap_host,
        enabled=config.enabled,
    )

    return EmailConfigResponse(
        enabled=config.enabled,
        imap_host=config.imap_host,
        imap_port=config.imap_port,
        imap_user=config.imap_user,
        imap_password="********",
        imap_use_ssl=config.imap_use_ssl,
        smtp_host=config.smtp_host,
        smtp_port=config.smtp_port,
        smtp_user=config.smtp_user,
        smtp_password="********",
        smtp_use_tls=config.smtp_use_tls,
        poll_interval_minutes=config.poll_interval_minutes,
        folder=config.folder,
        mark_as_read=config.mark_as_read,
        move_to_folder=config.move_to_folder,
        send_auto_reply=config.send_auto_reply,
    )


@router.get("/config/{tenant_id}", response_model=EmailConfigResponse)
async def get_email_config(
    tenant_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> EmailConfigResponse:
    """Get email intake configuration for a tenant.

    Returns configuration with masked passwords.
    """
    tenant_repo = TenantRepository(db)
    tenant = await tenant_repo.get(tenant_id)
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    config = tenant.email_config_json
    if not config:
        raise HTTPException(status_code=404, detail="Email config not found")

    return EmailConfigResponse(
        enabled=config.get("enabled", False),
        imap_host=config.get("imap_host", ""),
        imap_port=config.get("imap_port", 993),
        imap_user=config.get("imap_user", ""),
        imap_password="********",
        imap_use_ssl=config.get("imap_use_ssl", True),
        smtp_host=config.get("smtp_host"),
        smtp_port=config.get("smtp_port", 587),
        smtp_user=config.get("smtp_user"),
        smtp_password="********",
        smtp_use_tls=config.get("smtp_use_tls", True),
        poll_interval_minutes=config.get("poll_interval_minutes", 2),
        folder=config.get("folder", "INBOX"),
        mark_as_read=config.get("mark_as_read", True),
        move_to_folder=config.get("move_to_folder"),
        send_auto_reply=config.get("send_auto_reply", True),
    )


@router.delete("/config/{tenant_id}")
async def delete_email_config(
    tenant_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """Disable and remove email intake configuration for a tenant."""
    tenant_repo = TenantRepository(db)
    tenant = await tenant_repo.get(tenant_id)
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    # Clear config
    await tenant_repo.update(tenant_id, {"email_config_json": None})
    await db.commit()

    # Stop polling if running
    poller = get_email_poller()
    poller.remove_config(str(tenant_id))

    log.info("Email config deleted", tenant_id=str(tenant_id))

    return {"status": "deleted", "tenant_id": str(tenant_id)}


# ============================================================================
# Connection Testing Endpoints
# ============================================================================


@router.post("/test/{tenant_id}", response_model=EmailTestResponse)
async def test_email_connection(
    tenant_id: UUID,
    request: EmailTestRequest,
    db: AsyncSession = Depends(get_db),
) -> EmailTestResponse:
    """Test email connection for a tenant.

    Verifies IMAP and optionally SMTP connectivity.
    """
    import imaplib
    import smtplib
    import ssl

    tenant_repo = TenantRepository(db)
    tenant = await tenant_repo.get(tenant_id)
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    config = tenant.email_config_json
    if not config:
        raise HTTPException(status_code=400, detail="Email config not found")

    encryption = get_encryption()
    result = EmailTestResponse()

    # Test IMAP
    if request.test_imap:
        try:
            if config.get("imap_use_ssl", True):
                mail = imaplib.IMAP4_SSL(
                    config["imap_host"],
                    config.get("imap_port", 993),
                )
            else:
                mail = imaplib.IMAP4(
                    config["imap_host"],
                    config.get("imap_port", 143),
                )

            password = encryption.decrypt(config["imap_password_encrypted"])
            mail.login(config["imap_user"], password)
            mail.select(config.get("folder", "INBOX"))

            # Count messages
            status, messages = mail.search(None, "ALL")
            if status == "OK":
                result.imap_message_count = len(messages[0].split())

            mail.logout()
            result.imap_success = True

            log.info(
                "IMAP test successful",
                tenant_id=str(tenant_id),
                message_count=result.imap_message_count,
            )

        except Exception as e:
            result.imap_error = str(e)
            log.warning("IMAP test failed", tenant_id=str(tenant_id), error=str(e))

    # Test SMTP
    if request.test_smtp and config.get("smtp_host"):
        try:
            if config.get("smtp_use_tls", True):
                context = ssl.create_default_context()
                with smtplib.SMTP(
                    config["smtp_host"],
                    config.get("smtp_port", 587),
                ) as server:
                    server.starttls(context=context)
                    if config.get("smtp_password_encrypted"):
                        password = encryption.decrypt(config["smtp_password_encrypted"])
                        server.login(config["smtp_user"], password)
                    server.noop()
            else:
                with smtplib.SMTP_SSL(
                    config["smtp_host"],
                    config.get("smtp_port", 465),
                ) as server:
                    if config.get("smtp_password_encrypted"):
                        password = encryption.decrypt(config["smtp_password_encrypted"])
                        server.login(config["smtp_user"], password)
                    server.noop()

            result.smtp_success = True
            log.info("SMTP test successful", tenant_id=str(tenant_id))

        except Exception as e:
            result.smtp_error = str(e)
            log.warning("SMTP test failed", tenant_id=str(tenant_id), error=str(e))

    return result


# ============================================================================
# Polling Control Endpoints
# ============================================================================


@router.post("/poll/{tenant_id}")
async def trigger_poll(
    tenant_id: UUID,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Manually trigger email polling for a tenant.

    Polls the mailbox immediately instead of waiting for scheduled poll.
    Processing happens in background.
    """
    tenant_repo = TenantRepository(db)
    tenant = await tenant_repo.get(tenant_id)
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    config_json = tenant.email_config_json
    if not config_json or not config_json.get("enabled"):
        raise HTTPException(status_code=400, detail="Email intake not enabled")

    # Build EmailConfig from stored JSON
    encryption = get_encryption()
    config = EmailConfig(
        tenant_id=str(tenant_id),
        enabled=True,
        imap_host=config_json["imap_host"],
        imap_port=config_json.get("imap_port", 993),
        imap_user=config_json["imap_user"],
        imap_password=config_json["imap_password_encrypted"],  # Already encrypted
        imap_use_ssl=config_json.get("imap_use_ssl", True),
        smtp_host=config_json.get("smtp_host", ""),
        smtp_port=config_json.get("smtp_port", 587),
        smtp_user=config_json.get("smtp_user", ""),
        smtp_password=config_json.get("smtp_password_encrypted", ""),
        smtp_use_tls=config_json.get("smtp_use_tls", True),
        poll_interval_minutes=config_json.get("poll_interval_minutes", 2),
        folder=config_json.get("folder", "INBOX"),
        mark_as_read=config_json.get("mark_as_read", True),
        move_to_folder=config_json.get("move_to_folder"),
        send_auto_reply=config_json.get("send_auto_reply", True),
        company_name=tenant.name,
        emergency_phone=tenant.phone or "",
    )

    # Trigger poll in background
    async def do_poll():
        poller = get_email_poller()
        await poller.poll_once(config)

    background_tasks.add_task(do_poll)

    log.info("Manual poll triggered", tenant_id=str(tenant_id))

    return {
        "status": "polling",
        "tenant_id": str(tenant_id),
        "message": "Email polling started in background",
    }


@router.post("/polling/start/{tenant_id}")
async def start_polling(
    tenant_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """Start automated email polling for a tenant."""
    tenant_repo = TenantRepository(db)
    tenant = await tenant_repo.get(tenant_id)
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    config_json = tenant.email_config_json
    if not config_json:
        raise HTTPException(status_code=400, detail="Email config not found")

    # Build EmailConfig
    config = EmailConfig(
        tenant_id=str(tenant_id),
        enabled=True,
        imap_host=config_json["imap_host"],
        imap_port=config_json.get("imap_port", 993),
        imap_user=config_json["imap_user"],
        imap_password=config_json["imap_password_encrypted"],
        imap_use_ssl=config_json.get("imap_use_ssl", True),
        smtp_host=config_json.get("smtp_host", ""),
        smtp_port=config_json.get("smtp_port", 587),
        smtp_user=config_json.get("smtp_user", ""),
        smtp_password=config_json.get("smtp_password_encrypted", ""),
        smtp_use_tls=config_json.get("smtp_use_tls", True),
        poll_interval_minutes=config_json.get("poll_interval_minutes", 2),
        folder=config_json.get("folder", "INBOX"),
        mark_as_read=config_json.get("mark_as_read", True),
        move_to_folder=config_json.get("move_to_folder"),
        send_auto_reply=config_json.get("send_auto_reply", True),
        company_name=tenant.name,
        emergency_phone=tenant.phone or "",
    )

    # Add to poller
    poller = get_email_poller()
    poller.add_config(config)

    log.info("Email polling started", tenant_id=str(tenant_id))

    return {"status": "started", "tenant_id": str(tenant_id)}


@router.post("/polling/stop/{tenant_id}")
async def stop_polling(
    tenant_id: UUID,
) -> dict[str, str]:
    """Stop automated email polling for a tenant."""
    poller = get_email_poller()
    poller.remove_config(str(tenant_id))

    log.info("Email polling stopped", tenant_id=str(tenant_id))

    return {"status": "stopped", "tenant_id": str(tenant_id)}


# ============================================================================
# Classification Endpoints
# ============================================================================


@router.post("/classify", response_model=ClassificationResponse)
async def classify_email(
    request: ManualClassifyRequest,
) -> ClassificationResponse:
    """Manually classify email text.

    Useful for testing classification without actual email intake.
    """
    from phone_agent.services.email_parser import ParsedEmail

    # Create mock parsed email
    parsed = ParsedEmail(
        message_id="manual-test",
        subject=request.subject,
        sender_email=request.sender_email or "test@example.com",
        sender_name=None,
        recipient_email="info@test.de",
        recipient_name=None,
        plain_text=request.body,
    )

    # Classify
    classifier = EmailClassifier()
    classification = await classifier.classify(parsed)

    return ClassificationResponse(
        task_type=classification.task_type,
        urgency=classification.urgency,
        trade_category=classification.trade_category,
        customer_name=classification.customer_name,
        customer_phone=classification.customer_phone,
        customer_plz=classification.customer_plz,
        summary=classification.summary,
        confidence=classification.confidence,
        needs_human_review=classification.needs_human_review,
    )


# ============================================================================
# Statistics Endpoints
# ============================================================================


@router.get("/stats/{tenant_id}", response_model=EmailStatsResponse)
async def get_email_stats(
    tenant_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> EmailStatsResponse:
    """Get email processing statistics for a tenant."""
    from datetime import date

    task_repo = TaskRepository(db)

    # Get email tasks for tenant
    filters = {"tenant_id": tenant_id, "source_type": "email"}
    tasks = await task_repo.list(filters=filters, limit=1000)

    # Calculate stats
    today = date.today()
    today_tasks = [t for t in tasks if t.created_at and t.created_at.date() == today]

    by_task_type: dict[str, int] = {}
    by_urgency: dict[str, int] = {}
    total_confidence = 0.0

    for task in tasks:
        # Count by task_type
        task_type = task.task_type
        by_task_type[task_type] = by_task_type.get(task_type, 0) + 1

        # Count by urgency
        urgency = task.urgency
        by_urgency[urgency] = by_urgency.get(urgency, 0) + 1

        # Sum confidence (stored in metadata)
        if task.metadata_json and "classification_confidence" in task.metadata_json:
            total_confidence += task.metadata_json["classification_confidence"]

    avg_confidence = total_confidence / len(tasks) if tasks else 0.0

    return EmailStatsResponse(
        total_processed=len(tasks),
        today_processed=len(today_tasks),
        by_task_type=by_task_type,
        by_urgency=by_urgency,
        avg_confidence=avg_confidence,
    )


# ============================================================================
# Processed Emails Endpoint
# ============================================================================


@router.get("/processed/{tenant_id}", response_model=list[ProcessedEmailResponse])
async def list_processed_emails(
    tenant_id: UUID,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
) -> list[ProcessedEmailResponse]:
    """List processed emails for a tenant.

    Returns email tasks with classification details.
    """
    task_repo = TaskRepository(db)

    filters = {"tenant_id": tenant_id, "source_type": "email"}
    tasks = await task_repo.list(
        filters=filters,
        limit=limit,
        offset=offset,
        order_by="created_at",
        order_desc=True,
    )

    results = []
    for task in tasks:
        results.append(
            ProcessedEmailResponse(
                id=str(task.id),
                subject=task.title,
                sender_email=task.customer_email or "",
                sender_name=task.customer_name,
                received_at=task.created_at,
                task_type=task.task_type,
                urgency=task.urgency,
                trade_category=task.trade_category or "allgemein",
                confidence=task.metadata_json.get("classification_confidence", 0.0) if task.metadata_json else 0.0,
                task_id=str(task.id),
                auto_reply_sent=task.metadata_json.get("auto_reply_sent", False) if task.metadata_json else False,
            )
        )

    return results
