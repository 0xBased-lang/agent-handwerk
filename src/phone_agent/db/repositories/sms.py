"""SMS Message Repository for Phone Agent.

Specialized repository for SMS message tracking and delivery status.
Extends BaseRepository with SMS-specific queries.
"""
from __future__ import annotations

from datetime import datetime, date, timedelta
from typing import Any, Sequence
from uuid import UUID

from sqlalchemy import select, func, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from phone_agent.db.models.sms import SMSMessageModel
from phone_agent.db.repositories.base import BaseRepository


class SMSMessageRepository(BaseRepository[SMSMessageModel]):
    """Repository for SMS message database operations.

    Provides specialized queries for SMS delivery tracking,
    retry management, and analytics.
    """

    def __init__(self, session: AsyncSession):
        """Initialize with session.

        Args:
            session: Async database session
        """
        super().__init__(SMSMessageModel, session)

    # ========================================================================
    # Provider Message Lookup
    # ========================================================================

    async def get_by_provider_message_id(
        self,
        provider_message_id: str,
    ) -> SMSMessageModel | None:
        """Get SMS by provider's external message ID.

        Used for webhook status updates.

        Args:
            provider_message_id: External message ID from provider

        Returns:
            SMS message or None
        """
        stmt = select(self._model).where(
            self._model.provider_message_id == provider_message_id
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_to_number(
        self,
        to_number: str,
        *,
        skip: int = 0,
        limit: int = 50,
    ) -> Sequence[SMSMessageModel]:
        """Get SMS messages sent to a specific phone number.

        Args:
            to_number: Recipient phone number
            skip: Pagination offset
            limit: Maximum results

        Returns:
            List of SMS messages
        """
        stmt = (
            select(self._model)
            .where(self._model.to_number == to_number)
            .order_by(self._model.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return result.scalars().all()

    # ========================================================================
    # Status-Based Queries
    # ========================================================================

    async def get_by_status(
        self,
        status: str,
        *,
        provider: str | None = None,
        skip: int = 0,
        limit: int = 100,
    ) -> Sequence[SMSMessageModel]:
        """Get SMS messages by status.

        Args:
            status: Message status (pending, sent, delivered, failed)
            provider: Optional provider filter
            skip: Pagination offset
            limit: Maximum results

        Returns:
            List of SMS messages with given status
        """
        conditions = [self._model.status == status]

        if provider:
            conditions.append(self._model.provider == provider)

        stmt = (
            select(self._model)
            .where(and_(*conditions))
            .order_by(self._model.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return result.scalars().all()

    async def get_pending(
        self,
        *,
        limit: int = 100,
    ) -> Sequence[SMSMessageModel]:
        """Get pending messages ready for sending.

        Args:
            limit: Maximum results

        Returns:
            List of pending SMS messages
        """
        stmt = (
            select(self._model)
            .where(
                and_(
                    self._model.status == "pending",
                    or_(
                        self._model.next_retry_at.is_(None),
                        self._model.next_retry_at <= datetime.now(),
                    ),
                )
            )
            .order_by(self._model.created_at)
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return result.scalars().all()

    async def get_failed(
        self,
        *,
        include_undelivered: bool = True,
        skip: int = 0,
        limit: int = 100,
    ) -> Sequence[SMSMessageModel]:
        """Get failed messages.

        Args:
            include_undelivered: Include undelivered status
            skip: Pagination offset
            limit: Maximum results

        Returns:
            List of failed SMS messages
        """
        statuses = ["failed"]
        if include_undelivered:
            statuses.append("undelivered")

        stmt = (
            select(self._model)
            .where(self._model.status.in_(statuses))
            .order_by(self._model.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return result.scalars().all()

    async def get_retryable(
        self,
        *,
        limit: int = 50,
    ) -> Sequence[SMSMessageModel]:
        """Get messages that can be retried.

        Args:
            limit: Maximum results

        Returns:
            List of retryable SMS messages
        """
        now = datetime.now()
        stmt = (
            select(self._model)
            .where(
                and_(
                    self._model.status.in_(["failed", "undelivered"]),
                    self._model.retry_count < self._model.max_retries,
                    or_(
                        self._model.next_retry_at.is_(None),
                        self._model.next_retry_at <= now,
                    ),
                )
            )
            .order_by(self._model.created_at)
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return result.scalars().all()

    # ========================================================================
    # Appointment-Based Queries
    # ========================================================================

    async def get_by_appointment(
        self,
        appointment_id: str | UUID,
        *,
        message_type: str | None = None,
    ) -> Sequence[SMSMessageModel]:
        """Get SMS messages for an appointment.

        Args:
            appointment_id: Appointment UUID
            message_type: Optional message type filter

        Returns:
            List of SMS messages for the appointment
        """
        conditions = [self._model.appointment_id == str(appointment_id)]

        if message_type:
            conditions.append(self._model.message_type == message_type)

        stmt = (
            select(self._model)
            .where(and_(*conditions))
            .order_by(self._model.created_at.desc())
        )
        result = await self._session.execute(stmt)
        return result.scalars().all()

    async def get_by_contact(
        self,
        contact_id: str | UUID,
        *,
        skip: int = 0,
        limit: int = 50,
    ) -> Sequence[SMSMessageModel]:
        """Get SMS messages for a contact.

        Args:
            contact_id: Contact UUID
            skip: Pagination offset
            limit: Maximum results

        Returns:
            List of SMS messages for the contact
        """
        stmt = (
            select(self._model)
            .where(self._model.contact_id == str(contact_id))
            .order_by(self._model.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return result.scalars().all()

    # ========================================================================
    # Date Range Queries
    # ========================================================================

    async def get_by_date_range(
        self,
        date_from: date,
        date_to: date,
        *,
        status: str | None = None,
        provider: str | None = None,
        message_type: str | None = None,
        skip: int = 0,
        limit: int = 1000,
    ) -> Sequence[SMSMessageModel]:
        """Get SMS messages within a date range.

        Args:
            date_from: Start date (inclusive)
            date_to: End date (inclusive)
            status: Optional status filter
            provider: Optional provider filter
            message_type: Optional message type filter
            skip: Pagination offset
            limit: Maximum results

        Returns:
            List of SMS messages in date range
        """
        start_datetime = datetime.combine(date_from, datetime.min.time())
        end_datetime = datetime.combine(date_to, datetime.max.time())

        conditions = [
            self._model.created_at >= start_datetime,
            self._model.created_at <= end_datetime,
        ]

        if status:
            conditions.append(self._model.status == status)
        if provider:
            conditions.append(self._model.provider == provider)
        if message_type:
            conditions.append(self._model.message_type == message_type)

        stmt = (
            select(self._model)
            .where(and_(*conditions))
            .order_by(self._model.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return result.scalars().all()

    async def get_today(
        self,
        *,
        status: str | None = None,
    ) -> Sequence[SMSMessageModel]:
        """Get SMS messages sent today.

        Args:
            status: Optional status filter

        Returns:
            List of today's SMS messages
        """
        today = date.today()
        return await self.get_by_date_range(today, today, status=status)

    # ========================================================================
    # Status Update Methods
    # ========================================================================

    async def update_status(
        self,
        message_id: UUID | str,
        status: str,
        *,
        error_code: str | None = None,
        error_message: str | None = None,
        cost: float | None = None,
    ) -> SMSMessageModel | None:
        """Update SMS message status.

        Args:
            message_id: SMS message UUID
            status: New status
            error_code: Optional error code
            error_message: Optional error message
            cost: Optional cost

        Returns:
            Updated SMS message or None
        """
        sms = await self.get(message_id)
        if sms is None:
            return None

        sms.status = status
        sms.record_webhook()

        if status == "queued":
            sms.queued_at = datetime.now()
        elif status == "sent":
            sms.sent_at = datetime.now()
        elif status == "delivered":
            sms.delivered_at = datetime.now()
        elif status in ("failed", "undelivered"):
            sms.failed_at = datetime.now()
            sms.error_code = error_code
            sms.error_message = error_message

        if cost is not None:
            sms.cost = cost

        await self._session.flush()
        await self._session.refresh(sms)
        return sms

    async def update_status_by_provider_id(
        self,
        provider_message_id: str,
        status: str,
        *,
        error_code: str | None = None,
        error_message: str | None = None,
        cost: float | None = None,
    ) -> SMSMessageModel | None:
        """Update SMS message status by provider message ID.

        Used for webhook status updates.

        Args:
            provider_message_id: External message ID from provider
            status: New status
            error_code: Optional error code
            error_message: Optional error message
            cost: Optional cost

        Returns:
            Updated SMS message or None
        """
        sms = await self.get_by_provider_message_id(provider_message_id)
        if sms is None:
            return None

        return await self.update_status(
            sms.id,
            status,
            error_code=error_code,
            error_message=error_message,
            cost=cost,
        )

    async def mark_for_retry(
        self,
        message_id: UUID | str,
        delay_seconds: int = 60,
    ) -> SMSMessageModel | None:
        """Mark a failed message for retry.

        Args:
            message_id: SMS message UUID
            delay_seconds: Seconds until next retry attempt

        Returns:
            Updated SMS message or None
        """
        sms = await self.get(message_id)
        if sms is None:
            return None

        if not sms.can_retry():
            return sms  # Can't retry, return as-is

        sms.increment_retry(delay_seconds)

        await self._session.flush()
        await self._session.refresh(sms)
        return sms

    # ========================================================================
    # Analytics Queries
    # ========================================================================

    async def count_by_status(
        self,
        date_from: date | None = None,
        date_to: date | None = None,
        provider: str | None = None,
    ) -> dict[str, int]:
        """Count SMS messages grouped by status.

        Args:
            date_from: Optional start date filter
            date_to: Optional end date filter
            provider: Optional provider filter

        Returns:
            Dictionary of status -> count
        """
        stmt = (
            select(self._model.status, func.count().label("count"))
            .group_by(self._model.status)
        )

        conditions = []
        if date_from:
            conditions.append(
                self._model.created_at >= datetime.combine(date_from, datetime.min.time())
            )
        if date_to:
            conditions.append(
                self._model.created_at <= datetime.combine(date_to, datetime.max.time())
            )
        if provider:
            conditions.append(self._model.provider == provider)

        if conditions:
            stmt = stmt.where(and_(*conditions))

        result = await self._session.execute(stmt)
        return {row[0]: row[1] for row in result.all()}

    async def count_by_provider(
        self,
        date_from: date | None = None,
        date_to: date | None = None,
    ) -> dict[str, int]:
        """Count SMS messages grouped by provider.

        Args:
            date_from: Optional start date filter
            date_to: Optional end date filter

        Returns:
            Dictionary of provider -> count
        """
        stmt = (
            select(self._model.provider, func.count().label("count"))
            .group_by(self._model.provider)
        )

        conditions = []
        if date_from:
            conditions.append(
                self._model.created_at >= datetime.combine(date_from, datetime.min.time())
            )
        if date_to:
            conditions.append(
                self._model.created_at <= datetime.combine(date_to, datetime.max.time())
            )

        if conditions:
            stmt = stmt.where(and_(*conditions))

        result = await self._session.execute(stmt)
        return {row[0]: row[1] for row in result.all()}

    async def count_by_message_type(
        self,
        date_from: date | None = None,
        date_to: date | None = None,
    ) -> dict[str, int]:
        """Count SMS messages grouped by message type.

        Args:
            date_from: Optional start date filter
            date_to: Optional end date filter

        Returns:
            Dictionary of message_type -> count
        """
        stmt = (
            select(self._model.message_type, func.count().label("count"))
            .group_by(self._model.message_type)
        )

        conditions = []
        if date_from:
            conditions.append(
                self._model.created_at >= datetime.combine(date_from, datetime.min.time())
            )
        if date_to:
            conditions.append(
                self._model.created_at <= datetime.combine(date_to, datetime.max.time())
            )

        if conditions:
            stmt = stmt.where(and_(*conditions))

        result = await self._session.execute(stmt)
        return {row[0]: row[1] for row in result.all()}

    async def get_delivery_rate(
        self,
        date_from: date,
        date_to: date,
        provider: str | None = None,
    ) -> float:
        """Calculate delivery rate for a period.

        Args:
            date_from: Start date
            date_to: End date
            provider: Optional provider filter

        Returns:
            Delivery rate as percentage
        """
        conditions = [
            self._model.created_at >= datetime.combine(date_from, datetime.min.time()),
            self._model.created_at <= datetime.combine(date_to, datetime.max.time()),
            self._model.status.in_(["delivered", "sent", "failed", "undelivered"]),
        ]

        if provider:
            conditions.append(self._model.provider == provider)

        # Get total sent/delivered/failed
        total_stmt = select(func.count()).select_from(self._model).where(and_(*conditions))
        total_result = await self._session.execute(total_stmt)
        total = total_result.scalar() or 0

        if total == 0:
            return 0.0

        # Get delivered count
        delivered_conditions = conditions + [self._model.status == "delivered"]
        delivered_stmt = (
            select(func.count()).select_from(self._model).where(and_(*delivered_conditions))
        )
        delivered_result = await self._session.execute(delivered_stmt)
        delivered = delivered_result.scalar() or 0

        return round((delivered / total) * 100, 2)

    async def get_total_cost(
        self,
        date_from: date,
        date_to: date,
        provider: str | None = None,
    ) -> float:
        """Calculate total SMS cost for a period.

        Args:
            date_from: Start date
            date_to: End date
            provider: Optional provider filter

        Returns:
            Total cost in EUR
        """
        conditions = [
            self._model.created_at >= datetime.combine(date_from, datetime.min.time()),
            self._model.created_at <= datetime.combine(date_to, datetime.max.time()),
            self._model.cost.isnot(None),
        ]

        if provider:
            conditions.append(self._model.provider == provider)

        stmt = select(func.sum(self._model.cost)).where(and_(*conditions))
        result = await self._session.execute(stmt)
        return result.scalar() or 0.0

    async def get_daily_stats(
        self,
        target_date: date | None = None,
        provider: str | None = None,
    ) -> dict[str, Any]:
        """Get daily SMS statistics.

        Args:
            target_date: Date to analyze (default: today)
            provider: Optional provider filter

        Returns:
            Dictionary with daily statistics
        """
        if target_date is None:
            target_date = date.today()

        messages = await self.get_by_date_range(
            target_date, target_date, provider=provider
        )

        total = len(messages)
        if total == 0:
            return {
                "date": target_date.isoformat(),
                "total_messages": 0,
                "pending": 0,
                "queued": 0,
                "sent": 0,
                "delivered": 0,
                "failed": 0,
                "undelivered": 0,
                "delivery_rate": 0.0,
                "total_cost": 0.0,
                "total_segments": 0,
            }

        pending = sum(1 for m in messages if m.status == "pending")
        queued = sum(1 for m in messages if m.status == "queued")
        sent = sum(1 for m in messages if m.status == "sent")
        delivered = sum(1 for m in messages if m.status == "delivered")
        failed = sum(1 for m in messages if m.status == "failed")
        undelivered = sum(1 for m in messages if m.status == "undelivered")

        # Calculate delivery rate (delivered / (delivered + sent + failed + undelivered))
        terminal = delivered + sent + failed + undelivered
        delivery_rate = round((delivered / terminal) * 100, 2) if terminal else 0.0

        total_cost = sum(m.cost for m in messages if m.cost is not None)
        total_segments = sum(m.segments for m in messages)

        return {
            "date": target_date.isoformat(),
            "total_messages": total,
            "pending": pending,
            "queued": queued,
            "sent": sent,
            "delivered": delivered,
            "failed": failed,
            "undelivered": undelivered,
            "delivery_rate": delivery_rate,
            "total_cost": round(total_cost, 4),
            "total_segments": total_segments,
        }
