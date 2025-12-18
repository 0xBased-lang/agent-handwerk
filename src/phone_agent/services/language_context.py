"""Language context management for multilingual conversations.

Manages per-message language detection and response language selection
for the voice agent chat system.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List

from phone_agent.ai.text_language_detector import (
    TextLanguageDetector,
    LanguageDetectionResult,
    DetectedLanguage,
)


@dataclass
class MessageLanguageInfo:
    """Language information for a single message."""

    text: str
    detected_language: str  # de, ru, tr, en
    is_dialect: bool
    dialect_name: str | None
    response_language: str  # Language used for response
    confidence: float


@dataclass
class ConversationLanguageState:
    """Tracks language state across a conversation."""

    # Current response language (can change per message)
    current_language: str = "de"

    # History of detected languages
    message_history: List[MessageLanguageInfo] = field(default_factory=list)

    # Whether Schwäbisch has been detected in this session
    schwabisch_detected: bool = False

    # Dominant language (most frequently used)
    @property
    def dominant_language(self) -> str:
        """Get the most frequently used language in the conversation."""
        if not self.message_history:
            return self.current_language

        lang_counts: dict[str, int] = {}
        for msg in self.message_history:
            lang = msg.detected_language
            lang_counts[lang] = lang_counts.get(lang, 0) + 1

        return max(lang_counts, key=lang_counts.get)


class ConversationLanguageManager:
    """Manages language detection and response language for conversations.

    Handles per-message language detection with dynamic switching.
    Schwäbisch is understood but responses are in standard German.
    """

    def __init__(self):
        """Initialize the language manager."""
        self._detector = TextLanguageDetector()
        self._state = ConversationLanguageState()

    @property
    def current_language(self) -> str:
        """Get current response language."""
        return self._state.current_language

    @property
    def schwabisch_detected(self) -> bool:
        """Whether Schwäbisch dialect has been detected."""
        return self._state.schwabisch_detected

    def process_message(self, text: str) -> MessageLanguageInfo:
        """Process a message and determine response language.

        Args:
            text: User message text

        Returns:
            MessageLanguageInfo with detection results
        """
        # Detect language
        result = self._detector.detect(text)

        # Determine response language
        # For Schwäbisch: understand but respond in standard German
        response_lang = result.response_language.value

        # Update state
        self._state.current_language = response_lang
        if result.is_dialect and result.dialect_name == "schwäbisch":
            self._state.schwabisch_detected = True

        # Create message info
        msg_info = MessageLanguageInfo(
            text=text,
            detected_language=result.language.value,
            is_dialect=result.is_dialect,
            dialect_name=result.dialect_name,
            response_language=response_lang,
            confidence=result.confidence,
        )

        # Add to history
        self._state.message_history.append(msg_info)

        return msg_info

    def get_response_language(self) -> str:
        """Get the language to use for the next response.

        Returns:
            Language code (de, ru, tr)
        """
        return self._state.current_language

    def reset(self) -> None:
        """Reset language state for a new conversation."""
        self._state = ConversationLanguageState()


class MultilingualPromptSelector:
    """Selects appropriate prompts based on detected language."""

    def __init__(self, industry: str = "handwerk"):
        """Initialize prompt selector.

        Args:
            industry: Industry module name
        """
        self.industry = industry
        self._prompts_cache: dict[str, str] = {}

    def get_system_prompt(self, language: str) -> str:
        """Get system prompt for the specified language.

        Args:
            language: Language code (de, ru, tr, en)

        Returns:
            System prompt in the specified language
        """
        cache_key = f"{self.industry}_{language}"

        if cache_key not in self._prompts_cache:
            # Import the appropriate prompt module
            try:
                if language == "ru":
                    from phone_agent.industry.handwerk.prompts_ru import CHAT_SYSTEM_PROMPT
                elif language == "tr":
                    from phone_agent.industry.handwerk.prompts_tr import CHAT_SYSTEM_PROMPT
                elif language == "en":
                    # Try English prompts, fallback to German if not available
                    try:
                        from phone_agent.industry.handwerk.prompts_en import CHAT_SYSTEM_PROMPT
                    except ImportError:
                        from phone_agent.industry.handwerk.prompts import CHAT_SYSTEM_PROMPT
                else:
                    # Default to German
                    from phone_agent.industry.handwerk.prompts import CHAT_SYSTEM_PROMPT

                self._prompts_cache[cache_key] = CHAT_SYSTEM_PROMPT

            except ImportError:
                # Fallback to German if language module doesn't exist
                from phone_agent.industry.handwerk.prompts import CHAT_SYSTEM_PROMPT
                self._prompts_cache[cache_key] = CHAT_SYSTEM_PROMPT

        return self._prompts_cache[cache_key]

    def get_greeting(self, language: str) -> str:
        """Get greeting for the specified language.

        Args:
            language: Language code (de, ru, tr, en)

        Returns:
            Greeting in the specified language
        """
        greetings = {
            "de": "Guten Tag! Wie kann ich Ihnen helfen?",
            "ru": "Здравствуйте! Чем могу помочь?",
            "tr": "Merhaba! Size nasıl yardımcı olabilirim?",
            "en": "Hello! How can I help you?",
        }
        return greetings.get(language, greetings["de"])

    def get_error_message(self, language: str) -> str:
        """Get error message for the specified language.

        Args:
            language: Language code (de, ru, tr, en)

        Returns:
            Error message in the specified language
        """
        errors = {
            "de": "Entschuldigung, es gab einen Fehler. Können Sie das bitte wiederholen?",
            "ru": "Извините, произошла ошибка. Не могли бы вы повторить?",
            "tr": "Özür dilerim, bir hata oluştu. Lütfen tekrar eder misiniz?",
            "en": "Sorry, there was an error. Could you please repeat that?",
        }
        return errors.get(language, errors["de"])

    def get_job_created_message(self, language: str, job_number: str) -> str:
        """Get job created confirmation message.

        Args:
            language: Language code (de, ru, tr, en)
            job_number: The created job number

        Returns:
            Job created message in the specified language
        """
        messages = {
            "de": f"Ihr Auftrag {job_number} wurde erstellt. Wir melden uns schnellstmöglich bei Ihnen.",
            "ru": f"Ваша заявка {job_number} создана. Мы свяжемся с вами в ближайшее время.",
            "tr": f"Siparişiniz {job_number} oluşturuldu. En kısa sürede sizinle iletişime geçeceğiz.",
            "en": f"Your job {job_number} has been created. We will contact you as soon as possible.",
        }
        return messages.get(language, messages["de"])


# Convenience function for getting a language manager
def create_language_manager() -> ConversationLanguageManager:
    """Create a new language manager for a conversation.

    Returns:
        ConversationLanguageManager instance
    """
    return ConversationLanguageManager()
