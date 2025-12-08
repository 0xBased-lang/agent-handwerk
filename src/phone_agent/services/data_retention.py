"""Data Retention Service for DSGVO Compliance.

Automated cleanup of data based on retention policies:
- Scheduled job that runs periodically
- Archives data before permanent deletion
- Full audit trail of all deletions
- Configurable retention policies per resource type

German healthcare law requires:
- Medical records: 10 years (§ 10 MBO-Ä, § 630f BGB)
- Call recordings: 1 year (archive after 30 days)
- Audit logs: 5 years (Art. 5, 30 DSGVO)

Usage:
    from phone_agent.services.data_retention import (
        DataRetentionService,
        start_retention_scheduler,
        stop_retention_scheduler,
    )

    # Start scheduled cleanup (runs daily at 3 AM)
    await start_retention_scheduler()

    # Or run manually
    service = DataRetentionService()
    results = await service.run_cleanup()
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any
from uuid import UUID

logger = logging.getLogger(__name__)


class RetentionAction(str, Enum):
    """Actions taken on expired data."""
    ARCHIVED = "archived"
    DELETED = "deleted"
    SKIPPED = "skipped"
    FAILED = "failed"


@dataclass
class RetentionPolicy:
    """Data retention policy configuration."""
    resource_type: str
    retention_days: int
    archive_after_days: int | None = None
    legal_basis: str = ""
    description: str = ""
    enabled: bool = True


@dataclass
class RetentionResult:
    """Result of retention cleanup for one resource type."""
    resource_type: str
    scanned_count: int = 0
    archived_count: int = 0
    deleted_count: int = 0
    skipped_count: int = 0
    failed_count: int = 0
    errors: list[str] = field(default_factory=list)
    duration_seconds: float = 0.0


@dataclass
class CleanupReport:
    """Full report of retention cleanup run."""
    started_at: datetime
    completed_at: datetime | None = None
    results: list[RetentionResult] = field(default_factory=list)
    total_archived: int = 0
    total_deleted: int = 0
    total_errors: int = 0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for logging/API."""
        return {
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "duration_seconds": (
                (self.completed_at - self.started_at).total_seconds()
                if self.completed_at else None
            ),
            "total_archived": self.total_archived,
            "total_deleted": self.total_deleted,
            "total_errors": self.total_errors,
            "results": [
                {
                    "resource_type": r.resource_type,
                    "scanned": r.scanned_count,
                    "archived": r.archived_count,
                    "deleted": r.deleted_count,
                    "failed": r.failed_count,
                    "duration": r.duration_seconds,
                }
                for r in self.results
            ],
        }


# Default retention policies (German healthcare law)
DEFAULT_POLICIES: list[RetentionPolicy] = [
    RetentionPolicy(
        resource_type="call_recordings",
        retention_days=365,  # 1 year
        archive_after_days=30,
        legal_basis="Art. 6 DSGVO - Berechtigtes Interesse",
        description="Anrufaufzeichnungen zur Qualitätssicherung",
    ),
    RetentionPolicy(
        resource_type="call_transcripts",
        retention_days=365,  # 1 year
        archive_after_days=30,
        legal_basis="Art. 6 DSGVO - Berechtigtes Interesse",
        description="Transkripte zur Qualitätssicherung",
    ),
    RetentionPolicy(
        resource_type="appointment_records",
        retention_days=10 * 365,  # 10 years
        archive_after_days=365,  # Archive after 1 year
        legal_basis="§ 630f BGB",
        description="Terminaufzeichnungen als Teil der Behandlungsdokumentation",
    ),
    RetentionPolicy(
        resource_type="audit_logs",
        retention_days=5 * 365,  # 5 years
        legal_basis="Art. 5, 30 DSGVO",
        description="Verarbeitungsprotokolle",
    ),
    RetentionPolicy(
        resource_type="sms_messages",
        retention_days=365,  # 1 year
        archive_after_days=30,
        legal_basis="Art. 6 DSGVO",
        description="SMS-Kommunikation",
    ),
    RetentionPolicy(
        resource_type="email_messages",
        retention_days=365,  # 1 year
        archive_after_days=30,
        legal_basis="Art. 6 DSGVO",
        description="E-Mail-Kommunikation",
    ),
]


