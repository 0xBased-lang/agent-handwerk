"""Database Session Management for Phone Agent.

Provides:
- Async SQLAlchemy engine creation
- AsyncSession factory with dependency injection
- Database initialization and table creation
- Transaction context manager
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from phone_agent.config import get_settings
from phone_agent.db.base import Base


# Global engine and session factory (initialized lazily)
_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def get_engine() -> AsyncEngine:
    """Get or create the async database engine.

    Returns:
        AsyncEngine instance configured from settings.

    Connection pooling:
        - SQLite (dev): pool_size=1, max_overflow=0 (single connection)
        - PostgreSQL (prod): pool_size=5, max_overflow=10, pool_timeout=30
    """
    global _engine

    if _engine is None:
        settings = get_settings()

        # Ensure data directory exists
        db_url = settings.database.url
        if "sqlite" in db_url and "///" in db_url:
            db_path = db_url.split("///")[1]
            if db_path != ":memory:":
                Path(db_path).parent.mkdir(parents=True, exist_ok=True)

        # Configure connection pooling based on database type
        if "sqlite" in db_url:
            # SQLite: single connection (thread-safe with check_same_thread=False)
            _engine = create_async_engine(
                db_url,
                echo=settings.database.echo,
                connect_args={"check_same_thread": False},
                pool_pre_ping=True,
            )
        elif "postgresql" in db_url or "postgres" in db_url:
            # PostgreSQL: production-ready pooling
            _engine = create_async_engine(
                db_url,
                echo=settings.database.echo,
                pool_size=5,
                max_overflow=10,
                pool_timeout=30,
                pool_recycle=1800,  # Recycle connections after 30 minutes
                pool_pre_ping=True,  # Verify connection before checkout
            )
        else:
            # Generic database: moderate pooling
            _engine = create_async_engine(
                db_url,
                echo=settings.database.echo,
                pool_size=3,
                max_overflow=5,
                pool_timeout=30,
                pool_pre_ping=True,
            )

    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Get or create the async session factory.

    Returns:
        Session factory configured for the application engine.
    """
    global _session_factory

    if _session_factory is None:
        engine = get_engine()
        _session_factory = async_sessionmaker(
            engine,
            class_=AsyncSession,
            expire_on_commit=False,
            autocommit=False,
            autoflush=False,
        )

    return _session_factory


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency for database sessions.

    Yields:
        AsyncSession that is automatically committed/rolled back.

    Usage:
        @router.get("/items")
        async def get_items(db: AsyncSession = Depends(get_db)):
            ...
    """
    session_factory = get_session_factory()

    async with session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


@asynccontextmanager
async def get_db_context() -> AsyncGenerator[AsyncSession, None]:
    """Context manager for database sessions outside of FastAPI.

    Use this for background tasks, CLI commands, or tests.

    Usage:
        async with get_db_context() as db:
            result = await db.execute(select(Model))
    """
    session_factory = get_session_factory()

    async with session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def init_db() -> None:
    """Initialize database and create all tables.

    Call this during application startup to ensure
    all tables exist. Safe to call multiple times.
    """
    # Import all models to register them with Base.metadata
    from phone_agent.db.models import (  # noqa: F401
        CallModel,
        AppointmentModel,
        ContactModel,
        CompanyModel,
        ContactCompanyLinkModel,
        AuditLogModel,
        ConsentModel,
        CallMetricsModel,
        CampaignMetricsModel,
        RecallCampaignModel,
        CampaignContactModel,
        DashboardSnapshotModel,
        SMSMessageModel,
        EmailMessageModel,
    )

    engine = get_engine()

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def close_db() -> None:
    """Close database connections.

    Call this during application shutdown.
    """
    global _engine, _session_factory

    if _engine is not None:
        await _engine.dispose()
        _engine = None
        _session_factory = None


async def drop_all_tables() -> None:
    """Drop all tables in the database.

    WARNING: Destructive operation! Only use in testing.
    """
    engine = get_engine()

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


# Testing utilities
async def create_test_engine(url: str = "sqlite+aiosqlite:///:memory:") -> AsyncEngine:
    """Create a test database engine with in-memory SQLite.

    Args:
        url: Database URL (default: in-memory SQLite)

    Returns:
        Configured AsyncEngine for testing.
    """
    engine = create_async_engine(
        url,
        echo=False,
        connect_args={"check_same_thread": False} if "sqlite" in url else {},
    )

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    return engine


def get_test_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """Create a test session factory.

    Args:
        engine: Test engine from create_test_engine()

    Returns:
        Session factory for testing.
    """
    return async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autocommit=False,
        autoflush=False,
    )
