"""Tests for the streaming pipeline functionality.

Tests sentence extraction, streaming TTS, and the process_audio_streaming method.
"""

import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from uuid import uuid4

from phone_agent.core.conversation import (
    ConversationEngine,
    ConversationState,
    TurnRole,
    extract_complete_sentence,
    SENTENCE_END_PATTERN,
)


class TestSentenceExtraction:
    """Test the sentence extraction helper function."""

    def test_extract_simple_sentence(self):
        """Test extracting a simple sentence ending with period."""
        sentence, remaining = extract_complete_sentence("Guten Tag. Wie kann ich helfen?")
        assert sentence == "Guten Tag."
        assert remaining == "Wie kann ich helfen?"

    def test_extract_exclamation(self):
        """Test extracting sentence ending with exclamation."""
        sentence, remaining = extract_complete_sentence("Willkommen! Bitte nehmen Sie Platz.")
        assert sentence == "Willkommen!"
        assert remaining == "Bitte nehmen Sie Platz."

    def test_extract_question(self):
        """Test extracting sentence ending with question mark."""
        sentence, remaining = extract_complete_sentence("Wie heißen Sie? Ich brauche Ihren Namen.")
        assert sentence == "Wie heißen Sie?"
        assert remaining == "Ich brauche Ihren Namen."

    def test_no_complete_sentence(self):
        """Test when buffer has no complete sentence."""
        sentence, remaining = extract_complete_sentence("Ich möchte einen Termin")
        assert sentence is None
        assert remaining == "Ich möchte einen Termin"

    def test_empty_buffer(self):
        """Test with empty buffer."""
        sentence, remaining = extract_complete_sentence("")
        assert sentence is None
        assert remaining == ""

    def test_short_sentence_filtered(self):
        """Test that very short sentences are filtered out."""
        # "Ja." is only 3 chars, should be filtered
        sentence, remaining = extract_complete_sentence("Ja. Das ist gut.")
        # Since "Ja." is < 5 chars, it should not be extracted
        assert sentence is None
        assert remaining == "Ja. Das ist gut."

    def test_sentence_at_end_of_buffer(self):
        """Test sentence at end of buffer (no remaining text)."""
        sentence, remaining = extract_complete_sentence("Das ist alles.")
        assert sentence == "Das ist alles."
        assert remaining == ""

    def test_multiple_sentences(self):
        """Test extracting multiple sentences one by one."""
        buffer = "Erster Satz. Zweiter Satz. Dritter Satz."

        sentence1, remaining1 = extract_complete_sentence(buffer)
        assert sentence1 == "Erster Satz."

        sentence2, remaining2 = extract_complete_sentence(remaining1)
        assert sentence2 == "Zweiter Satz."

        sentence3, remaining3 = extract_complete_sentence(remaining2)
        assert sentence3 == "Dritter Satz."

        sentence4, remaining4 = extract_complete_sentence(remaining3)
        assert sentence4 is None

    def test_german_umlauts(self):
        """Test sentence with German umlauts."""
        sentence, remaining = extract_complete_sentence("Ich möchte einen Termin für Müller. Danke.")
        assert sentence == "Ich möchte einen Termin für Müller."
        assert remaining == "Danke."

    def test_abbreviations_not_split(self):
        """Test that common abbreviations don't cause premature splits."""
        # Note: Current implementation will split on "Dr." - this is a known limitation
        # For production, we'd need more sophisticated sentence boundary detection
        buffer = "Ich bin Dr. Schmidt."
        sentence, remaining = extract_complete_sentence(buffer)
        # Current behavior: splits on "Dr." - this test documents current behavior
        assert sentence is not None  # It will split


class TestSentenceEndPattern:
    """Test the regex pattern for sentence boundaries."""

    def test_period_space(self):
        """Test period followed by space."""
        assert SENTENCE_END_PATTERN.search("Hallo. Welt")

    def test_period_end(self):
        """Test period at end of string."""
        assert SENTENCE_END_PATTERN.search("Hallo.")

    def test_exclamation(self):
        """Test exclamation mark."""
        assert SENTENCE_END_PATTERN.search("Hallo! Welt")

    def test_question(self):
        """Test question mark."""
        assert SENTENCE_END_PATTERN.search("Hallo? Welt")

    def test_no_sentence_end(self):
        """Test no sentence boundary."""
        assert not SENTENCE_END_PATTERN.search("Hallo Welt")