class DataRetentionService:
    """Service for managing data retention and cleanup.

    Implements DSGVO-compliant data retention with:
    - Configurable policies per resource type
    - Archive before delete option
    - Full audit trail
    - Dry-run mode for testing
    """

    def __init__(self, policies: list[RetentionPolicy] | None = None):
        """Initialize retention service.

        Args:
            policies: Custom policies (defaults to German healthcare law)
        """
        self._policies = {p.resource_type: p for p in (policies or DEFAULT_POLICIES)}

    def get_policy(self, resource_type: str) -> RetentionPolicy | None:
        """Get retention policy for a resource type."""
        return self._policies.get(resource_type)

    async def run_cleanup(
        self,
        dry_run: bool = False,
        resource_types: list[str] | None = None,
    ) -> CleanupReport:
        """Run data retention cleanup.

        Args:
            dry_run: If True, only report what would be deleted
            resource_types: Specific types to clean (None = all)

        Returns:
            Cleanup report with statistics
        """
        report = CleanupReport(started_at=datetime.now(timezone.utc))

        policies_to_run = (
            [self._policies[rt] for rt in resource_types if rt in self._policies]
            if resource_types
            else [p for p in self._policies.values() if p.enabled]
        )

        for policy in policies_to_run:
            try:
                result = await self._cleanup_resource_type(policy, dry_run=dry_run)
                report.results.append(result)
                report.total_archived += result.archived_count
                report.total_deleted += result.deleted_count
                report.total_errors += result.failed_count
            except Exception as e:
                logger.error(f"Failed to cleanup {policy.resource_type}: {e}")
                report.results.append(
                    RetentionResult(
                        resource_type=policy.resource_type,
                        failed_count=1,
                        errors=[str(e)],
                    )
                )
                report.total_errors += 1

        report.completed_at = datetime.now(timezone.utc)

        # Log audit entry for the cleanup run
        await self._log_cleanup_audit(report, dry_run=dry_run)

        logger.info(
            "Data retention cleanup completed",
            dry_run=dry_run,
            archived=report.total_archived,
            deleted=report.total_deleted,
            errors=report.total_errors,
        )

        return report

    async def _cleanup_resource_type(
        self,
        policy: RetentionPolicy,
        dry_run: bool = False,
    ) -> RetentionResult:
        """Clean up a specific resource type.

        Args:
            policy: Retention policy to apply
            dry_run: If True, only count without deleting

        Returns:
            Result statistics
        """
        import time
        start_time = time.time()

        result = RetentionResult(resource_type=policy.resource_type)
        now = datetime.now(timezone.utc)

        # Calculate cutoff dates
        archive_cutoff = (
            now - timedelta(days=policy.archive_after_days)
            if policy.archive_after_days
            else None
        )
        delete_cutoff = now - timedelta(days=policy.retention_days)

        try:
            from phone_agent.db.session import get_db_context

            async with get_db_context() as session:
                if policy.resource_type == "call_recordings":
                    result = await self._cleanup_calls(
                        session, archive_cutoff, delete_cutoff, dry_run
                    )
                elif policy.resource_type == "call_transcripts":
                    result = await self._cleanup_transcripts(
                        session, archive_cutoff, delete_cutoff, dry_run
                    )
                elif policy.resource_type == "audit_logs":
                    result = await self._cleanup_audit_logs(
                        session, delete_cutoff, dry_run
                    )
                elif policy.resource_type == "sms_messages":
                    result = await self._cleanup_sms(
                        session, archive_cutoff, delete_cutoff, dry_run
                    )
                elif policy.resource_type == "email_messages":
                    result = await self._cleanup_emails(
                        session, archive_cutoff, delete_cutoff, dry_run
                    )
                elif policy.resource_type == "appointment_records":
                    result = await self._cleanup_appointments(
                        session, archive_cutoff, delete_cutoff, dry_run
                    )
                else:
                    logger.warning(f"Unknown resource type: {policy.resource_type}")
                    result.skipped_count = 1

                result.resource_type = policy.resource_type

        except Exception as e:
            logger.error(f"Error cleaning {policy.resource_type}: {e}")
            result.failed_count = 1
            result.errors.append(str(e))

        result.duration_seconds = time.time() - start_time
        return result

    async def _cleanup_calls(
        self,
        session,
        archive_cutoff: datetime | None,
        delete_cutoff: datetime,
        dry_run: bool,
    ) -> RetentionResult:
        """Clean up call records."""
        from sqlalchemy import select, func, update, delete as sql_delete
        from phone_agent.db.models import CallModel

        result = RetentionResult(resource_type="call_recordings")

        # Count records to process
        count_stmt = (
            select(func.count())
            .select_from(CallModel)
            .where(CallModel.created_at < delete_cutoff)
        )
        count_result = await session.execute(count_stmt)
        result.scanned_count = count_result.scalar() or 0

        if dry_run:
            result.deleted_count = result.scanned_count
            return result

        # Archive old calls (set transcript/summary to anonymized)
        if archive_cutoff:
            archive_stmt = (
                update(CallModel)
                .where(
                    CallModel.created_at < archive_cutoff,
                    CallModel.transcript.isnot(None),
                )
                .values(
                    transcript="[ARCHIVED]",
                    summary="[ARCHIVED]",
                )
            )
            archive_result = await session.execute(archive_stmt)
            result.archived_count = archive_result.rowcount

        # Delete very old calls
        delete_stmt = sql_delete(CallModel).where(CallModel.created_at < delete_cutoff)
        delete_result = await session.execute(delete_stmt)
        result.deleted_count = delete_result.rowcount

        await session.commit()
        return result

    async def _cleanup_transcripts(
        self,
        session,
        archive_cutoff: datetime | None,
        delete_cutoff: datetime,
        dry_run: bool,
    ) -> RetentionResult:
        """Clean up call transcripts (separate from call records)."""
        from sqlalchemy import select, func, update
        from phone_agent.db.models import CallModel

        result = RetentionResult(resource_type="call_transcripts")

        # Count transcripts to process
        count_stmt = (
            select(func.count())
            .select_from(CallModel)
            .where(
                CallModel.created_at < delete_cutoff,
                CallModel.transcript.isnot(None),
                CallModel.transcript != "[ARCHIVED]",
            )
        )
        count_result = await session.execute(count_stmt)
        result.scanned_count = count_result.scalar() or 0

        if dry_run:
            result.deleted_count = result.scanned_count
            return result

        # Clear transcripts (anonymize)
        update_stmt = (
            update(CallModel)
            .where(
                CallModel.created_at < delete_cutoff,
                CallModel.transcript.isnot(None),
                CallModel.transcript != "[ARCHIVED]",
            )
            .values(transcript=None, summary=None)
        )
        update_result = await session.execute(update_stmt)
        result.deleted_count = update_result.rowcount

        await session.commit()
        return result

    async def _cleanup_audit_logs(
        self,
        session,
        delete_cutoff: datetime,
        dry_run: bool,
    ) -> RetentionResult:
        """Clean up old audit logs."""
        from sqlalchemy import select, func, delete as sql_delete
        from phone_agent.db.models.compliance import AuditLogModel

        result = RetentionResult(resource_type="audit_logs")

        # Count logs to delete
        count_stmt = (
            select(func.count())
            .select_from(AuditLogModel)
            .where(AuditLogModel.timestamp < delete_cutoff)
        )
        count_result = await session.execute(count_stmt)
        result.scanned_count = count_result.scalar() or 0

        if dry_run:
            result.deleted_count = result.scanned_count
            return result

        # Delete old audit logs
        delete_stmt = sql_delete(AuditLogModel).where(
            AuditLogModel.timestamp < delete_cutoff
        )
        delete_result = await session.execute(delete_stmt)
        result.deleted_count = delete_result.rowcount

        await session.commit()
        return result

    async def _cleanup_sms(
        self,
        session,
        archive_cutoff: datetime | None,
        delete_cutoff: datetime,
        dry_run: bool,
    ) -> RetentionResult:
        """Clean up SMS messages."""
        from sqlalchemy import select, func, update, delete as sql_delete
        from phone_agent.db.models.sms import SMSMessageModel

        result = RetentionResult(resource_type="sms_messages")

        # Count messages
        count_stmt = (
            select(func.count())
            .select_from(SMSMessageModel)
            .where(SMSMessageModel.created_at < delete_cutoff)
        )
        count_result = await session.execute(count_stmt)
        result.scanned_count = count_result.scalar() or 0

        if dry_run:
            result.deleted_count = result.scanned_count
            return result

        # Archive (anonymize body)
        if archive_cutoff:
            archive_stmt = (
                update(SMSMessageModel)
                .where(
                    SMSMessageModel.created_at < archive_cutoff,
                    SMSMessageModel.body.isnot(None),
                    SMSMessageModel.body != "[ARCHIVED]",
                )
                .values(body="[ARCHIVED]")
            )
            archive_result = await session.execute(archive_stmt)
            result.archived_count = archive_result.rowcount

        # Delete very old
        delete_stmt = sql_delete(SMSMessageModel).where(
            SMSMessageModel.created_at < delete_cutoff
        )
        delete_result = await session.execute(delete_stmt)
        result.deleted_count = delete_result.rowcount

        await session.commit()
        return result

    async def _cleanup_emails(
        self,
        session,
        archive_cutoff: datetime | None,
        delete_cutoff: datetime,
        dry_run: bool,
    ) -> RetentionResult:
        """Clean up email messages."""
        from sqlalchemy import select, func, update, delete as sql_delete
        from phone_agent.db.models.email import EmailMessageModel

        result = RetentionResult(resource_type="email_messages")

        # Count messages
        count_stmt = (
            select(func.count())
            .select_from(EmailMessageModel)
            .where(EmailMessageModel.created_at < delete_cutoff)
        )
        count_result = await session.execute(count_stmt)
        result.scanned_count = count_result.scalar() or 0

        if dry_run:
            result.deleted_count = result.scanned_count
            return result

        # Archive
        if archive_cutoff:
            archive_stmt = (
                update(EmailMessageModel)
                .where(
                    EmailMessageModel.created_at < archive_cutoff,
                    EmailMessageModel.body.isnot(None),
                )
                .values(body="[ARCHIVED]", subject="[ARCHIVED]")
            )
            archive_result = await session.execute(archive_stmt)
            result.archived_count = archive_result.rowcount

        # Delete
        delete_stmt = sql_delete(EmailMessageModel).where(
            EmailMessageModel.created_at < delete_cutoff
        )
        delete_result = await session.execute(delete_stmt)
        result.deleted_count = delete_result.rowcount

        await session.commit()
        return result

    async def _cleanup_appointments(
        self,
        session,
        archive_cutoff: datetime | None,
        delete_cutoff: datetime,
        dry_run: bool,
    ) -> RetentionResult:
        """Clean up appointment records."""
        from sqlalchemy import select, func, update
        from phone_agent.db.models import AppointmentModel

        result = RetentionResult(resource_type="appointment_records")

        # Count old appointments
        count_stmt = (
            select(func.count())
            .select_from(AppointmentModel)
            .where(AppointmentModel.created_at < delete_cutoff)
        )
        count_result = await session.execute(count_stmt)
        result.scanned_count = count_result.scalar() or 0

        if dry_run:
            # Note: We don't delete medical records, only anonymize
            result.archived_count = result.scanned_count
            return result

        # Archive (anonymize PII but keep for legal compliance)
        if archive_cutoff:
            archive_stmt = (
                update(AppointmentModel)
                .where(AppointmentModel.created_at < archive_cutoff)
                .values(
                    patient_name="[ANONYMIZED]",
                    patient_phone="[ANONYMIZED]",
                    patient_email=None,
                    notes="[ARCHIVED]",
                )
            )
            archive_result = await session.execute(archive_stmt)
            result.archived_count = archive_result.rowcount

        # Note: We don't delete appointment records due to legal requirements
        # They are anonymized after archive period

        await session.commit()
        return result

    async def _log_cleanup_audit(
        self,
        report: CleanupReport,
        dry_run: bool = False,
    ) -> None:
        """Log audit entry for cleanup run."""
        try:
            from phone_agent.industry.gesundheit.compliance import (
                get_audit_logger,
                AuditAction,
            )

            logger_instance = get_audit_logger()
            logger_instance.log(
                action=AuditAction.CONFIG_CHANGE,
                actor_id="data_retention_service",
                actor_type="system",
                resource_type="retention_cleanup",
                details={
                    "dry_run": dry_run,
                    "archived": report.total_archived,
                    "deleted": report.total_deleted,
                    "errors": report.total_errors,
                    "results": [r.resource_type for r in report.results],
                },
            )
        except Exception as e:
            logger.error(f"Failed to log cleanup audit: {e}")


