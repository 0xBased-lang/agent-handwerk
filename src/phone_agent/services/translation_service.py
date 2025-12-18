"""Translation service for converting text to German.

Uses Groq LLM for domain-aware translation of job descriptions
and customer communications to German before database storage.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

from itf_shared import get_logger

log = get_logger(__name__)


# Language names in their native form for the translation prompt
LANGUAGE_NAMES = {
    "de": "German",
    "ru": "Russian",
    "tr": "Turkish",
    "en": "English",
}

# Translation prompt optimized for trade/handwerk domain
TRANSLATION_PROMPT = """Translate the following {source_lang} text to standard German (Hochdeutsch).
This is a service request for a German trades business (Handwerk).

IMPORTANT RULES:
1. Preserve urgency indicators (emergency, urgent, etc.) - translate them appropriately
2. Keep technical trade terms accurate (heating, plumbing, electrical, etc.)
3. Preserve all specific details (addresses, names, phone numbers)
4. Use formal German (Sie-form) where appropriate
5. Keep the translation natural and professional

Original text ({source_lang}):
{text}

German translation:"""


@dataclass
class TranslationResult:
    """Result of a translation operation."""

    german_text: str
    original_text: str
    source_language: str
    success: bool
    error: str | None = None

    @property
    def was_translated(self) -> bool:
        """True if actual translation occurred (not German input)."""
        return self.source_language != "de" and self.success


class TranslationService:
    """Service for translating text to German using Groq LLM.

    Designed for pre-database-storage translation to ensure
    all job descriptions are stored in German for the business owner.
    """

    def __init__(
        self,
        groq_client: Any | None = None,
        api_key: str | None = None,
    ):
        """Initialize translation service.

        Args:
            groq_client: Existing GroqLanguageModel instance
            api_key: Groq API key (used if groq_client not provided)
        """
        self._groq_client = groq_client
        self._api_key = api_key
        self._initialized = False

    def _ensure_client(self) -> None:
        """Lazily initialize the Groq client if needed."""
        if self._groq_client is not None:
            if not getattr(self._groq_client, "_loaded", False):
                self._groq_client.load()
            return

        if self._api_key:
            from phone_agent.ai.cloud.groq_client import GroqLanguageModel

            self._groq_client = GroqLanguageModel(
                api_key=self._api_key,
                model="llama-3.3-70b-versatile",
                temperature=0.3,  # Lower temperature for more consistent translations
                max_tokens=512,
            )
            self._groq_client.load()

    async def translate_to_german(
        self,
        text: str,
        source_language: str,
        context: str | None = None,
    ) -> TranslationResult:
        """Translate text to German.

        Args:
            text: Text to translate
            source_language: Source language code (ru, tr, en, de)
            context: Optional context for better translation

        Returns:
            TranslationResult with German text and metadata
        """
        # Already German - no translation needed
        if source_language == "de":
            return TranslationResult(
                german_text=text,
                original_text=text,
                source_language="de",
                success=True,
            )

        # Empty text
        if not text or not text.strip():
            return TranslationResult(
                german_text=text,
                original_text=text,
                source_language=source_language,
                success=True,
            )

        try:
            self._ensure_client()

            if self._groq_client is None:
                log.warning("No Groq client available, storing original text")
                return TranslationResult(
                    german_text=text,  # Store original as fallback
                    original_text=text,
                    source_language=source_language,
                    success=False,
                    error="No translation client available",
                )

            # Build translation prompt
            source_lang_name = LANGUAGE_NAMES.get(source_language, source_language)
            prompt = TRANSLATION_PROMPT.format(
                source_lang=source_lang_name,
                text=text,
            )

            # Add context if provided
            if context:
                prompt = f"Context: {context}\n\n{prompt}"

            # Generate translation
            log.debug(
                "Translating text",
                source_lang=source_language,
                text_length=len(text),
            )

            # Use async generation
            german_text = await self._groq_client.generate_async(
                prompt=prompt,
                max_tokens=512,
                temperature=0.3,
            )

            german_text = german_text.strip()

            # Validate we got something reasonable
            if not german_text or len(german_text) < len(text) * 0.3:
                log.warning(
                    "Translation seems incomplete",
                    original_len=len(text),
                    translated_len=len(german_text),
                )

            log.info(
                "Translation successful",
                source_lang=source_language,
                original_len=len(text),
                translated_len=len(german_text),
            )

            return TranslationResult(
                german_text=german_text,
                original_text=text,
                source_language=source_language,
                success=True,
            )

        except Exception as e:
            log.error(
                "Translation failed",
                source_lang=source_language,
                error=str(e),
            )
            # Return original text on failure - never block job creation
            return TranslationResult(
                german_text=text,  # Store original as fallback
                original_text=text,
                source_language=source_language,
                success=False,
                error=str(e),
            )

    async def translate_job_fields(
        self,
        description: str,
        source_language: str,
        customer_notes: str | None = None,
    ) -> dict[str, Any]:
        """Translate all job-related text fields.

        Args:
            description: Job description to translate
            source_language: Source language code
            customer_notes: Optional customer notes to translate

        Returns:
            Dict with translated fields and metadata
        """
        results = {
            "description": description,
            "customer_notes": customer_notes,
            "source_language": source_language,
            "translation_success": True,
            "original_description": None,
            "original_customer_notes": None,
        }

        # Already German
        if source_language == "de":
            return results

        # Translate description
        desc_result = await self.translate_to_german(description, source_language)
        results["description"] = desc_result.german_text
        results["original_description"] = desc_result.original_text
        results["translation_success"] = desc_result.success

        # Translate customer notes if present
        if customer_notes:
            notes_result = await self.translate_to_german(customer_notes, source_language)
            results["customer_notes"] = notes_result.german_text
            results["original_customer_notes"] = notes_result.original_text
            results["translation_success"] = results["translation_success"] and notes_result.success

        return results


# Module-level instance
_service: TranslationService | None = None


def get_translation_service(api_key: str | None = None) -> TranslationService:
    """Get or create the singleton translation service.

    Args:
        api_key: Groq API key (only needed on first call)

    Returns:
        TranslationService instance
    """
    global _service
    if _service is None:
        _service = TranslationService(api_key=api_key)
    return _service


async def translate_to_german(text: str, source_language: str) -> TranslationResult:
    """Convenience function for translation.

    Args:
        text: Text to translate
        source_language: Source language code

    Returns:
        TranslationResult
    """
    service = get_translation_service()
    return await service.translate_to_german(text, source_language)
