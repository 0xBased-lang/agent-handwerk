"""Conversation Transcript Repository.

CRUD operations for voice conversation transcripts.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from phone_agent.db.models.elektro import ConversationTranscriptModel
from phone_agent.db.repositories.base import BaseRepository


class TranscriptRepository(BaseRepository[ConversationTranscriptModel]):
    """Repository for conversation transcript operations."""

    def __init__(self, session: AsyncSession):
        """Initialize repository with async session."""
        super().__init__(ConversationTranscriptModel, session)

    async def get_by_session_id(self, session_id: str) -> ConversationTranscriptModel | None:
        """Get transcript by voice session ID.

        Args:
            session_id: Voice demo session identifier

        Returns:
            Transcript model or None
        """
        result = await self.session.execute(
            select(ConversationTranscriptModel).where(
                ConversationTranscriptModel.session_id == session_id
            )
        )
        return result.scalar_one_or_none()

    async def get_by_job_id(self, job_id: UUID) -> ConversationTranscriptModel | None:
        """Get transcript by linked job ID.

        Args:
            job_id: Job UUID

        Returns:
            Transcript model or None
        """
        result = await self.session.execute(
            select(ConversationTranscriptModel).where(
                ConversationTranscriptModel.job_id == job_id
            )
        )
        return result.scalar_one_or_none()

    async def list_recent(
        self,
        limit: int = 50,
        offset: int = 0,
        trade: str | None = "elektro",
        urgency: str | None = None,
        days_back: int | None = 7,
    ) -> list[ConversationTranscriptModel]:
        """List recent transcripts with optional filtering.

        Args:
            limit: Maximum number to return
            offset: Pagination offset
            trade: Filter by trade category
            urgency: Filter by urgency level
            days_back: Only return transcripts from last N days

        Returns:
            List of transcript models
        """
        query = select(ConversationTranscriptModel)

        # Apply filters
        conditions = []
        if trade:
            conditions.append(ConversationTranscriptModel.trade_detected == trade)
        if urgency:
            conditions.append(ConversationTranscriptModel.urgency_detected == urgency)
        if days_back:
            cutoff = datetime.now() - timedelta(days=days_back)
            conditions.append(ConversationTranscriptModel.created_at >= cutoff)

        if conditions:
            query = query.where(and_(*conditions))

        # Order by newest first
        query = query.order_by(ConversationTranscriptModel.created_at.desc())
        query = query.offset(offset).limit(limit)

        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def count_by_urgency(
        self,
        days_back: int = 7,
        trade: str | None = "elektro",
    ) -> dict[str, int]:
        """Count transcripts by urgency level.

        Args:
            days_back: Count transcripts from last N days
            trade: Filter by trade category

        Returns:
            Dict mapping urgency to count
        """
        cutoff = datetime.now() - timedelta(days=days_back)

        conditions = [ConversationTranscriptModel.created_at >= cutoff]
        if trade:
            conditions.append(ConversationTranscriptModel.trade_detected == trade)

        result = await self.session.execute(
            select(
                ConversationTranscriptModel.urgency_detected,
                func.count(ConversationTranscriptModel.id)
            )
            .where(and_(*conditions))
            .group_by(ConversationTranscriptModel.urgency_detected)
        )

        return {row[0] or "unknown": row[1] for row in result.all()}

    async def link_to_job(
        self,
        transcript_id: UUID,
        job_id: UUID,
    ) -> ConversationTranscriptModel | None:
        """Link a transcript to a job.

        Args:
            transcript_id: Transcript UUID
            job_id: Job UUID

        Returns:
            Updated transcript or None
        """
        transcript = await self.get(transcript_id)
        if transcript:
            transcript.job_id = job_id
            await self.session.commit()
            await self.session.refresh(transcript)
        return transcript

    async def create_from_session(
        self,
        session_id: str,
        turns: list[dict[str, Any]],
        language: str = "de",
        urgency: str | None = None,
        trade: str = "elektro",
        problem_description: str | None = None,
        job_id: UUID | None = None,
    ) -> ConversationTranscriptModel:
        """Create a transcript from a voice session.

        Args:
            session_id: Voice session ID
            turns: List of conversation turns
            language: Primary language
            urgency: Detected urgency
            trade: Trade category
            problem_description: Extracted problem
            job_id: Optional linked job

        Returns:
            Created transcript model
        """
        transcript = ConversationTranscriptModel(
            session_id=session_id,
            turns_json=turns,
            language=language,
            urgency_detected=urgency,
            trade_detected=trade,
            turn_count=len(turns),
            problem_description=problem_description,
            job_id=job_id,
        )

        self.session.add(transcript)
        await self.session.commit()
        await self.session.refresh(transcript)

        return transcript