# Scheduler for periodic cleanup
_retention_scheduler_task: asyncio.Task | None = None
_scheduler_running = False


async def _retention_scheduler_loop(
    interval_hours: float = 24.0,
    run_at_hour: int = 3,  # 3 AM
) -> None:
    """Background scheduler loop.

    Args:
        interval_hours: Hours between cleanup runs
        run_at_hour: Hour of day to run (0-23, in local time)
    """
    service = DataRetentionService()

    while _scheduler_running:
        try:
            # Calculate time until next run
            now = datetime.now()
            next_run = now.replace(
                hour=run_at_hour,
                minute=0,
                second=0,
                microsecond=0,
            )

            if next_run <= now:
                next_run += timedelta(days=1)

            wait_seconds = (next_run - now).total_seconds()

            logger.info(
                f"Data retention scheduler: next run at {next_run.isoformat()}"
            )

            await asyncio.sleep(wait_seconds)

            if not _scheduler_running:
                break

            # Run cleanup
            logger.info("Starting scheduled data retention cleanup")
            report = await service.run_cleanup(dry_run=False)

            logger.info(
                "Scheduled cleanup completed",
                archived=report.total_archived,
                deleted=report.total_deleted,
                errors=report.total_errors,
            )

        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Retention scheduler error: {e}")
            await asyncio.sleep(3600)  # Wait 1 hour on error


