"""Conversation engine orchestrating STT → LLM → TTS pipeline.

Manages the full conversation flow for the phone agent, including:
- Audio to text transcription
- LLM-based response generation
- Text to speech synthesis
- Conversation history management
"""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, AsyncGenerator, Callable, Awaitable
from uuid import UUID, uuid4

import numpy as np
from itf_shared import get_logger

from phone_agent.ai import (
    SpeechToText,
    DialectAwareSTT,
    DialectResult,
    LanguageModel,
    TextToSpeech,
)
from phone_agent.config import get_settings
from phone_agent.industry.gesundheit import (
    SYSTEM_PROMPT,
    perform_triage,
    TriageResult,
)

log = get_logger(__name__)


# Sentence boundary pattern for German text
# Matches: period, exclamation, question mark followed by space or end
SENTENCE_END_PATTERN = re.compile(r'([.!?])(?:\s+|$)')


def extract_complete_sentence(buffer: str) -> tuple[str | None, str]:
    """Extract the first complete sentence from a buffer.

    Args:
        buffer: Text buffer that may contain partial sentences

    Returns:
        Tuple of (complete_sentence or None, remaining_buffer)
    """
    match = SENTENCE_END_PATTERN.search(buffer)
    if match:
        # Found a sentence boundary
        end_pos = match.end()
        sentence = buffer[:end_pos].strip()
        remaining = buffer[end_pos:].lstrip()

        # Filter out very short "sentences" (likely noise)
        if len(sentence) >= 5:
            return sentence, remaining

    return None, buffer


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

    # Dialect tracking for German regional variants
    detected_dialect: str | None = None  # de_standard, de_alemannic, de_bavarian, etc.
    dialect_confidence: float = 0.0
    dialect_features: list[str] = field(default_factory=list)

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
        stt: SpeechToText | DialectAwareSTT | None = None,
        llm: LanguageModel | None = None,
        tts: TextToSpeech | None = None,
        system_prompt: str | None = None,
        dialect_aware: bool = True,
    ) -> None:
        """Initialize conversation engine.

        Args:
            stt: Speech-to-text engine (created if None)
            llm: Language model engine (created if None)
            tts: Text-to-speech engine (created if None)
            system_prompt: Custom system prompt (uses healthcare default if None)
            dialect_aware: Use dialect-aware STT for German variants (Schwäbisch, etc.)
        """
        settings = get_settings()

        # Initialize AI components (lazy loaded)
        # Use DialectAwareSTT for German dialect support (Schwäbisch, Bavarian, etc.)
        if stt is not None:
            self.stt = stt
        elif dialect_aware:
            self.stt = DialectAwareSTT(
                model_path=settings.ai.stt.model_path,
                device=settings.ai.stt.device,
                compute_type=settings.ai.stt.compute_type,
                dialect_detection=True,
                detection_mode="text",  # Post-transcription detection (faster)
            )
        else:
            self.stt = SpeechToText(
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
        self._dialect_aware = dialect_aware

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

    def _build_system_prompt_with_dialect(self, state: ConversationState) -> str:
        """Build system prompt with dialect context if detected.

        Args:
            state: Conversation state with dialect info

        Returns:
            System prompt with dialect context if applicable
        """
        if not state.detected_dialect or state.detected_dialect == "de_standard":
            return self.system_prompt

        # Map dialect codes to friendly names
        dialect_names = {
            "de_alemannic": "Schwäbisch/Alemannisch",
            "de_bavarian": "Bayerisch",
            "de_low": "Plattdeutsch",
        }
        dialect_name = dialect_names.get(state.detected_dialect, "Dialekt")

        dialect_context = f"""

DIALEKT-HINWEIS:
Der Anrufer spricht {dialect_name}.
- Verstehe dialektale Ausdrücke (z.B. "bissle", "net", "schaffe")
- Antworte selbst in klarem Hochdeutsch (Sie-Form)
- Sei geduldig, da Dialektsprecher manchmal anders formulieren"""

        return self.system_prompt + dialect_context

    def _update_dialect_from_stt(self, state: ConversationState) -> None:
        """Update conversation state with detected dialect.

        Args:
            state: Conversation state to update
        """
        if not self._dialect_aware or not hasattr(self.stt, "_last_dialect"):
            return

        dialect = getattr(self.stt, "_last_dialect", None)
        if dialect and dialect.confidence > state.dialect_confidence:
            state.detected_dialect = dialect.dialect
            state.dialect_confidence = dialect.confidence
            state.dialect_features = getattr(dialect, "features_detected", [])
            log.info(
                "Dialect detected",
                dialect=dialect.dialect,
                confidence=round(dialect.confidence, 2),
            )

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

        # Update dialect detection from STT (if using DialectAwareSTT)
        self._update_dialect_from_stt(state)

        state.add_turn(
            TurnRole.USER,
            user_text,
            audio_duration=len(audio) / sample_rate,
            metadata={"dialect": state.detected_dialect},
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

        # LLM: Generate response with conversation history
        log.debug(
            "Starting LLM generation",
            history_turns=len(state.turns),
            dialect=state.detected_dialect,
        )

        # Build messages with dialect-aware system prompt
        effective_prompt = self._build_system_prompt_with_dialect(state)
        messages = [{"role": "system", "content": effective_prompt}]
        messages.extend(state.get_history_for_llm(max_turns=10))

        response_text = await self.llm.generate_with_history_async(messages)
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

        # Generate response with dialect-aware conversation history
        effective_prompt = self._build_system_prompt_with_dialect(state)
        messages = [{"role": "system", "content": effective_prompt}]
        messages.extend(state.get_history_for_llm(max_turns=10))

        response_text = await self.llm.generate_with_history_async(messages)
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

        # Build messages with dialect-aware conversation history
        effective_prompt = self._build_system_prompt_with_dialect(state)
        messages = [{"role": "system", "content": effective_prompt}]
        messages.extend(state.get_history_for_llm(max_turns=10))

        # Stream from LLM with history
        full_response = ""
        for token in self.llm.generate_stream_with_history(messages):
            full_response += token
            yield token

        state.add_turn(TurnRole.ASSISTANT, full_response)

    async def process_audio_streaming(
        self,
        audio: np.ndarray,
        conversation_id: UUID,
        on_sentence_ready: Callable[[str, bytes], Awaitable[None]],
        sample_rate: int = 16000,
    ) -> tuple[str, str, bytes]:
        """Process audio with streaming TTS - speak as soon as first sentence is ready.

        This method significantly reduces perceived latency by starting TTS playback
        as soon as the first complete sentence is generated, while the LLM continues
        generating the rest of the response.

        Args:
            audio: Audio waveform as numpy array
            conversation_id: Active conversation ID
            on_sentence_ready: Async callback called with (sentence_text, audio_bytes)
                              for each complete sentence. Should play audio immediately.
            sample_rate: Audio sample rate (default 16kHz)

        Returns:
            Tuple of (user_text, full_response_text, full_response_audio)
        """
        import time

        state = self._conversations.get(conversation_id)
        if not state:
            raise ValueError(f"Unknown conversation: {conversation_id}")

        start_time = time.time()

        # === STT Phase ===
        log.debug("Streaming: Starting STT", audio_length=len(audio) / sample_rate)
        user_text = await self.stt.transcribe_async(audio, sample_rate)

        # Update dialect detection
        self._update_dialect_from_stt(state)

        state.add_turn(
            TurnRole.USER,
            user_text,
            audio_duration=len(audio) / sample_rate,
            metadata={"dialect": state.detected_dialect},
        )
        stt_time = time.time() - start_time
        log.info("Streaming: User said", text=user_text[:100], stt_time=f"{stt_time:.2f}s")

        # === Triage (quick check for emergencies) ===
        triage_result = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: perform_triage(user_text),
        )

        # === LLM + TTS Streaming Phase ===
        effective_prompt = self._build_system_prompt_with_dialect(state)
        messages = [{"role": "system", "content": effective_prompt}]
        messages.extend(state.get_history_for_llm(max_turns=10))

        buffer = ""
        full_response = ""
        all_audio_chunks: list[bytes] = []
        sentences_spoken = 0
        first_sentence_time = None

        log.debug("Streaming: Starting LLM generation")

        for token in self.llm.generate_stream_with_history(messages):
            buffer += token
            full_response += token

            # Try to extract complete sentences
            while True:
                sentence, buffer = extract_complete_sentence(buffer)
                if sentence is None:
                    break

                # Synthesize and play this sentence immediately
                if sentences_spoken == 0:
                    first_sentence_time = time.time() - start_time
                    log.info(
                        "Streaming: First sentence ready",
                        time=f"{first_sentence_time:.2f}s",
                        sentence=sentence[:50],
                    )

                audio_chunk = await self.tts.synthesize_async(sentence)
                all_audio_chunks.append(audio_chunk)

                # Call the callback to play audio immediately
                await on_sentence_ready(sentence, audio_chunk)
                sentences_spoken += 1

        # Handle any remaining text in buffer
        if buffer.strip() and len(buffer.strip()) >= 3:
            audio_chunk = await self.tts.synthesize_async(buffer.strip())
            all_audio_chunks.append(audio_chunk)
            await on_sentence_ready(buffer.strip(), audio_chunk)

        # Combine all audio chunks for the full response
        full_audio = b"".join(all_audio_chunks)

        state.add_turn(TurnRole.ASSISTANT, full_response, triage_result=triage_result)

        total_time = time.time() - start_time
        log.info(
            "Streaming: Complete",
            total_time=f"{total_time:.2f}s",
            first_sentence_time=f"{first_sentence_time:.2f}s" if first_sentence_time else "N/A",
            sentences=sentences_spoken,
        )

        return user_text, full_response, full_audio

    async def process_text_streaming(
        self,
        text: str,
        conversation_id: UUID,
        on_sentence_ready: Callable[[str, bytes], Awaitable[None]],
    ) -> tuple[str, bytes]:
        """Process text input with streaming TTS output.

        Args:
            text: User text input
            conversation_id: Active conversation ID
            on_sentence_ready: Async callback for each sentence

        Returns:
            Tuple of (full_response_text, full_response_audio)
        """
        import time

        state = self._conversations.get(conversation_id)
        if not state:
            raise ValueError(f"Unknown conversation: {conversation_id}")

        start_time = time.time()
        state.add_turn(TurnRole.USER, text)

        # Build messages with history
        effective_prompt = self._build_system_prompt_with_dialect(state)
        messages = [{"role": "system", "content": effective_prompt}]
        messages.extend(state.get_history_for_llm(max_turns=10))

        buffer = ""
        full_response = ""
        all_audio_chunks: list[bytes] = []
        sentences_spoken = 0

        for token in self.llm.generate_stream_with_history(messages):
            buffer += token
            full_response += token

            while True:
                sentence, buffer = extract_complete_sentence(buffer)
                if sentence is None:
                    break

                audio_chunk = await self.tts.synthesize_async(sentence)
                all_audio_chunks.append(audio_chunk)
                await on_sentence_ready(sentence, audio_chunk)
                sentences_spoken += 1

        # Handle remaining buffer
        if buffer.strip() and len(buffer.strip()) >= 3:
            audio_chunk = await self.tts.synthesize_async(buffer.strip())
            all_audio_chunks.append(audio_chunk)
            await on_sentence_ready(buffer.strip(), audio_chunk)

        full_audio = b"".join(all_audio_chunks)
        state.add_turn(TurnRole.ASSISTANT, full_response)

        log.debug(
            "Text streaming complete",
            time=f"{time.time() - start_time:.2f}s",
            sentences=sentences_spoken,
        )

        return full_response, full_audio

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
