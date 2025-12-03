"""Tests for database repositories."""

from __future__ import annotations

from datetime import date, time, datetime, timedelta
from uuid import uuid4

import pytest


# ============================================================================
# Contact Repository Tests
# ============================================================================

class TestContactRepository:
    """Tests for ContactRepository."""

    @pytest.mark.asyncio
    async def test_create_contact(self, db_session, contact_repository):
        """Test creating a contact."""
        from phone_agent.db.models.crm import ContactModel

        contact = ContactModel(
            id=uuid4(),
            first_name="Hans",
            last_name="Schmidt",
            phone_primary="+49111222333",
            contact_type="patient",
            industry="gesundheit",
        )

        created = await contact_repository.create(contact)
        await db_session.commit()

        assert created.id is not None
        assert created.first_name == "Hans"
        assert created.last_name == "Schmidt"
        assert created.full_name == "Hans Schmidt"

    @pytest.mark.asyncio
    async def test_get_contact(self, db_session, contact_repository):
        """Test retrieving a contact by ID."""
        from phone_agent.db.models.crm import ContactModel

        contact_id = uuid4()
        contact = ContactModel(
            id=contact_id,
            first_name="Maria",
            last_name="Müller",
            phone_primary="+49444555666",
            contact_type="patient",
            industry="gesundheit",
        )

        await contact_repository.create(contact)
        await db_session.commit()

        retrieved = await contact_repository.get(contact_id)

        assert retrieved is not None
        assert retrieved.id == contact_id
        assert retrieved.first_name == "Maria"

    @pytest.mark.asyncio
    async def test_search_by_name(self, db_session, contact_repository, sample_contact):
        """Test searching contacts by name."""
        results = await contact_repository.search_by_name("Muster")

        assert len(results) >= 1
        assert any(c.last_name == "Mustermann" for c in results)

    @pytest.mark.asyncio
    async def test_find_by_phone(self, db_session, contact_repository, sample_contact):
        """Test finding contact by phone number."""
        contact = await contact_repository.find_by_phone("+49123456789")

        assert contact is not None
        assert contact.phone_primary == "+49123456789"

    @pytest.mark.asyncio
    async def test_get_by_type(self, db_session, contact_repository, sample_contact):
        """Test getting contacts by type."""
        patients = await contact_repository.get_by_type("patient")

        assert len(patients) >= 1
        assert all(c.contact_type == "patient" for c in patients)

    @pytest.mark.asyncio
    async def test_update_contact(self, db_session, contact_repository, sample_contact):
        """Test updating a contact."""
        updated = await contact_repository.update(
            sample_contact.id,
            {"email": "updated@example.de"}
        )
        await db_session.commit()

        assert updated is not None
        assert updated.email == "updated@example.de"

    @pytest.mark.asyncio
    async def test_soft_delete(self, db_session, contact_repository, sample_contact):
        """Test soft deleting a contact."""
        deleted = await contact_repository.soft_delete(sample_contact.id)
        await db_session.commit()

        assert deleted is not None
        assert deleted.is_deleted is True

    @pytest.mark.asyncio
    async def test_count(self, db_session, contact_repository, sample_contact):
        """Test counting contacts."""
        count = await contact_repository.count()

        assert count >= 1


# ============================================================================
# Call Repository Tests
# ============================================================================

class TestCallRepository:
    """Tests for CallRepository."""

    @pytest.mark.asyncio
    async def test_create_call(self, db_session, call_repository, sample_contact):
        """Test creating a call."""
        from datetime import timezone
        from phone_agent.db.models.core import CallModel

        call = CallModel(
            id=uuid4(),
            direction="inbound",
            status="ringing",
            caller_id="+49111111111",
            callee_id="+49222222222",
            started_at=datetime.now(timezone.utc),
            contact_id=str(sample_contact.id),
        )

        created = await call_repository.create(call)
        await db_session.commit()

        assert created.id is not None
        assert created.direction == "inbound"
        assert created.status == "ringing"

    @pytest.mark.asyncio
    async def test_get_by_status(self, db_session, call_repository, sample_call):
        """Test getting calls by status."""
        completed = await call_repository.get_by_status("completed")

        assert len(completed) >= 1
        assert all(c.status == "completed" for c in completed)

    @pytest.mark.asyncio
    async def test_get_by_direction(self, db_session, call_repository, sample_call):
        """Test getting calls by direction."""
        inbound = await call_repository.get_by_direction("inbound")

        assert len(inbound) >= 1
        assert all(c.direction == "inbound" for c in inbound)

    @pytest.mark.asyncio
    async def test_get_by_contact(self, db_session, call_repository, sample_call, sample_contact):
        """Test getting calls for a contact."""
        calls = await call_repository.get_by_contact(sample_contact.id)

        assert len(calls) >= 1
        assert all(c.contact_id == str(sample_contact.id) for c in calls)

    @pytest.mark.asyncio
    async def test_count_by_status(self, db_session, call_repository, sample_call):
        """Test counting calls by status."""
        counts = await call_repository.count_by_status()

        assert "completed" in counts
        assert counts["completed"] >= 1

    @pytest.mark.asyncio
    async def test_get_daily_stats(self, db_session, call_repository, sample_call):
        """Test getting daily call statistics."""
        stats = await call_repository.get_daily_stats()

        assert "date" in stats
        assert "total_calls" in stats
        assert stats["total_calls"] >= 1


