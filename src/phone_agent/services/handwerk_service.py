"""Handwerk service for job creation and management.

Includes automatic translation of job descriptions to German
for multilingual customer support.
"""

from datetime import datetime
from typing import Any
from uuid import UUID

from itf_shared import get_logger

from phone_agent.db.models.crm import ContactModel
from phone_agent.db.models.handwerk import JobModel, JobStatus
from phone_agent.db.repositories import ContactRepository, JobRepository
from phone_agent.services.translation_service import TranslationService, TranslationResult

log = get_logger(__name__)


class HandwerkService:
    """Service for Handwerk job intake and management.

    Supports multilingual customer input with automatic translation
    to German for database storage.
    """

    def __init__(
        self,
        contact_repo: ContactRepository,
        job_repo: JobRepository,
        translation_service: TranslationService | None = None,
    ):
        """Initialize the service.

        Args:
            contact_repo: Contact repository
            job_repo: Job repository
            translation_service: Optional translation service (created lazily if not provided)
        """
        self.contact_repo = contact_repo
        self.job_repo = job_repo
        self._translation_service = translation_service

    async def create_job_from_intake(
        self,
        customer_name: str,
        description: str,
        trade_category: str,
        urgency: str,
        customer_phone: str | None = None,
        address: dict[str, Any] | None = None,
        session_id: str | None = None,
        source_language: str = "de",
    ) -> dict[str, Any]:
        """Create a job from customer intake.

        Automatically translates non-German descriptions to German for database storage.
        Original text is preserved in metadata.

        Args:
            customer_name: Customer name
            description: Problem description (in any supported language)
            trade_category: Trade category (shk, elektro, etc.)
            urgency: Urgency level (notfall, dringend, normal, routine)
            customer_phone: Customer phone number (optional)
            address: Customer address dict (optional)
            session_id: Chat session ID (optional)
            source_language: Language of the description (de, ru, tr) - default "de"

        Returns:
            Dict with job details
        """
        # Find or create contact
        contact = await self._get_or_create_contact(
            name=customer_name,
            phone=customer_phone,
            address=address,
        )

        # Generate job number with timestamp for uniqueness
        now = datetime.now()
        job_number = f"JOB-{now.year}-{now.strftime('%m%d%H%M%S')}"

        # Translate description to German if needed
        german_description = description
        original_description = None
        translation_success = True

        if source_language != "de" and description:
            log.info(
                "Translating job description to German",
                source_lang=source_language,
                description_preview=description[:50],
            )

            # Lazy initialize translation service
            if self._translation_service is None:
                self._translation_service = TranslationService()

            translation_result = await self._translation_service.translate_to_german(
                text=description,
                source_language=source_language,
            )

            german_description = translation_result.german_text
            original_description = translation_result.original_text
            translation_success = translation_result.success

            if translation_result.was_translated:
                log.info(
                    "Job description translated",
                    original_lang=source_language,
                    original_preview=original_description[:50] if original_description else "",
                    german_preview=german_description[:50],
                )

        # Build metadata with language info
        metadata = {
            "session_id": session_id,
            "created_via": "web_chat",
            "source_language": source_language,
        }
        if original_description:
            metadata["original_description"] = original_description
        if not translation_success:
            metadata["translation_failed"] = True

        # Create job with German description
        job = await self.job_repo.create(
            JobModel(
                job_number=job_number,
                contact_id=contact.id,
                trade_category=trade_category,
                urgency=urgency,
                status=JobStatus.REQUESTED,
                title=f"{trade_category.upper()} - {german_description[:50]}",
                description=german_description,
                # Address fields
                address_street=address.get("street") if address else None,
                address_number=address.get("number") if address else None,
                address_zip=address.get("zip") if address else None,
                address_city=address.get("city") if address else None,
                # Metadata
                metadata_json=metadata,
            )
        )

        # Generate confirmation message in customer's language
        confirmation_messages = {
            "de": f"Ihr Auftrag {job.job_number} wurde erstellt. Wir melden uns in Kürze.",
            "ru": f"Ваш заказ {job.job_number} создан. Мы свяжемся с вами в ближайшее время.",
            "tr": f"Siparişiniz {job.job_number} oluşturuldu. En kısa sürede sizinle iletişime geçeceğiz.",
            "en": f"Your job {job.job_number} has been created. We will contact you shortly.",
        }

        return {
            "job_id": str(job.id),
            "job_number": job.job_number,
            "status": job.status,
            "contact_id": str(contact.id),
            "trade_category": job.trade_category,
            "urgency": job.urgency,
            "message": confirmation_messages.get(source_language, confirmation_messages["de"]),
            "source_language": source_language,
            "was_translated": source_language != "de",
        }

    async def _get_or_create_contact(
        self,
        name: str,
        phone: str | None = None,
        address: dict[str, Any] | None = None,
    ) -> ContactModel:
        """Find existing contact or create new one.

        Args:
            name: Contact name
            phone: Phone number (optional)
            address: Address dict (optional)

        Returns:
            ContactModel instance
        """
        # Try to find by phone first
        if phone:
            existing = await self.contact_repo.find_by_phone(phone, industry="handwerk")
            if existing:
                return existing[0]

        # Parse name into first/last
        name_parts = name.split(" ", 1)
        first_name = name_parts[0]
        last_name = name_parts[1] if len(name_parts) > 1 else ""

        # Create new contact
        contact = await self.contact_repo.create(
            ContactModel(
                first_name=first_name,
                last_name=last_name,
                phone_primary=phone,
                industry="handwerk",
                contact_type="customer",
                source="web_chat",
                # Address fields
                street=address.get("street") if address else None,
                street_number=address.get("number") if address else None,
                zip_code=address.get("zip") if address else None,
                city=address.get("city") if address else None,
                country="Deutschland",
            )
        )

        return contact

    async def get_job(self, job_id: UUID) -> JobModel | None:
        """Get job by ID.

        Args:
            job_id: Job UUID

        Returns:
            JobModel or None
        """
        return await self.job_repo.get(job_id)

    async def get_job_by_number(self, job_number: str) -> JobModel | None:
        """Get job by job number.

        Args:
            job_number: Job number (e.g., JOB-2024-0001)

        Returns:
            JobModel or None
        """
        return await self.job_repo.get_by_number(job_number)

    async def update_job_status(
        self,
        job_id: UUID,
        status: str,
        notes: str | None = None,
    ) -> JobModel:
        """Update job status.

        Args:
            job_id: Job UUID
            status: New status
            notes: Optional notes

        Returns:
            Updated JobModel
        """
        job = await self.job_repo.get(job_id)
        if not job:
            raise ValueError(f"Job {job_id} not found")

        job.status = status
        if notes:
            job.internal_notes = (job.internal_notes or "") + f"\n{notes}"

        return await self.job_repo.update(job)

    async def assign_technician(
        self,
        job_id: UUID,
        technician_id: UUID,
    ) -> JobModel:
        """Assign technician to job.

        Args:
            job_id: Job UUID
            technician_id: Technician contact ID

        Returns:
            Updated JobModel
        """
        job = await self.job_repo.get(job_id)
        if not job:
            raise ValueError(f"Job {job_id} not found")

        job.technician_id = technician_id
        job.status = JobStatus.SCHEDULED

        return await self.job_repo.update(job)
