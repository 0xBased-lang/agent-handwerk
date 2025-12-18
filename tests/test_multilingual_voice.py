"""Tests for multilingual voice agent functionality.

Tests the ability to detect and respond in multiple languages:
- German (de) - Default, including standard German
- Russian (ru) - Cyrillic character detection
- Turkish (tr) - Turkish-specific character detection
- Schwäbisch - German dialect (understood, responds in standard German)

Also tests translation of job descriptions to German for database storage.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from phone_agent.ai.text_language_detector import (
    TextLanguageDetector,
    DetectedLanguage,
    LanguageDetectionResult,
    detect_language,
    get_response_language,
)
from phone_agent.services.language_context import (
    ConversationLanguageManager,
    MultilingualPromptSelector,
    MessageLanguageInfo,
    ConversationLanguageState,
)
from phone_agent.services.translation_service import (
    TranslationService,
    TranslationResult,
)


class TestTextLanguageDetector:
    """Test text-based language detection."""

    @pytest.fixture
    def detector(self):
        return TextLanguageDetector()

    # German detection tests
    @pytest.mark.parametrize(
        "text",
        [
            "Ich habe einen Stromausfall",
            "Meine Heizung funktioniert nicht",
            "Ich brauche einen Termin beim Elektriker",
            "Die Sicherung ist rausgeflogen",
            "Guten Tag, ich habe ein Problem mit meiner Steckdose",
        ],
    )
    def test_german_detection(self, detector, text):
        """Test that standard German text is correctly detected."""
        result = detector.detect(text)
        assert result.language == DetectedLanguage.GERMAN
        assert result.is_dialect is False
        assert result.confidence >= 0.7

    # Russian detection tests
    @pytest.mark.parametrize(
        "text,expected_confidence",
        [
            ("У меня нет электричества", 0.7),
            ("Мне нужен электрик", 0.7),
            ("Срочный ремонт розетки", 0.7),
            ("Здравствуйте, у меня проблема", 0.7),
            ("Отключился свет во всей квартире", 0.7),
        ],
    )
    def test_russian_detection(self, detector, text, expected_confidence):
        """Test that Russian text (Cyrillic) is correctly detected."""
        result = detector.detect(text)
        assert result.language == DetectedLanguage.RUSSIAN
        assert result.is_dialect is False
        assert result.confidence >= expected_confidence

    # Turkish detection tests
    # Note: Turkish is detected by specific characters: şŞğĞıİçÇ
    # Plain ASCII Turkish text without these chars defaults to German
    @pytest.mark.parametrize(
        "text",
        [
            "Işıklar yanmıyor",  # ı and ı
            "Bir teknisyen çağırmam lazım",  # ç and ı
            "Merhaba, yardıma ihtiyacım var",  # ı
            "Elektrik kesintisi var, çok acil",  # ç
            "Lütfen bana yardım edin",  # ü
        ],
    )
    def test_turkish_detection(self, detector, text):
        """Test that Turkish text with special chars is correctly detected."""
        result = detector.detect(text)
        assert result.language == DetectedLanguage.TURKISH
        assert result.is_dialect is False
        assert result.confidence >= 0.7

    def test_turkish_without_special_chars_defaults_to_german(self, detector):
        """Test that Turkish without special chars defaults to German.

        This is a known limitation of character-based detection.
        Text like 'Elektrik kesintisi var' has no Turkish-specific chars.
        """
        result = detector.detect("Elektrik kesintisi var")
        # Without special Turkish chars, defaults to German
        assert result.language == DetectedLanguage.GERMAN

    # English detection tests
    # Note: English detection requires at least 2 pattern matches
    @pytest.mark.parametrize(
        "text",
        [
            "I have a power outage and I need help",
            "Hello, I need help with my electrical system",
            "The outlet is broken and I need a repair",
            "Hello, can you help me with the electricity?",
            "I have a problem, my heater is not working",
        ],
    )
    def test_english_detection(self, detector, text):
        """Test that English text is correctly detected."""
        result = detector.detect(text)
        assert result.language == DetectedLanguage.ENGLISH
        assert result.is_dialect is False
        assert result.confidence >= 0.7

    def test_english_single_word_defaults_to_german(self, detector):
        """Test that single English words default to German.

        Need at least 2 English patterns to trigger detection.
        """
        result = detector.detect("Hello")
        # Single word with one pattern defaults to German
        assert result.language == DetectedLanguage.GERMAN

    # Schwäbisch dialect tests
    @pytest.mark.parametrize(
        "text",
        [
            "I hab koi Strom",
            "Des isch a bissle dringend",
            "I brauch schnell an Elektriker, gell",
            "Mei Heizung goht net",
            "I muss des mädle abhola",
        ],
    )
    def test_schwaebisch_detection(self, detector, text):
        """Test that Schwäbisch dialect is detected as German dialect."""
        result = detector.detect(text)
        assert result.language == DetectedLanguage.GERMAN
        assert result.is_dialect is True
        assert result.dialect_name == "schwäbisch"

    def test_schwaebisch_response_language(self, detector):
        """Test that Schwäbisch gets German as response language."""
        result = detector.detect("I hab a Problem mit dr Steckdose, bissle dringend")
        assert result.response_language == DetectedLanguage.GERMAN

    # Edge cases
    def test_empty_text(self, detector):
        """Test handling of empty text."""
        result = detector.detect("")
        assert result.language == DetectedLanguage.GERMAN
        assert result.confidence == 0.0

    def test_whitespace_only(self, detector):
        """Test handling of whitespace-only text."""
        result = detector.detect("   \n\t  ")
        assert result.language == DetectedLanguage.GERMAN
        assert result.confidence == 0.0


class TestConvenienceFunctions:
    """Test module-level convenience functions."""

    def test_detect_language_function(self):
        """Test the detect_language convenience function."""
        result = detect_language("У меня нет электричества")
        assert result.language == DetectedLanguage.RUSSIAN

    def test_get_response_language_function(self):
        """Test the get_response_language convenience function."""
        lang = get_response_language("I hab koi Strom, bissle dringend")
        assert lang == "de"  # Schwäbisch → German response


class TestConversationLanguageManager:
    """Test conversation language management."""

    @pytest.fixture
    def manager(self):
        return ConversationLanguageManager()

    def test_initial_state(self, manager):
        """Test initial conversation state."""
        assert manager.current_language == "de"
        assert manager.schwabisch_detected is False

    def test_process_german_message(self, manager):
        """Test processing a German message."""
        msg_info = manager.process_message("Ich habe einen Stromausfall")
        assert msg_info.detected_language == "de"
        assert msg_info.response_language == "de"
        assert not msg_info.is_dialect

    def test_process_russian_message(self, manager):
        """Test processing a Russian message."""
        msg_info = manager.process_message("У меня нет электричества")
        assert msg_info.detected_language == "ru"
        assert msg_info.response_language == "ru"
        assert manager.current_language == "ru"

    def test_process_turkish_message(self, manager):
        """Test processing a Turkish message."""
        msg_info = manager.process_message("Elektrik kesintisi var, çok acil")
        assert msg_info.detected_language == "tr"
        assert msg_info.response_language == "tr"
        assert manager.current_language == "tr"

    def test_process_schwaebisch_message(self, manager):
        """Test processing a Schwäbisch message."""
        msg_info = manager.process_message("I hab a bissle Problem")
        assert msg_info.detected_language == "de"
        assert msg_info.is_dialect is True
        assert msg_info.response_language == "de"  # Respond in standard German
        assert manager.schwabisch_detected is True

    def test_process_english_message(self, manager):
        """Test processing an English message."""
        msg_info = manager.process_message("I have a problem with the electricity")
        assert msg_info.detected_language == "en"
        assert msg_info.response_language == "en"
        assert manager.current_language == "en"

    def test_language_switching(self, manager):
        """Test dynamic language switching in conversation."""
        # Start with German
        manager.process_message("Hallo, ich brauche Hilfe")
        assert manager.current_language == "de"

        # Switch to Russian
        manager.process_message("Мне нужна помощь с электричеством")
        assert manager.current_language == "ru"

        # Switch back to German
        manager.process_message("Danke, das reicht erstmal")
        assert manager.current_language == "de"

    def test_message_history(self, manager):
        """Test that message history is maintained."""
        manager.process_message("Erste Nachricht")
        manager.process_message("Вторая сообщение")
        manager.process_message("Üçüncü mesaj")

        assert len(manager._state.message_history) == 3

    def test_reset(self, manager):
        """Test conversation reset."""
        manager.process_message("У меня нет электричества")
        assert manager.current_language == "ru"

        manager.reset()
        assert manager.current_language == "de"
        assert len(manager._state.message_history) == 0


class TestMultilingualPromptSelector:
    """Test multilingual prompt selection."""

    @pytest.fixture
    def selector(self):
        return MultilingualPromptSelector("handwerk")

    def test_german_prompt(self, selector):
        """Test German prompt selection."""
        prompt = selector.get_system_prompt("de")
        assert len(prompt) > 100  # Should have substantial content
        assert "Handwerk" in prompt or "Elektro" in prompt.lower() or "Kunde" in prompt

    def test_russian_prompt(self, selector):
        """Test Russian prompt selection.

        Note: If prompts_ru.py doesn't have CHAT_SYSTEM_PROMPT,
        it falls back to German prompts. This test checks that
        the selector returns a valid prompt in either case.
        """
        prompt = selector.get_system_prompt("ru")
        assert len(prompt) > 100
        # Either contains Cyrillic (Russian) or German text (fallback)
        has_cyrillic = any('\u0400' <= c <= '\u04FF' for c in prompt)
        has_german_content = "Handwerk" in prompt or "Elektro" in prompt.lower()
        assert has_cyrillic or has_german_content

    def test_turkish_prompt(self, selector):
        """Test Turkish prompt selection."""
        prompt = selector.get_system_prompt("tr")
        assert len(prompt) > 100

    def test_greeting_german(self, selector):
        """Test German greeting."""
        greeting = selector.get_greeting("de")
        assert "Tag" in greeting or "Hallo" in greeting or "helfen" in greeting

    def test_greeting_russian(self, selector):
        """Test Russian greeting."""
        greeting = selector.get_greeting("ru")
        assert any('\u0400' <= c <= '\u04FF' for c in greeting)

    def test_greeting_turkish(self, selector):
        """Test Turkish greeting."""
        greeting = selector.get_greeting("tr")
        assert "Merhaba" in greeting or "yardım" in greeting

    def test_greeting_english(self, selector):
        """Test English greeting."""
        greeting = selector.get_greeting("en")
        assert "Hello" in greeting or "help" in greeting

    def test_job_created_message(self, selector):
        """Test job created messages in different languages."""
        job_number = "JOB-2024-0001"

        german_msg = selector.get_job_created_message("de", job_number)
        assert job_number in german_msg
        assert "Auftrag" in german_msg

        russian_msg = selector.get_job_created_message("ru", job_number)
        assert job_number in russian_msg

        turkish_msg = selector.get_job_created_message("tr", job_number)
        assert job_number in turkish_msg

        english_msg = selector.get_job_created_message("en", job_number)
        assert job_number in english_msg
        assert "job" in english_msg or "created" in english_msg


class TestTranslationService:
    """Test translation service functionality."""

    @pytest.fixture
    def service(self):
        return TranslationService()

    @pytest.mark.asyncio
    async def test_german_no_translation(self, service):
        """Test that German text is not translated."""
        result = await service.translate_to_german(
            "Ich habe einen Stromausfall",
            source_language="de",
        )
        assert result.success is True
        assert result.german_text == "Ich habe einen Stromausfall"
        assert result.was_translated is False

    @pytest.mark.asyncio
    async def test_empty_text(self, service):
        """Test empty text handling."""
        result = await service.translate_to_german(
            "",
            source_language="ru",
        )
        assert result.success is True
        assert result.german_text == ""

    @pytest.mark.asyncio
    async def test_translation_result_dataclass(self):
        """Test TranslationResult dataclass."""
        result = TranslationResult(
            german_text="Stromausfall",
            original_text="Отключение электричества",
            source_language="ru",
            success=True,
        )
        assert result.was_translated is True
        assert result.german_text == "Stromausfall"
        assert result.original_text == "Отключение электричества"

    @pytest.mark.asyncio
    async def test_translation_failure_returns_original(self, service):
        """Test that translation failure returns original text."""
        # Without Groq client, translation should fail gracefully
        result = await service.translate_to_german(
            "Test text",
            source_language="ru",
        )
        # Should return original text as fallback
        assert result.german_text == "Test text"
        assert result.success is False  # No client available


class TestTranslationWithMockedLLM:
    """Test translation with mocked LLM client."""

    @pytest.mark.asyncio
    async def test_russian_translation(self):
        """Test Russian to German translation with mocked LLM."""
        mock_client = MagicMock()
        mock_client._loaded = True
        mock_client.generate_async = AsyncMock(return_value="Stromausfall in der Wohnung")

        service = TranslationService(groq_client=mock_client)
        result = await service.translate_to_german(
            "Отключение электричества в квартире",
            source_language="ru",
        )

        assert result.success is True
        assert result.german_text == "Stromausfall in der Wohnung"
        assert result.original_text == "Отключение электричества в квартире"
        assert result.was_translated is True

    @pytest.mark.asyncio
    async def test_turkish_translation(self):
        """Test Turkish to German translation with mocked LLM."""
        mock_client = MagicMock()
        mock_client._loaded = True
        mock_client.generate_async = AsyncMock(return_value="Steckdose funktioniert nicht")

        service = TranslationService(groq_client=mock_client)
        result = await service.translate_to_german(
            "Priz çalışmıyor",
            source_language="tr",
        )

        assert result.success is True
        assert result.german_text == "Steckdose funktioniert nicht"
        assert result.was_translated is True

    @pytest.mark.asyncio
    async def test_translate_job_fields(self):
        """Test translating multiple job fields."""
        mock_client = MagicMock()
        mock_client._loaded = True
        mock_client.generate_async = AsyncMock(
            side_effect=[
                "Dringender Stromausfall",
                "Kunde bittet um schnelle Hilfe",
            ]
        )

        service = TranslationService(groq_client=mock_client)
        result = await service.translate_job_fields(
            description="Срочное отключение электричества",
            source_language="ru",
            customer_notes="Клиент просит быстрой помощи",
        )

        assert result["description"] == "Dringender Stromausfall"
        assert result["customer_notes"] == "Kunde bittet um schnelle Hilfe"
        assert result["original_description"] == "Срочное отключение электричества"
        assert result["translation_success"] is True


class TestLanguageDetectionResults:
    """Test LanguageDetectionResult dataclass."""

    def test_response_language_for_dialect(self):
        """Test that dialects return standard German for responses."""
        result = LanguageDetectionResult(
            language=DetectedLanguage.GERMAN,
            is_dialect=True,
            confidence=0.8,
            dialect_name="schwäbisch",
        )
        assert result.response_language == DetectedLanguage.GERMAN

    def test_response_language_for_russian(self):
        """Test that Russian returns Russian for responses."""
        result = LanguageDetectionResult(
            language=DetectedLanguage.RUSSIAN,
            is_dialect=False,
            confidence=0.9,
        )
        assert result.response_language == DetectedLanguage.RUSSIAN


class TestMultilingualIntegration:
    """Integration tests for complete multilingual flow."""

    @pytest.mark.asyncio
    async def test_full_russian_conversation_flow(self):
        """Test complete flow: Russian input → Detection → Translation → German storage."""
        # 1. Detect language
        detector = TextLanguageDetector()
        russian_text = "У меня проблема с электричеством, нет света"
        detection = detector.detect(russian_text)
        assert detection.language == DetectedLanguage.RUSSIAN

        # 2. Get response language
        lang_manager = ConversationLanguageManager()
        msg_info = lang_manager.process_message(russian_text)
        assert msg_info.response_language == "ru"

        # 3. Select prompts for response
        prompt_selector = MultilingualPromptSelector("handwerk")
        system_prompt = prompt_selector.get_system_prompt("ru")
        assert len(system_prompt) > 0

        # 4. Translate for storage (mocked)
        mock_client = MagicMock()
        mock_client._loaded = True
        mock_client.generate_async = AsyncMock(
            return_value="Ich habe ein Problem mit der Elektrik, kein Licht"
        )

        translator = TranslationService(groq_client=mock_client)
        translation = await translator.translate_to_german(russian_text, "ru")

        assert translation.success is True
        assert translation.was_translated is True
        assert "Elektrik" in translation.german_text or "Licht" in translation.german_text

    @pytest.mark.asyncio
    async def test_full_turkish_conversation_flow(self):
        """Test complete flow: Turkish input → Detection → Translation → German storage."""
        # 1. Detect language
        detector = TextLanguageDetector()
        turkish_text = "Acil elektrik arızası var, ışıklar yanmıyor"
        detection = detector.detect(turkish_text)
        assert detection.language == DetectedLanguage.TURKISH

        # 2. Get response language
        lang_manager = ConversationLanguageManager()
        msg_info = lang_manager.process_message(turkish_text)
        assert msg_info.response_language == "tr"

        # 3. Translate for storage (mocked)
        mock_client = MagicMock()
        mock_client._loaded = True
        mock_client.generate_async = AsyncMock(
            return_value="Dringender Elektrikfehler, Lichter funktionieren nicht"
        )

        translator = TranslationService(groq_client=mock_client)
        translation = await translator.translate_to_german(turkish_text, "tr")

        assert translation.success is True
        assert translation.was_translated is True

    def test_full_schwaebisch_flow(self):
        """Test Schwäbisch flow: Understand dialect, respond in standard German."""
        # 1. Detect language
        detector = TextLanguageDetector()
        schwaebisch_text = "I hab koi Strom, des isch a bissle dringend, gell"
        detection = detector.detect(schwaebisch_text)

        assert detection.language == DetectedLanguage.GERMAN
        assert detection.is_dialect is True
        assert detection.dialect_name == "schwäbisch"

        # 2. Get response language (should be standard German)
        lang_manager = ConversationLanguageManager()
        msg_info = lang_manager.process_message(schwaebisch_text)

        assert msg_info.response_language == "de"
        assert lang_manager.schwabisch_detected is True

        # 3. No translation needed - already German
        # The system should respond in standard German, not Schwäbisch

    @pytest.mark.asyncio
    async def test_full_english_conversation_flow(self):
        """Test complete flow: English input → Detection → Translation → German storage."""
        # 1. Detect language
        detector = TextLanguageDetector()
        english_text = "I have a problem with my electrical outlet, it's not working"
        detection = detector.detect(english_text)
        assert detection.language == DetectedLanguage.ENGLISH

        # 2. Get response language
        lang_manager = ConversationLanguageManager()
        msg_info = lang_manager.process_message(english_text)
        assert msg_info.response_language == "en"

        # 3. Select prompts for response
        prompt_selector = MultilingualPromptSelector("handwerk")
        greeting = prompt_selector.get_greeting("en")
        assert "Hello" in greeting or "help" in greeting

        # 4. Translate for storage (mocked)
        mock_client = MagicMock()
        mock_client._loaded = True
        mock_client.generate_async = AsyncMock(
            return_value="Ich habe ein Problem mit meiner Steckdose, sie funktioniert nicht"
        )

        translator = TranslationService(groq_client=mock_client)
        translation = await translator.translate_to_german(english_text, "en")

        assert translation.success is True
        assert translation.was_translated is True
        assert "Steckdose" in translation.german_text or "Problem" in translation.german_text


class TestConversationLanguageState:
    """Test conversation language state tracking."""

    def test_dominant_language_single(self):
        """Test dominant language with single language."""
        state = ConversationLanguageState()
        state.message_history = [
            MessageLanguageInfo(
                text="Text",
                detected_language="de",
                is_dialect=False,
                dialect_name=None,
                response_language="de",
                confidence=0.9,
            )
            for _ in range(3)
        ]
        assert state.dominant_language == "de"

    def test_dominant_language_mixed(self):
        """Test dominant language with mixed languages."""
        state = ConversationLanguageState()
        state.message_history = [
            MessageLanguageInfo(
                text="Text",
                detected_language="ru",
                is_dialect=False,
                dialect_name=None,
                response_language="ru",
                confidence=0.9,
            )
            for _ in range(3)
        ]
        state.message_history.append(
            MessageLanguageInfo(
                text="Text",
                detected_language="de",
                is_dialect=False,
                dialect_name=None,
                response_language="de",
                confidence=0.9,
            )
        )
        assert state.dominant_language == "ru"  # 3 vs 1
