"""Multilingual prompt loader for Phone Agent.

Loads industry-specific prompts based on detected language.
Falls back to German if translation not available.
"""

from __future__ import annotations

import importlib
from functools import lru_cache
from typing import Any

from itf_shared import get_logger

log = get_logger(__name__)


# Supported languages
SUPPORTED_LANGUAGES = ["de", "tr", "ru"]

# Industry module paths
INDUSTRY_MODULES = {
    "gesundheit": "phone_agent.industry.gesundheit",
    "handwerk": "phone_agent.industry.handwerk",
    "gastro": "phone_agent.industry.gastro",
    "freie_berufe": "phone_agent.industry.freie_berufe",
}


@lru_cache(maxsize=32)
def get_prompts_module(industry: str, language: str = "de") -> Any:
    """Load the prompts module for an industry and language.

    Results are cached to avoid repeated importlib calls.

    Args:
        industry: Industry name (gesundheit, handwerk, gastro, freie_berufe)
        language: Language code (de, tr, ru)

    Returns:
        Prompts module with SYSTEM_PROMPT and other constants
    """
    base_module = INDUSTRY_MODULES.get(industry)
    if not base_module:
        log.warning(
            "Unknown industry, falling back to gesundheit",
            requested=industry,
        )
        base_module = INDUSTRY_MODULES["gesundheit"]

    # Try language-specific module first
    if language != "de" and language in SUPPORTED_LANGUAGES:
        try:
            module_path = f"{base_module}.prompts_{language}"
            module = importlib.import_module(module_path)
            log.debug(
                "Loaded language-specific prompts",
                industry=industry,
                language=language,
            )
            return module
        except ImportError:
            log.debug(
                "Language-specific prompts not found, using German",
                industry=industry,
                language=language,
            )

    # Fall back to German (default)
    try:
        module_path = f"{base_module}.prompts"
        module = importlib.import_module(module_path)
        log.debug(
            "Loaded German prompts",
            industry=industry,
        )
        return module
    except ImportError:
        log.error(
            "Failed to load prompts module",
            industry=industry,
            language=language,
        )
        raise


@lru_cache(maxsize=32)
def get_system_prompt(industry: str, language: str = "de") -> str:
    """Get the system prompt for an industry and language.

    Args:
        industry: Industry name
        language: Language code

    Returns:
        System prompt string
    """
    module = get_prompts_module(industry, language)
    return module.SYSTEM_PROMPT


@lru_cache(maxsize=32)
def get_greeting_prompt(industry: str, language: str = "de") -> str:
    """Get the greeting prompt for an industry and language.

    Args:
        industry: Industry name
        language: Language code

    Returns:
        Greeting prompt string
    """
    module = get_prompts_module(industry, language)
    return getattr(module, "GREETING_PROMPT", "")


@lru_cache(maxsize=32)
def get_triage_prompt(industry: str, language: str = "de") -> str:
    """Get the triage prompt for healthcare.

    Args:
        industry: Industry name
        language: Language code

    Returns:
        Triage prompt string (healthcare only)
    """
    if industry != "gesundheit":
        return ""

    module = get_prompts_module(industry, language)
    return getattr(module, "TRIAGE_PROMPT", "")


@lru_cache(maxsize=32)
def get_farewell_prompt(industry: str, language: str = "de") -> str:
    """Get the farewell prompt for an industry and language.

    Args:
        industry: Industry name
        language: Language code

    Returns:
        Farewell prompt string
    """
    module = get_prompts_module(industry, language)
    return getattr(module, "FAREWELL_PROMPT", "")


class MultilingualPrompts:
    """Convenience class for accessing prompts in multiple languages.

    Example usage:
        prompts = MultilingualPrompts("gesundheit")
        prompts.set_language("tr")
        system = prompts.system_prompt
    """

    def __init__(self, industry: str, language: str = "de"):
        """Initialize with industry and language.

        Args:
            industry: Industry name
            language: Initial language code
        """
        self.industry = industry
        self._language = language
        self._module: Any = None
        self._load_module()

    def _load_module(self) -> None:
        """Load the prompts module for current language."""
        self._module = get_prompts_module(self.industry, self._language)

    @property
    def language(self) -> str:
        """Get current language."""
        return self._language

    def set_language(self, language: str) -> None:
        """Change the language and reload prompts.

        Args:
            language: New language code
        """
        if language != self._language:
            self._language = language
            self._load_module()
            log.debug(
                "Prompts language changed",
                industry=self.industry,
                language=language,
            )

    @property
    def system_prompt(self) -> str:
        """Get the system prompt."""
        return self._module.SYSTEM_PROMPT

    @property
    def greeting_prompt(self) -> str:
        """Get the greeting prompt."""
        return getattr(self._module, "GREETING_PROMPT", "")

    @property
    def triage_prompt(self) -> str:
        """Get the triage prompt (healthcare only)."""
        return getattr(self._module, "TRIAGE_PROMPT", "")

    @property
    def farewell_prompt(self) -> str:
        """Get the farewell prompt."""
        return getattr(self._module, "FAREWELL_PROMPT", "")

    @property
    def appointment_prompt(self) -> str:
        """Get the appointment prompt."""
        return getattr(self._module, "APPOINTMENT_PROMPT", "")

    @property
    def recall_prompt(self) -> str:
        """Get the recall/campaign prompt."""
        return getattr(self._module, "RECALL_PROMPT", "")

    def get_prompt(self, name: str) -> str:
        """Get any prompt by name.

        Args:
            name: Prompt constant name (e.g., "SYSTEM_PROMPT")

        Returns:
            Prompt string or empty string if not found
        """
        return getattr(self._module, name, "")
