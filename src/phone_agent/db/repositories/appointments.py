"""Appointment Repository for Phone Agent.

Specialized repository for appointment-related database operations.
Extends BaseRepository with appointment-specific queries.
"""
from __future__ import annotations

from datetime import datetime, date, time, timedelta
from typing import Sequence, Any
from uuid import UUID

from sqlalchemy import select, func, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from phone_agent.db.models.core import AppointmentModel
from phone_agent.db.repositories.base import BaseRepository


class AppointmentRepository(BaseRepository[AppointmentModel]):
    """Repository for appointment database operations.

    Provides specialized queries for appointment management,
    scheduling, and analytics.
    """

    def __init__(self, session: AsyncSession):
        """Initialize with session.

        Args:
            session: Async database session
        """
        super().__init__(AppointmentModel, session)

    # ========================================================================
    # Query by Status
    # ========================================================================

    async def get_by_status(
        self,
        status: str,
        *,
        skip: int = 0,
        limit: int = 100,
    ) -> Sequence[AppointmentModel]:
        """Get appointments by status.

        Args:
            status: Appointment status (scheduled, confirmed, etc.)
            skip: Pagination offset
            limit: Maximum results

        Returns:
            List of appointments with given status
        """
        stmt = (
            select(self._model)
            .where(self._model.status == status)
            .order_by(self._model.appointment_date, self._model.appointment_time)
            .offset(skip)
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return result.scalars().all()

    async def get_by_type(
        self,
        appointment_type: str,
        *,
        skip: int = 0,
        limit: int = 100,
    ) -> Sequence[AppointmentModel]:
        """Get appointments by type.

        Args:
            appointment_type: Appointment type (consultation, checkup, etc.)
            skip: Pagination offset
            limit: Maximum results

        Returns:
            List of appointments of given type
        """
        stmt = (
            select(self._model)
            .where(self._model.appointment_type == appointment_type)
            .order_by(self._model.appointment_date, self._model.appointment_time)
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
        industry: str | None = None,
        skip: int = 0,
        limit: int = 1000,
    ) -> Sequence[AppointmentModel]:
        """Get appointments within a date range.

        Args:
            date_from: Start date (inclusive)
            date_to: End date (inclusive)
            status: Optional status filter
            industry: Optional industry filter
            skip: Pagination offset
            limit: Maximum results

        Returns:
            List of appointments in date range
        """
        conditions = [
            self._model.appointment_date >= date_from,
            self._model.appointment_date <= date_to,
        ]

        if status:
            conditions.append(self._model.status == status)
        if industry:
            conditions.append(self._model.industry == industry)

        stmt = (
            select(self._model)
            .where(and_(*conditions))
            .order_by(self._model.appointment_date, self._model.appointment_time)
            .offset(skip)
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return result.scalars().all()

    async def get_for_date(
        self,
        target_date: date,
        *,
        status: str | None = None,
    ) -> Sequence[AppointmentModel]:
        """Get all appointments for a specific date.

        Args:
            target_date: Date to query
            status: Optional status filter

        Returns:
            List of appointments for the date
        """
        conditions = [self._model.appointment_date == target_date]

        if status:
            conditions.append(self._model.status == status)

        stmt = (
            select(self._model)
            .where(and_(*conditions))
            .order_by(self._model.appointment_time)
        )
        result = await self._session.execute(stmt)
        return result.scalars().all()

    async def get_today(self, industry: str | None = None) -> Sequence[AppointmentModel]:
        """Get all appointments for today.

        Args:
            industry: Optional industry filter

        Returns:
            List of today's appointments
        """
        today = date.today()
        conditions = [self._model.appointment_date == today]

        if industry:
            conditions.append(self._model.industry == industry)

        stmt = (
            select(self._model)
            .where(and_(*conditions))
            .order_by(self._model.appointment_time)
        )
        result = await self._session.execute(stmt)
        return result.scalars().all()

    async def get_upcoming(
        self,
        days: int = 7,
        *,
        industry: str | None = None,
        limit: int = 100,
    ) -> Sequence[AppointmentModel]:
        """Get upcoming appointments.

        Args:
            days: Number of days to look ahead
            industry: Optional industry filter
            limit: Maximum results

        Returns:
            List of upcoming appointments
        """
        today = date.today()
        end_date = today + timedelta(days=days)

        conditions = [
            self._model.appointment_date >= today,
            self._model.appointment_date <= end_date,
            self._model.status.in_(["scheduled", "confirmed"]),
        ]

        if industry:
            conditions.append(self._model.industry == industry)

        stmt = (
            select(self._model)
            .where(and_(*conditions))
            .order_by(self._model.appointment_date, self._model.appointment_time)
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return result.scalars().all()

    # ========================================================================
    # Contact-based Queries
    # ========================================================================

    async def get_by_contact(
        self,
        contact_id: UUID,
        *,
        skip: int = 0,
        limit: int = 50,
    ) -> Sequence[AppointmentModel]:
        """Get appointments for a specific contact.

        Args:
            contact_id: Contact UUID
            skip: Pagination offset
            limit: Maximum results

        Returns:
            List of appointments for the contact
        """
        # Contact_id is stored as string, convert for comparison
        contact_id_str = str(contact_id)
        stmt = (
            select(self._model)
            .where(self._model.contact_id == contact_id_str)
            .order_by(self._model.appointment_date.desc(), self._model.appointment_time.desc())
            .offset(skip)
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return result.scalars().all()

    async def get_next_for_contact(self, contact_id: UUID) -> AppointmentModel | None:
        """Get the next upcoming appointment for a contact.

        Args:
            contact_id: Contact UUID

        Returns:
            Next appointment or None
        """
        today = date.today()
        now = datetime.now().time()

        stmt = (
            select(self._model)
            .where(
                and_(
                    self._model.contact_id == contact_id,
                    self._model.status.in_(["scheduled", "confirmed"]),
                    or_(
                        self._model.appointment_date > today,
                        and_(
                            self._model.appointment_date == today,
                            self._model.appointment_time > now,
                        ),
                    ),
                )
            )
            .order_by(self._model.appointment_date, self._model.appointment_time)
            .limit(1)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    # ========================================================================
    # Scheduling Queries
    # ========================================================================

    async def check_slot_availability(
        self,
        target_date: date,
        target_time: time,
        duration_minutes: int = 15,
        exclude_id: UUID | None = None,
    ) -> bool:
        """Check if a time slot is available.

        Args:
            target_date: Date to check
            target_time: Time to check
            duration_minutes: Duration of the slot
            exclude_id: Optional appointment ID to exclude (for updates)

        Returns:
            True if slot is available
        """
        # Check for overlapping appointments
        conditions = [
            self._model.appointment_date == target_date,
            self._model.status.in_(["scheduled", "confirmed"]),
        ]

        if exclude_id:
            conditions.append(self._model.id != exclude_id)

        stmt = select(self._model).where(and_(*conditions))
        result = await self._session.execute(stmt)
        existing = result.scalars().all()

        # Check for time conflicts
        target_start = datetime.combine(target_date, target_time)
        target_end = target_start + timedelta(minutes=duration_minutes)

        for apt in existing:
            apt_start = datetime.combine(apt.appointment_date, apt.appointment_time)
            apt_end = apt_start + timedelta(minutes=apt.duration_minutes or 15)

            # Check for overlap
            if target_start < apt_end and target_end > apt_start:
                return False

        return True

    async def get_conflicts(
        self,
        target_date: date,
        target_time: time,
        duration_minutes: int = 15,
    ) -> Sequence[AppointmentModel]:
        """Get appointments that conflict with a proposed time slot.

        Args:
            target_date: Date to check
            target_time: Time to check
            duration_minutes: Duration of the slot

        Returns:
            List of conflicting appointments
        """
        # Get all appointments for the date
        stmt = (
            select(self._model)
            .where(
                and_(
                    self._model.appointment_date == target_date,
                    self._model.status.in_(["scheduled", "confirmed"]),
                )
            )
        )
        result = await self._session.execute(stmt)
        existing = result.scalars().all()

        # Check for time conflicts
        target_start = datetime.combine(target_date, target_time)
        target_end = target_start + timedelta(minutes=duration_minutes)

        conflicts = []
        for apt in existing:
            apt_start = datetime.combine(apt.appointment_date, apt.appointment_time)
            apt_end = apt_start + timedelta(minutes=apt.duration_minutes or 15)

            if target_start < apt_end and target_end > apt_start:
                conflicts.append(apt)

        return conflicts

    # ========================================================================
    # Reminder Queries
    # ========================================================================

    async def get_needing_reminder(
        self,
        hours_ahead: int = 24,
    ) -> Sequence[AppointmentModel]:
        """Get appointments that need reminders sent.

        Args:
            hours_ahead: How many hours before appointment to send reminder

        Returns:
            List of appointments needing reminders
        """
        now = datetime.utcnow()
        reminder_cutoff = now + timedelta(hours=hours_ahead)

        # Convert to date and time for comparison
        cutoff_date = reminder_cutoff.date()
        cutoff_time = reminder_cutoff.time()

        stmt = (
            select(self._model)
            .where(
                and_(
                    self._model.reminder_sent == False,
                    self._model.status.in_(["scheduled", "confirmed"]),
                    or_(
                        self._model.appointment_date < cutoff_date,
                        and_(
                            self._model.appointment_date == cutoff_date,
                            self._model.appointment_time <= cutoff_time,
                        ),
                    ),
                )
            )
            .order_by(self._model.appointment_date, self._model.appointment_time)
        )
        result = await self._session.execute(stmt)
        return result.scalars().all()

    async def mark_reminder_sent(self, appointment_id: UUID) -> AppointmentModel | None:
        """Mark appointment reminder as sent.

        Args:
            appointment_id: Appointment UUID

        Returns:
            Updated appointment or None
        """
        return await self.update(appointment_id, {
            "reminder_sent": True,
            "reminder_sent_at": datetime.utcnow(),
        })

    # ========================================================================
    # Analytics Queries
    # ========================================================================

    async def count_by_status(
        self,
        date_from: date | None = None,
        date_to: date | None = None,
        industry: str | None = None,
    ) -> dict[str, int]:
        """Count appointments grouped by status.

        Args:
            date_from: Optional start date filter
            date_to: Optional end date filter
            industry: Optional industry filter

        Returns:
            Dictionary of status -> count
        """
        stmt = (
            select(self._model.status, func.count().label("count"))
            .group_by(self._model.status)
        )

        conditions = []
        if date_from:
            conditions.append(self._model.appointment_date >= date_from)
        if date_to:
            conditions.append(self._model.appointment_date <= date_to)
        if industry:
            conditions.append(self._model.industry == industry)

        if conditions:
            stmt = stmt.where(and_(*conditions))

        result = await self._session.execute(stmt)
        return {row[0]: row[1] for row in result.all()}

    async def get_no_show_rate(
        self,
        date_from: date,
        date_to: date,
        industry: str | None = None,
    ) -> float:
        """Calculate no-show rate for a period.

        Args:
            date_from: Start date
            date_to: End date
            industry: Optional industry filter

        Returns:
            No-show rate as percentage
        """
        conditions = [
            self._model.appointment_date >= date_from,
            self._model.appointment_date <= date_to,
            self._model.status.in_(["completed", "no_show"]),
        ]

        if industry:
            conditions.append(self._model.industry == industry)

        # Get total completed + no_show
        total_stmt = select(func.count()).select_from(self._model).where(and_(*conditions))
        total_result = await self._session.execute(total_stmt)
        total = total_result.scalar() or 0

        if total == 0:
            return 0.0

        # Get no_show count
        no_show_conditions = conditions + [self._model.status == "no_show"]
        no_show_stmt = select(func.count()).select_from(self._model).where(and_(*no_show_conditions))
        no_show_result = await self._session.execute(no_show_stmt)
        no_shows = no_show_result.scalar() or 0

        return (no_shows / total) * 100

    async def get_daily_stats(
        self,
        target_date: date | None = None,
        industry: str | None = None,
    ) -> dict[str, Any]:
        """Get daily appointment statistics.

        Args:
            target_date: Date to analyze (default: today)
            industry: Optional industry filter

        Returns:
            Dictionary with daily statistics
        """
        if target_date is None:
            target_date = date.today()

        appointments = await self.get_for_date(target_date)

        total = len(appointments)
        if total == 0:
            return {
                "date": target_date.isoformat(),
                "total_appointments": 0,
                "scheduled": 0,
                "confirmed": 0,
                "completed": 0,
                "cancelled": 0,
                "no_shows": 0,
            }

        scheduled = sum(1 for a in appointments if a.status == "scheduled")
        confirmed = sum(1 for a in appointments if a.status == "confirmed")
        completed = sum(1 for a in appointments if a.status == "completed")
        cancelled = sum(1 for a in appointments if a.status == "cancelled")
        no_shows = sum(1 for a in appointments if a.status == "no_show")

        return {
            "date": target_date.isoformat(),
            "total_appointments": total,
            "scheduled": scheduled,
            "confirmed": confirmed,
            "completed": completed,
            "cancelled": cancelled,
            "no_shows": no_shows,
            "completion_rate": round((completed / total) * 100, 2) if total else 0.0,
            "no_show_rate": round((no_shows / (completed + no_shows)) * 100, 2) if (completed + no_shows) else 0.0,
        }
