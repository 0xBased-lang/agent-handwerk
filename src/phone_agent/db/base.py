"""SQLAlchemy Base and Mixins for Phone Agent Database.

Provides:
- DeclarativeBase for all ORM models
- TimestampMixin for created_at/updated_at
- UUIDMixin for UUID primary keys
- SoftDeleteMixin for soft delete support
"""
from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import DateTime, String, Boolean, func, TypeDecorator
from sqlalchemy.dialects.sqlite import JSON
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, declared_attr


class UUIDType(TypeDecorator):
    """Platform-independent UUID type.

    Uses String(36) storage but handles UUID <-> str conversion.
    Compatible with SQLite and PostgreSQL.
    """

    impl = String(36)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        """Convert UUID to string for storage."""
        if value is None:
            return None
        if isinstance(value, UUID):
            return str(value)
        return value

    def process_result_value(self, value, dialect):
        """Convert string back to UUID on retrieval."""
        if value is None:
            return None
        if isinstance(value, UUID):
            return value
        return UUID(value)


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy ORM models.

    Provides common configuration and type annotations.
    """

    # Enable JSON type for metadata columns
    type_annotation_map = {
        dict[str, Any]: JSON,
        UUID: UUIDType,  # Use our custom UUID type
    }


class UUIDMixin:
    """Mixin providing UUID primary key.

    All models should use UUID for distributed compatibility
    and better security (non-sequential IDs).
    """

    id: Mapped[UUID] = mapped_column(
        UUIDType(),
        primary_key=True,
        default=uuid4,
        nullable=False,
    )


class TimestampMixin:
    """Mixin providing created_at and updated_at timestamps.

    Automatically sets created_at on insert and updated_at on update.
    """

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class SoftDeleteMixin:
    """Mixin providing soft delete functionality.

    Instead of physically deleting rows, marks them as deleted
    for audit trail and potential recovery.
    """

    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        default=None,
    )

    is_deleted: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )

    def soft_delete(self) -> None:
        """Mark this record as deleted."""
        self.is_deleted = True
        self.deleted_at = datetime.now()

    def restore(self) -> None:
        """Restore a soft-deleted record."""
        self.is_deleted = False
        self.deleted_at = None


class IndustryMixin:
    """Mixin for industry-specific models.

    Provides industry classification for multi-industry support.
    """

    @declared_attr
    def industry(cls) -> Mapped[str]:
        """Industry this record belongs to (gesundheit, handwerk, etc.)."""
        return mapped_column(String(50), nullable=False, index=True)


# Convenience function to generate UUID strings
def generate_uuid() -> str:
    """Generate a new UUID string."""
    return str(uuid4())
