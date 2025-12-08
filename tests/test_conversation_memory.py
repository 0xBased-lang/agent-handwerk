"""Tests for conversation memory functionality.

Tests that the LLM correctly receives and uses conversation history
to maintain context across multiple turns.
"""

import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from uuid import uuid4

from phone_agent.core.conversation import (
    ConversationEngine,
    ConversationState,
    ConversationTurn,
    TurnRole,
)


class TestConversationState:
    """Test ConversationState memory functionality."""

    def test_add_turn_stores_content(self):
        """Test that turns are stored correctly."""
        state = ConversationState()
        state.add_turn(TurnRole.USER, "Hallo, ich bin Peter.")
        state.add_turn(TurnRole.ASSISTANT, "Guten Tag, Peter!")

        assert len(state.turns) == 2
        assert state.turns[0].role == TurnRole.USER
        assert state.turns[0].content == "Hallo, ich bin Peter."
        assert state.turns[1].role == TurnRole.ASSISTANT
        assert state.turns[1].content == "Guten Tag, Peter!"

    def test_get_history_for_llm_format(self):
        """Test that history is formatted correctly for LLM."""
        state = ConversationState()
        state.add_turn(TurnRole.USER, "Ich habe Kopfschmerzen.")
        state.add_turn(TurnRole.ASSISTANT, "Seit wann haben Sie Kopfschmerzen?")
        state.add_turn(TurnRole.USER, "Seit gestern Abend.")

        history = state.get_history_for_llm()

        assert len(history) == 3
        assert history[0] == {"role": "user", "content": "Ich habe Kopfschmerzen."}
        assert history[1] == {"role": "assistant", "content": "Seit wann haben Sie Kopfschmerzen?"}
        assert history[2] == {"role": "user", "content": "Seit gestern Abend."}

    def test_get_history_max_turns(self):
        """Test that max_turns limits history length."""
        state = ConversationState()
        # Add 10 turns (20 total: 10 user + 10 assistant)
        for i in range(10):
            state.add_turn(TurnRole.USER, f"User message {i}")
            state.add_turn(TurnRole.ASSISTANT, f"Assistant message {i}")

        history = state.get_history_for_llm(max_turns=4)

        # Should only include the last 4 turns
        assert len(history) == 4
        # And they should be the most recent ones (messages 8 and 9)
        assert "User message 9" in history[-2]["content"]
        assert "Assistant message 9" in history[-1]["content"]

    def test_empty_history(self):
        """Test history for new conversation."""
        state = ConversationState()
        history = state.get_history_for_llm()
        assert history == []

    def test_dialect_tracking_fields(self):
        """Test that dialect tracking fields exist."""
        state = ConversationState()
        assert state.detected_dialect is None
        assert state.dialect_confidence == 0.0
        assert state.dialect_features == []


class TestConversationEngineMemory:
    """Test ConversationEngine memory integration."""

    @pytest.fixture
    def mock_engine(self):
        """Create engine with mocked AI components."""
        with patch("phone_agent.core.conversation.DialectAwareSTT") as mock_stt, \
             patch("phone_agent.core.conversation.LanguageModel") as mock_llm, \
             patch("phone_agent.core.conversation.TextToSpeech") as mock_tts:

            # Configure mocks
            mock_stt_instance = MagicMock()
            mock_stt_instance.is_loaded = True
            mock_stt.return_value = mock_stt_instance

            mock_llm_instance = MagicMock()
            mock_llm_instance.is_loaded = True
            mock_llm_instance.generate_with_history_async = AsyncMock(
                return_value="Ich verstehe. Wie kann ich Ihnen helfen?"
            )
            mock_llm.return_value = mock_llm_instance

            mock_tts_instance = MagicMock()
            mock_tts_instance.is_loaded = True
            mock_tts_instance.synthesize_async = AsyncMock(return_value=b"audio_bytes")
            mock_tts.return_value = mock_tts_instance

            engine = ConversationEngine()
            yield engine, mock_llm_instance

    @pytest.mark.asyncio
    async def test_process_text_passes_history(self, mock_engine):
        """Test that process_text passes conversation history to LLM."""
        engine, mock_llm = mock_engine

        # Start conversation
        conv = engine.start_conversation()

        # First turn
        await engine.process_text("Hallo, ich bin Peter.", conv.id)

        # Verify LLM was called with history
        call_args = mock_llm.generate_with_history_async.call_args
        messages = call_args[0][0]

        # Should have system prompt + user message
        assert len(messages) >= 2
        assert messages[0]["role"] == "system"
        assert messages[-1]["role"] == "user"
        assert "Peter" in messages[-1]["content"]

    @pytest.mark.asyncio
    async def test_multi_turn_conversation_passes_full_history(self, mock_engine):
        """Test that multi-turn conversations include all history."""
        engine, mock_llm = mock_engine

        # Configure mock to return different responses
        responses = iter([
            "Guten Tag, Peter!",
            "Seit wann haben Sie die Schmerzen?",
            "Ich empfehle einen Termin beim Arzt.",
        ])
        mock_llm.generate_with_history_async = AsyncMock(
            side_effect=lambda msgs: next(responses)
        )

        # Start conversation
        conv = engine.start_conversation()

        # Turn 1
        await engine.process_text("Ich bin Peter.", conv.id)

        # Turn 2
        await engine.process_text("Ich habe Kopfschmerzen.", conv.id)

        # Verify second call includes previous turn
        call_args = mock_llm.generate_with_history_async.call_args
        messages = call_args[0][0]

        # Should have: system + user1 + assistant1 + user2
        assert len(messages) >= 4

        # Find user messages
        user_messages = [m for m in messages if m["role"] == "user"]
        assert len(user_messages) == 2
        assert "Peter" in user_messages[0]["content"]
        assert "Kopfschmerzen" in user_messages[1]["content"]

    @pytest.mark.asyncio
    async def test_conversation_remembers_name(self, mock_engine):
        """Test that LLM receives name from previous turns."""
        engine, mock_llm = mock_engine

        conv = engine.start_conversation()

        # User introduces themselves
        await engine.process_text("Ich heiße Maria Schmidt.", conv.id)

        # Second message asking about their symptoms
        await engine.process_text("Ich habe seit zwei Tagen Fieber.", conv.id)

        # Verify the history includes the name
        call_args = mock_llm.generate_with_history_async.call_args
        messages = call_args[0][0]

        # The history should contain the name from the first message
        history_text = str(messages)
        assert "Maria" in history_text or "Schmidt" in history_text