async def start_retention_scheduler(
    interval_hours: float = 24.0,
    run_at_hour: int = 3,
) -> None:
    """Start the data retention scheduler.

    Args:
        interval_hours: Hours between runs (default: 24)
        run_at_hour: Hour to run (0-23, default: 3 AM)
    """
    global _retention_scheduler_task, _scheduler_running

    if _scheduler_running:
        logger.warning("Retention scheduler already running")
        return

    _scheduler_running = True
    _retention_scheduler_task = asyncio.create_task(
        _retention_scheduler_loop(interval_hours, run_at_hour)
    )
    logger.info("Data retention scheduler started")


async def stop_retention_scheduler() -> None:
    """Stop the data retention scheduler."""
    global _retention_scheduler_task, _scheduler_running

    _scheduler_running = False

    if _retention_scheduler_task:
        _retention_scheduler_task.cancel()
        try:
            await _retention_scheduler_task
        except asyncio.CancelledError:
            pass
        _retention_scheduler_task = None

    logger.info("Data retention scheduler stopped")


async def run_cleanup_now(dry_run: bool = True) -> CleanupReport:
    """Run data retention cleanup immediately.

    Args:
        dry_run: If True, only report what would be deleted

    Returns:
        Cleanup report
    """
    service = DataRetentionService()
    return await service.run_cleanup(dry_run=dry_run)
