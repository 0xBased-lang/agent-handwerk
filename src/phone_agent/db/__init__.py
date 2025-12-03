"""Database module for Phone Agent.

Provides:
- SQLAlchemy ORM models for all data entities
- Async session management with dependency injection
- Repository pattern for data access
- Database initialization and lifecycle management
"""
from phone_agent.db.base import (
    Base,
    UUIDMixin,
    TimestampMixin,
    SoftDeleteMixin,
    IndustryMixin,
    generate_uuid,
)
from phone_agent.db.session import (
    get_engine,
    get_session_factory,
    get_db,
    get_db_context,
    init_db,
    close_db,
    create_test_engine,
    get_test_session_factory,
)

__all__ = [
    # Base and mixins
    "Base",
    "UUIDMixin",
    "TimestampMixin",
    "SoftDeleteMixin",
    "IndustryMixin",
    "generate_uuid",
    # Session management
    "get_engine",
    "get_session_factory",
    "get_db",
    "get_db_context",
    "init_db",
    "close_db",
    # Testing
    "create_test_engine",
    "get_test_session_factory",
]