class TestLLMHistoryMethods:
    """Test LLM generate_with_history methods."""

    def test_generate_with_history_formats_messages(self):
        """Test that generate_with_history accepts message format."""
        from phone_agent.ai import LanguageModel

        # This tests the method signature, not actual generation
        llm = LanguageModel.__new__(LanguageModel)
        llm._loaded = False
        llm._model = None
        llm._llm = None
        llm.temperature = 0.7
        llm.max_tokens = 150
        llm._device = "cpu"

        # Verify method exists and signature is correct
        assert hasattr(llm, "generate_with_history")
        assert hasattr(llm, "generate_with_history_async")
        assert hasattr(llm, "generate_stream_with_history")


class TestDialectAwarePrompts:
    """Test that dialect detection affects system prompts."""

    def test_build_system_prompt_standard(self):
        """Test system prompt for standard German."""
        with patch("phone_agent.core.conversation.DialectAwareSTT"), \
             patch("phone_agent.core.conversation.LanguageModel"), \
             patch("phone_agent.core.conversation.TextToSpeech"):

            engine = ConversationEngine()
            state = ConversationState()
            state.detected_dialect = "de_standard"

            prompt = engine._build_system_prompt_with_dialect(state)

            # Should not include dialect hints for standard German
            assert "DIALEKT-HINWEIS" not in prompt

    def test_build_system_prompt_alemannic(self):
        """Test system prompt includes dialect context for Schwäbisch."""
        with patch("phone_agent.core.conversation.DialectAwareSTT"), \
             patch("phone_agent.core.conversation.LanguageModel"), \
             patch("phone_agent.core.conversation.TextToSpeech"):

            engine = ConversationEngine()
            state = ConversationState()
            state.detected_dialect = "de_alemannic"

            prompt = engine._build_system_prompt_with_dialect(state)

            # Should include dialect hints
            assert "DIALEKT-HINWEIS" in prompt
            assert "Schwäbisch" in prompt or "Alemannisch" in prompt
            assert "Hochdeutsch" in prompt  # Response language

    def test_build_system_prompt_bavarian(self):
        """Test system prompt includes dialect context for Bavarian."""
        with patch("phone_agent.core.conversation.DialectAwareSTT"), \
             patch("phone_agent.core.conversation.LanguageModel"), \
             patch("phone_agent.core.conversation.TextToSpeech"):

            engine = ConversationEngine()
            state = ConversationState()
            state.detected_dialect = "de_bavarian"

            prompt = engine._build_system_prompt_with_dialect(state)

            # Should include dialect hints
            assert "DIALEKT-HINWEIS" in prompt
            assert "Bayerisch" in prompt


class TestConversationContextRetention:
    """Test that conversation context is retained across turns."""

    def test_state_retains_turns(self):
        """Test that state retains all turns."""
        state = ConversationState()

        # Simulate a multi-turn healthcare conversation
        state.add_turn(TurnRole.USER, "Guten Tag, ich möchte einen Termin.")
        state.add_turn(TurnRole.ASSISTANT, "Guten Tag! Wann hätten Sie Zeit?")
        state.add_turn(TurnRole.USER, "Am Montag wäre gut.")
        state.add_turn(TurnRole.ASSISTANT, "Um wieviel Uhr am Montag?")
        state.add_turn(TurnRole.USER, "10 Uhr wäre ideal.")

        assert len(state.turns) == 5

        # Get full history
        history = state.get_history_for_llm()
        assert len(history) == 5

        # Verify chronological order
        assert "Termin" in history[0]["content"]
        assert "Montag" in history[2]["content"]
        assert "10 Uhr" in history[4]["content"]

    def test_triage_result_preserved(self):
        """Test that triage results are preserved in turn metadata."""
        state = ConversationState()

        # Add turn with triage result
        from phone_agent.industry.gesundheit import UrgencyLevel

        class MockTriageResult:
            level = UrgencyLevel.URGENT
            reason = "Fieber über 39°C"

        turn = state.add_turn(
            TurnRole.USER,
            "Ich habe hohes Fieber.",
            triage_result=MockTriageResult(),
        )

        assert turn.triage_result is not None
        assert turn.triage_result.level == UrgencyLevel.URGENT
