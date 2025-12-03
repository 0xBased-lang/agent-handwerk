"""Base Repository Pattern for Phone Agent.

Provides generic CRUD operations with async SQLAlchemy support.
All specialized repositories inherit from BaseRepository.
"""
from __future__ import annotations

from typing import Any, Generic, TypeVar, Sequence
from uuid import UUID

from sqlalchemy import select, func, delete, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from phone_agent.db.base import Base

# Type variable for model classes
ModelT = TypeVar("ModelT", bound=Base)


class BaseRepository(Generic[ModelT]):
    """Generic base repository with async CRUD operations.

    Provides standard database operations that work with any
    SQLAlchemy model. Specialized repositories can extend this
    with domain-specific queries.

    Usage:
        class UserRepository(BaseRepository[UserModel]):
            def __init__(self, session: AsyncSession):
                super().__init__(UserModel, session)

            async def find_by_email(self, email: str) -> UserModel | None:
                # Custom query method
                ...
    """

    def __init__(self, model: type[ModelT], session: AsyncSession):
        """Initialize repository with model class and session.

        Args:
            model: SQLAlchemy model class
            session: Async database session
        """
        self._model = model
        self._session = session

    @property
    def session(self) -> AsyncSession:
        """Get the current database session."""
        return self._session

    # ========================================================================
    # Basic CRUD Operations
    # ========================================================================

    async def get(self, id: UUID | str) -> ModelT | None:
        """Get a single record by ID.

        Args:
            id: UUID or string primary key

        Returns:
            Model instance or None if not found
        """
        if isinstance(id, str):
            id = UUID(id)

        stmt = select(self._model).where(self._model.id == id)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_or_raise(self, id: UUID | str) -> ModelT:
        """Get a single record by ID, raising if not found.

        Args:
            id: UUID or string primary key

        Returns:
            Model instance

        Raises:
            ValueError: If record not found
        """
        obj = await self.get(id)
        if obj is None:
            raise ValueError(f"{self._model.__name__} with id {id} not found")
        return obj

    async def get_multi(
        self,
        *,
        skip: int = 0,
        limit: int = 100,
        order_by: str | None = None,
        descending: bool = True,
    ) -> Sequence[ModelT]:
        """Get multiple records with pagination.

        Args:
            skip: Number of records to skip
            limit: Maximum records to return
            order_by: Column name to order by (default: created_at if exists)
            descending: Sort in descending order

        Returns:
            List of model instances
        """
        stmt = select(self._model)

        # Apply ordering
        if order_by:
            column = getattr(self._model, order_by, None)
            if column is not None:
                stmt = stmt.order_by(column.desc() if descending else column)
        elif hasattr(self._model, "created_at"):
            stmt = stmt.order_by(
                self._model.created_at.desc() if descending else self._model.created_at
            )

        stmt = stmt.offset(skip).limit(limit)

        result = await self._session.execute(stmt)
        return result.scalars().all()

    async def get_by_ids(self, ids: list[UUID | str]) -> Sequence[ModelT]:
        """Get multiple records by their IDs.

        Args:
            ids: List of UUIDs or string primary keys

        Returns:
            List of model instances
        """
        if not ids:
            return []

        # Convert strings to UUIDs
        uuid_ids = [UUID(id) if isinstance(id, str) else id for id in ids]

        stmt = select(self._model).where(self._model.id.in_(uuid_ids))
        result = await self._session.execute(stmt)
        return result.scalars().all()

    async def create(self, obj_in: ModelT) -> ModelT:
        """Create a new record.

        Args:
            obj_in: Model instance to create

        Returns:
            Created model instance with generated ID
        """
        self._session.add(obj_in)
        await self._session.flush()
        await self._session.refresh(obj_in)
        return obj_in

    async def create_multi(self, objs_in: list[ModelT]) -> list[ModelT]:
        """Create multiple records in batch.

        Args:
            objs_in: List of model instances to create

        Returns:
            List of created model instances
        """
        self._session.add_all(objs_in)
        await self._session.flush()
        for obj in objs_in:
            await self._session.refresh(obj)
        return objs_in

    async def update(self, id: UUID | str, obj_in: dict[str, Any]) -> ModelT | None:
        """Update a record by ID.

        Args:
            id: UUID or string primary key
            obj_in: Dictionary of fields to update

        Returns:
            Updated model instance or None if not found
        """
        db_obj = await self.get(id)
        if db_obj is None:
            return None

        for field, value in obj_in.items():
            if hasattr(db_obj, field):
                setattr(db_obj, field, value)

        await self._session.flush()
        await self._session.refresh(db_obj)
        return db_obj

    async def update_or_raise(self, id: UUID | str, obj_in: dict[str, Any]) -> ModelT:
        """Update a record by ID, raising if not found.

        Args:
            id: UUID or string primary key
            obj_in: Dictionary of fields to update

        Returns:
            Updated model instance

        Raises:
            ValueError: If record not found
        """
        result = await self.update(id, obj_in)
        if result is None:
            raise ValueError(f"{self._model.__name__} with id {id} not found")
        return result

    async def delete(self, id: UUID | str) -> bool:
        """Delete a record by ID.

        Args:
            id: UUID or string primary key

        Returns:
            True if deleted, False if not found
        """
        db_obj = await self.get(id)
        if db_obj is None:
            return False

        await self._session.delete(db_obj)
        await self._session.flush()
        return True

    async def soft_delete(self, id: UUID | str) -> ModelT | None:
        """Soft delete a record by ID (if model supports it).

        Sets is_deleted=True and deleted_at timestamp.

        Args:
            id: UUID or string primary key

        Returns:
            Soft-deleted model instance or None
        """
        from datetime import datetime

        db_obj = await self.get(id)
        if db_obj is None:
            return None

        if hasattr(db_obj, "is_deleted"):
            db_obj.is_deleted = True
        if hasattr(db_obj, "deleted_at"):
            db_obj.deleted_at = datetime.utcnow()

        await self._session.flush()
        await self._session.refresh(db_obj)
        return db_obj

    # ========================================================================
    # Query Helpers
    # ========================================================================

    async def count(self) -> int:
        """Get total count of records.

        Returns:
            Total number of records
        """
        stmt = select(func.count()).select_from(self._model)
        result = await self._session.execute(stmt)
        return result.scalar() or 0

    async def exists(self, id: UUID | str) -> bool:
        """Check if a record exists.

        Args:
            id: UUID or string primary key

        Returns:
            True if record exists
        """
        if isinstance(id, str):
            id = UUID(id)

        stmt = select(func.count()).select_from(self._model).where(self._model.id == id)
        result = await self._session.execute(stmt)
        return (result.scalar() or 0) > 0

    async def find_one(self, **filters: Any) -> ModelT | None:
        """Find a single record by arbitrary filters.

        Args:
            **filters: Column name to value mappings

        Returns:
            First matching model instance or None
        """
        stmt = select(self._model)
        for field, value in filters.items():
            if hasattr(self._model, field):
                stmt = stmt.where(getattr(self._model, field) == value)

        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def find_many(
        self,
        *,
        skip: int = 0,
        limit: int = 100,
        **filters: Any,
    ) -> Sequence[ModelT]:
        """Find multiple records by arbitrary filters.

        Args:
            skip: Number of records to skip
            limit: Maximum records to return
            **filters: Column name to value mappings

        Returns:
            List of matching model instances
        """
        stmt = select(self._model)
        for field, value in filters.items():
            if hasattr(self._model, field):
                stmt = stmt.where(getattr(self._model, field) == value)

        stmt = stmt.offset(skip).limit(limit)

        result = await self._session.execute(stmt)
        return result.scalars().all()

    async def find_with_eager_load(
        self,
        id: UUID | str,
        relationships: list[str],
    ) -> ModelT | None:
        """Get a record with eager-loaded relationships.

        Args:
            id: UUID or string primary key
            relationships: List of relationship attribute names to eager load

        Returns:
            Model instance with relationships loaded, or None
        """
        if isinstance(id, str):
            id = UUID(id)

        stmt = select(self._model).where(self._model.id == id)

        for rel in relationships:
            if hasattr(self._model, rel):
                stmt = stmt.options(selectinload(getattr(self._model, rel)))

        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    # ========================================================================
    # Bulk Operations
    # ========================================================================

    async def bulk_update(
        self,
        filters: dict[str, Any],
        updates: dict[str, Any],
    ) -> int:
        """Bulk update records matching filters.

        Args:
            filters: Column name to value filter mappings
            updates: Column name to new value mappings

        Returns:
            Number of records updated
        """
        stmt = update(self._model)

        for field, value in filters.items():
            if hasattr(self._model, field):
                stmt = stmt.where(getattr(self._model, field) == value)

        stmt = stmt.values(**updates)
        result = await self._session.execute(stmt)
        await self._session.flush()
        return result.rowcount

    async def bulk_delete(self, filters: dict[str, Any]) -> int:
        """Bulk delete records matching filters.

        Args:
            filters: Column name to value filter mappings

        Returns:
            Number of records deleted
        """
        stmt = delete(self._model)

        for field, value in filters.items():
            if hasattr(self._model, field):
                stmt = stmt.where(getattr(self._model, field) == value)

        result = await self._session.execute(stmt)
        await self._session.flush()
        return result.rowcount

    # ========================================================================
    # Transaction Helpers
    # ========================================================================

    async def commit(self) -> None:
        """Commit the current transaction."""
        await self._session.commit()

    async def rollback(self) -> None:
        """Rollback the current transaction."""
        await self._session.rollback()

    async def refresh(self, obj: ModelT) -> ModelT:
        """Refresh an object from the database.

        Args:
            obj: Model instance to refresh

        Returns:
            Refreshed model instance
        """
        await self._session.refresh(obj)
        return obj
