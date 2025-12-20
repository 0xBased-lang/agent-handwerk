"""Notification service for SMS, Telegram, and push notifications.

Supports:
- ETA notifications (technician on the way)
- Appointment confirmations and reminders
- Post-job feedback requests
- Job status updates
"""

from __future__ import annotations

from datetime import datetime, timezone, timedelta
from typing import Any
from uuid import UUID

from itf_shared import get_logger

from phone_agent.db.models.sms import SMSMessageModel
from phone_agent.db.models.handwerk import JobModel
from phone_agent.db.repositories.sms import SMSMessageRepository
from phone_agent.db.repositories.jobs import JobRepository
from phone_agent.industry.handwerk.prompts import (
    SMS_TECHNICIAN_ETA,
    SMS_APPOINTMENT_CONFIRMATION,
    SMS_APPOINTMENT_REMINDER,
)

log = get_logger(__name__)


# Default company settings (should come from tenant config in production)
DEFAULT_COMPANY_NAME = "IT-Friends Elektro"
DEFAULT_COMPANY_PHONE = "+49 30 12345678"


class NotificationService:
    """Service for sending notifications via SMS and other channels.

    Handles ETA notifications, appointment reminders, and feedback requests.
    """

    def __init__(
        self,
        sms_repo: SMSMessageRepository,
        job_repo: JobRepository,
        company_name: str = DEFAULT_COMPANY_NAME,
        company_phone: str = DEFAULT_COMPANY_PHONE,
        sms_provider: str = "mock",
    ):
        """Initialize the notification service.

        Args:
            sms_repo: SMS message repository
            job_repo: Job repository
            company_name: Company name for SMS templates
            company_phone: Company phone for SMS templates
            sms_provider: SMS provider (mock, twilio, sipgate)
        """
        self.sms_repo = sms_repo
        self.job_repo = job_repo
        self.company_name = company_name
        self.company_phone = company_phone
        self.sms_provider = sms_provider

    async def send_eta_notification(
        self,
        job_id: UUID,
        eta_minutes: int = 15,
        technician_name: str | None = None,
    ) -> dict[str, Any]:
        """Send ETA notification to customer.

        Sends SMS: "Techniker unterwegs, Ankunft in ca. X Minuten"

        Args:
            job_id: Job UUID
            eta_minutes: Estimated time of arrival in minutes
            technician_name: Optional technician name

        Returns:
            Dict with notification status and message ID
        """
        # Get job with customer info
        job = await self.job_repo.get_with_relations(job_id)
        if not job:
            log.warning("Job not found for ETA notification", job_id=str(job_id))
            return {"success": False, "error": "Job not found"}

        if not job.contact:
            log.warning("Job has no contact for ETA", job_id=str(job_id))
            return {"success": False, "error": "No customer contact"}

        phone = job.contact.phone_primary
        if not phone:
            log.warning("Customer has no phone", job_id=str(job_id))
            return {"success": False, "error": "No customer phone number"}

        # Calculate ETA time
        eta_time = datetime.now() + timedelta(minutes=eta_minutes)
        eta_time_str = eta_time.strftime("%H:%M")

        # Format SMS message
        sms_body = SMS_TECHNICIAN_ETA.format(
            Firmenname=self.company_name,
            Uhrzeit=eta_time_str,
            X=eta_minutes,
            Telefonnummer=self.company_phone,
        )

        # Create SMS record
        sms = await self.sms_repo.create(
            SMSMessageModel(
                to_number=phone,
                from_number=self.company_phone,
                body=sms_body,
                provider=self.sms_provider,
                status="pending",
                message_type="eta_notification",
                metadata_json={
                    "job_id": str(job_id),
                    "job_number": job.job_number,
                    "eta_minutes": eta_minutes,
                    "eta_time": eta_time.isoformat(),
                    "technician_name": technician_name,
                },
            )
        )

        # Update job metadata to track ETA notification sent
        job_metadata = job.metadata_json or {}
        job_metadata["eta_notification_sent"] = True
        job_metadata["eta_notification_time"] = datetime.now(timezone.utc).isoformat()
        job_metadata["eta_minutes"] = eta_minutes
        job_metadata["eta_sms_id"] = str(sms.id)
        await self.job_repo.update(job.id, {"metadata_json": job_metadata})

        # Send the SMS (mock implementation - in production would call actual provider)
        await self._send_sms(sms)

        log.info(
            "ETA notification sent",
            job_id=str(job_id),
            job_number=job.job_number,
            phone=phone,
            eta_minutes=eta_minutes,
            sms_id=str(sms.id),
        )

        return {
            "success": True,
            "sms_id": str(sms.id),
            "phone": phone,
            "eta_minutes": eta_minutes,
            "eta_time": eta_time_str,
            "message": sms_body,
        }

    async def send_appointment_confirmation(
        self,
        job_id: UUID,
        date_str: str,
        time_window: str,
    ) -> dict[str, Any]:
        """Send appointment confirmation SMS.

        Args:
            job_id: Job UUID
            date_str: Appointment date string (e.g., "23.12.2024")
            time_window: Time window description (e.g., "Vormittags (8-12 Uhr)")

        Returns:
            Dict with notification status
        """
        job = await self.job_repo.get_with_relations(job_id)
        if not job or not job.contact:
            return {"success": False, "error": "Job or contact not found"}

        phone = job.contact.phone_primary
        if not phone:
            return {"success": False, "error": "No customer phone number"}

        sms_body = SMS_APPOINTMENT_CONFIRMATION.format(
            Firmenname=self.company_name,
            Datum=date_str,
            Zeitfenster=time_window,
            Telefonnummer=self.company_phone,
        )

        sms = await self.sms_repo.create(
            SMSMessageModel(
                to_number=phone,
                from_number=self.company_phone,
                body=sms_body,
                provider=self.sms_provider,
                status="pending",
                message_type="confirmation",
                metadata_json={
                    "job_id": str(job_id),
                    "job_number": job.job_number,
                    "date": date_str,
                    "time_window": time_window,
                },
            )
        )

        await self._send_sms(sms)

        return {
            "success": True,
            "sms_id": str(sms.id),
            "message": sms_body,
        }

    async def send_appointment_reminder(
        self,
        job_id: UUID,
        time_window: str,
    ) -> dict[str, Any]:
        """Send appointment reminder SMS (day before).

        Args:
            job_id: Job UUID
            time_window: Time window description

        Returns:
            Dict with notification status
        """
        job = await self.job_repo.get_with_relations(job_id)
        if not job or not job.contact:
            return {"success": False, "error": "Job or contact not found"}

        phone = job.contact.phone_primary
        if not phone:
            return {"success": False, "error": "No customer phone number"}

        sms_body = SMS_APPOINTMENT_REMINDER.format(
            Firmenname=self.company_name,
            Zeitfenster=time_window,
            Telefonnummer=self.company_phone,
        )

        sms = await self.sms_repo.create(
            SMSMessageModel(
                to_number=phone,
                from_number=self.company_phone,
                body=sms_body,
                provider=self.sms_provider,
                status="pending",
                message_type="reminder",
                metadata_json={
                    "job_id": str(job_id),
                    "job_number": job.job_number,
                    "time_window": time_window,
                },
            )
        )

        await self._send_sms(sms)

        return {
            "success": True,
            "sms_id": str(sms.id),
            "message": sms_body,
        }

    async def send_feedback_request(
        self,
        job_id: UUID,
        feedback_url: str | None = None,
    ) -> dict[str, Any]:
        """Send post-job feedback request SMS.

        Args:
            job_id: Job UUID
            feedback_url: Optional feedback form URL

        Returns:
            Dict with notification status
        """
        job = await self.job_repo.get_with_relations(job_id)
        if not job or not job.contact:
            return {"success": False, "error": "Job or contact not found"}

        phone = job.contact.phone_primary
        if not phone:
            return {"success": False, "error": "No customer phone number"}

        # Build feedback message
        if feedback_url:
            sms_body = (
                f"{self.company_name}: Vielen Dank für Ihren Auftrag!\n"
                f"Wir freuen uns über Ihre Bewertung:\n{feedback_url}"
            )
        else:
            sms_body = (
                f"{self.company_name}: Vielen Dank für Ihren Auftrag {job.job_number}!\n"
                f"Waren Sie zufrieden? Antworten Sie mit 1-5 (1=sehr gut, 5=schlecht).\n"
                f"Fragen: {self.company_phone}"
            )

        sms = await self.sms_repo.create(
            SMSMessageModel(
                to_number=phone,
                from_number=self.company_phone,
                body=sms_body,
                provider=self.sms_provider,
                status="pending",
                message_type="feedback_request",
                metadata_json={
                    "job_id": str(job_id),
                    "job_number": job.job_number,
                    "feedback_url": feedback_url,
                },
            )
        )

        await self._send_sms(sms)

        # Update job metadata
        job_metadata = job.metadata_json or {}
        job_metadata["feedback_requested"] = True
        job_metadata["feedback_request_time"] = datetime.now(timezone.utc).isoformat()
        job_metadata["feedback_sms_id"] = str(sms.id)
        await self.job_repo.update(job.id, {"metadata_json": job_metadata})

        return {
            "success": True,
            "sms_id": str(sms.id),
            "message": sms_body,
        }

    async def get_notification_history(
        self,
        job_id: UUID,
    ) -> list[dict[str, Any]]:
        """Get notification history for a job.

        Args:
            job_id: Job UUID

        Returns:
            List of notification records
        """
        # Get all SMS for this job via metadata search
        all_sms = await self.sms_repo.get_by_date_range(
            date_from=datetime.now().date() - timedelta(days=90),
            date_to=datetime.now().date(),
            limit=100,
        )

        # Filter by job_id in metadata
        job_notifications = []
        for sms in all_sms:
            if sms.metadata_json and sms.metadata_json.get("job_id") == str(job_id):
                job_notifications.append(sms.to_dict())

        return job_notifications

    async def _send_sms(self, sms: SMSMessageModel) -> None:
        """Send SMS via provider.

        In production, this would call Twilio/sipgate API.
        For now, marks as sent immediately.

        Args:
            sms: SMS message model
        """
        if self.sms_provider == "mock":
            # Mock provider - just mark as sent
            sms.mark_sent(provider_message_id=f"mock-{sms.id}")
            log.info(
                "Mock SMS sent",
                sms_id=str(sms.id),
                to=sms.to_number,
                body_preview=sms.body[:50],
            )
        else:
            # TODO: Implement actual SMS provider integration
            # For twilio: use twilio client to send
            # For sipgate: use sipgate API
            sms.mark_queued()
            log.info(
                "SMS queued for sending",
                sms_id=str(sms.id),
                provider=self.sms_provider,
            )

        await self.sms_repo.update(sms)


# Singleton instance
_notification_service: NotificationService | None = None


def get_notification_service(
    sms_repo: SMSMessageRepository,
    job_repo: JobRepository,
) -> NotificationService:
    """Get or create notification service.

    Args:
        sms_repo: SMS repository
        job_repo: Job repository

    Returns:
        NotificationService instance
    """
    global _notification_service
    if _notification_service is None:
        _notification_service = NotificationService(
            sms_repo=sms_repo,
            job_repo=job_repo,
        )
    return _notification_service
