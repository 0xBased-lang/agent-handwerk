"""Call handler with state machine for managing phone calls.

Orchestrates the full call lifecycle:
- Call reception and greeting
- Conversation management
- Appointment scheduling
- Call transfer and termination
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from typing import Any, Callable
from uuid import UUID, uuid4

from itf_shared import get_logger

from phone_agent.core.audio import AudioPipeline, AudioConfig
from phone_agent.core.conversation import ConversationEngine, ConversationState

log = get_logger(__name__)


class CallState(Enum):
    """States in the call state machine."""

    IDLE = auto()  # No active call
    RINGING = auto()  # Incoming call, not yet answered
    GREETING = auto()  # Playing greeting message
    LISTENING = auto()  # Waiting for user speech
    PROCESSING = auto()  # Processing user input
    SPEAKING = auto()  # Playing response
    TRANSFERRING = auto()  # Transferring to human
    ENDED = auto()  # Call ended


class CallEvent(Enum):
    """Events that trigger state transitions."""

    INCOMING_CALL = auto()
    CALL_ANSWERED = auto()
    GREETING_COMPLETE = auto()
    SPEECH_DETECTED = auto()
    UTTERANCE_COMPLETE = auto()
    RESPONSE_READY = auto()
    PLAYBACK_COMPLETE = auto()
    TRANSFER_REQUESTED = auto()
    TRANSFER_COMPLETE = auto()
    HANGUP = auto()
    ERROR = auto()
    TIMEOUT = auto()


@dataclass
class CallContext:
    """Context for an active call."""

    call_id: UUID = field(default_factory=uuid4)
    conversation: ConversationState | None = None
    caller_id: str = ""
    callee_id: str = ""
    state: CallState = CallState.IDLE
    started_at: datetime | None = None
    ended_at: datetime | None = None
    transfer_target: str | None = None
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def duration_seconds(self) -> float | None:
        """Get call duration in seconds."""
        if self.started_at is None:
            return None
        end = self.ended_at or datetime.now()
        return (end - self.started_at).total_seconds()


class CallHandler:
    """Manages phone call lifecycle with state machine.

    Handles:
    - Call state transitions
    - Audio pipeline management
    - Conversation orchestration
    - Event callbacks
    """

    def __init__(
        self,
        conversation_engine: ConversationEngine | None = None,
        audio_pipeline: AudioPipeline | None = None,
    ) -> None:
        """Initialize call handler.

        Args:
            conversation_engine: Engine for AI conversation
            audio_pipeline: Audio I/O pipeline
        """
        self.conversation_engine = conversation_engine or ConversationEngine()
        self.audio_pipeline = audio_pipeline or AudioPipeline(AudioConfig())

        self._current_call: CallContext | None = None
        self._call_history: list[CallContext] = []
        self._call_lock = asyncio.Lock()  # Protect call state changes

        # Event callbacks
        self._on_state_change: Callable[[CallState, CallState, CallContext], None] | None = None
        self._on_call_start: Callable[[CallContext], None] | None = None
        self._on_call_end: Callable[[CallContext], None] | None = None

        # State transition table
        self._transitions: dict[tuple[CallState, CallEvent], CallState] = {
            # From IDLE
            (CallState.IDLE, CallEvent.INCOMING_CALL): CallState.RINGING,

            # From RINGING
            (CallState.RINGING, CallEvent.CALL_ANSWERED): CallState.GREETING,
            (CallState.RINGING, CallEvent.HANGUP): CallState.ENDED,
            (CallState.RINGING, CallEvent.TIMEOUT): CallState.ENDED,

            # From GREETING
            (CallState.GREETING, CallEvent.GREETING_COMPLETE): CallState.LISTENING,
            (CallState.GREETING, CallEvent.HANGUP): CallState.ENDED,

            # From LISTENING
            (CallState.LISTENING, CallEvent.SPEECH_DETECTED): CallState.LISTENING,
            (CallState.LISTENING, CallEvent.UTTERANCE_COMPLETE): CallState.PROCESSING,
            (CallState.LISTENING, CallEvent.HANGUP): CallState.ENDED,
            (CallState.LISTENING, CallEvent.TIMEOUT): CallState.SPEAKING,  # Prompt user

            # From PROCESSING
            (CallState.PROCESSING, CallEvent.RESPONSE_READY): CallState.SPEAKING,
            (CallState.PROCESSING, CallEvent.TRANSFER_REQUESTED): CallState.TRANSFERRING,
            (CallState.PROCESSING, CallEvent.HANGUP): CallState.ENDED,
            (CallState.PROCESSING, CallEvent.ERROR): CallState.SPEAKING,  # Error message

            # From SPEAKING
            (CallState.SPEAKING, CallEvent.PLAYBACK_COMPLETE): CallState.LISTENING,
            (CallState.SPEAKING, CallEvent.HANGUP): CallState.ENDED,

            # From TRANSFERRING
            (CallState.TRANSFERRING, CallEvent.TRANSFER_COMPLETE): CallState.ENDED,
            (CallState.TRANSFERRING, CallEvent.ERROR): CallState.SPEAKING,
            (CallState.TRANSFERRING, CallEvent.HANGUP): CallState.ENDED,
        }

    async def handle_incoming_call(
        self,
        caller_id: str,
        callee_id: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> CallContext:
        """Handle an incoming phone call.

        Args:
            caller_id: Caller's phone number
            callee_id: Called number
            metadata: Additional call metadata

        Returns:
            Call context for the new call
        """
        async with self._call_lock:
            if self._current_call and self._current_call.state not in (CallState.IDLE, CallState.ENDED):
                log.warning("Already in call, rejecting", caller_id=caller_id)
                raise RuntimeError("Already handling a call")

            # Create call context
            self._current_call = CallContext(
                caller_id=caller_id,
                callee_id=callee_id,
                metadata=metadata or {},
            )

            # Transition to RINGING (caller already holds lock)
            await self._transition(CallEvent.INCOMING_CALL, _lock_held=True)

            log.info(
                "Incoming call",
                call_id=str(self._current_call.call_id),
                caller_id=caller_id,
            )

            return self._current_call

    async def answer_call(self) -> None:
        """Answer the current ringing call."""
        # Perform state checks and mutations under lock
        async with self._call_lock:
            if not self._current_call or self._current_call.state != CallState.RINGING:
                raise RuntimeError("No ringing call to answer")

            self._current_call.started_at = datetime.now()

            # Start conversation
            self._current_call.conversation = self.conversation_engine.start_conversation()

            # Transition to GREETING (caller already holds lock)
            await self._transition(CallEvent.CALL_ANSWERED, _lock_held=True)

            if self._on_call_start:
                self._on_call_start(self._current_call)

        # Long-running I/O operations outside lock
        # Start audio pipeline
        self.audio_pipeline.start()

        # Generate and play greeting
        await self._play_greeting()

    async def _play_greeting(self) -> None:
        """Generate and play greeting message."""
        if not self._current_call or not self._current_call.conversation:
            return

        greeting_text, greeting_audio = await self.conversation_engine.generate_greeting(
            self._current_call.conversation.id
        )

        log.info("Playing greeting", text=greeting_text[:50])

        # Play audio
        self.audio_pipeline.play(greeting_audio)

        # Wait for playback (approximate)
        await asyncio.sleep(len(greeting_audio) / 22050)  # Rough estimate

        await self._transition(CallEvent.GREETING_COMPLETE)

    async def process_utterance(self, audio: bytes | None = None) -> str:
        """Process user utterance and generate response.

        Args:
            audio: Audio bytes (if None, captures from pipeline)

        Returns:
            Response text
        """
        if not self._current_call or not self._current_call.conversation:
            raise RuntimeError("No active call")

        import numpy as np

        # Get audio
        if audio is None:
            # Capture from pipeline
            audio_array = await self.audio_pipeline.capture_utterance(timeout=30.0)
            if audio_array is None:
                # Timeout - prompt user
                await self._transition(CallEvent.TIMEOUT)
                return await self._speak_prompt()
        else:
            # Parse provided audio
            import io
            import wave

            with io.BytesIO(audio) as f:
                with wave.open(f, "rb") as wav:
                    frames = wav.readframes(wav.getnframes())
                    audio_array = np.frombuffer(frames, dtype=np.int16)
                    audio_array = audio_array.astype(np.float32) / 32768.0

        await self._transition(CallEvent.UTTERANCE_COMPLETE)

        # Process through conversation engine
        response_text, response_audio = await self.conversation_engine.process_audio(
            audio_array,
            self._current_call.conversation.id,
        )

        await self._transition(CallEvent.RESPONSE_READY)

        # Check for transfer trigger
        if self._should_transfer(response_text):
            await self._transition(CallEvent.TRANSFER_REQUESTED)
            return response_text

        # Play response
        self.audio_pipeline.play(response_audio)

        # Wait for playback
        await asyncio.sleep(len(response_audio) / 22050)

        await self._transition(CallEvent.PLAYBACK_COMPLETE)

        return response_text

    async def _speak_prompt(self) -> str:
        """Speak a prompt when user is silent."""
        prompt = "Entschuldigung, ich habe Sie nicht verstanden. Können Sie das bitte wiederholen?"

        if self._current_call and self._current_call.conversation:
            response_audio = await self.conversation_engine.tts.synthesize_async(prompt)
            self.audio_pipeline.play(response_audio)
            await asyncio.sleep(len(response_audio) / 22050)

        await self._transition(CallEvent.PLAYBACK_COMPLETE)
        return prompt

    def _should_transfer(self, response: str) -> bool:
        """Check if response indicates need for human transfer."""
        transfer_keywords = [
            "verbinde sie",
            "weiterleite",
            "notfall",
            "112",
            "sofort",
        ]
        response_lower = response.lower()
        return any(kw in response_lower for kw in transfer_keywords)

    async def hangup(self) -> CallContext | None:
        """End the current call."""
        if not self._current_call:
            return None

        call = self._current_call

        # Stop audio
        self.audio_pipeline.stop()

        # End conversation
        if call.conversation:
            self.conversation_engine.end_conversation(call.conversation.id)

        call.ended_at = datetime.now()
        await self._transition(CallEvent.HANGUP)

        if self._on_call_end:
            self._on_call_end(call)

        # Archive call
        self._call_history.append(call)
        self._current_call = None

        log.info(
            "Call ended",
            call_id=str(call.call_id),
            duration=call.duration_seconds,
        )

        return call

    async def _transition(self, event: CallEvent, _lock_held: bool = False) -> None:
        """Perform state transition based on event.

        Args:
            event: The event triggering the transition
            _lock_held: Internal flag indicating if caller already holds the lock
                       to avoid deadlock. Do not use externally.
        """
        async def _do_transition() -> None:
            if not self._current_call:
                return

            current_state = self._current_call.state
            key = (current_state, event)

            if key not in self._transitions:
                log.warning(
                    "Invalid transition",
                    current_state=current_state.name,
                    event=event.name,
                )
                return

            new_state = self._transitions[key]
            self._current_call.state = new_state

            log.debug(
                "State transition",
                from_state=current_state.name,
                event=event.name,
                to_state=new_state.name,
            )

            if self._on_state_change:
                self._on_state_change(current_state, new_state, self._current_call)

        if _lock_held:
            # Caller already holds lock, execute directly
            await _do_transition()
        else:
            # Acquire lock for thread-safe state transitions
            async with self._call_lock:
                await _do_transition()

    def on_state_change(
        self,
        callback: Callable[[CallState, CallState, CallContext], None],
    ) -> None:
        """Set callback for state changes."""
        self._on_state_change = callback

    def on_call_start(self, callback: Callable[[CallContext], None]) -> None:
        """Set callback for call start."""
        self._on_call_start = callback

    def on_call_end(self, callback: Callable[[CallContext], None]) -> None:
        """Set callback for call end."""
        self._on_call_end = callback

    @property
    def current_call(self) -> CallContext | None:
        """Get current call context."""
        return self._current_call

    @property
    def is_in_call(self) -> bool:
        """Check if currently handling a call."""
        return (
            self._current_call is not None
            and self._current_call.state not in (CallState.IDLE, CallState.ENDED)
        )
