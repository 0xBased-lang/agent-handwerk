"""Conversation engine orchestrating STT → LLM → TTS pipeline.

Manages the full conversation flow for the phone agent, including:
- Audio to text transcription
- LLM-based response generation
- Text to speech synthesis
- Conversation history management
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, AsyncGenerator
from uuid import UUID, uuid4

import numpy as np
from itf_shared import get_logger

from phone_agent.ai import SpeechToText, LanguageModel, TextToSpeech
from phone_agent.config import get_settings
from phone_agent.industry.gesundheit import (
    SYSTEM_PROMPT,
    perform_triage,
    TriageResult,
)

log = get_logger(__name__)


class TurnRole(str, Enum):
    """Role in conversation turn."""

    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"


@dataclass
class ConversationTurn:
    """A single turn in the conversation."""

    role: TurnRole
    content: str
    timestamp: datetime = field(default_factory=datetime.now)
    audio_duration: float | None = None
    triage_result: TriageResult | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ConversationState:
    """State of an ongoing conversation."""

    id: UUID = field(default_factory=uuid4)
    turns: list[ConversationTurn] = field(default_factory=list)
    patient_name: str | None = None
    patient_phone: str | None = None
    triage_result: TriageResult | None = None
    appointment_id: UUID | None = None
    started_at: datetime = field(default_factory=datetime.now)
    ended_at: datetime | None = None

    def add_turn(self, role: TurnRole, content: str, **kwargs: Any) -> ConversationTurn:
        """Add a turn to the conversation."""
        turn = ConversationTurn(role=role, content=content, **kwargs)
        self.turns.append(turn)
        return turn

    def get_history_for_llm(self, max_turns: int = 10) -> list[dict[str, str]]:
        """Get conversation history formatted for LLM.

        Args:
            max_turns: Maximum number of turns to include

        Returns:
            List of message dicts with role and content
        """
        recent_turns = self.turns[-max_turns:] if max_turns else self.turns
        return [
            {"role": turn.role.value, "content": turn.content}
            for turn in recent_turns
            if turn.role != TurnRole.SYSTEM
        ]


class ConversationEngine:
    """Orchestrates the STT → LLM → TTS conversation pipeline.

    Manages:
    - AI model lifecycle (lazy loading)
    - Conversation state
    - Turn-by-turn processing
    - Industry-specific logic (triage, etc.)
    """

    def __init__(
        self,
        stt: SpeechToText | None = None,
        llm: LanguageModel | None = None,
        tts: TextToSpeech | None = None,
        system_prompt: str | None = None,
    ) -> None:
        """Initialize conversation engine.

        Args:
            stt: Speech-to-text engine (created if None)
            llm: Language model engine (created if None)
            tts: Text-to-speech engine (created if None)
            system_prompt: Custom system prompt (uses healthcare default if None)
        """
        settings = get_settings()

        # Initialize AI components (lazy loaded)
        self.stt = stt or SpeechToText(
            model=settings.ai.stt.model,
            model_path=settings.ai.stt.model_path,
            device=settings.ai.stt.device,
            compute_type=settings.ai.stt.compute_type,
            language=settings.ai.stt.language,
        )
        self.llm = llm or LanguageModel(
            model=settings.ai.llm.model,
            model_path=settings.ai.llm.model_path,
            n_ctx=settings.ai.llm.n_ctx,
            n_threads=settings.ai.llm.n_threads,
            n_gpu_layers=settings.ai.llm.n_gpu_layers,
        )
        self.tts = tts or TextToSpeech(
            model=settings.ai.tts.model,
            model_path=settings.ai.tts.model_path,
        )

        self.system_prompt = system_prompt or SYSTEM_PROMPT
        self._conversations: dict[UUID, ConversationState] = {}

    def preload_models(self) -> None:
        """Preload all AI models into memory.

        Call this at startup for faster first response.
        """
        log.info("Preloading AI models...")
        self.stt.load()
        self.llm.load()
        self.tts.load()
        log.info("All models loaded")

    def unload_models(self) -> None:
        """Unload all AI models to free memory."""
        self.stt.unload()
        self.llm.unload()
        self.tts.unload()
        log.info("All models unloaded")

    def start_conversation(self) -> ConversationState:
        """Start a new conversation.

        Returns:
            New conversation state
        """
        state = ConversationState()
        state.add_turn(TurnRole.SYSTEM, self.system_prompt)
        self._conversations[state.id] = state

        log.info("Conversation started", conversation_id=str(state.id))
        return state

    def end_conversation(self, conversation_id: UUID) -> ConversationState | None:
        """End a conversation.

        Args:
            conversation_id: Conversation to end

        Returns:
            Final conversation state or None if not found
        """
        state = self._conversations.get(conversation_id)
        if state:
            state.ended_at = datetime.now()
            log.info(
                "Conversation ended",
                conversation_id=str(conversation_id),
                turns=len(state.turns),
            )
        return state

    async def process_audio(
        self,
        audio: np.ndarray,
        conversation_id: UUID,
        sample_rate: int = 16000,
    ) -> tuple[str, bytes]:
        """Process audio input and generate audio response.

        Full pipeline: Audio → STT → LLM → TTS → Audio

        Args:
            audio: Input audio as numpy array
            conversation_id: Conversation context
            sample_rate: Audio sample rate

        Returns:
            Tuple of (text_response, audio_response_bytes)
        """
        state = self._conversations.get(conversation_id)
        if not state:
            raise ValueError(f"Unknown conversation: {conversation_id}")

        # STT: Audio → Text
        log.debug("Starting STT", audio_length=len(audio) / sample_rate)
        user_text = await self.stt.transcribe_async(audio, sample_rate)
        state.add_turn(
            TurnRole.USER,
            user_text,
            audio_duration=len(audio) / sample_rate,
        )
        log.info("User said", text=user_text[:100])

        # Triage check (healthcare specific)
        triage_result = perform_triage(user_text)
        if triage_result.level.value in ("akut", "dringend"):
            state.triage_result = triage_result
            log.warning(
                "Triage alert",
                level=triage_result.level.value,
                reason=triage_result.reason,
            )

        # LLM: Generate response
        log.debug("Starting LLM generation")
        response_text = await self.llm.generate_async(
            prompt=user_text,
            system_prompt=self.system_prompt,
        )
        state.add_turn(TurnRole.ASSISTANT, response_text, triage_result=triage_result)
        log.info("Assistant response", text=response_text[:100])

        # TTS: Text → Audio
        log.debug("Starting TTS")
        response_audio = await self.tts.synthesize_async(response_text)

        return response_text, response_audio

    async def process_text(
        self,
        text: str,
        conversation_id: UUID,
    ) -> str:
        """Process text input and generate text response.

        Args:
            text: User text input
            conversation_id: Conversation context

        Returns:
            Text response
        """
        state = self._conversations.get(conversation_id)
        if not state:
            raise ValueError(f"Unknown conversation: {conversation_id}")

        state.add_turn(TurnRole.USER, text)

        # Triage check
        triage_result = perform_triage(text)
        if triage_result.level.value in ("akut", "dringend"):
            state.triage_result = triage_result

        # Generate response
        response_text = await self.llm.generate_async(
            prompt=text,
            system_prompt=self.system_prompt,
        )
        state.add_turn(TurnRole.ASSISTANT, response_text, triage_result=triage_result)

        return response_text

    async def generate_greeting(self, conversation_id: UUID) -> tuple[str, bytes]:
        """Generate initial greeting for a new call.

        Args:
            conversation_id: Conversation to greet

        Returns:
            Tuple of (greeting_text, greeting_audio)
        """
        from phone_agent.industry.gesundheit.workflows import get_time_of_day

        time_of_day = await get_time_of_day()
        settings = get_settings()

        greeting = f"Guten {time_of_day}, Praxis, hier spricht der Telefonassistent. Wie kann ich Ihnen helfen?"

        state = self._conversations.get(conversation_id)
        if state:
            state.add_turn(TurnRole.ASSISTANT, greeting)

        greeting_audio = await self.tts.synthesize_async(greeting)

        return greeting, greeting_audio

    async def stream_response(
        self,
        text: str,
        conversation_id: UUID,
    ) -> AsyncGenerator[str, None]:
        """Generate streaming text response.

        Yields tokens as they're generated for lower latency.

        Args:
            text: User text input
            conversation_id: Conversation context

        Yields:
            Response tokens
        """
        state = self._conversations.get(conversation_id)
        if not state:
            raise ValueError(f"Unknown conversation: {conversation_id}")

        state.add_turn(TurnRole.USER, text)

        # Stream from LLM
        full_response = ""
        for token in self.llm.generate_stream(
            prompt=text,
            system_prompt=self.system_prompt,
        ):
            full_response += token
            yield token

        state.add_turn(TurnRole.ASSISTANT, full_response)

    def get_conversation(self, conversation_id: UUID) -> ConversationState | None:
        """Get conversation state by ID."""
        return self._conversations.get(conversation_id)

    @property
    def models_loaded(self) -> bool:
        """Check if all models are loaded."""
        return self.stt.is_loaded and self.llm.is_loaded and self.tts.is_loaded


# Convenience function for quick testing
async def quick_chat(user_input: str, engine: ConversationEngine | None = None) -> str:
    """Quick single-turn chat for testing.

    Args:
        user_input: User message
        engine: Conversation engine (created if None)

    Returns:
        Assistant response
    """
    if engine is None:
        engine = ConversationEngine()

    state = engine.start_conversation()
    response = await engine.process_text(user_input, state.id)
    engine.end_conversation(state.id)

    return response