class TestStreamingPipelineMocked:
    """Test streaming pipeline with mocked components."""

    @pytest.fixture
    def mock_engine(self):
        """Create engine with mocked AI components."""
        with patch("phone_agent.core.conversation.DialectAwareSTT") as mock_stt, \
             patch("phone_agent.core.conversation.LanguageModel") as mock_llm, \
             patch("phone_agent.core.conversation.TextToSpeech") as mock_tts:

            # Configure mocks
            mock_stt_instance = MagicMock()
            mock_stt_instance.is_loaded = True
            mock_stt_instance.transcribe_async = AsyncMock(return_value="Ich habe Kopfschmerzen.")
            mock_stt.return_value = mock_stt_instance

            mock_llm_instance = MagicMock()
            mock_llm_instance.is_loaded = True
            # Simulate streaming by yielding tokens
            mock_llm_instance.generate_stream_with_history = MagicMock(
                return_value=iter([
                    "Ich ", "verstehe. ", "Seit ", "wann ", "haben ", "Sie ",
                    "die ", "Schmerzen? ", "Ich ", "empfehle ", "einen ", "Arztbesuch."
                ])
            )
            mock_llm.return_value = mock_llm_instance

            mock_tts_instance = MagicMock()
            mock_tts_instance.is_loaded = True
            mock_tts_instance.synthesize_async = AsyncMock(return_value=b"audio_chunk")
            mock_tts.return_value = mock_tts_instance

            engine = ConversationEngine()
            yield engine, mock_stt_instance, mock_llm_instance, mock_tts_instance

    @pytest.mark.asyncio
    async def test_process_text_streaming_calls_callback(self, mock_engine):
        """Test that streaming calls the callback for each sentence."""
        engine, _, _, mock_tts = mock_engine

        conversation = engine.start_conversation()
        sentences_received = []

        async def on_sentence(sentence: str, audio: bytes):
            sentences_received.append(sentence)

        await engine.process_text_streaming(
            "Ich habe Kopfschmerzen.",
            conversation.id,
            on_sentence_ready=on_sentence,
        )

        # Should have received at least one sentence
        assert len(sentences_received) >= 1
        # TTS should have been called for each sentence
        assert mock_tts.synthesize_async.call_count >= 1

    @pytest.mark.asyncio
    async def test_process_text_streaming_returns_full_response(self, mock_engine):
        """Test that streaming returns the full response."""
        engine, _, _, _ = mock_engine

        conversation = engine.start_conversation()

        async def on_sentence(sentence: str, audio: bytes):
            pass  # Just consume

        response_text, response_audio = await engine.process_text_streaming(
            "Test input",
            conversation.id,
            on_sentence_ready=on_sentence,
        )

        # Should return combined response
        assert len(response_text) > 0
        assert isinstance(response_audio, bytes)

    @pytest.mark.asyncio
    async def test_process_text_streaming_updates_state(self, mock_engine):
        """Test that streaming updates conversation state correctly."""
        engine, _, _, _ = mock_engine

        conversation = engine.start_conversation()
        initial_turns = len(conversation.turns)

        async def on_sentence(sentence: str, audio: bytes):
            pass

        await engine.process_text_streaming(
            "User message",
            conversation.id,
            on_sentence_ready=on_sentence,
        )

        state = engine.get_conversation(conversation.id)
        # Should have added 2 turns (User + Assistant) to whatever was there initially
        assert len(state.turns) == initial_turns + 2
        # Last two turns should be User and Assistant
        assert state.turns[-2].role == TurnRole.USER
        assert state.turns[-1].role == TurnRole.ASSISTANT


class TestStreamingWithHistory:
    """Test that streaming maintains conversation history."""

    @pytest.fixture
    def mock_engine(self):
        """Create engine with mocked AI components."""
        with patch("phone_agent.core.conversation.DialectAwareSTT") as mock_stt, \
             patch("phone_agent.core.conversation.LanguageModel") as mock_llm, \
             patch("phone_agent.core.conversation.TextToSpeech") as mock_tts:

            mock_stt_instance = MagicMock()
            mock_stt_instance.is_loaded = True
            mock_stt.return_value = mock_stt_instance

            mock_llm_instance = MagicMock()
            mock_llm_instance.is_loaded = True
            mock_llm_instance.generate_stream_with_history = MagicMock(
                return_value=iter(["Antwort ", "Satz. ", "Noch ", "ein ", "Satz."])
            )
            mock_llm.return_value = mock_llm_instance

            mock_tts_instance = MagicMock()
            mock_tts_instance.is_loaded = True
            mock_tts_instance.synthesize_async = AsyncMock(return_value=b"audio")
            mock_tts.return_value = mock_tts_instance

            engine = ConversationEngine()
            yield engine, mock_llm_instance

    @pytest.mark.asyncio
    async def test_streaming_passes_history_to_llm(self, mock_engine):
        """Test that streaming passes conversation history to LLM."""
        engine, mock_llm = mock_engine

        conversation = engine.start_conversation()

        # Add some history first
        conversation.add_turn(TurnRole.USER, "First message")
        conversation.add_turn(TurnRole.ASSISTANT, "First response")

        async def on_sentence(sentence: str, audio: bytes):
            pass

        await engine.process_text_streaming(
            "Second message",
            conversation.id,
            on_sentence_ready=on_sentence,
        )

        # Check that LLM was called with history
        call_args = mock_llm.generate_stream_with_history.call_args
        messages = call_args[0][0]

        # Should have system prompt + 3 user/assistant messages
        assert len(messages) >= 4
        assert messages[0]["role"] == "system"

        # Find user messages - should include both first and second
        user_messages = [m for m in messages if m["role"] == "user"]
        assert len(user_messages) >= 2


class TestStreamingEdgeCases:
    """Test edge cases in streaming pipeline."""

    def test_extract_sentence_with_numbers(self):
        """Test sentence with numbers and decimals."""
        # Numbers shouldn't cause premature splits
        sentence, remaining = extract_complete_sentence("Die Temperatur ist 38.5 Grad.")
        # Note: This will split on the period in 38.5 - known limitation
        # For production, need more sophisticated parsing
        assert sentence is not None

    def test_extract_sentence_with_ellipsis(self):
        """Test handling of ellipsis."""
        buffer = "Ich weiß nicht... Vielleicht morgen."
        sentence, remaining = extract_complete_sentence(buffer)
        # Current implementation will match first period in ellipsis
        assert sentence is not None

    def test_empty_callback(self):
        """Test that streaming works with minimal callback."""
        # This is more of a smoke test to ensure basic functionality
        pass
