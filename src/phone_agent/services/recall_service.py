"""Recall Campaign Service.

Provides business logic for patient recall campaigns including:
- Campaign CRUD operations
- Contact management within campaigns
- Call scheduling and tracking
- Metrics aggregation
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any, Sequence
from uuid import UUID

from sqlalchemy import Integer, and_, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from itf_shared import get_logger

from phone_agent.db.models.analytics import (
    CampaignContactModel,
    CampaignMetricsModel,
    RecallCampaignModel,
)

log = get_logger(__name__)


class RecallServiceError(Exception):
    """Recall service error."""

    pass


class RecallService:
    """Service for managing recall campaigns.

    Provides database-backed campaign and contact management with
    support for scheduling, tracking, and metrics.

    Usage:
        async with get_session() as session:
            service = RecallService(session)
            campaign = await service.create_campaign(
                name="Vorsorge Q1 2025",
                campaign_type="vorsorge",
                industry="gesundheit",
                start_date=date.today(),
            )
            await service.add_contacts(campaign.id, contact_ids)
    """

    def __init__(self, session: AsyncSession) -> None:
        """Initialize service with database session.

        Args:
            session: SQLAlchemy async session
        """
        self.session = session

    # =========================================================================
    # Campaign CRUD
    # =========================================================================

    async def create_campaign(
        self,
        name: str,
        campaign_type: str,
        industry: str,
        start_date: date,
        end_date: date | None = None,
        description: str | None = None,
        target_criteria: dict[str, Any] | None = None,
        max_attempts: int = 3,
        call_interval_hours: int = 24,
        priority: int = 5,
        call_script: str | None = None,
        sms_template: str | None = None,
        tenant_id: UUID | None = None,
    ) -> RecallCampaignModel:
        """Create a new recall campaign.

        Args:
            name: Campaign name
            campaign_type: Type (vorsorge, impfung, kontrolle, etc.)
            industry: Industry vertical
            start_date: Campaign start date
            end_date: Optional end date
            description: Campaign description
            target_criteria: JSON criteria for targeting
            max_attempts: Maximum call attempts per contact
            call_interval_hours: Hours between retry attempts
            priority: Campaign priority (1-10)
            call_script: Call script template
            sms_template: SMS template for follow-up
            tenant_id: Optional tenant ID

        Returns:
            Created campaign model
        """
        campaign = RecallCampaignModel(
            name=name,
            campaign_type=campaign_type,
            industry=industry,
            start_date=start_date,
            end_date=end_date,
            description=description,
            max_attempts=max_attempts,
            call_interval_hours=call_interval_hours,
            priority=priority,
            call_script=call_script,
            sms_template=sms_template,
            tenant_id=tenant_id,
            status="draft",
        )

        if target_criteria:
            campaign.target_criteria = target_criteria

        self.session.add(campaign)
        await self.session.commit()
        await self.session.refresh(campaign)

        log.info(f"Created campaign: {campaign.id} - {name}")
        return campaign

    async def get_campaign(self, campaign_id: UUID) -> RecallCampaignModel | None:
        """Get campaign by ID.

        Args:
            campaign_id: Campaign UUID

        Returns:
            Campaign model or None
        """
        result = await self.session.execute(
            select(RecallCampaignModel).where(RecallCampaignModel.id == campaign_id)
        )
        return result.scalar_one_or_none()

    async def list_campaigns(
        self,
        status: str | None = None,
        industry: str | None = None,
        campaign_type: str | None = None,
        tenant_id: UUID | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> Sequence[RecallCampaignModel]:
        """List campaigns with optional filters.

        Args:
            status: Filter by status
            industry: Filter by industry
            campaign_type: Filter by type
            tenant_id: Filter by tenant
            limit: Maximum results
            offset: Result offset

        Returns:
            List of campaigns
        """
        query = select(RecallCampaignModel)

        conditions = []
        if status:
            conditions.append(RecallCampaignModel.status == status)
        if industry:
            conditions.append(RecallCampaignModel.industry == industry)
        if campaign_type:
            conditions.append(RecallCampaignModel.campaign_type == campaign_type)
        if tenant_id:
            conditions.append(RecallCampaignModel.tenant_id == tenant_id)

        if conditions:
            query = query.where(and_(*conditions))

        query = query.order_by(
            RecallCampaignModel.priority,
            RecallCampaignModel.start_date.desc(),
        ).limit(limit).offset(offset)

        result = await self.session.execute(query)
        return result.scalars().all()

    async def update_campaign(
        self,
        campaign_id: UUID,
        **updates: Any,
    ) -> RecallCampaignModel | None:
        """Update campaign fields.

        Args:
            campaign_id: Campaign UUID
            **updates: Fields to update

        Returns:
            Updated campaign or None
        """
        campaign = await self.get_campaign(campaign_id)
        if not campaign:
            return None

        # Handle special fields
        if "target_criteria" in updates:
            campaign.target_criteria = updates.pop("target_criteria")

        # Update other fields
        for key, value in updates.items():
            if hasattr(campaign, key):
                setattr(campaign, key, value)

        await self.session.commit()
        await self.session.refresh(campaign)

        log.info(f"Updated campaign: {campaign_id}")
        return campaign

    async def delete_campaign(self, campaign_id: UUID) -> bool:
        """Delete a campaign and all related data.

        Args:
            campaign_id: Campaign UUID

        Returns:
            True if deleted
        """
        campaign = await self.get_campaign(campaign_id)
        if not campaign:
            return False

        await self.session.delete(campaign)
        await self.session.commit()

        log.info(f"Deleted campaign: {campaign_id}")
        return True

    async def activate_campaign(self, campaign_id: UUID) -> RecallCampaignModel | None:
        """Activate a draft campaign.

        Changes status from 'draft' to 'active' and schedules contacts.

        Args:
            campaign_id: Campaign UUID

        Returns:
            Activated campaign or None
        """
        campaign = await self.get_campaign(campaign_id)
        if not campaign:
            return None

        if campaign.status != "draft":
            raise RecallServiceError(f"Cannot activate campaign in status: {campaign.status}")

        campaign.status = "active"

        # Schedule all pending contacts
        await self._schedule_pending_contacts(campaign_id)

        await self.session.commit()
        await self.session.refresh(campaign)

        log.info(f"Activated campaign: {campaign_id}")
        return campaign

    async def pause_campaign(self, campaign_id: UUID) -> RecallCampaignModel | None:
        """Pause an active campaign.

        Args:
            campaign_id: Campaign UUID

        Returns:
            Paused campaign or None
        """
        campaign = await self.get_campaign(campaign_id)
        if not campaign:
            return None

        if campaign.status != "active":
            raise RecallServiceError(f"Cannot pause campaign in status: {campaign.status}")

        campaign.status = "paused"
        await self.session.commit()
        await self.session.refresh(campaign)

        log.info(f"Paused campaign: {campaign_id}")
        return campaign

    async def resume_campaign(self, campaign_id: UUID) -> RecallCampaignModel | None:
        """Resume a paused campaign.

        Args:
            campaign_id: Campaign UUID

        Returns:
            Resumed campaign or None
        """
        campaign = await self.get_campaign(campaign_id)
        if not campaign:
            return None

        if campaign.status != "paused":
            raise RecallServiceError(f"Cannot resume campaign in status: {campaign.status}")

        campaign.status = "active"
        await self.session.commit()
        await self.session.refresh(campaign)

        log.info(f"Resumed campaign: {campaign_id}")
        return campaign

    async def complete_campaign(self, campaign_id: UUID) -> RecallCampaignModel | None:
        """Mark campaign as completed.

        Args:
            campaign_id: Campaign UUID

        Returns:
            Completed campaign or None
        """
        campaign = await self.get_campaign(campaign_id)
        if not campaign:
            return None

        campaign.status = "completed"
        campaign.end_date = date.today()
        await self.session.commit()
        await self.session.refresh(campaign)

        log.info(f"Completed campaign: {campaign_id}")
        return campaign

    # =========================================================================
    # Contact Management
    # =========================================================================

    async def add_contact(
        self,
        campaign_id: UUID,
        contact_id: UUID,
        phone_number: str,
        contact_name: str | None = None,
        priority: int = 5,
        custom_data: dict[str, Any] | None = None,
    ) -> CampaignContactModel:
        """Add a single contact to a campaign.

        Args:
            campaign_id: Campaign UUID
            contact_id: CRM contact UUID
            phone_number: Phone number to call
            contact_name: Contact name
            priority: Contact priority
            custom_data: Custom data for personalization

        Returns:
            Created campaign contact
        """
        campaign = await self.get_campaign(campaign_id)
        if not campaign:
            raise RecallServiceError(f"Campaign not found: {campaign_id}")

        contact = CampaignContactModel(
            campaign_id=campaign_id,
            contact_id=contact_id,
            phone_number=phone_number,
            contact_name=contact_name,
            priority=priority,
            max_attempts=campaign.max_attempts,
            status="pending",
        )

        if custom_data:
            contact.custom_data = custom_data

        # Schedule first attempt if campaign is active
        if campaign.status == "active":
            contact.next_attempt_at = datetime.now()
            contact.status = "scheduled"

        self.session.add(contact)

        # Update campaign contact count
        campaign.total_contacts += 1

        await self.session.commit()
        await self.session.refresh(contact)

        return contact

    async def add_contacts_bulk(
        self,
        campaign_id: UUID,
        contacts: list[dict[str, Any]],
    ) -> int:
        """Add multiple contacts to a campaign.

        Args:
            campaign_id: Campaign UUID
            contacts: List of contact dicts with keys:
                - contact_id: UUID
                - phone_number: str
                - contact_name: str (optional)
                - priority: int (optional)
                - custom_data: dict (optional)

        Returns:
            Number of contacts added
        """
        campaign = await self.get_campaign(campaign_id)
        if not campaign:
            raise RecallServiceError(f"Campaign not found: {campaign_id}")

        added = 0
        for contact_data in contacts:
            try:
                contact = CampaignContactModel(
                    campaign_id=campaign_id,
                    contact_id=contact_data["contact_id"],
                    phone_number=contact_data["phone_number"],
                    contact_name=contact_data.get("contact_name"),
                    priority=contact_data.get("priority", 5),
                    max_attempts=campaign.max_attempts,
                    status="pending" if campaign.status != "active" else "scheduled",
                )

                if contact_data.get("custom_data"):
                    contact.custom_data = contact_data["custom_data"]

                if campaign.status == "active":
                    contact.next_attempt_at = datetime.now()

                self.session.add(contact)
                added += 1

            except Exception as e:
                log.warning(f"Failed to add contact: {e}")
                continue

        # Update campaign contact count
        campaign.total_contacts += added

        await self.session.commit()

        log.info(f"Added {added} contacts to campaign {campaign_id}")
        return added

    async def get_campaign_contacts(
        self,
        campaign_id: UUID,
        status: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> Sequence[CampaignContactModel]:
        """Get contacts in a campaign.

        Args:
            campaign_id: Campaign UUID
            status: Filter by status
            limit: Maximum results
            offset: Result offset

        Returns:
            List of campaign contacts
        """
        query = select(CampaignContactModel).where(
            CampaignContactModel.campaign_id == campaign_id
        )

        if status:
            query = query.where(CampaignContactModel.status == status)

        query = query.order_by(
            CampaignContactModel.priority,
            CampaignContactModel.next_attempt_at,
        ).limit(limit).offset(offset)

        result = await self.session.execute(query)
        return result.scalars().all()

    async def get_contact(self, contact_id: UUID) -> CampaignContactModel | None:
        """Get campaign contact by ID.

        Args:
            contact_id: Contact UUID

        Returns:
            Contact model or None
        """
        result = await self.session.execute(
            select(CampaignContactModel).where(CampaignContactModel.id == contact_id)
        )
        return result.scalar_one_or_none()

    async def remove_contact(self, contact_id: UUID) -> bool:
        """Remove a contact from a campaign.

        Args:
            contact_id: Contact UUID

        Returns:
            True if removed
        """
        contact = await self.get_contact(contact_id)
        if not contact:
            return False

        campaign = await self.get_campaign(contact.campaign_id)
        if campaign:
            campaign.total_contacts = max(0, campaign.total_contacts - 1)

        await self.session.delete(contact)
        await self.session.commit()

        return True

    async def opt_out_contact(self, contact_id: UUID) -> CampaignContactModel | None:
        """Mark contact as opted out.

        Args:
            contact_id: Contact UUID

        Returns:
            Updated contact or None
        """
        contact = await self.get_contact(contact_id)
        if not contact:
            return None

        contact.status = "opted_out"
        contact.opted_out = True
        contact.opted_out_at = datetime.now()
        contact.next_attempt_at = None

        await self.session.commit()
        await self.session.refresh(contact)

        return contact

    # =========================================================================
    # Call Scheduling
    # =========================================================================

    async def get_contacts_to_call(
        self,
        limit: int = 10,
        campaign_id: UUID | None = None,
    ) -> Sequence[CampaignContactModel]:
        """Get contacts that are due for calling.

        Returns contacts where:
        - Campaign is active
        - Status is 'scheduled'
        - next_attempt_at <= now
        - Ordered by priority and next_attempt_at

        Args:
            limit: Maximum contacts to return
            campaign_id: Optional filter by campaign

        Returns:
            List of contacts ready to call
        """
        now = datetime.now()

        query = (
            select(CampaignContactModel)
            .join(RecallCampaignModel)
            .where(
                and_(
                    RecallCampaignModel.status == "active",
                    CampaignContactModel.status == "scheduled",
                    CampaignContactModel.next_attempt_at <= now,
                )
            )
        )

        if campaign_id:
            query = query.where(CampaignContactModel.campaign_id == campaign_id)

        query = query.order_by(
            CampaignContactModel.priority,
            CampaignContactModel.next_attempt_at,
        ).limit(limit)

        result = await self.session.execute(query)
        return result.scalars().all()

    async def record_call_attempt(
        self,
        contact_id: UUID,
        result: str,
        duration: int | None = None,
        call_id: UUID | None = None,
        notes: str | None = None,
    ) -> CampaignContactModel | None:
        """Record the result of a call attempt.

        Args:
            contact_id: Campaign contact UUID
            result: Call result (answered, voicemail, no_answer, busy, failed)
            duration: Call duration in seconds
            call_id: Reference to call record
            notes: Call notes

        Returns:
            Updated contact or None
        """
        contact = await self.get_contact(contact_id)
        if not contact:
            return None

        campaign = await self.get_campaign(contact.campaign_id)
        if not campaign:
            return None

        # Record the attempt
        contact.record_attempt(result, duration, call_id)

        if notes:
            contact.notes = notes

        # Update campaign stats
        campaign.contacts_called += 1
        if result == "answered":
            campaign.contacts_reached += 1

        # Schedule next attempt if needed
        if contact.can_attempt() and result != "answered":
            contact.schedule_next_attempt(campaign.call_interval_hours)

        await self.session.commit()
        await self.session.refresh(contact)

        log.info(f"Recorded call attempt for contact {contact_id}: {result}")
        return contact

    async def record_conversion(
        self,
        contact_id: UUID,
        outcome: str,
        appointment_id: UUID | None = None,
        notes: str | None = None,
    ) -> CampaignContactModel | None:
        """Record a successful conversion.

        Args:
            contact_id: Campaign contact UUID
            outcome: Conversion outcome (appointment_booked, callback_requested, etc.)
            appointment_id: Optional appointment reference
            notes: Notes

        Returns:
            Updated contact or None
        """
        contact = await self.get_contact(contact_id)
        if not contact:
            return None

        campaign = await self.get_campaign(contact.campaign_id)
        if not campaign:
            return None

        contact.convert(outcome, appointment_id)

        if notes:
            contact.notes = notes

        # Update campaign stats
        if outcome == "appointment_booked":
            campaign.appointments_booked += 1

        await self.session.commit()
        await self.session.refresh(contact)

        log.info(f"Recorded conversion for contact {contact_id}: {outcome}")
        return contact

    async def _schedule_pending_contacts(self, campaign_id: UUID) -> int:
        """Schedule all pending contacts for immediate calling.

        Args:
            campaign_id: Campaign UUID

        Returns:
            Number of contacts scheduled
        """
        now = datetime.now()

        result = await self.session.execute(
            update(CampaignContactModel)
            .where(
                and_(
                    CampaignContactModel.campaign_id == campaign_id,
                    CampaignContactModel.status == "pending",
                )
            )
            .values(status="scheduled", next_attempt_at=now)
        )

        await self.session.commit()
        return result.rowcount

    # =========================================================================
    # Metrics and Reporting
    # =========================================================================

    async def get_campaign_stats(self, campaign_id: UUID) -> dict[str, Any]:
        """Get comprehensive campaign statistics.

        Args:
            campaign_id: Campaign UUID

        Returns:
            Statistics dictionary
        """
        campaign = await self.get_campaign(campaign_id)
        if not campaign:
            return {}

        # Count contacts by status
        status_counts = await self.session.execute(
            select(
                CampaignContactModel.status,
                func.count(CampaignContactModel.id),
            )
            .where(CampaignContactModel.campaign_id == campaign_id)
            .group_by(CampaignContactModel.status)
        )
        status_dict = dict(status_counts.all())

        # Count by outcome
        outcome_counts = await self.session.execute(
            select(
                CampaignContactModel.outcome,
                func.count(CampaignContactModel.id),
            )
            .where(
                and_(
                    CampaignContactModel.campaign_id == campaign_id,
                    CampaignContactModel.outcome.isnot(None),
                )
            )
            .group_by(CampaignContactModel.outcome)
        )
        outcome_dict = dict(outcome_counts.all())

        # Average attempts
        avg_attempts = await self.session.execute(
            select(func.avg(CampaignContactModel.attempts))
            .where(
                and_(
                    CampaignContactModel.campaign_id == campaign_id,
                    CampaignContactModel.attempts > 0,
                )
            )
        )
        avg_attempts_value = avg_attempts.scalar_one_or_none() or 0

        return {
            "campaign_id": str(campaign_id),
            "campaign_name": campaign.name,
            "status": campaign.status,
            "total_contacts": campaign.total_contacts,
            "contacts_called": campaign.contacts_called,
            "contacts_reached": campaign.contacts_reached,
            "appointments_booked": campaign.appointments_booked,
            "status_breakdown": status_dict,
            "outcome_breakdown": outcome_dict,
            "average_attempts": round(avg_attempts_value, 2),
            "progress": campaign.calculate_progress(),
        }

    async def update_campaign_metrics(self, campaign_id: UUID) -> None:
        """Recalculate and update campaign denormalized metrics.

        Args:
            campaign_id: Campaign UUID
        """
        campaign = await self.get_campaign(campaign_id)
        if not campaign:
            return

        # Count totals from contacts
        counts = await self.session.execute(
            select(
                func.count(CampaignContactModel.id).label("total"),
                func.sum(
                    func.cast(CampaignContactModel.attempts > 0, Integer)
                ).label("called"),
                func.sum(
                    func.cast(CampaignContactModel.status == "reached", Integer)
                ).label("reached"),
                func.sum(
                    func.cast(CampaignContactModel.status == "converted", Integer)
                ).label("converted"),
            )
            .where(CampaignContactModel.campaign_id == campaign_id)
        )
        row = counts.one()

        campaign.total_contacts = row.total or 0
        campaign.contacts_called = row.called or 0
        campaign.contacts_reached = row.reached or 0
        campaign.appointments_booked = row.converted or 0

        await self.session.commit()
