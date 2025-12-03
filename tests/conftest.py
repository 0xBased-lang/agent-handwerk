"""Pytest configuration and fixtures for Phone Agent tests."""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path
from typing import AsyncGenerator

import pytest
import pytest_asyncio

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

# Set test environment
os.environ["ITF_ENV"] = "development"
os.environ["ITF_DEBUG"] = "true"
os.environ["ITF_DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"


# Verify itf_shared is installed
try:
    import itf_shared  # noqa: F401
except ImportError as e:
    pytest.exit(
        f"\n\nERROR: itf_shared module not found.\n"
        f"Please run the setup script first:\n\n"
        f"    cd {Path(__file__).parent.parent}\n"
        f"    chmod +x scripts/setup_dev.sh\n"
        f"    ./scripts/setup_dev.sh\n\n"
        f"Original error: {e}\n",
        returncode=1,
    )


@pytest.fixture
def sample_audio():
    """Generate sample audio data for testing."""
    import numpy as np

    # 3 seconds of sine wave at 440Hz
    sample_rate = 16000
    duration = 3.0
    t = np.linspace(0, duration, int(sample_rate * duration))
    audio = np.sin(2 * np.pi * 440 * t).astype(np.float32) * 0.5
    return audio, sample_rate


@pytest.fixture
def sample_text():
    """Sample German text for testing."""
    return "Guten Tag, ich möchte einen Termin vereinbaren."


@pytest.fixture
def mock_settings(monkeypatch):
    """Mock settings for testing without real models."""
    from phone_agent.config import Settings

    settings = Settings(
        device_id="test-device",
        environment="test",
        debug=True,
    )

    from phone_agent import config

    monkeypatch.setattr(config, "get_settings", lambda: settings)
    return settings


# ============================================================================
# Async Database Fixtures
# ============================================================================

@pytest.fixture(scope="session")
def event_loop():
    """Create event loop for async tests."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="function")
async def db_engine():
    """Create test database engine with in-memory SQLite.

    Creates a fresh database for each test function.
    """
    from sqlalchemy.ext.asyncio import create_async_engine

    from phone_agent.db.base import Base
    # Import all models to register them with Base metadata
    from phone_agent.db.models import (  # noqa: F401
        CallModel,
        AppointmentModel,
        ContactModel,
        CompanyModel,
        ContactCompanyLinkModel,
        AuditLogModel,
        ConsentModel,
        DataRetentionPolicyModel,
        CallMetricsModel,
        CampaignMetricsModel,
        RecallCampaignModel,
        DashboardSnapshotModel,
    )

    # Create in-memory SQLite engine
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
    )

    # Create all tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    # Cleanup
    await engine.dispose()


@pytest_asyncio.fixture(scope="function")
async def db_session(db_engine) -> AsyncGenerator:
    """Create test database session.

    Provides a session that rolls back after each test.
    """
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    async_session_factory = async_sessionmaker(
        db_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async with async_session_factory() as session:
        yield session
        await session.rollback()


@pytest_asyncio.fixture
async def call_repository(db_session):
    """Create CallRepository instance for testing."""
    from phone_agent.db.repositories.calls import CallRepository

    return CallRepository(db_session)


@pytest_asyncio.fixture
async def appointment_repository(db_session):
    """Create AppointmentRepository instance for testing."""
    from phone_agent.db.repositories.appointments import AppointmentRepository

    return AppointmentRepository(db_session)


@pytest_asyncio.fixture
async def contact_repository(db_session):
    """Create ContactRepository instance for testing."""
    from phone_agent.db.repositories.contacts import ContactRepository

    return ContactRepository(db_session)


@pytest_asyncio.fixture
async def sample_contact(db_session, contact_repository):
    """Create a sample contact for testing."""
    from uuid import uuid4
    from phone_agent.db.models.crm import ContactModel

    contact = ContactModel(
        id=uuid4(),
        first_name="Max",
        last_name="Mustermann",
        phone_primary="+49123456789",
        email="max@example.de",
        contact_type="patient",
        industry="gesundheit",
    )

    await contact_repository.create(contact)
    await db_session.commit()

    return contact


@pytest_asyncio.fixture
async def sample_call(db_session, call_repository, sample_contact):
    """Create a sample call for testing."""
    from uuid import uuid4
    from datetime import datetime, timezone
    from phone_agent.db.models.core import CallModel

    call = CallModel(
        id=uuid4(),
        direction="inbound",
        status="completed",
        caller_id="+49123456789",
        callee_id="+49987654321",
        started_at=datetime.now(timezone.utc),
        duration_seconds=120,
        contact_id=str(sample_contact.id),
    )

    await call_repository.create(call)
    await db_session.commit()

    return call


@pytest_asyncio.fixture
async def sample_appointment(db_session, appointment_repository, sample_contact):
    """Create a sample appointment for testing."""
    from uuid import uuid4
    from datetime import date, time
    from phone_agent.db.models.core import AppointmentModel

    appointment = AppointmentModel(
        id=uuid4(),
        patient_name="Max Mustermann",
        patient_phone="+49123456789",
        appointment_date=date.today(),
        appointment_time=time(10, 0),
        duration_minutes=30,
        type="consultation",
        status="scheduled",
        contact_id=str(sample_contact.id),
    )

    await appointment_repository.create(appointment)
    await db_session.commit()

    return appointment


# ============================================================================
# Compliance Fixtures
# ============================================================================


@pytest_asyncio.fixture
async def consent_repository(db_session):
    """Create ConsentRepository instance for testing."""
    from phone_agent.db.repositories.compliance import ConsentRepository

    return ConsentRepository(db_session)


@pytest_asyncio.fixture
async def audit_repository(db_session):
    """Create AuditLogRepository instance for testing."""
    from phone_agent.db.repositories.compliance import AuditLogRepository

    return AuditLogRepository(db_session)


@pytest_asyncio.fixture
async def compliance_service(consent_repository, audit_repository):
    """Create ComplianceService instance for testing."""
    from phone_agent.services.compliance_service import ComplianceService

    return ComplianceService(consent_repository, audit_repository)


@pytest_asyncio.fixture
async def sample_consent(db_session, consent_repository, sample_contact):
    """Create a sample consent for testing."""
    from uuid import uuid4
    from phone_agent.db.models.compliance import ConsentModel

    consent = ConsentModel(
        id=uuid4(),
        contact_id=sample_contact.id,
        consent_type="voice_recording",
        industry="gesundheit",
    )
    consent.grant(
        granted_by="phone_agent",
        duration_days=365,
        version="1.0",
    )

    await consent_repository.create(consent)
    await db_session.commit()

    return consent


@pytest_asyncio.fixture
async def sample_audit_log(db_session, audit_repository, sample_contact):
    """Create a sample audit log entry for testing."""
    from phone_agent.db.models.compliance import AuditLogModel

    entry = AuditLogModel.create(
        action="test_action",
        actor_id="test_actor",
        actor_type="system",
        resource_type="test_resource",
        resource_id="test-123",
        contact_id=sample_contact.id,
        details={"test": "data"},
        industry="gesundheit",
    )

    created = await audit_repository.create_with_chain(entry)
    await db_session.commit()

    return created