# ============================================================================
# Appointment Repository Tests
# ============================================================================

class TestAppointmentRepository:
    """Tests for AppointmentRepository."""

    @pytest.mark.asyncio
    async def test_create_appointment(self, db_session, appointment_repository, sample_contact):
        """Test creating an appointment."""
        from phone_agent.db.models.core import AppointmentModel

        appointment = AppointmentModel(
            id=uuid4(),
            patient_name="Test Patient",
            patient_phone="+49333444555",
            appointment_date=date.today() + timedelta(days=1),
            appointment_time=time(14, 30),
            duration_minutes=30,
            type="checkup",
            status="scheduled",
            contact_id=str(sample_contact.id),
        )

        created = await appointment_repository.create(appointment)
        await db_session.commit()

        assert created.id is not None
        assert created.status == "scheduled"

    @pytest.mark.asyncio
    async def test_get_by_status(self, db_session, appointment_repository, sample_appointment):
        """Test getting appointments by status."""
        scheduled = await appointment_repository.get_by_status("scheduled")

        assert len(scheduled) >= 1
        assert all(a.status == "scheduled" for a in scheduled)

    @pytest.mark.asyncio
    async def test_get_today(self, db_session, appointment_repository, sample_appointment):
        """Test getting today's appointments."""
        today_appointments = await appointment_repository.get_today()

        assert len(today_appointments) >= 1

    @pytest.mark.asyncio
    async def test_check_slot_availability(self, db_session, appointment_repository, sample_appointment):
        """Test checking slot availability."""
        # Same slot as sample_appointment should not be available
        is_available = await appointment_repository.check_slot_availability(
            sample_appointment.appointment_date,
            sample_appointment.appointment_time,
            30,
        )

        assert is_available is False

        # Different time should be available
        is_available = await appointment_repository.check_slot_availability(
            sample_appointment.appointment_date,
            time(15, 0),  # Different time
            30,
        )

        assert is_available is True

    @pytest.mark.asyncio
    async def test_get_by_contact(self, db_session, appointment_repository, sample_appointment, sample_contact):
        """Test getting appointments for a contact."""
        appointments = await appointment_repository.get_by_contact(sample_contact.id)

        assert len(appointments) >= 1
        assert all(a.contact_id == str(sample_contact.id) for a in appointments)

    @pytest.mark.asyncio
    async def test_update_status(self, db_session, appointment_repository, sample_appointment):
        """Test updating appointment status."""
        updated = await appointment_repository.update(
            sample_appointment.id,
            {"status": "confirmed"}
        )
        await db_session.commit()

        assert updated is not None
        assert updated.status == "confirmed"


# ============================================================================
# Base Repository Tests
# ============================================================================

class TestBaseRepository:
    """Tests for BaseRepository base functionality."""

    @pytest.mark.asyncio
    async def test_get_multi(self, db_session, contact_repository, sample_contact):
        """Test getting multiple records."""
        contacts = await contact_repository.get_multi(limit=10)

        assert len(contacts) >= 1

    @pytest.mark.asyncio
    async def test_get_nonexistent(self, db_session, contact_repository):
        """Test getting a record that doesn't exist."""
        contact = await contact_repository.get(uuid4())

        assert contact is None

    @pytest.mark.asyncio
    async def test_exists(self, db_session, contact_repository, sample_contact):
        """Test checking if record exists."""
        exists = await contact_repository.exists(sample_contact.id)
        assert exists is True

        not_exists = await contact_repository.exists(uuid4())
        assert not_exists is False

    @pytest.mark.asyncio
    async def test_find_one(self, db_session, contact_repository, sample_contact):
        """Test finding a single record by filter."""
        contact = await contact_repository.find_one(
            first_name="Max",
            industry="gesundheit",
        )

        assert contact is not None
        assert contact.first_name == "Max"

    @pytest.mark.asyncio
    async def test_delete(self, db_session, contact_repository):
        """Test hard deleting a record."""
        from phone_agent.db.models.crm import ContactModel

        # Create a contact to delete
        contact = ContactModel(
            id=uuid4(),
            first_name="Delete",
            last_name="Me",
            phone_primary="+49999999999",
            contact_type="lead",
            industry="gesundheit",
        )

        await contact_repository.create(contact)
        await db_session.commit()

        # Delete it
        deleted = await contact_repository.delete(contact.id)
        await db_session.commit()

        assert deleted is True

        # Verify it's gone
        found = await contact_repository.get(contact.id)
        assert found is None
